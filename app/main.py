from __future__ import annotations

from decimal import Decimal, InvalidOperation
import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .models import Account, AutoBudgetRequest, Candle, Order, OrderRequest, PositionSellRequest, Quote, StrategyStatus, now_utc
from .paper import PaperTrader
from .toss_client import TossApiError, TossClient

app = FastAPI(title="Toss Auto Trader", version="0.1.0", description="PAPER-only automatic trading API")
app.mount("/assets", StaticFiles(directory=Path(__file__).resolve().parent.parent / "assets"), name="assets")
try:
    INITIAL_AUTO_BUY_BUDGET_PERCENT = Decimal(os.getenv("AUTO_BUY_BUDGET_PERCENT", "40"))
except (InvalidOperation, ValueError):
    INITIAL_AUTO_BUY_BUDGET_PERCENT = Decimal("40")
if not Decimal(0) <= INITIAL_AUTO_BUY_BUDGET_PERCENT <= Decimal(100):
    INITIAL_AUTO_BUY_BUDGET_PERCENT = Decimal("40")
trader = PaperTrader(auto_budget_percent=INITIAL_AUTO_BUY_BUDGET_PERCENT)
toss = TossClient()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
try:
    AUTO_TRADE_INTERVAL_SECONDS = max(15, int(os.getenv("AUTO_TRADE_INTERVAL_SECONDS", "60")))
except ValueError:
    AUTO_TRADE_INTERVAL_SECONDS = 60
strategy_task: asyncio.Task | None = None
strategy_command_id = 0


@app.exception_handler(OSError)
async def storage_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": "계좌 저장에 실패해 처리를 취소했습니다. 저장 공간과 권한을 확인해 주세요."})


@app.on_event("startup")
def load_paper_state() -> None:
    trader.enable_persistence(Path(__file__).resolve().parent.parent / "data" / "paper-state.json")


try:
    AUTO_MIN_DAILY_CHANGE_PERCENT = max(0.0, float(os.getenv("AUTO_MIN_DAILY_CHANGE_PERCENT", "1.0")))
except ValueError:
    AUTO_MIN_DAILY_CHANGE_PERCENT = 1.0


async def _market_momentum_candidates() -> list[dict]:
    """Intersect market-wide volume leaders with positive daily gainers."""
    volume_rows, gainer_rows = await asyncio.gather(
        toss.rankings("MARKET_TRADING_VOLUME", "realtime", 100),
        toss.rankings("TOP_GAINERS", "1d", 100),
    )
    volume_by_symbol = {row.get("symbol"): row for row in volume_rows if row.get("symbol")}
    gainers_by_symbol = {row.get("symbol"): row for row in gainer_rows if row.get("symbol")}
    overlap = set(volume_by_symbol) & set(gainers_by_symbol)
    if not overlap:
        return []

    names: dict[str, str] = {}
    symbols = sorted(overlap)
    for offset in range(0, len(symbols), 200):
        names.update(await toss.stock_names(symbols[offset:offset + 200]))

    candidates: list[dict] = []
    for symbol in overlap:
        volume_row = volume_by_symbol[symbol]
        gainer_row = gainers_by_symbol[symbol]
        try:
            change_percent = float(gainer_row["price"]["changeRate"]) * 100
            price = Decimal(str(gainer_row["price"]["lastPrice"]))
            volume_rank = int(volume_row.get("rank", 101))
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0 or change_percent < AUTO_MIN_DAILY_CHANGE_PERCENT:
            continue
        quote = Quote(symbol=symbol, name=names.get(symbol), price=price, timestamp=now_utc())
        score = change_percent * 0.7 + max(0, 101 - volume_rank) * 0.3
        candidates.append({
            "quote": quote,
            "change_rate": change_percent,
            "volume_rank": volume_rank,
            "volume": volume_row.get("tradingVolume", "0"),
            "score": round(score, 3),
        })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


