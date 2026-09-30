from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field


Side = Literal["BUY", "SELL"]
OrderStatus = Literal["FILLED", "REJECTED"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Quote(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str | None = None
    price: Decimal = Field(gt=0)
    timestamp: datetime = Field(default_factory=now_utc)


class Candle(BaseModel):
    symbol: str
    timestamp: datetime
    close_price: Decimal
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: Decimal | None = None


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Side
    quantity: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, max_length=36)


class Order(BaseModel):
    order_id: str
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    filled_quantity: Decimal
    price: Decimal
    status: OrderStatus
    created_at: datetime
    symbol_name: str | None = None
    source: Literal["AUTO", "MANUAL"] = "MANUAL"

    @computed_field
    @property
    def total_amount(self) -> Decimal:
        return self.price * self.filled_quantity


class PositionSellRequest(BaseModel):
    quantity: Decimal = Field(gt=0)
    client_order_id: str = Field(min_length=1, max_length=36)


class Position(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal


class Account(BaseModel):
    mode: Literal["PAPER"] = "PAPER"
    cash: Decimal
    initial_cash: Decimal
    positions: list[Position]
    daily_budget_date: date
    daily_auto_buy_limit: Decimal
    daily_auto_buy_used: Decimal
    daily_auto_buy_remaining: Decimal
    auto_buy_budget_percent: Decimal


class AutoBudgetRequest(BaseModel):
    percent: Decimal = Field(ge=0, le=100)


class StrategyStatus(BaseModel):
    running: bool
    symbol: str
    symbol_name: str | None = None
    last_signal: str | None = None
    price_samples: int = 0
    buy_tranches_used: int = 0
    max_buy_tranches: int = 4
    poll_interval_seconds: int = 60
    last_checked_at: datetime | None = None
    last_error: str | None = None
    max_positions: int = 5
    managed_symbols: list[str] = Field(default_factory=list)


class PaperState(BaseModel):
    version: Literal[1] = 1
    initial_cash: Decimal = Field(ge=0)
    cash: Decimal = Field(ge=0)
    auto_budget_percent: Decimal = Field(ge=0, le=100)
    positions: list[Position]
    orders: list[Order]
    quotes: list[Quote]
    strategy: StrategyStatus
    budget_date: date | None = None
    budget_basis_cash: Decimal = Field(default=0, ge=0)
    daily_limit: Decimal = Field(default=0, ge=0)
    daily_used: Decimal = Field(default=0, ge=0)
    buy_rounds: int = Field(default=0, ge=0, le=4)
    last_buy_at: datetime | None = None
    blocked_symbols: list[str] = Field(default_factory=list)
    symbol_buy_used: dict[str, Decimal] = Field(default_factory=dict)
