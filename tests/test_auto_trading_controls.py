import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import app.main as server
from app.models import Quote
from app.paper import PaperTrader
from app.toss_client import TossApiError


@pytest.fixture
def isolated_server(monkeypatch):
    monkeypatch.setattr(server, "trader", PaperTrader(Decimal(5000)))
    monkeypatch.setattr(server, "strategy_task", None)
    monkeypatch.setattr(server, "strategy_command_id", 0)
    monkeypatch.setattr(server, "AUTO_TRADE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(server, "AUTO_MIN_DAILY_CHANGE_PERCENT", 1.0)


def test_candidates_use_broad_volume_and_gainer_rankings(isolated_server, monkeypatch):
    async def scenario():
        fake_toss = type("FakeToss", (), {
            "rankings": AsyncMock(side_effect=[
                [{"rank": 1, "symbol": "A", "tradingVolume": "1000"}, {"rank": 2, "symbol": "B", "tradingVolume": "800"}],
                [
                    {"rank": 1, "symbol": "A", "price": {"lastPrice": "100", "changeRate": "0.05"}},
                    {"rank": 2, "symbol": "B", "price": {"lastPrice": "50", "changeRate": "0.005"}},
                    {"rank": 3, "symbol": "C", "price": {"lastPrice": "75", "changeRate": "0.08"}},
                ],
            ]),
            "stock_names": AsyncMock(return_value={"A": "종목 A", "B": "종목 B"}),
        })()
        monkeypatch.setattr(server, "toss", fake_toss)
        result = await server._market_momentum_candidates()
        assert [item["quote"].symbol for item in result] == ["A"]
        assert result[0]["quote"].name == "종목 A"
        assert result[0]["change_rate"] == 5
        assert result[0]["volume_rank"] == 1
        fake_toss.rankings.assert_any_await("MARKET_TRADING_VOLUME", "realtime", 100)
        fake_toss.rankings.assert_any_await("TOP_GAINERS", "1d", 100)

    asyncio.run(scenario())


def test_momentum_buys_from_daily_budget_then_sells_when_signal_fades():
    trader = PaperTrader(Decimal(5000))
    quote = Quote(symbol="A", name="종목 A", price=100)
    trader.start_strategy("A")
    trader.set_quote(quote)
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5, "score": 10}])
    assert trader.orders[0].side == "BUY"
    assert trader.orders[0].quantity == 1
    assert trader.account().daily_auto_buy_used == 100
    assert trader.strategy.buy_tranches_used == 1

    trader.set_quote(Quote(symbol="A", name="종목 A", price=105))
    trader.run_momentum_strategy([])
    assert trader.orders[-1].side == "SELL"
    assert trader.orders[-1].quantity == 1
    assert trader.orders[-1].symbol_name == "종목 A"
    assert trader.strategy.last_signal == "SELL_MOMENTUM_FADE"
    assert trader.account().daily_auto_buy_used == 100


@pytest.mark.parametrize("price,signal", [
    ("96", "SELL_STOP_LOSS"),
    ("97", "SELL_STOP_LOSS"),
    ("97.01", "WAIT_TRANCHE"),
    ("109.99", "WAIT_TRANCHE"),
    ("110", "SELL_TAKE_PROFIT"),
    ("111", "SELL_TAKE_PROFIT"),
])
def test_momentum_price_exit_boundaries(price, signal):
    trader = PaperTrader(Decimal(5000))
    trader.start_strategy("A")
    quote = trader.set_quote(Quote(symbol="A", name="종목 A", price=100))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    quote = trader.set_quote(Quote(symbol="A", name="종목 A", price=price))
    candidates = [{"quote": quote, "change_rate": 5}]
    trader.run_momentum_strategy(candidates)
    assert trader.strategy.last_signal == signal
    if signal.startswith("SELL_"):
        assert len(trader.orders) == 2
        assert trader.orders[-1].side == "SELL"
        assert trader.orders[-1].source == "AUTO"
        assert trader.orders[-1].quantity == 1
        assert trader.orders[-1].price == Decimal(price)
        assert trader.cash == Decimal(4900) + Decimal(price)
        assert trader.positions["A"].quantity == 0
        # A sale neither restores today's buy budget nor allows same-day reentry.
        trader.run_momentum_strategy(candidates)
        assert len(trader.orders) == 2
        assert trader.account().daily_auto_buy_used == 100
        assert trader.strategy.buy_tranches_used == 1
    else:
        assert len(trader.orders) == 1
        assert trader.positions["A"].quantity == 1


