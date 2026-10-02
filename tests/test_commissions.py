import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.commissions import migrate_commissions
from app.models import OrderRequest, PaperState, Quote, now_utc
from app.paper import PaperTrader
from app.toss_client import TossApiError, TossClient


def test_buy_and_partial_sales_include_both_fees_without_changing_quote_average():
    trader = PaperTrader(Decimal(1000000))
    buy = trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=10000))
    assert buy.commission == 15
    assert buy.settlement_amount == 100015
    assert trader.cash == 899985
    assert trader.positions["A"].average_price == 10000
    assert trader.positions["A"].purchase_commission == 15
    sale = trader.order(OrderRequest(symbol="A", side="SELL", quantity=4, price=11000, client_order_id="sale"))
    assert sale.commission == 6  # 6.6 KRW is truncated.
    assert sale.cost_basis == 40006
    assert sale.realized_pnl == 3988
    assert sale.realized_pnl_rate == Decimal(3988) / Decimal(40006) * 100
    assert trader.cash == 943979
    assert trader.positions["A"].purchase_commission == 9
    assert trader.order(OrderRequest(symbol="A", side="SELL", quantity=4, price=11000, client_order_id="sale")) == sale
    assert trader.cash == 943979
    last = trader.order(OrderRequest(symbol="A", side="SELL", quantity=6, price=10000))
    assert last.realized_pnl == -18
    assert trader.positions["A"].purchase_commission == 0
    assert trader.account().realized_pnl == 3970
    assert trader.account().total_commission == 30
    assert trader.cash == 1003970


def test_buy_requires_cash_for_fee_and_account_rate_zero_is_respected():
    trader = PaperTrader(Decimal(100000))
    with pytest.raises(ValueError, match="cash"):
        trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=10000))
    assert not trader.orders
    assert trader.cash == 100000
    assert trader.max_buy_quantity(Decimal(10000), trader.cash) == 9
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    assert trader.max_buy_quantity(Decimal(10000), trader.cash) == 10
    assert trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=10000)).commission == 0
    assert trader.cash == 0


def test_expired_account_rate_falls_back_without_repricing_prior_fills():
    trader = PaperTrader(Decimal(1000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT", trader._today())
    first = trader.order(OrderRequest(symbol="A", side="BUY", quantity=1, price=100000))
    trader.commission_end_date = trader._today() - timedelta(days=1)
    second = trader.order(OrderRequest(symbol="A", side="BUY", quantity=1, price=100000))
    assert first.commission == 0
    assert second.commission == 15
    assert second.commission_source == "KRX_DEFAULT"
    assert trader.account().commission_source == "KRX_DEFAULT"


def test_diversified_rounds_cash_limits_and_manual_credit_include_commissions(monkeypatch):
    trader = PaperTrader(Decimal(1000000))
    trader.start_strategy("AUTO")
    candidates = [{"quote": Quote(symbol=s, price=1000), "change_rate": 5} for s in "ABCDE"]
    clock = [now_utc()]
    monkeypatch.setattr("app.paper.now_utc", lambda: clock[0])
    for _ in range(8):
        before = trader.account().daily_auto_buy_used
        trader.run_momentum_strategy(candidates)
        account = trader.account()
        assert account.daily_auto_buy_used - before <= 87500
        assert account.daily_auto_buy_used <= 350000
        assert all(value <= 80000 for value in trader._symbol_buy_used.values())
        assert trader.cash == trader.initial_cash - sum(o.settlement_amount for o in trader.orders)
        clock[0] += timedelta(minutes=15)
    quantity = trader.positions["A"].quantity
    buy_cost = quantity * 1000 + trader.positions["A"].purchase_commission
    sale = trader.order(OrderRequest(symbol="A", side="SELL", quantity=quantity, price=900))
    assert trader.account().daily_manual_sell_credit == min(buy_cost, sale.settlement_amount)


def test_strategy_skips_share_when_cash_cannot_cover_its_commission():
    trader = PaperTrader(Decimal(10000), auto_budget_percent=Decimal(100))
    trader.start_strategy("A")
    for price in (9600, 9700, 9800, 9900, 10000):
        trader.set_quote(Quote(symbol="A", price=price))
    trader.run_strategy("A")
    assert trader.cash == 10000
    assert not trader.orders
    assert trader.strategy.last_signal == "BUDGET_LIMIT"


def legacy_state():
    trader = PaperTrader(Decimal(1000000))
    trader.set_commission(Decimal(0), "TOSS_ACCOUNT")
    trader.start_strategy("A")
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=10000), automatic=True)
    trader.order(OrderRequest(symbol="A", side="SELL", quantity=4, price=11000))
    payload = trader.snapshot().model_dump(mode="json")
    payload["version"] = 1
    for order in payload["orders"]:
        for key in ("commission", "commission_rate", "commission_source", "settlement_amount"):
            order.pop(key, None)
    for position in payload["positions"]:
        position.pop("purchase_commission", None)
    for key in ("commission_rate", "commission_source", "commission_end_date"):
        payload.pop(key, None)
    return PaperState.model_validate(payload)