async def _auto_trade_loop(initial_candidates: list[dict] | None = None) -> None:
    while trader.strategy.running:
        try:
            candidates = initial_candidates if initial_candidates is not None else await _market_momentum_candidates()
            initial_candidates = None
            for candidate in candidates:
                trader.set_quote(candidate["quote"])
            symbols = [p.symbol for p in trader.account().positions if p.quantity > 0]
            fresh_symbols = set()
            failed = []
            for symbol in symbols:
                try:
                    async with asyncio.timeout(20):
                        quote = await toss.quote(symbol)
                    if quote.symbol != symbol:
                        raise TossApiError("조회 시세의 종목이 일치하지 않습니다.")
                    trader.set_quote(quote)
                    fresh_symbols.add(symbol)
                    # Use the same current price for both exits and additional buys.
                    for item in candidates:
                        if item["quote"].symbol == symbol:
                            item["quote"] = trader.quotes[symbol]
                except (TossApiError, TimeoutError):
                    failed.append(symbol)
            trader.run_momentum_strategy(candidates, fresh_symbols=fresh_symbols, allow_buys=not failed)
            trader.strategy.last_error = f"시세 확인 실패: {', '.join(failed)} · 해당 종목 매도 및 신규 매수 보류" if failed else None
        except (TossApiError, ValueError) as exc:
            trader.strategy.last_error = str(exc)
        except Exception as exc:
            trader.strategy.last_error = f"전략 실행 오류: {exc}"
        trader.strategy.last_checked_at = now_utc()
        await asyncio.sleep(AUTO_TRADE_INTERVAL_SECONDS)


async def _stop_auto_trade_loop(*, invalidate_pending: bool = True) -> None:
    global strategy_task, strategy_command_id
    if invalidate_pending:
        strategy_command_id += 1
    trader.stop_strategy()
    task = strategy_task
    strategy_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.on_event("shutdown")
async def stop_auto_trade_on_shutdown() -> None:
    await _stop_auto_trade_loop()

@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/app.js", include_in_schema=False)
def frontend_js() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")

@app.get("/styles.css", include_in_schema=False)
def frontend_css() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "mode": "PAPER"}


@app.get("/health/toss")
async def toss_health() -> dict[str, str | bool]:
    try:
        await toss._access_token()
        return {"connected": True, "message": "토스 API 연결됨"}
    except TossApiError as exc:
        return {"connected": False, "message": str(exc)}


@app.get("/api/v1/market-indicators")
async def market_indicators() -> list[dict]:
    try:
        return await toss.market_prices()
    except TossApiError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/stocks/search")
async def search_stocks(q: str) -> list[dict]:
    if len(q.strip()) < 1:
        return []
    try:
        return await toss.search_stocks(q.strip())
    except TossApiError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/recommendations")
async def recommendations() -> list[dict]:
    candidates = [{"name": "삼성전자", "symbol": "005930"}, {"name": "SK하이닉스", "symbol": "000660"}, {"name": "NAVER", "symbol": "035420"}, {"name": "현대차", "symbol": "005380"}, {"name": "카카오", "symbol": "035720"}, {"name": "LG전자", "symbol": "066570"}, {"name": "LG화학", "symbol": "051910"}, {"name": "삼성SDI", "symbol": "006400"}, {"name": "삼성전기", "symbol": "009150"}, {"name": "두산에너빌리티", "symbol": "034020"}]
    failures: list[str] = []

    async def score(candidate: dict) -> dict | None:
        try:
            candles = await toss.candles(candidate["symbol"], 10)
        except TossApiError as exc:
            failures.append(str(exc))
            return None
        if len(candles) < 2:
            failures.append(f"{candidate['symbol']} 종목의 일봉 데이터가 부족합니다.")
            return None
        previous, latest = candles[-2], candles[-1]
        if previous.close_price <= 0:
            failures.append(f"{candidate['symbol']} 종목의 종가 데이터가 올바르지 않습니다.")
            return None
        change_rate = float((latest.close_price - previous.close_price) / previous.close_price * 100)
        volume = float(latest.volume or 0)
        avg_volume = sum(float(c.volume or 0) for c in candles[:-1]) / max(1, len(candles) - 1)
        volume_ratio = volume / avg_volume if avg_volume else 1
        score_value = max(0, min(100, 50 + change_rate * 8 + min(volume_ratio, 3) * 8))
        return {**candidate, "score": round(score_value), "change_rate": round(change_rate, 2), "volume": round(volume_ratio, 2)}

    result = [item for item in await asyncio.gather(*(score(candidate) for candidate in candidates)) if item]
    if not result:
        detail = failures[0] if failures else "추천 계산에 필요한 일봉 데이터가 없습니다."
        raise HTTPException(503, f"추천 종목 데이터를 가져오지 못했습니다. {detail}")
    return sorted(result, key=lambda item: item["score"], reverse=True)[:5]


@app.get("/api/v1/account", response_model=Account)
def get_account() -> Account:
    return trader.account()


@app.put("/api/v1/settings/auto-budget", response_model=Account)
def update_auto_budget(request: AutoBudgetRequest) -> Account:
    try:
        return trader.set_auto_budget_percent(request.percent)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/v1/quotes/{symbol}", response_model=Quote)
