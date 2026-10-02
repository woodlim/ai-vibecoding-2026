from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from pathlib import Path
from uuid import uuid4
from shutil import copy2

from .commissions import KRX_COMMISSION_RATE, commission_for, migrate_commissions
from .models import Account, Order, OrderRequest, PaperState, Position, PositionSellRequest, Quote, StrategyStatus, now_utc
from .state import persisted, save_state


class PaperTrader:
    """V0.1 가상계좌. 실제 브로커 API를 호출하지 않는다."""

    AUTO_BUY_TRANCHES = 4
    AUTO_BUY_TARGET_RATIO = Decimal("0.875")
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
        self.commission_rate = KRX_COMMISSION_RATE
        self.commission_source = "KRX_DEFAULT"
        self.commission_end_date: date | None = None
        self.commission_error: str | None = None

    def snapshot(self) -> PaperState:
        with self._lock:
            return PaperState(
                version=2, commission_rate=self.commission_rate,
                commission_source=self.commission_source, commission_end_date=self.commission_end_date,
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
            self.commission_rate, self.commission_source = state.commission_rate, state.commission_source
            self.commission_end_date = state.commission_end_date
            self.positions = {p.symbol: p.model_copy(deep=True) for p in state.positions}
            self.orders = [o.model_copy(deep=True) for o in state.orders]
            self._backfill_realized_pnl()
            self.client_orders = {o.client_order_id: o for o in self.orders}
            self.quotes = {q.symbol: q.model_copy(deep=True) for q in state.quotes}
            self.strategy = state.strategy.model_copy(deep=True)
            self._budget_date, self._budget_basis_cash = state.budget_date, state.budget_basis_cash
            self._daily_limit, self._daily_used = state.daily_limit, state.daily_used
            self._auto_buy_tranches_used, self._last_auto_buy_at = state.buy_rounds, state.last_buy_at
            self._blocked_symbols = set(state.blocked_symbols)
            self._symbol_buy_used = defaultdict(Decimal, state.symbol_buy_used)

    def _backfill_realized_pnl(self) -> None:
        """Fill P/L for snapshots created before sell P/L fields existed."""
        quantities: dict[str, Decimal] = defaultdict(Decimal)
        cost: dict[str, Decimal] = defaultdict(Decimal)
        for index, order in enumerate(self.orders):
            if order.status != "FILLED":
                continue
            quantity = order.filled_quantity or order.quantity
            amount = order.price * quantity
            if order.side == "BUY":
                quantities[order.symbol] += quantity
                cost[order.symbol] += amount + order.commission
                continue
            if order.side != "SELL":
                continue
            average = cost[order.symbol] / quantities[order.symbol] if quantities[order.symbol] else Decimal(0)
            basis = order.cost_basis if order.cost_basis else average * quantity
            pnl = order.realized_pnl if order.cost_basis else amount - order.commission - basis
            rate = order.realized_pnl_rate if order.cost_basis else (pnl / basis * Decimal(100) if basis else Decimal(0))
            self.orders[index] = order.model_copy(update={
                "realized_pnl": pnl, "realized_pnl_rate": rate, "cost_basis": basis,
            })
            quantities[order.symbol] = max(Decimal(0), quantities[order.symbol] - quantity)
            cost[order.symbol] = max(Decimal(0), cost[order.symbol] - basis)

    def enable_persistence(self, path: Path) -> None:
        with self._lock:
            if path.exists():
                # Invalid snapshots fail startup instead of silently resetting the account.
                state = PaperState.model_validate_json(path.read_text(encoding="utf-8"))
                if state.version == 1:
                    state = migrate_commissions(state)
                    backup = path.with_name(path.stem + ".pre-commissions.json")
                    if not backup.exists():
                        copy2(path, backup)
                self.restore(state)
            self.strategy.running = False  # Restarts never silently resume trading.
            save_state(path, self.snapshot())
            self._state_path = path

    @persisted
    def set_commission(self, rate: Decimal, source: str, end_date: date | None = None) -> None:
        if not rate.is_finite() or not Decimal(0) <= rate <= Decimal(1):
            raise ValueError("수수료율이 올바르지 않습니다.")
        if source not in {"TOSS_ACCOUNT", "KRX_DEFAULT"}:
            raise ValueError("수수료 출처가 올바르지 않습니다.")
        self.commission_rate, self.commission_source = rate, source
        self.commission_end_date = end_date

    def _commission(self, amount: Decimal) -> Decimal:
        expired = self.commission_end_date is not None and self.commission_end_date < self._today()
        return commission_for(amount, KRX_COMMISSION_RATE if expired else self.commission_rate)

    def _buy_cost(self, price: Decimal, quantity: Decimal) -> Decimal:
        amount = price * quantity
        return amount + self._commission(amount)

    def max_buy_quantity(self, price: Decimal, budget: Decimal) -> Decimal:
        """Find the largest whole-share order affordable including rounded fees."""
        low, high = 0, int(max(Decimal(0), budget) // price)
        while low < high:
            mid = (low + high + 1) // 2
            if self._buy_cost(price, Decimal(mid)) <= budget:
                low = mid
            else:
                high = mid - 1
        return Decimal(low)

    @staticmethod
    def _today() -> date:
        return now_utc().astimezone(timezone(timedelta(hours=9))).date()

    def _ensure_daily_budget(self) -> None:
        # Freeze the limit at the first start/tick of each Korean calendar day.
        # Manual sales can release used principal, but never increase this limit.
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

    def _manual_replacement_info(self) -> tuple[Decimal, int]:
        """Replay fills so old snapshots and duplicate requests share one credit ledger.

        Only today's automatic-buy principal is released by manual sales. Gains
        do not add credit, losses reduce it, and automatic sales add no credit.
        """
        today = self._today()
        quantities: dict[str, Decimal] = defaultdict(Decimal)
        automatic_cost: dict[str, Decimal] = defaultdict(Decimal)
        released = Decimal(0)
        slots = 0
        for order in self.orders:
            if order.status != "FILLED" or order.filled_quantity <= 0:
                continue
            symbol, quantity = order.symbol, order.filled_quantity
            today_order = order.created_at.astimezone(timezone(timedelta(hours=9))).date() == today
            if order.side == "BUY":
                if today_order and order.source == "AUTO":
                    automatic_cost[symbol] += order.settlement_amount
                    if quantities[symbol] == 0 and slots:
                        slots -= 1
                quantities[symbol] += quantity
            elif quantities[symbol] >= quantity:
                removed_cost = automatic_cost[symbol] * quantity / quantities[symbol]
                automatic_cost[symbol] -= removed_cost
                quantities[symbol] -= quantity
                if today_order and order.source == "MANUAL":
                    released += min(removed_cost, order.settlement_amount)
                    if quantities[symbol] == 0:
                        slots += 1
        held_count = sum(p.quantity > 0 for p in self.positions.values())
        return released, min(slots, max(0, self.MAX_POSITIONS - held_count))

    def account(self) -> Account:
        with self._lock:
            today = self._today()
            # Viewing the account previews the budget; only trading fixes it.
            limit = self._daily_limit if self._budget_date == today else max(Decimal(0), self.cash) * self.auto_budget_percent / Decimal(100)
            used = self._daily_used if self._budget_date == today else Decimal(0)
            target = limit * self.AUTO_BUY_TARGET_RATIO
            credit, refill_slots = self._manual_replacement_info()
            net_used = max(Decimal(0), used - credit)
            held_cost = sum((p.quantity * p.average_price + p.purchase_commission for p in self.positions.values()), Decimal(0))
            realized_pnl = sum((order.realized_pnl for order in self.orders if order.side == "SELL" and order.status == "FILLED"), Decimal(0))
            realized_cost_basis = sum((order.cost_basis for order in self.orders if order.side == "SELL" and order.status == "FILLED"), Decimal(0))
            return Account(
                cash=self.cash, initial_cash=self.initial_cash,
                positions=[position.model_copy() for position in self.positions.values()],
                daily_budget_date=today, daily_auto_buy_limit=limit,
                daily_auto_buy_used=used,
                daily_auto_buy_remaining=max(Decimal(0), min(self.cash, limit - net_used, limit - held_cost)),
                daily_auto_buy_target=target,
                daily_auto_buy_target_remaining=max(Decimal(0), min(self.cash, target - net_used, target - held_cost)),
                auto_buy_budget_percent=self.auto_budget_percent,
                daily_manual_sell_credit=credit, daily_auto_buy_net_used=net_used, refill_slots=refill_slots,
                realized_pnl=realized_pnl,
                realized_cost_basis=realized_cost_basis,
                total_commission=sum((o.commission for o in self.orders if o.status == "FILLED"), Decimal(0)),
                commission_rate=KRX_COMMISSION_RATE if self.commission_end_date and self.commission_end_date < today else self.commission_rate,
                commission_source="KRX_DEFAULT" if self.commission_end_date and self.commission_end_date < today else self.commission_source,
                commission_error=self.commission_error, commission_end_date=self.commission_end_date,
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
        commission = self._commission(amount)
        buy_cost = amount + commission

        if request.side == "BUY" and buy_cost > self.cash:
            raise ValueError("insufficient paper cash")
        if request.side == "SELL" and request.quantity > position.quantity:
            raise ValueError("insufficient paper position")
        if automatic and request.side == "BUY":
            self._ensure_daily_budget()
            released, _ = self._manual_replacement_info()
            if buy_cost > self._daily_limit - max(Decimal(0), self._daily_used - released):
                raise ValueError(f"하루 자동매매 사용 한도({self.auto_budget_percent}%)를 초과했습니다.")

        realized_pnl = Decimal(0)
        realized_pnl_rate = Decimal(0)
        cost_basis = Decimal(0)
        if request.side == "BUY":
            total = position.average_price * position.quantity + amount
            position.quantity += request.quantity
            position.average_price = total / position.quantity
            position.purchase_commission += commission
            self.cash -= buy_cost
            if automatic:
                self._daily_used += buy_cost
                self._symbol_buy_used[request.symbol] += buy_cost
        else:
            allocated_buy_fee = position.purchase_commission * request.quantity / position.quantity
            cost_basis = position.average_price * request.quantity + allocated_buy_fee
            realized_pnl = amount - commission - cost_basis
            realized_pnl_rate = realized_pnl / cost_basis * Decimal(100) if cost_basis else Decimal(0)
            position.quantity -= request.quantity
            position.purchase_commission -= allocated_buy_fee
            self.cash += amount - commission
            if position.quantity == 0:
                position.average_price = Decimal(0)
                position.purchase_commission = Decimal(0)
        self.positions[request.symbol] = position

        name = quote.name if quote else None
        if not name and automatic and self.strategy.symbol == request.symbol:
            name = self.strategy.symbol_name
        result = Order(order_id=str(uuid4()), client_order_id=key, symbol=request.symbol, side=request.side,
                       quantity=request.quantity, filled_quantity=request.quantity, price=execution_price,
                       status="FILLED", created_at=now_utc(), symbol_name=name,
                       source="AUTO" if automatic else "MANUAL",
                       realized_pnl=realized_pnl, realized_pnl_rate=realized_pnl_rate,
                       cost_basis=cost_basis, commission=commission,
                       commission_rate=KRX_COMMISSION_RATE if self.commission_end_date and self.commission_end_date < self._today() else self.commission_rate,
                       commission_source="KRX_DEFAULT" if self.commission_end_date and self.commission_end_date < self._today() else self.commission_source)
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
        target = self._daily_limit * self.AUTO_BUY_TARGET_RATIO
        account = self.account()
        replacing = account.refill_slots > 0
        if account.daily_auto_buy_net_used >= target:
            self.strategy.last_signal = "TARGET_REACHED"
            return
        now = now_utc()
        if not replacing and self._last_auto_buy_at and now < self._last_auto_buy_at + self.AUTO_BUY_TRANCHE_COOLDOWN:
            self.strategy.last_signal = "WAIT_TRANCHE"
            return
        # Four base rounds, followed by spaced top-ups if integer shares or prior
        # candidate shortages left the target underused. Manual sales release principal.
        round_budget = max(Decimal(0), min(account.daily_auto_buy_target_remaining,
                                           target / self.AUTO_BUY_TRANCHES))
        per_symbol_limit = self._daily_limit / self.MAX_POSITIONS
        allocations: list[dict] = []
        seen: set[str] = set()
        held = {p.symbol for p in self.positions.values() if p.quantity > 0}
        originally_held = set(held)
        slot_limit = account.refill_slots if replacing else self.MAX_POSITIONS
        remaining = round_budget
        for item in sorted(candidates, key=lambda item: item.get("score", 0), reverse=True):
            quote = item["quote"]
            if quote.symbol in seen:
                continue
            seen.add(quote.symbol)
            if len(allocations) >= slot_limit:
                break
            if replacing and quote.symbol in originally_held:
                continue
            if quote.symbol not in held and len(held) >= self.MAX_POSITIONS:
                continue
            position = self.positions.get(quote.symbol)
            held_cost = position.quantity * position.average_price + position.purchase_commission if position else Decimal(0)
            symbol_room = per_symbol_limit - max(self._symbol_buy_used[quote.symbol], held_cost)
            max_quantity = self.max_buy_quantity(quote.price, symbol_room)
            first_cost = self._buy_cost(quote.price, Decimal(1))
            if max_quantity < 1 or first_cost > remaining:
                continue  # An expensive top-ranked stock must not block cheaper candidates.
            allocations.append({"quote": quote, "quantity": Decimal(1), "max_quantity": max_quantity})
            remaining -= first_cost
            held.add(quote.symbol)

        # Spread each pass equally, then reuse rounding/cap leftovers. Every pass
        # buys at least one share or exits, and never exceeds the round budget.
        while True:
            active = [a for a in allocations if a["quantity"] < a["max_quantity"]
                      and self._buy_cost(a["quote"].price, a["quantity"] + 1)
                      - self._buy_cost(a["quote"].price, a["quantity"]) <= remaining]
            if not active:
                break
            equal_share = remaining / len(active)
            allocated = Decimal(0)
            for allocation in active:
                price = allocation["quote"].price
                before = self._buy_cost(price, allocation["quantity"])
                extra = min(self.max_buy_quantity(price, before + equal_share) - allocation["quantity"],
                            allocation["max_quantity"] - allocation["quantity"])
                allocation["quantity"] += extra
                allocated += self._buy_cost(price, allocation["quantity"]) - before
            if allocated == 0:
                allocation = min(active, key=lambda a: a["quantity"] * a["quote"].price)
                before = self._buy_cost(allocation["quote"].price, allocation["quantity"])
                allocation["quantity"] += 1
                allocated = self._buy_cost(allocation["quote"].price, allocation["quantity"]) - before
            remaining -= allocated

        for allocation in allocations:
            quote = allocation["quote"]
            self.set_quote(quote)
            self.order(OrderRequest(
                symbol=quote.symbol, side="BUY", quantity=allocation["quantity"],
                client_order_id=f"momentum-buy-{len(self.orders) + 1}",
            ), automatic=True)
        if allocations:
            self._auto_buy_tranches_used += 1  # One round can contain several orders.
            self.strategy.buy_tranches_used = self._auto_buy_tranches_used
            self._last_auto_buy_at = now
            self.strategy.last_signal = "BUY_REPLACEMENT" if replacing else ("BUY_TOP_UP" if self._auto_buy_tranches_used > self.AUTO_BUY_TRANCHES else "BUY_DIVERSIFIED")
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
            quantity = self.max_buy_quantity(self.quotes[symbol].price, available)
            if quantity < 1:
                self.strategy.last_signal = "BUDGET_LIMIT"
                return self.strategy
            self.order(OrderRequest(symbol=symbol, side="BUY", quantity=quantity, client_order_id=f"sma-buy-{len(self.orders)+1}"), automatic=True)
            self.strategy.last_signal = "BUY"
        elif fast < slow and position and position.quantity > 0:
            self.order(OrderRequest(symbol=symbol, side="SELL", quantity=position.quantity, client_order_id=f"sma-sell-{len(self.orders)+1}"), automatic=True)
            self.strategy.last_signal = "SELL"
        return self.strategy