def test_legacy_migration_preserves_backup_and_never_charges_twice(tmp_path):
    state = legacy_state()
    original = state.model_dump_json()
    path = tmp_path / "state.json"
    path.write_text(original, encoding="utf-8")
    trader = PaperTrader()
    trader.enable_persistence(path)
    assert path.with_name("state.pre-commissions.json").read_text(encoding="utf-8") == original
    assert trader.cash == 943979
    assert trader.positions["A"].purchase_commission == 9
    assert trader.orders[-1].realized_pnl == 3988
    assert all(o.commission_source == "LEGACY_ESTIMATE" for o in trader.orders)
    assert trader.account().daily_auto_buy_used == 100015
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    restored = PaperTrader()
    restored.enable_persistence(path)
    assert restored.snapshot() == trader.snapshot()
    assert path.with_name("state.pre-commissions.json").read_text(encoding="utf-8") == original


def test_migration_refuses_incomplete_history_and_insufficient_cash():
    state = legacy_state()
    state.positions[0].quantity += 1
    with pytest.raises(ValueError, match="보유 수량"):
        migrate_commissions(state)
    state = legacy_state()
    state.cash = Decimal(0)
    with pytest.raises(ValueError, match="현금"):
        migrate_commissions(state)


def test_failed_persistence_restores_cash_and_purchase_fees(tmp_path, monkeypatch):
    trader = PaperTrader(Decimal(1000000))
    trader.enable_persistence(tmp_path / "state.json")
    trader.order(OrderRequest(symbol="A", side="BUY", quantity=10, price=10000))
    before = trader.snapshot()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("app.state.save_state", fail)
    with pytest.raises(OSError):
        trader.order(OrderRequest(symbol="A", side="SELL", quantity=4, price=11000))
    assert trader.snapshot() == before


def commission_client(monkeypatch, rows):
    client = TossClient()
    client.account_seq = "test-account"
    monkeypatch.setattr(client, "_access_token", AsyncMock(return_value="test-token"))
    request = AsyncMock(return_value=httpx.Response(200, json={"result": rows}))
    monkeypatch.setattr(client, "_request", request)
    return client, request


def test_toss_commission_uses_account_header_and_current_kr_rate(monkeypatch):
    client, request = commission_client(monkeypatch, [
        {"marketCountry": "US", "commissionRate": "0.001"},
        {"marketCountry": "KR", "commissionRate": "0", "endDate": "2099-12-31"},
        {"marketCountry": "KR", "commissionRate": "0.00015", "endDate": "2020-12-31"},
    ])
    assert asyncio.run(client.domestic_commission()) == (Decimal(0), date(2099, 12, 31))
    request.assert_awaited_once_with("GET", "/api/v1/commissions", headers={
        "Authorization": "Bearer test-token", "X-Tossinvest-Account": "test-account",
    })


@pytest.mark.parametrize("rows", [[], [{"marketCountry": "KR", "commissionRate": "NaN"}],
                                   [{"marketCountry": "KR", "commissionRate": "-1"}],
                                   [{"marketCountry": "KR", "commissionRate": "0", "startDate": "2099-01-01"}]])
def test_invalid_or_inactive_account_commissions_are_not_used(monkeypatch, rows):
    client, _ = commission_client(monkeypatch, rows)
    with pytest.raises(TossApiError):
        asyncio.run(client.domestic_commission())


def test_account_discovery_is_read_only_and_selects_only_a_single_account(monkeypatch):
    client = TossClient()
    client.account_seq = ""
    monkeypatch.setattr(client, "_access_token", AsyncMock(return_value="test-token"))
    request = AsyncMock(side_effect=[
        httpx.Response(200, json={"result": [{"accountSeq": 1, "accountType": "BROKERAGE"}]}),
        httpx.Response(200, json={"result": [{"marketCountry": "KR", "commissionRate": "0.00014"}]}),
    ])
    monkeypatch.setattr(client, "_request", request)
    assert asyncio.run(client.domestic_commission()) == (Decimal("0.00014"), None)
    assert request.await_args_list[0].args == ("GET", "/api/v1/accounts")
    assert request.await_args_list[1].kwargs["headers"]["X-Tossinvest-Account"] == "1"


@pytest.mark.parametrize("accounts", [[], [{"accountSeq": 1}, {"accountSeq": 2}]])
def test_account_discovery_does_not_guess_when_no_unique_account(monkeypatch, accounts):
    client = TossClient()
    client.account_seq = ""
    monkeypatch.setattr(client, "_access_token", AsyncMock(return_value="test-token"))
    request = AsyncMock(return_value=httpx.Response(200, json={"result": accounts}))
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(TossApiError):
        asyncio.run(client.domestic_commission())
    assert request.await_count == 1
