from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import OrderRequest, Quote
from app.paper import PaperTrader


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch):
    monkeypatch.setattr("app.paper.now_utc", lambda: datetime(2026, 9, 29, 1, tzinfo=timezone.utc))


def feed(trader, symbol, prices):
    for price in prices:
        trader.set_quote(Quote(symbol=symbol, price=Decimal(price)))
    return trader.run_strategy(symbol)


def test_budget_uses_available_cash_and_account_preview_does_not_freeze_it():
    trader = PaperTrader(Decimal(1000))
    assert trader.account().daily_auto_buy_limit == 400
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=6, price=100))
    assert trader.account().daily_auto_buy_limit == 160
    trader.start_strategy("B")
    assert trader.account().daily_auto_buy_limit == 160


def test_user_can_change_percent_and_recalculate_current_day_limit():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    assert trader.account().daily_auto_buy_limit == 400

    account = trader.set_auto_budget_percent(Decimal(60))
    assert account.auto_buy_budget_percent == 60
    assert account.daily_auto_buy_limit == 600

    feed(trader, "A", [60, 70, 80, 90, 100])
    assert trader.account().daily_auto_buy_used == 600
    account = trader.set_auto_budget_percent(Decimal(30))
    assert account.daily_auto_buy_limit == 300
    assert account.daily_auto_buy_used == 600
    assert account.daily_auto_buy_remaining == 0


@pytest.mark.parametrize("percent", [Decimal("-0.1"), Decimal("100.1")])
def test_user_budget_percent_must_be_between_zero_and_one_hundred(percent):
    trader = PaperTrader(Decimal(1000))
    with pytest.raises(ValueError, match="0~100%"):
        trader.set_auto_budget_percent(percent)


def test_signal_buys_maximum_whole_shares_within_forty_percent():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    feed(trader, "A", [90, 100, 110, 120, 130])
    account = trader.account()
    assert trader.orders[0].quantity == 3
    assert account.cash == 610
    assert account.daily_auto_buy_limit == 400
    assert account.daily_auto_buy_used == 390
    assert account.daily_auto_buy_remaining == 10


def test_unaffordable_share_is_skipped_without_fractional_buy():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    status = feed(trader, "A", [500, 510, 520, 530, 540])
    assert status.last_signal == "BUDGET_LIMIT"
    assert trader.orders == []
    assert trader.account().daily_auto_buy_used == 0


def test_sell_restart_and_symbol_switch_share_the_same_daily_limit():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    feed(trader, "A", [90, 100, 110, 120, 130])
    feed(trader, "A", [140, 130, 120, 110, 100])
    assert trader.orders[-1].side == "SELL"
    assert trader.account().daily_auto_buy_used == 390
    trader.stop_strategy()
    trader.start_strategy("B")
    feed(trader, "B", [1, 2, 3, 4, 5])
    assert trader.orders[-1].quantity == 2
    assert trader.account().daily_auto_buy_limit == 400
    assert trader.account().daily_auto_buy_used == 400
    trader.start_strategy("C")
    feed(trader, "C", [1, 2, 3, 4, 5])
    assert len(trader.orders) == 3
    assert trader.strategy.last_signal == "BUDGET_LIMIT"


def test_remaining_cash_also_limits_automatic_buys():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    trader.order(OrderRequest(symbol="B", side="BUY", quantity=9, price=100))
    feed(trader, "A", [10, 20, 30, 40, 50])
    assert trader.orders[-1].quantity == 2
    assert trader.cash == 0
    assert trader.account().daily_auto_buy_used == 100
    assert trader.account().daily_auto_buy_remaining == 0


def test_order_boundary_rejects_over_limit_and_deduplicates_usage():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    with pytest.raises(ValueError, match="40%"):
        trader.order(OrderRequest(symbol="A", side="BUY", quantity=5, price=100), automatic=True)
    assert trader.cash == 1000
    assert trader.orders == []
    request = OrderRequest(symbol="A", side="BUY", quantity=4, price=100, client_order_id="same")
    first = trader.order(request, automatic=True)
    assert trader.order(request, automatic=True).order_id == first.order_id
    assert trader.account().daily_auto_buy_used == 400


def test_budget_resets_at_korean_midnight_on_next_active_tick(monkeypatch):
    monkeypatch.setattr("app.paper.now_utc", lambda: datetime(2026, 9, 29, 14, 59, tzinfo=timezone.utc))
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    feed(trader, "A", [90, 100, 110, 120, 130])
    trader.start_strategy("B")
    assert trader.account().daily_auto_buy_limit == 400
    monkeypatch.setattr("app.paper.now_utc", lambda: datetime(2026, 9, 29, 15, tzinfo=timezone.utc))
    assert str(trader.account().daily_budget_date) == "2026-09-30"
    assert trader.account().daily_auto_buy_limit == Decimal(244)
    feed(trader, "B", [50, 55, 60, 65, 70])
    assert trader.account().daily_auto_buy_used == 210
    assert trader.account().daily_auto_buy_limit == 244


def test_concurrent_automatic_orders_cannot_exceed_daily_budget():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")

    def buy(index):
        try:
            trader.order(OrderRequest(symbol="A", side="BUY", quantity=1, price=100,
                                      client_order_id=f"parallel-{index}"), automatic=True)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(buy, range(10))) == 4
    assert trader.account().daily_auto_buy_used == 400
    assert trader.cash == 600


def test_stopped_strategy_does_not_place_orders():
    trader = PaperTrader(Decimal(1000))
    trader.start_strategy("A")
    trader.stop_strategy()
    feed(trader, "A", [1, 2, 3, 4, 5])
    assert trader.orders == []
