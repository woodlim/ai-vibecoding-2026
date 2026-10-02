import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import app.main as server
from app.models import OrderRequest, PositionSellRequest, Quote
from app.paper import PaperTrader


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 10, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.paper.now_utc", lambda: current[0])
    monkeypatch.setattr("app.models.now_utc", lambda: current[0])
    return current


def pool(symbols):
    return [{"quote": Quote(symbol=s, price=1000), "change_rate": 5, "score": 100 - i}
            for i, s in enumerate(symbols)]


def filled_account(clock):
    trader = PaperTrader(Decimal(10000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.start_strategy("AUTO")
    for index in range(4):
        trader.run_momentum_strategy(pool("ABCDE"))
        if index < 3:
            clock[0] += timedelta(minutes=15)
    assert trader.account().daily_auto_buy_used == 3500000
    return trader


def manual_sell(trader, symbol, price=1000):
    request = PositionSellRequest(quantity=trader.positions[symbol].quantity, client_order_id=f"close-{symbol}")
    return trader.sell_position(symbol, request, Quote(symbol=symbol, price=price))


def test_manual_sales_fill_four_empty_slots_without_topping_up_remaining_stock(clock):
    trader = filled_account(clock)
    for symbol in "BCDE":
        manual_sell(trader, symbol)
    account = trader.account()
    assert account.refill_slots == 4
    assert account.daily_manual_sell_credit == 2800000
    assert account.daily_auto_buy_used == 3500000  # Keep turnover history.
    assert account.daily_auto_buy_target_remaining == 2800000
    held_quantity = trader.positions["A"].quantity
    trader.stop_strategy()
    trader.start_strategy("AUTO")
    trader.run_momentum_strategy(pool("ABCDEFGHI"))
    assert set(trader.strategy.managed_symbols) == set("AFGHI")
    assert trader.positions["A"].quantity == held_quantity
    assert trader.account().refill_slots == 0
    assert trader.strategy.last_signal == "BUY_REPLACEMENT"
    assert trader.account().daily_auto_buy_used == 4375000
    assert trader.account().daily_auto_buy_net_used == 1575000
    count = len(trader.orders)
    trader.run_momentum_strategy(pool("AFGHI"))
    assert len(trader.orders) == count
    assert trader.strategy.last_signal == "WAIT_TRANCHE"


@pytest.mark.parametrize("price,credit", [(1100, 700000), (900, 630000)])
def test_release_never_counts_profit_or_unrecovered_loss(clock, price, credit):
    trader = filled_account(clock)
    manual_sell(trader, "B", price)
    assert trader.account().daily_manual_sell_credit == credit
    retry = PositionSellRequest(quantity=700, client_order_id="close-B")
    trader.sell_position("B", retry, Quote(symbol="B", price=1200))
    assert trader.account().daily_manual_sell_credit == credit


def test_automatic_exit_does_not_release_budget_or_skip_cooldown(clock):
    trader = filled_account(clock)
    trader.order(OrderRequest(symbol="B", side="SELL", quantity=700), automatic=True)
    assert trader.account().daily_manual_sell_credit == 0
    assert trader.account().refill_slots == 0
    assert trader.account().daily_auto_buy_target_remaining == 0


def test_partial_sales_only_release_their_automatic_principal(clock):
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=100), automatic=False)
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=200), automatic=True)
    trader.order(OrderRequest(symbol="A", side="SELL", quantity=10, price=200))
    assert trader.account().daily_manual_sell_credit == 1000
    assert trader.account().refill_slots == 0


def test_legacy_snapshot_replays_sales_without_resetting_budget(clock, tmp_path):
    trader = filled_account(clock)
    manual_sell(trader, "B")
    path = tmp_path / "state.json"
    trader.enable_persistence(path)
    restored = PaperTrader()
    restored.enable_persistence(path)
    assert restored.account().daily_manual_sell_credit == 700000
    assert restored.account().refill_slots == 1
    assert restored.account().daily_auto_buy_used == 3500000
    restored.start_strategy("AUTO")
    restored.run_momentum_strategy(pool("ACDEF"))
    restored_again = PaperTrader()
    restored_again.enable_persistence(path)
    assert restored_again.account().refill_slots == 0
    clock[0] += timedelta(days=1)
    assert restored_again.account().daily_manual_sell_credit == 0
    assert restored_again.account().refill_slots == 0


def test_missing_candidates_do_not_buy_blocked_or_add_to_held_stocks(clock):
    trader = filled_account(clock)
    manual_sell(trader, "B")
    count = len(trader.orders)
    trader.run_momentum_strategy(pool("ABCDE"))
    assert len(trader.orders) == count
    assert trader.account().refill_slots == 1


def test_start_while_running_rescans_pending_slots_and_does_not_spawn_duplicate_workers(clock, monkeypatch):
    trader = filled_account(clock)
    manual_sell(trader, "B")
    monkeypatch.setattr(server, "trader", trader)
    monkeypatch.setattr(server, "strategy_task", None)
    monkeypatch.setattr(server, "strategy_command_id", 0)
    scan = AsyncMock(return_value=pool("ACDEF"))
    monkeypatch.setattr(server, "_market_momentum_candidates", scan)
    monkeypatch.setattr(server.toss, "quote", AsyncMock(side_effect=lambda s: Quote(symbol=s, price=1000)))

    async def scenario():
        previous_worker = asyncio.create_task(asyncio.sleep(3600))
        server.strategy_task = previous_worker
        try:
            await server.start_strategy()
            await asyncio.sleep(0)
            assert previous_worker.done()
            assert trader.positions["F"].quantity > 0
            worker = server.strategy_task
            await server.start_strategy()
            assert server.strategy_task is worker
            scan.assert_awaited_once()
        finally:
            await server._stop_auto_trade_loop()

    asyncio.run(scenario())
