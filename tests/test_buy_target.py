from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Quote
from app.paper import PaperTrader


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 10, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.paper.now_utc", lambda: current[0])
    return current


def pool(prices):
    return [{"quote": Quote(symbol=str(i), price=price), "change_rate": 5, "score": 100 - i}
            for i, price in enumerate(prices)]


def test_ten_million_account_uses_three_point_five_million_in_spaced_rounds(clock):
    trader = PaperTrader(Decimal(10000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.start_strategy("AUTO")
    quotes = pool([1000] * 5)
    assert trader.account().daily_auto_buy_limit == 4000000
    assert trader.account().daily_auto_buy_target == 3500000
    for round_number in range(4):
        trader.run_momentum_strategy(quotes)
        assert trader.account().daily_auto_buy_used == 875000 * (round_number + 1)
        trader.run_momentum_strategy(quotes)
        assert trader.account().daily_auto_buy_used == 875000 * (round_number + 1)
        clock[0] += timedelta(minutes=15)
    assert trader.cash == 6500000
    assert trader.account().daily_auto_buy_target_remaining == 0
    trader.run_momentum_strategy(quotes)
    assert len(trader.orders) == 20
    assert trader.strategy.last_signal == "TARGET_REACHED"
    assert all(used == 700000 for used in trader._symbol_buy_used.values())


def test_rounding_leftovers_are_bought_after_four_rounds_and_survive_restart(clock, tmp_path):
    path = tmp_path / "target-state.json"
    trader = PaperTrader(Decimal(10000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.enable_persistence(path)
    trader.start_strategy("AUTO")
    quotes = pool([10000] * 5)
    for _ in range(4):
        trader.run_momentum_strategy(quotes)
        clock[0] += timedelta(minutes=15)
    assert trader.account().daily_auto_buy_used == 3480000
    trader.run_momentum_strategy(quotes)
    assert trader.account().daily_auto_buy_used == 3500000
    assert trader.strategy.buy_tranches_used == 5
    restored = PaperTrader()
    restored.enable_persistence(path)
    restored.start_strategy("AUTO")
    restored.run_momentum_strategy(quotes)
    assert restored.account().daily_auto_buy_used == 3500000
    assert restored.strategy.buy_tranches_used == 5
    assert restored.strategy.last_signal == "TARGET_REACHED"


def test_new_target_respects_changed_percent_cash_and_existing_usage(clock):
    trader = PaperTrader(Decimal(10000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.start_strategy("AUTO")
    quotes = pool([1000] * 5)
    trader.run_momentum_strategy(quotes)
    account = trader.set_auto_budget_percent(Decimal(5))
    assert account.daily_auto_buy_target == 437500
    assert account.daily_auto_buy_used == 875000
    assert account.daily_auto_buy_target_remaining == 0
    clock[0] += timedelta(minutes=15)
    trader.run_momentum_strategy(quotes)
    assert trader.account().daily_auto_buy_used == 875000
    trader.set_auto_budget_percent(Decimal(40))
    trader.cash = Decimal(1000)
    trader.run_momentum_strategy(quotes)
    assert trader.cash == 0
    assert trader.account().daily_auto_buy_used == 876000


def test_fewer_candidates_never_break_concentration_limit_to_force_target(clock):
    trader = PaperTrader(Decimal(10000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.start_strategy("AUTO")
    quotes = pool([1000, 1000])
    for _ in range(6):
        trader.run_momentum_strategy(quotes)
        clock[0] += timedelta(minutes=15)
    assert trader.account().daily_auto_buy_used == 1600000
    assert all(used == 800000 for used in trader._symbol_buy_used.values())


def test_irregular_prices_cannot_overspend_target_or_round(clock):
    trader = PaperTrader(Decimal(10000000))
    trader.start_strategy("AUTO")
    quotes = pool([51700, 90300, 2400, 69000, 157000])
    for _ in range(12):
        before = trader.account().daily_auto_buy_used
        trader.run_momentum_strategy(quotes)
        used = trader.account().daily_auto_buy_used
        assert used - before <= 875000
        assert used <= 3500000
        assert all(value <= 800000 for value in trader._symbol_buy_used.values())
        clock[0] += timedelta(minutes=15)
    assert used > 3400000
