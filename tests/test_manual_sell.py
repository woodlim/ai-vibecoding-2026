from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as server
from app.models import OrderRequest, Quote
from app.paper import PaperTrader
from app.toss_client import TossApiError


@pytest.fixture
def market(monkeypatch):
    trader = PaperTrader(Decimal(1000))
    trader.set_quote(Quote(symbol="A", name="종목 A", price=100))
    trader.start_strategy("A")
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=2), automatic=True)
    quote = AsyncMock(return_value=Quote(symbol="A", name="종목 A", price=110))
    monkeypatch.setattr(server, "trader", trader)
    monkeypatch.setattr(server.toss, "quote", quote)
    return TestClient(server.app), trader, quote


def sell(client, **overrides):
    return client.post("/api/v1/positions/A/sell", json={
        "quantity": "2", "client_order_id": "manual-sell-test", **overrides,
    })


def test_sell_updates_cash_position_history_and_preserves_budget(market):
    client, trader, quote = market
    response = sell(client)
    assert response.status_code == 201
    order = response.json()
    assert order["source"] == "MANUAL"
    assert order["symbol_name"] == "종목 A"
    assert order["side"] == "SELL"
    assert Decimal(order["total_amount"]) == 220
    assert trader.cash == 1020
    assert trader.positions["A"].quantity == 0
    assert trader.account().daily_auto_buy_used == 200
    assert trader.account().daily_auto_buy_limit == 400
    assert trader.strategy.running
    assert trader.strategy.last_signal == "SELL_MANUAL"
    quote.assert_awaited_once_with("A")
    assert client.get("/api/v1/orders").json()[-1]["order_id"] == order["order_id"]


def test_sell_is_idempotent_and_rejects_second_order(market):
    client, trader, quote = market
    first = sell(client)
    quote.side_effect = TossApiError("offline after fill")
    retry = sell(client)
    assert retry.status_code == 201
    assert first.json()["order_id"] == retry.json()["order_id"]
    assert sell(client, client_order_id="another").status_code == 409
    assert sell(client, quantity="1").status_code == 409
    assert len(trader.orders) == 2
    assert trader.cash == 1020
    quote.assert_awaited_once()


@pytest.mark.parametrize("error", [TossApiError("offline"), TimeoutError()])
def test_no_cached_price_fallback_when_live_quote_fails(market, error):
    client, trader, quote = market
    quote.side_effect = error
    assert sell(client).status_code == 503
    assert trader.positions["A"].quantity == 2
    assert trader.cash == 800
    assert len(trader.orders) == 1
    assert "A" not in trader._blocked_symbols


def test_quantity_change_requires_confirmation_again(market):
    client, trader, quote = market

    async def add_shares(symbol):
        trader.order(OrderRequest(symbol="A", side="BUY", quantity=1), automatic=True)
        return Quote(symbol=symbol, price=110)

    quote.side_effect = add_shares
    assert sell(client).status_code == 409
    assert trader.positions["A"].quantity == 3
    assert [order.side for order in trader.orders] == ["BUY", "BUY"]


def test_automatic_sell_while_fetching_does_not_sell_twice(market):
    client, trader, quote = market

    async def automatic_sell(symbol):
        trader.run_momentum_strategy([])
        return Quote(symbol=symbol, price=110)

    quote.side_effect = automatic_sell
    assert sell(client).status_code == 409
    assert len(trader.orders) == 2
    assert trader.orders[-1].source == "AUTO"


def test_manual_sell_works_while_stopped_and_blocks_reentry_until_next_day(market, monkeypatch):
    client, trader, _ = market
    trader.stop_strategy()
    assert sell(client).status_code == 201
    assert not trader.strategy.running
    trader.start_strategy("A")
    trader.run_momentum_strategy([{"quote": trader.quotes["A"], "change_rate": 10}])
    assert len(trader.orders) == 2
    next_day = trader._today() + timedelta(days=1)
    monkeypatch.setattr(trader, "_today", lambda: next_day)
    trader._ensure_daily_budget()
    assert "A" not in trader._blocked_symbols


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN"])
def test_invalid_sell_quantity_is_rejected(market, quantity):
    client, trader, quote = market
    assert sell(client, quantity=quantity).status_code == 422
    quote.assert_not_awaited()
    assert len(trader.orders) == 1


def test_mismatched_quote_is_rejected(market):
    client, trader, quote = market
    quote.return_value = Quote(symbol="OTHER", price=110)
    assert sell(client).status_code == 409
    assert trader.positions["A"].quantity == 2
