const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const controls = source.slice(source.indexOf('function syncStrategyControls()'), source.indexOf('function selectRecommendation('));

function render(running, slots, pending = '') {
  const elements = { strategyButton: {}, killButton: {}, selectedStrategyStock: {} };
  vm.runInNewContext(controls + '\nsyncStrategyControls();', {
    $: id => elements[id], currentStrategyStatus: { running },
    availableRefillSlots: slots, pendingStrategyAction: pending,
  });
  return elements.strategyButton;
}

test('running strategy allows immediate refill only when manual-sale slots exist', () => {
  assert.equal(render(true, 0).disabled, true);
  assert.equal(render(true, 4).disabled, false);
  assert.equal(render(true, 4).textContent, '빈자리 4종목 채우기');
});

test('pending refill cannot be submitted twice', () => {
  assert.equal(render(true, 4, 'start').disabled, true);
  assert.equal(render(true, 4, 'start').textContent, '후보 확인 중…');
});

test('stopped strategy can start with or without refill slots', () => {
  for (const slots of [0, 4]) {
    assert.equal(render(false, slots).disabled, false);
    assert.equal(render(false, slots).textContent, '자동매매 시작');
  }
});