def test_take_profit_uses_updated_average_price_and_sells_all_shares():
    from app.models import OrderRequest

    trader = PaperTrader(Decimal(5000))
    trader.start_strategy("A")
    quote = trader.set_quote(Quote(symbol="A", price=100))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    trader.set_quote(Quote(symbol="A", price=120))
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=1), automatic=True)
    assert trader.positions["A"].average_price == 110
    for price in ("120", "121"):
        quote = trader.set_quote(Quote(symbol="A", price=price))
        trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
        if price == "120":
            assert len(trader.orders) == 2  # +20% vs first fill, but below +10% vs average.
    assert trader.strategy.last_signal == "SELL_TAKE_PROFIT"
    assert trader.orders[-1].quantity == 2
    assert trader.positions["A"].quantity == 0
    assert trader.account().daily_auto_buy_used == 220


def test_stopped_strategy_does_not_take_profit():
    trader = PaperTrader(Decimal(5000))
    trader.start_strategy("A")
    quote = trader.set_quote(Quote(symbol="A", price=100))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    trader.stop_strategy()
    quote = trader.set_quote(Quote(symbol="A", price=110))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    assert len(trader.orders) == 1
    assert trader.positions["A"].quantity == 1


def test_momentum_entries_are_split_and_spaced_by_fifteen_minutes(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import app.paper as paper_module

    now = [datetime(2026, 9, 29, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(paper_module, "now_utc", lambda: now[0])
    trader = PaperTrader(Decimal(5000))
    trader.start_strategy("A")
    candidate = {"quote": Quote(symbol="A", name="종목 A", price=100), "change_rate": 5, "score": 10}

    trader.set_quote(candidate["quote"])
    trader.run_momentum_strategy([candidate])
    assert trader.orders[0].quantity == 1
    assert trader.account().daily_auto_buy_used == 100

    trader.run_momentum_strategy([candidate])
    assert trader.strategy.last_signal == "WAIT_TRANCHE"
    assert len(trader.orders) == 1

    for _ in range(3):
        now[0] += timedelta(minutes=15)
        trader.set_quote(candidate["quote"])
        trader.run_momentum_strategy([candidate])

    assert len(trader.orders) == 4
    assert [order.quantity for order in trader.orders] == [1, 1, 1, 1]
    assert trader.account().daily_auto_buy_used == 400
    assert trader.strategy.buy_tranches_used == 4
    now[0] += timedelta(minutes=15)
    trader.run_momentum_strategy([candidate])
    assert trader.strategy.last_signal == "TRANCHE_LIMIT"
    assert len(trader.orders) == 4


def test_start_uses_market_rankings_not_recommendations_and_stop_cancels_worker(isolated_server, monkeypatch):
    async def scenario():
        names = {"A": "시장 급등주"}
        async def rankings(ranking_type, duration, count):
            if ranking_type == "MARKET_TRADING_VOLUME":
                return [{"rank": 1, "symbol": "A", "tradingVolume": "10000"}]
            return [{"rank": 1, "symbol": "A", "price": {"lastPrice": "100", "changeRate": "0.05"}}]

        fake_toss = type("FakeToss", (), {
            "rankings": staticmethod(rankings),
            "stock_names": AsyncMock(return_value=names),
            "quote": AsyncMock(return_value=Quote(symbol="A", name="시장 급등주", price=100)),
        })()
        monkeypatch.setattr(server, "toss", fake_toss)
        recommendations = AsyncMock(return_value=[{"symbol": "REC", "name": "추천 종목"}])
        monkeypatch.setattr(server, "recommendations", recommendations)
        try:
            status = await server.start_strategy("REC")
            assert status.running and status.symbol == "AUTO"
            assert status.symbol_name == "다종목 분산매매"
            recommendations.assert_not_awaited()
            worker = server.strategy_task
            await asyncio.sleep(0)
            assert server.trader.orders[0].symbol == "A"
            assert server.trader.orders[0].source == "AUTO"
            stopped = await server.stop_strategy()
            assert not stopped.running
            assert worker.done()
        finally:
            await server._stop_auto_trade_loop()

    asyncio.run(scenario())


def test_start_keeps_scanning_when_market_has_no_current_signal(isolated_server, monkeypatch):
    async def scenario():
        monkeypatch.setattr(server, "toss", type("FakeToss", (), {
            "rankings": AsyncMock(side_effect=[[], []]),
            "stock_names": AsyncMock(return_value={}),
        })())
        try:
            status = await server.start_strategy()
            assert status.running and status.symbol == "AUTO"
            assert status.last_signal in (None, "NO_SIGNAL")
        finally:
            await server._stop_auto_trade_loop()

    asyncio.run(scenario())


def test_ranking_api_error_does_not_start_worker(isolated_server, monkeypatch):
    async def scenario():
        monkeypatch.setattr(server, "toss", type("FakeToss", (), {
            "rankings": AsyncMock(side_effect=TossApiError("연결 실패")),
        })())
        with pytest.raises(TossApiError):
            await server._market_momentum_candidates()
        assert server.strategy_task is None

    asyncio.run(scenario())
