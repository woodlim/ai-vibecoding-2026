const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const orderHistory = fs.readFileSync(path.join(__dirname, '../frontend/order-history.js'), 'utf8');
const history = source.slice(source.indexOf('const orderStockNames ='), source.indexOf('function resolveOrderNames('));
const rendering = source.slice(source.indexOf('function render(account,'), source.indexOf('async function refresh('));

function setup() {
  const elements = {};
  const context = vm.createContext({
    $: id => id === 'commissionNote' ? elements[id] : elements[id] ||= {
      innerHTML: '', addEventListener() {}, after(node) { elements[node.id] = node; },
    },
    document: { activeElement: {}, querySelectorAll: () => [], createElement: () => ({}) },
    latestQuotes: { A: 11000 }, syncStrategyControls() {}, resolveOrderNames() {}, message() {},
    pendingStrategyAction: '', strategyHelp: null, autoBudgetPercentDraft: null,
    money: value => `${value} 원`,
  });
  vm.runInContext(orderHistory + history + rendering, context);
  return { context, elements };
}

test('asset total, holding P/L and sell history reflect fees exactly once', () => {
  const { context, elements } = setup();
  context.account = {
    cash: '943979', initial_cash: '1000000', total_commission: '21',
    commission_rate: '0.00015', commission_source: 'TOSS_ACCOUNT',
    positions: [{ symbol: 'A', quantity: '6', average_price: '10000', purchase_commission: '9' }],
  };
  context.orders = [{
    symbol: 'A', symbol_name: '종목 A', side: 'SELL', source: 'MANUAL', status: 'FILLED',
    filled_quantity: '4', price: '11000', total_amount: '44000', commission: '6',
    settlement_amount: '43994', realized_pnl: '3988', realized_pnl_rate: '9.9685',
    created_at: '2026-10-02T01:00:00Z', commission_source: 'LEGACY_ESTIMATE',
  }];
  vm.runInContext('render(account, orders, {running:false});', context);
  assert.match(elements.accountSummary.innerHTML, /1009979 원/);
  assert.match(elements.accountSummary.innerHTML, /9979 원/);
  assert.match(elements.positions.innerHTML, /5991 원/);
  assert.match(elements.orders.innerHTML, /43,994 원/);
  assert.match(elements.orders.innerHTML, /3,988 원/);
  assert.match(elements.orders.innerHTML, /과거 거래 추정/);
  assert.match(elements.commissionNote.textContent, /토스 계좌 조회 요율/);
  assert.match(elements.commissionNote.textContent, /누적 수수료 21 원/);
  assert.match(elements.commissionNote.textContent, /매도 세금 제외/);
  vm.runInContext('render(account, orders, {running:false});', context);
  assert.match(elements.accountSummary.innerHTML, /1009979 원/);
});

test('fallback fee source and fee-inclusive affordable quantities are visible', () => {
  const { context, elements } = setup();
  context.account = { cash: 100000, initial_cash: 100000, positions: [], commission_source: 'KRX_DEFAULT', commission_error: '조회 실패' };
  vm.runInContext('render(account, [], {running:false});', context);
  assert.match(elements.commissionNote.textContent, /계좌 요율 미확인/);
  assert.equal(elements.commissionNote.title, '조회 실패');
  assert.equal(vm.runInContext('maximumBuyQuantity(10000, 100000, 0.00015)', context), 9);
  assert.equal(vm.runInContext('maximumBuyQuantity(10000, 100000, 0)', context), 10);
});
