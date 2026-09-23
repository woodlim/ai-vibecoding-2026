from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


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


class Position(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal


class Account(BaseModel):
    mode: Literal["PAPER"] = "PAPER"
    cash: Decimal
    initial_cash: Decimal
    positions: list[Position]


class StrategyStatus(BaseModel):
    running: bool
    symbol: str
    last_signal: str | None = None
