function orderHistoryTable(orders, { limit = Infinity, stockNames = new Map() } = {}) {
  const historyOrders = orders.slice().reverse().slice(0, limit);
  if (!historyOrders.length) return '<p class="subtle">아직 매매 내역이 없습니다. 자동매매와 직접 매도 내역이 이곳에 표시됩니다.</p>';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const money = value => `${Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0, minimumFractionDigits: 0 })} 원`;
  const rows = historyOrders.map(order => {
    const name = order.symbol_name || stockNames.get(order.symbol) || order.symbol;
    const date = new Date(order.created_at);
    const time = Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false });
    const quantity = Number(order.filled_quantity ?? order.quantity);
    const amount = order.total_amount ?? Number(order.price) * quantity;
    const buy = order.side === 'BUY';
    const automatic = order.source ? order.source === 'AUTO' : /^sma-(buy|sell)-/.test(order.client_order_id || '');
    const status = `${automatic ? '자동' : '수동'} · ${{ FILLED: '체결 완료', REJECTED: '주문 거절' }[order.status] || order.status}`;
    const realized = Number(order.realized_pnl ?? 0);
    const commission = Number(order.commission ?? 0);
    const settlement = order.settlement_amount ?? Number(amount) + (buy ? commission : -commission);
    const feeLabel = order.commission_source === 'LEGACY_ESTIMATE' ? '과거 거래 추정' : 'PAPER 계산';
    const result = buy ? '-' : `<strong class="${realized >= 0 ? 'positive' : 'negative'}">${realized >= 0 ? '+' : ''}${money(realized)}<small>${Number(order.realized_pnl_rate ?? 0).toFixed(2)}%</small></strong>`;
    return `<tr><td>${escape(time)}</td><td><strong class="trade-stock-name">${escape(name)}</strong><small>${escape(order.symbol)}</small></td><td><span class="trade-side ${buy ? 'trade-buy' : 'trade-sell'}">${buy ? '매수' : '매도'}</span></td><td class="numeric">${quantity.toLocaleString('ko-KR', { maximumFractionDigits: 8 })}주</td><td class="numeric">${money(order.price)}</td><td class="numeric"><strong>${money(amount)}</strong></td><td class="numeric" title="${feeLabel}">${money(commission)}<small>${feeLabel}</small></td><td class="numeric">${money(settlement)}</td><td class="numeric trade-realized">${result}</td><td>${escape(status)}</td></tr>`;
  }).join('');
  return `<table><thead><tr><th scope="col">체결 시각</th><th scope="col">종목명</th><th scope="col">구분</th><th scope="col" class="numeric">체결 수량</th><th scope="col" class="numeric">체결 단가</th><th scope="col" class="numeric">거래금액</th><th scope="col" class="numeric">수수료</th><th scope="col" class="numeric">정산금액</th><th scope="col" class="numeric">실현손익</th><th scope="col">상태</th></tr></thead><tbody>${rows}</tbody></table>`;
}
