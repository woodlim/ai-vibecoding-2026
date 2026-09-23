from __future__ import annotations

from decimal import Decimal
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .models import Account, Candle, Order, OrderRequest, Quote, StrategyStatus
from .paper import PaperTrader
from .toss_client import TossApiError, TossClient

app = FastAPI(title="Toss Auto Trader", version="0.1.0", description="PAPER-only automatic trading API")
app.mount("/assets", StaticFiles(directory=Path(__file__).resolve().parent.parent / "assets"), name="assets")
trader = PaperTrader()
toss = TossClient()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

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
    async def score(candidate: dict) -> dict:
        try:
            candles = await toss.candles(candidate["symbol"], 10)
            if len(candles) < 2:
                return {**candidate, "score": 0, "change_rate": 0, "volume": 0}
            previous, latest = candles[-2], candles[-1]
            change_rate = float((latest.close_price - previous.close_price) / previous.close_price * 100)
            volume = float(latest.volume or 0)
            avg_volume = sum(float(c.volume or 0) for c in candles[:-1]) / max(1, len(candles) - 1)
            volume_ratio = volume / avg_volume if avg_volume else 1
            score_value = max(0, min(100, 50 + change_rate * 8 + min(volume_ratio, 3) * 8))
            return {**candidate, "score": round(score_value), "change_rate": round(change_rate, 2), "volume": round(volume_ratio, 2)}
        except TossApiError:
            return {**candidate, "score": 0, "change_rate": 0, "volume": 0}
    result = await asyncio.gather(*(score(candidate) for candidate in candidates))
    return sorted(result, key=lambda item: item["score"], reverse=True)[:5]


@app.get("/api/v1/account", response_model=Account)
def get_account() -> Account:
    return trader.account()


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


@app.get("/api/v1/strategies/status", response_model=StrategyStatus)
def strategy_status() -> StrategyStatus:
    return trader.strategy


@app.post("/api/v1/strategies/sma/start", response_model=StrategyStatus)
def start_strategy(symbol: str = "005930") -> StrategyStatus:
    return trader.run_strategy(symbol)


@app.post("/api/v1/system/kill-switch")
def kill_switch() -> dict[str, str]:
    trader.strategy.running = False
    return {"status": "stopped", "mode": "PAPER"}