def get_quote(symbol: str) -> Quote:
    quote = trader.quotes.get(symbol)
    if not quote:
        raise HTTPException(404, "quote not found")
    return quote


@app.get("/api/v1/quotes/{symbol}/live", response_model=Quote)
async def get_live_quote(symbol: str) -> Quote:
    """토스증권 REST 현재가를 조회한다. PAPER 계좌에는 반영하지 않는다."""
    try:
        return await toss.quote(symbol)
    except TossApiError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/quotes-batch/live", response_model=list[Quote])
async def get_live_quotes(symbols: str) -> list[Quote]:
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested or len(requested) > 200:
        raise HTTPException(400, "symbols는 1~200개의 종목코드를 쉼표로 입력해야 합니다.")
    try:
        quotes = [await toss.quote(symbol) for symbol in requested]
        names = await toss.stock_names(requested)
        return [quote.model_copy(update={"name": names.get(quote.symbol)}) for quote in quotes]
    except TossApiError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/v1/candles/{symbol}", response_model=list[Candle])
async def get_daily_candles(symbol: str, count: int = 60) -> list[Candle]:
    try:
        return await toss.candles(symbol, count)
    except TossApiError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/v1/quotes", response_model=Quote)
def set_quote(quote: Quote) -> Quote:
    return trader.set_quote(quote)


@app.get("/api/v1/orders", response_model=list[Order])
def get_orders() -> list[Order]:
    return trader.orders


@app.post("/api/v1/orders", response_model=Order, status_code=201)
def create_order(request: OrderRequest) -> Order:
    try:
        return trader.order(request)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/v1/positions/{symbol}/sell", response_model=Order, status_code=201)
async def sell_position(symbol: str, request: PositionSellRequest) -> Order:
    """PAPER only: use a newly fetched price; never fall back to cached prices."""
    try:
        previous = trader.check_position_sell(symbol, request)
        if previous:
            return previous
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        async with asyncio.timeout(20):
            quote = await toss.quote(symbol)
    except (TossApiError, TimeoutError) as exc:
        raise HTTPException(503, "최신 시세를 가져오지 못해 매도하지 않았습니다. 잠시 후 다시 시도해 주세요.") from exc
    try:
        return trader.sell_position(symbol, request, quote)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/v1/strategies/status", response_model=StrategyStatus)
def strategy_status() -> StrategyStatus:
    return trader.strategy


@app.post("/api/v1/strategies/momentum/start", response_model=StrategyStatus)
@app.post("/api/v1/strategies/sma/start", response_model=StrategyStatus, include_in_schema=False)
async def start_strategy(symbol: str | None = None) -> StrategyStatus:
    global strategy_task, strategy_command_id
    if trader.strategy.running and strategy_task and not strategy_task.done():
        return trader.strategy

    strategy_command_id += 1
    command_id = strategy_command_id
    try:
        async with asyncio.timeout(25):
            initial_candidates = await _market_momentum_candidates()
            open_positions = [position for position in trader.positions.values() if position.quantity > 0]
            if not open_positions:
                initial_candidates = [
                    item for item in initial_candidates
                    if item["quote"].price <= trader.account().daily_auto_buy_remaining
                ]
    except TimeoutError as exc:
        raise HTTPException(503, "추천 종목과 시세 확인 시간이 초과되었습니다. 다시 시작해 주세요.") from exc
    except TossApiError as exc:
        raise HTTPException(503, f"토스 시장 랭킹을 가져오지 못했습니다: {exc}") from exc
    if command_id != strategy_command_id:
        raise HTTPException(409, "자동매매 시작 요청이 취소되었습니다.")
    await _stop_auto_trade_loop(invalidate_pending=False)
    if command_id != strategy_command_id:
        raise HTTPException(409, "자동매매 시작 요청이 취소되었습니다.")
    trader.start_strategy("AUTO")
    trader.strategy.symbol_name = "다종목 분산매매"
    trader.strategy.poll_interval_seconds = AUTO_TRADE_INTERVAL_SECONDS
    strategy_task = asyncio.create_task(_auto_trade_loop(initial_candidates))
    return trader.strategy


@app.post("/api/v1/strategies/momentum/stop", response_model=StrategyStatus)
@app.post("/api/v1/strategies/sma/stop", response_model=StrategyStatus, include_in_schema=False)
async def stop_strategy() -> StrategyStatus:
    await _stop_auto_trade_loop()
    return trader.strategy


@app.post("/api/v1/system/kill-switch")
async def kill_switch() -> dict[str, str]:
    await _stop_auto_trade_loop()
    return {"status": "stopped", "mode": "PAPER"}
