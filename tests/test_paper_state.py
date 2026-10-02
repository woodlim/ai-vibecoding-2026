from decimal import Decimal

import pytest

from app.models import PositionSellRequest, Quote
from app.paper import PaperTrader


def test_round_trip_preserves_holdings_budget_rounds_names_and_setting(tmp_path):
    path = tmp_path / "state.json"
    trader = PaperTrader(Decimal(100000))
    trader.enable_persistence(path)
    trader.set_auto_budget_percent(Decimal(50))
    trader.start_strategy("AUTO")
    quote = trader.set_quote(Quote(symbol="A", name="종목 A", price=100))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    restored = PaperTrader()
    restored.enable_persistence(path)
    assert restored.cash == trader.cash
    assert restored.positions == trader.positions
    assert restored.orders == trader.orders
    assert restored.account() == trader.account()
    assert restored.strategy.buy_tranches_used == 1
    assert restored._last_auto_buy_at == trader._last_auto_buy_at
    assert restored._symbol_buy_used == trader._symbol_buy_used
    assert not restored.strategy.running


def test_manual_sale_and_idempotency_survive_restart(tmp_path):
    path = tmp_path / "state.json"
    trader = PaperTrader(Decimal(100000))
    trader.enable_persistence(path)
    trader.start_strategy("AUTO")
    quote = trader.set_quote(Quote(symbol="A", price=100))
    trader.run_momentum_strategy([{"quote": quote, "change_rate": 5}])
    request = PositionSellRequest(quantity=79, client_order_id="sell")
    order = trader.sell_position("A", request, Quote(symbol="A", price=110))
    restored = PaperTrader()
    restored.enable_persistence(path)
    assert restored.check_position_sell("A", request).order_id == order.order_id
    assert restored.cash == 100788
    assert "A" in restored._blocked_symbols
    assert restored.account().daily_auto_buy_used == 7901


def test_save_failure_rolls_back_entire_multi_stock_round(tmp_path, monkeypatch):
    trader = PaperTrader(Decimal(100000))
    path = tmp_path / "state.json"
    trader.enable_persistence(path)
    trader.start_strategy("AUTO")
    before = path.read_text(encoding="utf-8")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("app.paper.save_state", fail)
    monkeypatch.setattr("app.state.save_state", fail)
    with pytest.raises(OSError):
        trader.run_momentum_strategy([
            {"quote": Quote(symbol=s, price=100), "change_rate": 5} for s in "ABC"
        ])
    assert not trader.orders
    assert not trader.positions
    assert trader.cash == 100000
    assert trader.account().daily_auto_buy_used == 0
    assert trader.strategy.buy_tranches_used == 0
    assert path.read_text(encoding="utf-8") == before


def test_invalid_state_fails_instead_of_resetting_cash(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"cash":"broken"}', encoding="utf-8")
    with pytest.raises(ValueError):
        PaperTrader().enable_persistence(path)
    assert path.read_text(encoding="utf-8") == '{"cash":"broken"}'
