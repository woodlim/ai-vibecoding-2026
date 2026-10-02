from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio
from unittest.mock import AsyncMock

import app.main as server
from app.models import OrderRequest, Quote
from app.paper import PaperTrader
from app.toss_client import TossApiError


def candidates(trader, symbols="ABCDE", price=100):
    return [{"quote": trader.set_quote(Quote(symbol=s, name=s, price=price)),
             "change_rate": 5, "score": 100 - i} for i, s in enumerate(symbols)]


def test_four_rounds_split_five_stocks_and_stay_within_budget(monkeypatch):
    clock = [datetime(2026, 9, 30, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.paper.now_utc", lambda: clock[0])
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    pool = candidates(trader, price=25)
    for round_number in range(4):
        trader.run_momentum_strategy(pool)
        assert len(trader.orders) == (round_number + 1) * 5
        assert trader.strategy.buy_tranches_used == round_number + 1
        assert trader.account().daily_auto_buy_used == (round_number + 1) * 8750
        trader.run_momentum_strategy(pool)
        assert len(trader.orders) == (round_number + 1) * 5
        clock[0] += timedelta(minutes=15)
    trader.run_momentum_strategy(pool)
    assert len(trader.orders) == 20
    assert len(trader.strategy.managed_symbols) == 5
    assert all(p.quantity == 280 for p in trader.positions.values())
    assert all(amount == 7000 for amount in trader._symbol_buy_used.values())
    assert trader.cash == 65000


def test_fewer_candidates_leave_cash_and_expensive_top_does_not_block_others():
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    expensive = {"quote": Quote(symbol="EXPENSIVE", price=100000), "score": 1000, "change_rate": 5}
    pool = candidates(trader, "AB", price=50)
    trader.run_momentum_strategy([expensive, *pool, pool[0]])
    assert [o.symbol for o in trader.orders] == ["A", "B"]
    assert trader.account().daily_auto_buy_used == 8750
    assert trader.strategy.buy_tranches_used == 1


def test_all_holdings_are_checked_for_stop_loss_profit_and_fade():
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    trader.run_momentum_strategy(candidates(trader))
    pool = candidates(trader, "ABCD")
    trader.set_quote(Quote(symbol="A", price=97))
    trader.set_quote(Quote(symbol="B", price=110))
    trader.set_quote(Quote(symbol="E", price=101))
    trader.run_momentum_strategy(pool)
    assert {o.symbol for o in trader.orders if o.side == "SELL"} == {"A", "B", "E"}
    assert set(trader.strategy.managed_symbols) == {"C", "D"}
    assert trader.account().daily_auto_buy_used == 8700
    assert trader.strategy.buy_tranches_used == 1


def test_existing_large_holding_cannot_receive_more_allocation():
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    pool = candidates(trader)
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=90), automatic=True)
    trader.run_momentum_strategy(pool)
    assert trader.positions["A"].quantity == 90
    assert len(trader.strategy.managed_symbols) == 5
    assert trader._symbol_buy_used["A"] == 9001


def test_one_failed_quote_does_not_prevent_other_holding_exit(monkeypatch):
    trader = PaperTrader(Decimal(100000))
    trader.start_strategy("AUTO")
    pool = candidates(trader, "AB")
    trader.run_momentum_strategy(pool)

    async def quote(symbol):
        if symbol == "A":
            raise TossApiError("offline")
        return Quote(symbol="B", price=110)

    monkeypatch.setattr(server, "trader", trader)
    monkeypatch.setattr(server, "toss", type("Fake", (), {"quote": staticmethod(quote)})())
    monkeypatch.setattr(server, "_market_momentum_candidates", AsyncMock(return_value=pool))

    async def scenario():
        task = asyncio.create_task(server._auto_trade_loop(pool))
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert trader.positions["A"].quantity == 44
    assert trader.positions["B"].quantity == 0
    assert "A" in trader.strategy.last_error
    assert len(trader.orders) == 3
