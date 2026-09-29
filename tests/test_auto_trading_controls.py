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
    monkeypatch.setattr(server, "trader", PaperTrader(Decimal(1000)))
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
    trader = PaperTrader(Decimal(1000))
    quote = Quote(symbol="A", name="종목 A", price=100)
    trader.start_strategy("A")
    trader.set_quote(quote)
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5, "score": 10}])
    assert trader.orders[0].side == "BUY"
    assert trader.orders[0].quantity == 4
    assert trader.account().daily_auto_buy_used == 400

    trader.set_quote(Quote(symbol="A", name="종목 A", price=110))
    trader.run_momentum_strategy([])
    assert trader.orders[-1].side == "SELL"
    assert trader.orders[-1].quantity == 4
    assert trader.orders[-1].symbol_name == "종목 A"
    assert trader.account().daily_auto_buy_used == 400


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
            assert status.running and status.symbol == "A"
            assert status.symbol_name == "시장 급등주"
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
