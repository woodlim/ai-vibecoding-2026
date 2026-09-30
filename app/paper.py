from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from pathlib import Path
from uuid import uuid4

from .models import Account, Order, OrderRequest, PaperState, Position, PositionSellRequest, Quote, StrategyStatus, now_utc
from .state import persisted, save_state


class PaperTrader:
    """V0.1 가상계좌. 실제 브로커 API를 호출하지 않는다."""

    AUTO_BUY_TRANCHES = 4
    MAX_POSITIONS = 5
    AUTO_BUY_TRANCHE_COOLDOWN = timedelta(minutes=15)

    def __init__(
        self,
        initial_cash: Decimal = Decimal("10000000"),
        auto_budget_percent: Decimal = Decimal("40"),
    ) -> None:
        if not Decimal(0) <= auto_budget_percent <= Decimal(100):
            raise ValueError("자동매매 사용 비율은 0~100% 사이여야 합니다.")
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.auto_budget_percent = auto_budget_percent
        self.quotes: dict[str, Quote] = {}
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.client_orders: dict[str, Order] = {}
        self.strategy = StrategyStatus(running=False, symbol="005930")
        self._prices: dict[str, list[Decimal]] = defaultdict(list)
        self._lock = RLock()
        self._budget_date: date | None = None
        self._budget_basis_cash = Decimal(0)
        self._daily_limit = Decimal(0)
        self._daily_used = Decimal(0)
        self._auto_buy_tranches_used = 0
        self._last_auto_buy_at: datetime | None = None
        self._blocked_symbols: set[str] = set()
        self._symbol_buy_used: dict[str, Decimal] = defaultdict(Decimal)
        self._state_path: Path | None = None
        self._mutation_depth = 0

    def snapshot(self) -> PaperState:
        with self._lock:
            return PaperState(
                initial_cash=self.initial_cash, cash=self.cash, auto_budget_percent=self.auto_budget_percent,
                positions=list(self.positions.values()), orders=self.orders, quotes=list(self.quotes.values()),
                strategy=self.strategy, budget_date=self._budget_date, budget_basis_cash=self._budget_basis_cash,
                daily_limit=self._daily_limit, daily_used=self._daily_used, buy_rounds=self._auto_buy_tranches_used,
                last_buy_at=self._last_auto_buy_at, blocked_symbols=sorted(self._blocked_symbols),
                symbol_buy_used=dict(self._symbol_buy_used),
            ).model_copy(deep=True)

    def restore(self, state: PaperState) -> None:
        with self._lock:
            self.initial_cash, self.cash = state.initial_cash, state.cash
            self.auto_budget_percent = state.auto_budget_percent
            self.positions = {p.symbol: p.model_copy(deep=True) for p in state.positions}
            self.orders = [o.model_copy(deep=True) for o in state.orders]
            self.client_orders = {o.client_order_id: o for o in self.orders}
            self.quotes = {q.symbol: q.model_copy(deep=True) for q in state.quotes}
            self.strategy = state.strategy.model_copy(deep=True)
            self._budget_date, self._budget_basis_cash = state.budget_date, state.budget_basis_cash
            self._daily_limit, self._daily_used = state.daily_limit, state.daily_used
            self._auto_buy_tranches_used, self._last_auto_buy_at = state.buy_rounds, state.last_buy_at
            self._blocked_symbols = set(state.blocked_symbols)
            self._symbol_buy_used = defaultdict(Decimal, state.symbol_buy_used)

    def enable_persistence(self, path: Path) -> None:
        with self._lock:
            if path.exists():
                # Invalid snapshots fail startup instead of silently resetting the account.
                self.restore(PaperState.model_validate_json(path.read_text(encoding="utf-8")))
            self.strategy.running = False  # Restarts never silently resume trading.
            save_state(path, self.snapshot())
            self._state_path = path

    @staticmethod
    def _today() -> date:
        return now_utc().astimezone(timezone(timedelta(hours=9))).date()

    def _ensure_daily_budget(self) -> None:
        # Freeze the limit at the first start/tick of each Korean calendar day.
        # Stopping, switching stocks, and selling never replenish this limit.
        today = self._today()
        if self._budget_date != today:
            self._budget_date = today
            self._budget_basis_cash = max(Decimal(0), self.cash)
            self._daily_limit = self._budget_basis_cash * self.auto_budget_percent / Decimal(100)
            self._daily_used = Decimal(0)
            self._auto_buy_tranches_used = 0
            self._last_auto_buy_at = None
            self._blocked_symbols.clear()
            self._symbol_buy_used.clear()
            self.strategy.buy_tranches_used = 0

    @persisted
    def set_auto_budget_percent(self, percent: Decimal) -> Account:
        if not Decimal(0) <= percent <= Decimal(100):
            raise ValueError("자동매매 사용 비율은 0~100% 사이여야 합니다.")
        with self._lock:
            self.auto_budget_percent = percent
            if self._budget_date == self._today():
                self._daily_limit = self._budget_basis_cash * percent / Decimal(100)
            return self.account()

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
            limit = self._daily_limit if self._budget_date == today else max(Decimal(0), self.cash) * self.auto_budget_percent / Decimal(100)
            used = self._daily_used if self._budget_date == today else Decimal(0)
            return Account(
                cash=self.cash, initial_cash=self.initial_cash,
                positions=[position.model_copy() for position in self.positions.values()],
                daily_budget_date=today, daily_auto_buy_limit=limit,
                daily_auto_buy_used=used,
                daily_auto_buy_remaining=max(Decimal(0), min(self.cash, limit - used)),
                auto_buy_budget_percent=self.auto_budget_percent,
            )

    @persisted
    def start_strategy(self, symbol: str) -> StrategyStatus:
        with self._lock:
            self._ensure_daily_budget()
            self._prices[symbol].clear()
            self.strategy = StrategyStatus(
                running=True,
                symbol=symbol,
                buy_tranches_used=self._auto_buy_tranches_used,
                max_buy_tranches=self.AUTO_BUY_TRANCHES,
            )
            return self.strategy

    @persisted
    def stop_strategy(self) -> StrategyStatus:
        with self._lock:
            self.strategy.running = False
            self.strategy.last_error = None
            return self.strategy

    @persisted
    def order(self, request: OrderRequest, *, automatic: bool = False) -> Order:
        with self._lock:
            return self._execute_order(request, automatic=automatic)

    def check_position_sell(self, symbol: str, request: PositionSellRequest) -> Order | None:
        """Return a prior fill, or validate the position before requesting a price."""
        with self._lock:
            previous = self.client_orders.get(request.client_order_id)
            if previous:
                if (previous.symbol, previous.side, previous.quantity, previous.source) != (
                    symbol, "SELL", request.quantity, "MANUAL"
                ):
                    raise ValueError("이미 다른 주문에 사용된 요청 번호입니다.")
                return previous
            position = self.positions.get(symbol)
            if not position or position.quantity <= 0:
                raise ValueError("이미 매도되었거나 보유하지 않은 종목입니다.")
            if position.quantity != request.quantity:
                raise ValueError("보유 수량이 변경되었습니다. 새로고침 후 다시 확인해 주세요.")
            return None

    @persisted
    def sell_position(self, symbol: str, request: PositionSellRequest, quote: Quote) -> Order:
        """Close the confirmed position atomically, without automatic same-day reentry."""
        with self._lock:
            previous = self.check_position_sell(symbol, request)
            if previous:
                return previous
            if quote.symbol != symbol:
                raise ValueError("매도 종목과 조회 시세가 일치하지 않습니다.")
            self._ensure_daily_budget()
            self.set_quote(quote)
            result = self._execute_order(OrderRequest(
                symbol=symbol, side="SELL", quantity=request.quantity,
                client_order_id=request.client_order_id,
            ), automatic=False)
            self._blocked_symbols.add(symbol)
            self.strategy.last_signal = "SELL_MANUAL"
            self.strategy.managed_symbols = [p.symbol for p in self.positions.values() if p.quantity > 0]
            return result

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
                raise ValueError(f"하루 자동매매 사용 한도({self.auto_budget_percent}%)를 초과했습니다.")

        if request.side == "BUY":
            total = position.average_price * position.quantity + amount
            position.quantity += request.quantity
            position.average_price = total / position.quantity
            self.cash -= amount
            if automatic:
                self._daily_used += amount
                self._symbol_buy_used[request.symbol] += amount
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

    @persisted
    def run_strategy(self, symbol: str) -> StrategyStatus:
        with self._lock:
            return self._run_strategy(symbol)

    @persisted
    def run_momentum_strategy(self, candidates: list[dict], *, fresh_symbols: set[str] | None = None,
                              allow_buys: bool = True) -> StrategyStatus:
        """Monitor every holding, then allocate a timed round across up to five stocks."""
        with self._lock:
            if not self.strategy.running:
                return self.strategy
            self._ensure_daily_budget()
            eligible = [
                item for item in candidates
                if isinstance(item.get("quote"), Quote)
                and float(item.get("change_rate", 0)) > 0
                and item["quote"].symbol not in self._blocked_symbols
            ]
            self.strategy.managed_symbols = [p.symbol for p in self.positions.values() if p.quantity > 0]
            sold = False
            for symbol in self.strategy.managed_symbols:
                position = self.positions[symbol]
                if fresh_symbols is not None and symbol not in fresh_symbols:
                    continue
                current_quote = self.quotes.get(symbol)
                candidate = next((item for item in eligible if item["quote"].symbol == symbol), None)
                stop_price = position.average_price * Decimal("0.97")
                take_profit_price = position.average_price * Decimal("1.10")
                sell_signal = None
                if current_quote:
                    if current_quote.price <= stop_price:
                        sell_signal = "SELL_STOP_LOSS"
                    elif current_quote.price >= take_profit_price:
                        sell_signal = "SELL_TAKE_PROFIT"
                    elif candidate is None:
                        sell_signal = "SELL_MOMENTUM_FADE"
                if sell_signal:
                    self.order(OrderRequest(
                        symbol=symbol,
                        side="SELL",
                        quantity=position.quantity,
                        client_order_id=f"momentum-sell-{len(self.orders) + 1}",
                    ), automatic=True)
                    self.strategy.last_signal = sell_signal
                    self._blocked_symbols.add(symbol)
                    sold = True
            self.strategy.managed_symbols = [p.symbol for p in self.positions.values() if p.quantity > 0]
            if sold or not allow_buys:
                return self.strategy
            if not eligible:
                self.strategy.last_signal = "NO_SIGNAL"
                return self.strategy
            self._buy_momentum_round(eligible)
            self.strategy.managed_symbols = [p.symbol for p in self.positions.values() if p.quantity > 0]
            return self.strategy

    def _buy_momentum_round(self, candidates: list[dict]) -> None:
        if self._auto_buy_tranches_used >= self.AUTO_BUY_TRANCHES:
            self.strategy.last_signal = "TRANCHE_LIMIT"
            return
        now = now_utc()
        if self._last_auto_buy_at and now < self._last_auto_buy_at + self.AUTO_BUY_TRANCHE_COOLDOWN:
            self.strategy.last_signal = "WAIT_TRANCHE"
            return
        # Unused allocations stay in cash; fewer candidates never concentrate the round.
        per_symbol_limit = self._daily_limit / self.MAX_POSITIONS
        per_slot = per_symbol_limit / self.AUTO_BUY_TRANCHES
        bought: set[str] = set()
        seen: set[str] = set()
        held = {p.symbol for p in self.positions.values() if p.quantity > 0}
        for item in sorted(candidates, key=lambda item: item.get("score", 0), reverse=True):
            quote = item["quote"]
            if quote.symbol in seen:
                continue
            seen.add(quote.symbol)
            if len(bought) >= self.MAX_POSITIONS:
                break
            if quote.symbol not in held and len(held) >= self.MAX_POSITIONS:
                continue
            position = self.positions.get(quote.symbol)
            held_cost = position.quantity * position.average_price if position else Decimal(0)
            symbol_room = per_symbol_limit - max(self._symbol_buy_used[quote.symbol], held_cost)
            available = max(Decimal(0), min(self.cash, self._daily_limit - self._daily_used, per_slot, symbol_room))
            quantity = available // quote.price
            if quantity < 1:
                continue  # An expensive top-ranked stock must not block cheaper candidates.
            self.set_quote(quote)
            self.order(OrderRequest(
                symbol=quote.symbol, side="BUY", quantity=quantity,
                client_order_id=f"momentum-buy-{len(self.orders) + 1}",
            ), automatic=True)
            bought.add(quote.symbol)
            held.add(quote.symbol)
        if bought:
            self._auto_buy_tranches_used += 1  # One round can contain several orders.
            self.strategy.buy_tranches_used = self._auto_buy_tranches_used
            self._last_auto_buy_at = now
            self.strategy.last_signal = "BUY_DIVERSIFIED"
        else:
            self.strategy.last_signal = "BUDGET_LIMIT"

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

