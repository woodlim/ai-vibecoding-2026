const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const orderHistory = fs.readFileSync(path.join(__dirname, '../frontend/order-history.js'), 'utf8');
const sellCode = source.slice(source.indexOf('const orderStockNames ='), source.indexOf('function resolveOrderNames('));

function setup({ confirm = true, api, refresh } = {}) {
  const elements = {};
  const requests = [];
  const fill = { symbol: 'A', filled_quantity: '2', price: '110', total_amount: '220' };
  const context = vm.createContext({
    $: id => elements[id] ||= { innerHTML: '', addEventListener(event, handler) { this[event] = handler; } },
    latestQuotes: { A: 110 }, refreshSequence: 0,
    money: value => `${value} 원`,
    window: { confirm: () => confirm }, crypto: { randomUUID: () => 'test-id' },
    message: (id, text, error) => { elements[id] = { text, error }; },
    api: async (url, options) => { requests.push({ url, ...JSON.parse(options.body) }); return api ? api() : fill; },
    refresh: refresh || (async () => {}),
  });
  vm.runInContext(orderHistory + sellCode, context);
  vm.runInContext(`displayedPositions = [{symbol:'A',quantity:'2',average_price:'100'}]; orderStockNames.set('A','종목 A'); renderPositions();`, context);
  return {
    elements, requests, context,
    click: () => elements.positions.click({ target: { closest: () => ({ dataset: { sellSymbol: 'A' } }) } }),
  };
}

test('shows the name, holding status and sell button; cancel makes no order', async () => {
  const ui = setup({ confirm: false });
  assert.match(ui.elements.positions.innerHTML, /종목 A/);
  assert.match(ui.elements.positions.innerHTML, /보유 중/);
  assert.match(ui.elements.positions.innerHTML, /전량 매도/);
  await ui.click();
  assert.equal(ui.requests.length, 0);
});

test('confirmed click sells the full confirmed quantity and refreshes once', async () => {
  let refreshes = 0;
  const ui = setup({ refresh: async options => { assert.equal(options.quotes, false); refreshes++; } });
  await ui.click();
  assert.deepEqual(ui.requests, [{ url: '/api/v1/positions/A/sell', quantity: '2', client_order_id: 'test-id' }]);
  assert.equal(refreshes, 1);
  assert.match(ui.elements.sellMessage.text, /매도 완료/);
  assert.match(ui.elements.positions.innerHTML, /보유 주식이 없습니다/);
});

test('pending sale disables the button and ignores duplicate clicks', async () => {
  let finish;
  const ui = setup({ api: () => new Promise(resolve => { finish = resolve; }) });
  const first = ui.click();
  assert.match(ui.elements.positions.innerHTML, /disabled/);
  await ui.click();
  assert.equal(ui.requests.length, 1);
  finish({ price: '110', filled_quantity: '2', total_amount: '220' });
  await first;
});

test('failed request keeps holdings and allows another attempt', async () => {
  const ui = setup({ api: async () => { throw new Error('최신 시세 조회 실패'); } });
  await ui.click();
  assert.match(ui.elements.sellMessage.text, /최신 시세 조회 실패/);
  assert.equal(ui.elements.sellMessage.error, true);
  assert.match(ui.elements.positions.innerHTML, /보유 중/);
  assert.doesNotMatch(ui.elements.positions.innerHTML, /disabled/);
});

test('successful fill with failed refresh is not presented as a failed sale', async () => {
  const ui = setup({ refresh: async () => { throw new Error('offline'); } });
  await ui.click();
  assert.match(ui.elements.sellMessage.text, /매도는 완료/);
  assert.match(ui.elements.positions.innerHTML, /보유 주식이 없습니다/);
});

test('manual sales remain visible in history and names are escaped', () => {
  const ui = setup();
  vm.runInContext(`renderOrderHistory([{source:'MANUAL',symbol:'A',symbol_name:'<종목>',side:'SELL',filled_quantity:'2',price:'110',total_amount:'220',status:'FILLED',created_at:'2026-09-30T00:00:00Z'}]);`, ui.context);
  assert.match(ui.elements.orders.innerHTML, /수동 · 체결 완료/);
  assert.match(ui.elements.orders.innerHTML, /&lt;종목&gt;/);
  assert.match(ui.elements.orders.innerHTML, /220 원/);
});
