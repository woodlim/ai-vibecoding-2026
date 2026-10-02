"""KRW PAPER commissions; official rates checked on 2026-10-02.

https://home.tossinvest.com/ko/open-api (KRX 0.015%, NXT 0.014%)
https://openapi.tossinvest.com/openapi-docs/latest/openapi.json (/commissions)
Toss's domestic margin trading guide specifies truncating fractions of a won.
PAPER has no exchange routing, so KRX is the explicit fallback estimate.
"""
from collections import defaultdict
from datetime import timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from .models import PaperState


KRX_COMMISSION_RATE = Decimal("0.00015")


def commission_for(amount: Decimal, rate: Decimal) -> Decimal:
    return (amount * rate).quantize(Decimal(1), rounding=ROUND_DOWN)


def migrate_commissions(state: PaperState) -> PaperState:
    """Add estimated costs once without discarding cash or trade history."""
    if state.version == 2:
        return state.model_copy(deep=True)
    migrated = state.model_copy(deep=True)
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    gross_cost: dict[str, Decimal] = defaultdict(Decimal)
    fees: dict[str, Decimal] = defaultdict(Decimal)
    daily_fees = Decimal(0)
    symbol_fees: dict[str, Decimal] = defaultdict(Decimal)
    total_fees = Decimal(0)
    for order in migrated.orders:
        if order.status != "FILLED" or order.filled_quantity <= 0:
            continue
        symbol, quantity = order.symbol, order.filled_quantity
        order.commission_rate = KRX_COMMISSION_RATE
        order.commission_source = "LEGACY_ESTIMATE"
        order.commission = commission_for(order.total_amount, KRX_COMMISSION_RATE)
        total_fees += order.commission
        if order.side == "BUY":
            quantities[symbol] += quantity
            gross_cost[symbol] += order.total_amount
            fees[symbol] += order.commission
            day = order.created_at.astimezone(timezone(timedelta(hours=9))).date()
            if order.source == "AUTO" and day == state.budget_date:
                daily_fees += order.commission
                symbol_fees[symbol] += order.commission
        else:
            if quantities[symbol] < quantity:
                raise ValueError("수수료 재계산 실패: 매도에 대응하는 매수 내역이 없습니다.")
            full_sale = quantity == quantities[symbol]
            gross_basis = gross_cost[symbol] if full_sale else gross_cost[symbol] * quantity / quantities[symbol]
            buy_fee = fees[symbol] if full_sale else fees[symbol] * quantity / quantities[symbol]
            order.cost_basis = gross_basis + buy_fee
            order.realized_pnl = order.settlement_amount - order.cost_basis
            order.realized_pnl_rate = order.realized_pnl / order.cost_basis * 100 if order.cost_basis else Decimal(0)
            quantities[symbol] -= quantity
            gross_cost[symbol] -= gross_basis
            fees[symbol] -= buy_fee
    positions = {p.symbol: p for p in migrated.positions}
    for symbol in set(quantities) | set(positions):
        position = positions.get(symbol)
        if (position.quantity if position else Decimal(0)) != quantities[symbol]:
            raise ValueError("수수료 재계산 실패: 보유 수량과 체결 내역이 일치하지 않습니다.")
        if position:
            position.purchase_commission = fees[symbol]
    if total_fees > migrated.cash:
        raise ValueError("수수료 재계산에 필요한 현금이 부족합니다. 기존 계좌 파일을 확인하세요.")
    migrated.cash -= total_fees
    migrated.daily_used += daily_fees
    for symbol, fee in symbol_fees.items():
        migrated.symbol_buy_used[symbol] = migrated.symbol_buy_used.get(symbol, Decimal(0)) + fee
    migrated.version = 2
    return migrated
