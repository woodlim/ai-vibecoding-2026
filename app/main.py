from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI, HTTPException

from .models import Account, Order, OrderRequest, Quote, StrategyStatus
from .paper import PaperTrader

app = FastAPI(title="Toss Auto Trader", version="0.1.0", description="PAPER-only automatic trading API")
trader = PaperTrader()


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "mode": "PAPER"}


@app.get("/api/v1/account", response_model=Account)
def get_account() -> Account:
    return trader.account()


@app.get("/api/v1/quotes/{symbol}", response_model=Quote)
def get_quote(symbol: str) -> Quote:
    quote = trader.quotes.get(symbol)
    if not quote:
        raise HTTPException(404, "quote not found")
    return quote


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

