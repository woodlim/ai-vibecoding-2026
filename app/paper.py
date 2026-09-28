from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
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

    def set_quote(self, quote: Quote) -> Quote:
        self.quotes[quote.symbol] = quote
        prices = self._prices[quote.symbol]
        prices.append(quote.price)
        del prices[:-50]
        return quote

    def account(self) -> Account:
        return Account(cash=self.cash, initial_cash=self.initial_cash, positions=list(self.positions.values()))

    def start_strategy(self, symbol: str) -> StrategyStatus:
        self._prices[symbol].clear()
        self.strategy = StrategyStatus(running=True, symbol=symbol)
        return self.strategy

    def stop_strategy(self) -> StrategyStatus:
        self.strategy.running = False
        self.strategy.last_error = None
        return self.strategy

    def order(self, request: OrderRequest) -> Order:
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

        if request.side == "BUY":
            total = position.average_price * position.quantity + amount
            position.quantity += request.quantity
            position.average_price = total / position.quantity
            self.cash -= amount
        else:
            position.quantity -= request.quantity
            self.cash += amount
            if position.quantity == 0:
                position.average_price = Decimal(0)
        self.positions[request.symbol] = position

        result = Order(order_id=str(uuid4()), client_order_id=key, symbol=request.symbol, side=request.side,
                       quantity=request.quantity, filled_quantity=request.quantity, price=execution_price,
                       status="FILLED", created_at=now_utc())
        self.orders.append(result)
        self.client_orders[key] = result
        return result

    def run_strategy(self, symbol: str) -> StrategyStatus:
        prices = self._prices.get(symbol, [])
        self.strategy.price_samples = len(prices)
        if len(prices) < 5:
            return self.strategy
        fast = sum(prices[-3:]) / Decimal(3)
        slow = sum(prices[-5:]) / Decimal(5)
        position = self.positions.get(symbol)
        if fast > slow and (not position or position.quantity <= 0):
            self.order(OrderRequest(symbol=symbol, side="BUY", quantity=Decimal(1), client_order_id=f"sma-buy-{len(self.orders)+1}"))
            self.strategy.last_signal = "BUY"
        elif fast < slow and position and position.quantity > 0:
            self.order(OrderRequest(symbol=symbol, side="SELL", quantity=position.quantity, client_order_id=f"sma-sell-{len(self.orders)+1}"))
            self.strategy.last_signal = "SELL"
        return self.strategy

