from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta, timezone
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from .models import Account, Order, OrderRequest, Position, Quote, StrategyStatus, now_utc


class PaperTrader:
    """V0.1 가상계좌. 실제 브로커 API를 호출하지 않는다."""

    def __init__(self, initial_cash: Decimal = Decimal("10000000")) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.quotes: dict[str, Quote] = {}
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.client_orders: dict[str, Order] = {}
        self.strategy = StrategyStatus(running=False, symbol="005930")
        self._prices: dict[str, list[Decimal]] = defaultdict(list)
        self._lock = RLock()
        self._budget_date: date | None = None
        self._daily_limit = Decimal(0)
        self._daily_used = Decimal(0)

    @staticmethod
    def _today() -> date:
        return now_utc().astimezone(timezone(timedelta(hours=9))).date()

    def _ensure_daily_budget(self) -> None:
        # Freeze the limit at the first start/tick of each Korean calendar day.
        # Stopping, switching stocks, and selling never replenish this limit.
        today = self._today()
        if self._budget_date != today:
            self._budget_date = today
            self._daily_limit = max(Decimal(0), self.cash) * Decimal("0.4")
            self._daily_used = Decimal(0)

    def set_quote(self, quote: Quote) -> Quote:
        with self._lock:
            previous = self.quotes.get(quote.symbol)
            if not quote.name and previous and previous.name:
                quote = quote.model_copy(update={"name": previous.name})
            self.quotes[quote.symbol] = quote
            prices = self._prices[quote.symbol]
            prices.append(quote.price)
            del prices[:-50]
            return quote

    def account(self) -> Account:
        with self._lock:
            today = self._today()
            # Viewing the account previews the budget; only trading fixes it.
            limit = self._daily_limit if self._budget_date == today else max(Decimal(0), self.cash) * Decimal("0.4")
            used = self._daily_used if self._budget_date == today else Decimal(0)
            return Account(
                cash=self.cash, initial_cash=self.initial_cash,
                positions=[position.model_copy() for position in self.positions.values()],
                daily_budget_date=today, daily_auto_buy_limit=limit,
                daily_auto_buy_used=used,
                daily_auto_buy_remaining=max(Decimal(0), min(self.cash, limit - used)),
            )

    def start_strategy(self, symbol: str) -> StrategyStatus:
        with self._lock:
            self._ensure_daily_budget()
            self._prices[symbol].clear()
            self.strategy = StrategyStatus(running=True, symbol=symbol)
            return self.strategy

    def stop_strategy(self) -> StrategyStatus:
        with self._lock:
            self.strategy.running = False
            self.strategy.last_error = None
            return self.strategy

    def order(self, request: OrderRequest, *, automatic: bool = False) -> Order:
        with self._lock:
            return self._execute_order(request, automatic=automatic)

    def _execute_order(self, request: OrderRequest, *, automatic: bool) -> Order:
        key = request.client_order_id or str(uuid4())
        if key in self.client_orders:
            previous = self.client_orders[key]
            if (previous.symbol, previous.side, previous.quantity, previous.price) != (
                request.symbol, request.side, request.quantity, request.price or previous.price
            ):
                raise ValueError("client_order_id already exists with different order content")
            return previous

        quote = self.quotes.get(request.symbol)
        execution_price = request.price or (quote.price if quote else None)
        if execution_price is None:
            raise ValueError("quote is required before placing an order")
        position = self.positions.get(request.symbol, Position(symbol=request.symbol, quantity=Decimal(0), average_price=Decimal(0)))
        amount = execution_price * request.quantity

        if request.side == "BUY" and amount > self.cash:
            raise ValueError("insufficient paper cash")
        if request.side == "SELL" and request.quantity > position.quantity:
            raise ValueError("insufficient paper position")
        if automatic and request.side == "BUY":
            self._ensure_daily_budget()
            if amount > self._daily_limit - self._daily_used:
                raise ValueError("하루 자동매매 사용 한도(40%)를 초과했습니다.")

        if request.side == "BUY":
            total = position.average_price * position.quantity + amount
            position.quantity += request.quantity
            position.average_price = total / position.quantity
            self.cash -= amount
            if automatic:
                self._daily_used += amount
        else:
            position.quantity -= request.quantity
            self.cash += amount
            if position.quantity == 0:
                position.average_price = Decimal(0)
        self.positions[request.symbol] = position

        name = quote.name if quote else None
        if not name and automatic and self.strategy.symbol == request.symbol:
            name = self.strategy.symbol_name
        result = Order(order_id=str(uuid4()), client_order_id=key, symbol=request.symbol, side=request.side,
                       quantity=request.quantity, filled_quantity=request.quantity, price=execution_price,
                       status="FILLED", created_at=now_utc(), symbol_name=name,
                       source="AUTO" if automatic else "MANUAL")
        self.orders.append(result)
        self.client_orders[key] = result
        return result

    def run_strategy(self, symbol: str) -> StrategyStatus:
        with self._lock:
            return self._run_strategy(symbol)

    def run_momentum_strategy(self, candidates: list[dict]) -> StrategyStatus:
        """Trade the leading market-wide gainers that also rank highly by volume."""
        with self._lock:
            if not self.strategy.running:
                return self.strategy
            self._ensure_daily_budget()
            eligible = [
                item for item in candidates
                if isinstance(item.get("quote"), Quote)
                and float(item.get("change_rate", 0)) > 0
            ]
            position = self.positions.get(self.strategy.symbol)
            if position and position.quantity > 0:
                current_quote = self.quotes.get(self.strategy.symbol)
                candidate = next((item for item in eligible if item["quote"].symbol == self.strategy.symbol), None)
                stop_price = position.average_price * Decimal("0.97")
                if current_quote and (candidate is None or current_quote.price <= stop_price):
                    self.order(OrderRequest(
                        symbol=self.strategy.symbol,
                        side="SELL",
                        quantity=position.quantity,
                        client_order_id=f"momentum-sell-{len(self.orders) + 1}",
                    ), automatic=True)
                    self.strategy.last_signal = "SELL_STOP_LOSS" if current_quote.price <= stop_price else "SELL_MOMENTUM_FADE"
                    return self.strategy
                self.strategy.last_signal = "HOLD_MOMENTUM"
                return self.strategy

            self.strategy.last_signal = "NO_SIGNAL"
            for item in eligible:
                quote = item["quote"]
                available = min(self.cash, self._daily_limit - self._daily_used)
                quantity = available // quote.price
                if quantity < 1:
                    continue
                self.strategy.symbol = quote.symbol
                self.strategy.symbol_name = quote.name
                self.order(OrderRequest(
                    symbol=quote.symbol,
                    side="BUY",
                    quantity=quantity,
                    client_order_id=f"momentum-buy-{len(self.orders) + 1}",
                ), automatic=True)
                self.strategy.last_signal = "BUY_VOLUME_MOMENTUM"
                return self.strategy
            if eligible:
                self.strategy.last_signal = "BUDGET_LIMIT"
            return self.strategy

    def _run_strategy(self, symbol: str) -> StrategyStatus:
        if not self.strategy.running or self.strategy.symbol != symbol:
            return self.strategy
        self._ensure_daily_budget()
        prices = self._prices.get(symbol, [])
        self.strategy.price_samples = len(prices)
        if len(prices) < 5:
            self.strategy.last_signal = "COLLECTING"
            return self.strategy
        self.strategy.last_signal = "HOLD"
        fast = sum(prices[-3:]) / Decimal(3)
        slow = sum(prices[-5:]) / Decimal(5)
        position = self.positions.get(symbol)
        if fast > slow and (not position or position.quantity <= 0):
            available = min(self.cash, self._daily_limit - self._daily_used)
            quantity = available // self.quotes[symbol].price
            if quantity < 1:
                self.strategy.last_signal = "BUDGET_LIMIT"
                return self.strategy
            self.order(OrderRequest(symbol=symbol, side="BUY", quantity=quantity, client_order_id=f"sma-buy-{len(self.orders)+1}"), automatic=True)
            self.strategy.last_signal = "BUY"
        elif fast < slow and position and position.quantity > 0:
            self.order(OrderRequest(symbol=symbol, side="SELL", quantity=position.quantity, client_order_id=f"sma-sell-{len(self.orders)+1}"), automatic=True)
            self.strategy.last_signal = "SELL"
        return self.strategy

