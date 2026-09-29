from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app, trader

client = TestClient(app)


def setup_function() -> None:
    trader.cash = trader.initial_cash
    trader.quotes.clear()
    trader.positions.clear()
    trader.orders.clear()
    trader.client_orders.clear()


def test_paper_buy_and_idempotency() -> None:
    client.post("/api/v1/quotes", json={"symbol": "005930", "name": "삼성전자", "price": "70000"})
    payload = {"symbol": "005930", "side": "BUY", "quantity": "2", "client_order_id": "test-1"}
    first = client.post("/api/v1/orders", json=payload)
    second = client.post("/api/v1/orders", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]
    assert len(client.get("/api/v1/orders").json()) == 1
    history = client.get("/api/v1/orders").json()[0]
    assert history["symbol_name"] == "삼성전자"
    assert history["source"] == "MANUAL"
    assert Decimal(history["total_amount"]) == Decimal("140000")


def test_rejects_sell_without_position() -> None:
    client.post("/api/v1/quotes", json={"symbol": "005930", "price": "70000"})
    response = client.post("/api/v1/orders", json={"symbol": "005930", "side": "SELL", "quantity": "1"})
    assert response.status_code == 400
