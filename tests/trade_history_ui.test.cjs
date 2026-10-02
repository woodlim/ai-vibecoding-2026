const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const readFrontend = file => fs.readFileSync(path.join(__dirname, '../frontend', file), 'utf8');
const tableSource = readFrontend('order-history.js');
const dashboardSource = readFrontend('app.js');
const previewSource = dashboardSource.slice(dashboardSource.indexOf('function renderOrderHistory('), dashboardSource.indexOf('function resolveOrderNames('));
const orders = Array.from({ length: 15 }, (_, index) => ({
  order_id: String(index), symbol: `stock-${index}`, symbol_name: `종목 ${index}`,
  side: index % 2 ? 'SELL' : 'BUY', source: 'AUTO', status: 'FILLED',
  filled_quantity: '1', price: '10000', total_amount: '10000', commission: '1',
  created_at: `2026-10-02T01:${String(index).padStart(2, '0')}:00Z`,
}));
const rowCount = html => (html.match(/<tbody>([\s\S]*)<\/tbody>/)?.[1].match(/<tr>/g) || []).length;

test('dashboard shows exactly the latest ten trades without changing history', () => {
  const element = {};
  const context = vm.createContext({ $: () => element, orderStockNames: new Map(), latestOrderHistory: [] });
  vm.runInContext(tableSource + previewSource, context);
  const before = JSON.stringify(orders);
  context.orders = orders;
  vm.runInContext('renderOrderHistory(orders);', context);
  assert.equal(rowCount(element.innerHTML), 10);
  assert.ok(element.innerHTML.indexOf('stock-14') < element.innerHTML.indexOf('stock-13'));
  assert.match(element.innerHTML, /stock-5/);
  assert.doesNotMatch(element.innerHTML, /stock-4</);
  assert.equal(JSON.stringify(orders), before);
  assert.equal(context.latestOrderHistory.length, 15);
});

test('preview handles fewer than ten trades and empty accounts', () => {
  const element = {};
  const context = vm.createContext({ $: () => element, orderStockNames: new Map() });
  vm.runInContext(tableSource + previewSource, context);
  context.orders = orders.slice(0, 3);
  vm.runInContext('renderOrderHistory(orders);', context);
  assert.equal(rowCount(element.innerHTML), 3);
  vm.runInContext('renderOrderHistory([]);', context);
  assert.match(element.innerHTML, /아직 매매 내역이 없습니다/);
});

function fullPage(fetch) {
  const elements = Object.fromEntries(['historyOrders', 'historyCount', 'historyMessage', 'historyRefreshButton'].map(id => [id, {
    innerHTML: '', textContent: '', classList: { add() {}, remove() {} },
    setAttribute(name, value) { this[name] = value; },
    addEventListener(event, handler) { this[event] = handler; },
  }]));
  const context = vm.createContext({
    document: { getElementById: id => elements[id], body: { classList: { toggle() {} } } },
    localStorage: { getItem: () => 'dark' }, fetch, setInterval() {},
  });
  vm.runInContext(tableSource + readFrontend('trade-history.js'), context);
  return { context, elements };
}

test('full page loads every trade in newest-first order and keeps fees', async () => {
  let finish;
  const { context, elements } = fullPage(() => new Promise(resolve => { finish = resolve; }));
  finish({ ok: true, json: async () => orders });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(rowCount(elements.historyOrders.innerHTML), 15);
  assert.match(elements.historyOrders.innerHTML, /stock-0</);
  assert.ok(elements.historyOrders.innerHTML.indexOf('stock-14') < elements.historyOrders.innerHTML.indexOf('stock-13'));
  assert.match(elements.historyOrders.innerHTML, /수수료/);
  assert.match(elements.historyOrders.innerHTML, /정산금액/);
  assert.match(elements.historyCount.textContent, /전체 15건/);
  assert.equal(elements.historyOrders['aria-busy'], 'false');
  assert.equal(elements.historyRefreshButton.disabled, false);
});

test('full page keeps existing history after a failed refresh and allows retry', async () => {
  let fail = false;
  const { context, elements } = fullPage(async () => ({ ok: !fail, json: async () => orders }));
  await new Promise(resolve => setImmediate(resolve));
  const before = elements.historyOrders.innerHTML;
  fail = true;
  await vm.runInContext('refreshHistory();', context);
  assert.equal(elements.historyOrders.innerHTML, before);
  assert.match(elements.historyMessage.textContent, /새로고침/);
  assert.equal(elements.historyRefreshButton.disabled, false);
  fail = false;
  await elements.historyRefreshButton.click();
  assert.match(elements.historyMessage.textContent, /갱신/);
});
