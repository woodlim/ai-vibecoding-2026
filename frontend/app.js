const $ = (id) => document.getElementById(id);
const favicon = document.createElement('link'); favicon.rel = 'icon'; favicon.type = 'image/png'; favicon.href = '/assets/trader-favicon.png'; document.head.appendChild(favicon);
document.querySelector('#quoteLookupForm').closest('article').classList.add('quote-panel');
const themeToggle = document.createElement('button'); themeToggle.id = 'themeToggle'; themeToggle.className = 'theme-toggle'; themeToggle.type = 'button'; document.body.appendChild(themeToggle);
const themeStyle = document.createElement('style'); themeStyle.textContent = '.theme-toggle{position:fixed;right:24px;bottom:24px;z-index:20;height:44px;padding:0 16px;border:1px solid #40547b;border-radius:999px;background:#151e35;color:#dbe6ff;font-size:12px;font-weight:800;cursor:pointer;box-shadow:0 10px 26px #0005}.theme-toggle:hover{transform:translateY(-2px)}body.light{color:#30233a;background:#fff5fa}body.light main{background:transparent}body.light h1,body.light h2,body.light .summary strong{color:#241a24}body.light .card{background:#fffaff;border-color:#f1dbe7;box-shadow:0 12px 30px #d98aa51a}body.light .topbar{border-color:#f0dbe6}body.light .topbar small{color:#d74c83}body.light .badge{background:#fff0f6;border-color:#f3cadd;color:#d74c83}body.light input,body.light select{background:#fff;border-color:#e8cbd9;color:#30233a}body.light .theme-toggle{background:#fff;color:#d74c83;border-color:#e8b8cf;box-shadow:0 8px 22px #d98aa52b}body.light .summary span,body.light th,body.light .subtle{color:#9d7188}body.light td{color:#493647}body.light .message{color:#b23f72}body.light .market-status{background:#fff4f9;border-color:#f0cfdf}body.light .market-status span,body.light .market-status small{color:#9d7188}body.light .market-status strong{color:#492c3c}@media(max-width:520px){.theme-toggle{right:16px;bottom:16px}}'; document.head.appendChild(themeStyle);
function applyTheme(theme) { document.body.classList.toggle('light', theme === 'light'); themeToggle.textContent = theme === 'light' ? '☀ Light' : '☾ Dark'; localStorage.setItem('theme', theme); }
const lightTextStyle = document.createElement('style'); lightTextStyle.textContent = 'body.light h1,body.light h2,body.light .summary strong{color:#30233a!important}body.light .summary span{color:#6f5363!important}'; document.head.appendChild(lightTextStyle);
applyTheme(localStorage.getItem('theme') || 'dark'); themeToggle.onclick = () => applyTheme(document.body.classList.contains('light') ? 'dark' : 'light');
const controls = document.createElement('div'); controls.className = 'top-controls'; controls.innerHTML = '<button id="refreshPageButton" class="top-button">새로고침</button><button id="apiStatusButton" class="top-button api-unknown">API 확인</button><button id="modeButton" class="top-button mode-paper">PAPER</button>'; document.querySelector('.topbar').appendChild(controls);
document.querySelector('.topbar').insertAdjacentHTML('afterend', '<section id="marketStatus" class="market-status"><span>코스피</span><strong>조회 중...</strong><small>토스증권 시장지표</small></section>');
const controlStyle = document.createElement('style'); controlStyle.textContent = '.top-controls{display:flex;gap:8px;align-items:center}.top-button{height:34px;padding:0 12px;border-radius:9px;border:1px solid #40547b;background:#202f50;color:#dbe6ff;font-size:12px;font-weight:700;cursor:pointer}.top-button:hover{filter:brightness(1.15)}.api-connected{background:#123d35;border-color:#36d29a;color:#6ff0bb}.api-failed{background:#4a202c;border-color:#ff6b78;color:#ff9ca6}.api-unknown{background:#202f50}.mode-paper{background:#21365d;border-color:#6d91ff;color:#abc0ff}@media(max-width:650px){.top-controls{gap:4px}.top-button{padding:0 8px;font-size:11px}}'; document.head.appendChild(controlStyle);
const quoteStyle = document.createElement('style'); quoteStyle.textContent = '.quote-panel{grid-column:1/-1}.quote-panel form{display:grid;grid-template-columns:1fr auto}.quote-panel form input{width:100%}.quote-complete{color:#91a0bd;font-size:13px;margin:22px 0 12px}.quote-table th,.quote-table td{padding:13px 10px}.quote-table .quote-price{font-weight:800;color:#fff}@media(max-width:600px){.quote-panel form{grid-template-columns:1fr}.quote-panel form button{width:100%}}body.light .quote-table .quote-price{color:#30233a}'; document.head.appendChild(quoteStyle);
const marketStyle = document.createElement('style'); marketStyle.textContent = '.market-status{display:flex;align-items:baseline;gap:14px;margin:-22px 0 22px;padding:13px 17px;border:1px solid #2a3858;border-radius:14px;background:#151e35}.market-status span{color:#91a0bd;font-size:13px}.market-status strong{font-size:21px;color:#fff}.market-status small{color:#657797;font-size:11px}'; document.head.appendChild(marketStyle);
$('refreshPageButton').onclick = () => window.location.reload();
$('modeButton').onclick = () => window.alert('현재 PAPER 모드입니다. LIVE 주문은 아직 활성화되지 않았습니다.');
async function checkTossConnection() { const button = $('apiStatusButton'); button.textContent = '확인 중...'; button.className = 'top-button api-unknown'; try { const result = await api('/health/toss'); button.textContent = result.connected ? 'API 연결됨' : '연결 실패'; button.className = `top-button ${result.connected ? 'api-connected' : 'api-failed'}`; button.title = result.message; } catch { button.textContent = '연결 실패'; button.className = 'top-button api-failed'; } }
setTimeout(checkTossConnection, 300);
const suggestionBox = document.createElement('div'); suggestionBox.className = 'stock-suggestions'; suggestionBox.style.display = 'none'; document.querySelector('#quoteLookupForm').after(suggestionBox);
document.querySelector('#quoteLookupForm').parentElement.style.position = 'relative';
const suggestionStyle = document.createElement('style'); suggestionStyle.textContent = '.stock-suggestions{position:absolute;z-index:5;margin-top:6px;width:min(360px,90%);background:#151e35;border:1px solid #40547b;border-radius:10px;overflow:hidden;box-shadow:0 12px 28px #0005}.stock-suggestions button{display:flex;justify-content:space-between;width:100%;height:auto;padding:12px 14px;border:0;border-radius:0;background:transparent;color:#eef3ff;text-align:left;box-shadow:none}.stock-suggestions button:hover{background:#24365d;transform:none}.stock-suggestions small{color:#91a0bd}'; document.head.appendChild(suggestionStyle);
const fallbackStocks = [{name:'삼성전자',symbol:'005930',market:'KOSPI'},{name:'삼성전기',symbol:'009150',market:'KOSPI'},{name:'삼성SDI',symbol:'006400',market:'KOSPI'},{name:'삼성물산',symbol:'028260',market:'KOSPI'},{name:'삼성바이오로직스',symbol:'207940',market:'KOSPI'},{name:'LG전자',symbol:'066570',market:'KOSPI'},{name:'LG화학',symbol:'051910',market:'KOSPI'},{name:'LG에너지솔루션',symbol:'373220',market:'KOSPI'},{name:'LG생활건강',symbol:'051900',market:'KOSPI'},{name:'LG디스플레이',symbol:'034220',market:'KOSPI'},{name:'SK하이닉스',symbol:'000660',market:'KOSPI'},{name:'NAVER',symbol:'035420',market:'KOSPI'}];
let selectedRecommendationSymbol = '';
let selectedRecommendationName = '';
let currentStrategyStatus = { running: false, symbol: '' };
let pendingStrategyAction = '';
let strategyCommandSequence = 0;
let refreshSequence = 0;
function syncStrategyControls() {
  const selected = $('selectedStrategyStock');
  const startButton = $('strategyButton');
  const stopButton = $('killButton');
  if (selected) selected.textContent = '추천 TOP 5는 참고용이며 자동매매 대상은 국내 거래량·등락률 랭킹에서 별도로 찾습니다.';
  if (startButton) {
    const alreadyRunning = currentStrategyStatus.running;
    startButton.disabled = Boolean(pendingStrategyAction) || alreadyRunning;
    startButton.textContent = pendingStrategyAction === 'start' ? '시작 준비 중…' : alreadyRunning ? '자동매매 실행 중' : '자동매매 시작';
  }
  if (stopButton) {
    stopButton.disabled = pendingStrategyAction === 'stop';
    stopButton.textContent = pendingStrategyAction === 'stop' ? '중지 중…' : '자동매매 중지';
  }
}
function selectRecommendation(symbol, name) {
  selectedRecommendationSymbol = symbol;
  selectedRecommendationName = name || symbol;
  document.querySelectorAll('#recommendations .recommend-card').forEach(card => {
    card.classList.toggle('selected', card.querySelector('small')?.textContent.trim() === symbol);
    card.setAttribute('aria-pressed', String(card.classList.contains('selected')));
  });
  syncStrategyControls();
}
let searchTimer;
$('lookupSymbol').addEventListener('input', () => { clearTimeout(searchTimer); const query = $('lookupSymbol').value.trim(); if (!query) { suggestionBox.innerHTML = ''; suggestionBox.style.display = 'none'; return; } searchTimer = setTimeout(async () => { let items = []; try { items = await api(`/api/v1/stocks/search?q=${encodeURIComponent(query)}`); } catch { items = []; } if (!items.length) items = fallbackStocks.filter(item => item.name.includes(query) || item.symbol.includes(query)); suggestionBox.innerHTML = items.map(item => `<button type="button" data-symbol="${item.symbol}"><span><b>${item.name}</b><br><small>${item.symbol} · ${item.market}</small></span><span>›</span></button>`).join(''); suggestionBox.style.display = items.length ? 'block' : 'none'; suggestionBox.querySelectorAll('button').forEach(button => button.onclick = () => { $('lookupSymbol').value = button.dataset.symbol; suggestionBox.innerHTML = ''; suggestionBox.style.display = 'none'; }); }, 300); });
function safeMarketTime(value) { const date = value ? new Date(value) : null; return date && !Number.isNaN(date.getTime()) && date.getFullYear() >= 2000 ? date.toLocaleString('ko-KR') : new Date().toLocaleString('ko-KR') + ' (조회 시각)'; }
async function loadMarketStatus() { try { const items = await api('/api/v1/market-indicators'); const kospi = items.find(item => item.symbol === 'KOSPI'); $('marketStatus').innerHTML = `<span>코스피</span><strong>${kospi ? Number(kospi.lastPrice).toLocaleString('ko-KR', {maximumFractionDigits:2}) : '-'}</strong><small>${kospi ? safeMarketTime(kospi.timestamp) : '데이터 없음'}</small>`; } catch (error) { $('marketStatus').innerHTML = `<span>코스피</span><strong class="error">조회 실패</strong><small>${error.message}</small>`; } }
loadMarketStatus();
// 추천 목록은 일봉 상승률·거래량 기반 동적 API를 사용합니다.
async function loadDynamicRecommendations() {
  const retryButton = $('findRecommendations');
  retryButton.disabled = true;
  retryButton.textContent = '불러오는 중...';
  $('recommendations').textContent = '거래 데이터를 분석하고 있습니다...';
  try {
    const account = await api('/api/v1/account');
    const budget = Number(account.daily_auto_buy_remaining ?? 0);
    const items = await api('/api/v1/recommendations');
    items.forEach(item => { if (item.name) orderStockNames.set(item.symbol, item.name); });
    if (!items.length) throw new Error('분석할 수 있는 종목 데이터가 없습니다.');
    let prices = {};
    try {
      const quotes = await api(`/api/v1/quotes-batch/live?symbols=${items.map(item => item.symbol).join(',')}`);
      prices = Object.fromEntries(quotes.map(q => [q.symbol, Number(q.price)]));
    } catch {
      // 추천 점수 데이터가 있으면 현재가 조회에 실패해도 종목 목록은 표시합니다.
    }
    $('recommendations').innerHTML = items.map((item, index) => {
      const price = prices[item.symbol] || 0;
      const quantity = price ? Math.floor(budget / price) : 0;
      return `<div class="recommend-card" data-price="${price}" role="button" tabindex="0" aria-pressed="false"><div class="recommend-rank">#${index + 1} · ${item.score}점</div><strong>${item.name}</strong><small>${item.symbol}</small><b>${price ? money(price) : '시세 대기 중'}</b><p>등락률 ${item.change_rate}% · 거래량 ${item.volume}배<br><span class="recommend-quantity">${price ? `최대 ${quantity}주 매수 가능` : '현재가 연결 후 수량 계산'}</span></p><span class="subtle">종목 차트 보기 · 추천은 참고용</span></div>`;
    }).join('');
    if (selectedRecommendationSymbol) selectRecommendation(selectedRecommendationSymbol, selectedRecommendationName);
    else if (currentStrategyStatus.running) {
      const activeRecommendation = items.find(item => item.symbol === currentStrategyStatus.symbol);
      if (activeRecommendation) selectRecommendation(activeRecommendation.symbol, activeRecommendation.name);
    }
  } catch (error) {
    $('recommendations').textContent = `추천 종목을 불러오지 못했습니다. ${error.message}`;
  } finally {
    retryButton.disabled = false;
    retryButton.textContent = '후보 찾기';
  }
}
// 동적 추천 API가 점수와 수량을 함께 렌더링하므로 별도 덮어쓰기를 하지 않습니다.
async function showRecommendationChart(symbol, name) { const chart = $('recommendationChart'); chart.innerHTML = '<p>차트를 불러오는 중...</p>'; try { const candles = await api(`/api/v1/candles/${encodeURIComponent(symbol)}?count=30`); if (!candles.length) throw new Error('차트 데이터가 없습니다.'); chart.innerHTML = `<h3>${name} (${symbol}) 최근 거래일 종가</h3><canvas id="recommendationCanvas" height="230"></canvas>`; const canvas = $('recommendationCanvas'); const dpr = window.devicePixelRatio || 1; const width = Math.max(canvas.clientWidth, 320); const height = 230; canvas.width = width * dpr; canvas.height = height * dpr; const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); const values = candles.map(item => Number(item.close_price)).filter(Number.isFinite); const min = Math.min(...values); const max = Math.max(...values); const pad = { left: 82, right: 14, top: 18, bottom: 30 }; const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom; const y = value => pad.top + (max === min ? plotH / 2 : (max - value) / (max - min) * plotH); const x = index => pad.left + (values.length === 1 ? plotW / 2 : index / (values.length - 1) * plotW); ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--border').trim() || '#30405f'; ctx.lineWidth = 1; for (let i = 0; i < 4; i += 1) { const gy = pad.top + i * plotH / 3; ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(width - pad.right, gy); ctx.stroke(); } ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--muted').trim() || '#91a0bd'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right'; for (let i = 0; i < 4; i += 1) { const value = max - (max - min) * i / 3; ctx.fillText(Math.round(value).toLocaleString('ko-KR'), pad.left - 8, pad.top + i * plotH / 3 + 4); } ctx.strokeStyle = '#61a6ff'; ctx.lineWidth = 2.5; ctx.beginPath(); values.forEach((value, index) => { const pointX = x(index); const pointY = y(value); if (index === 0) ctx.moveTo(pointX, pointY); else ctx.lineTo(pointX, pointY); }); ctx.stroke(); ctx.fillStyle = '#61a6ff'; values.forEach((value, index) => { ctx.beginPath(); ctx.arc(x(index), y(value), 2.5, 0, Math.PI * 2); ctx.fill(); }); ctx.globalAlpha = 0.92; candles.forEach((item, index) => { const close = Number(item.close_price); const open = Number(item.open_price ?? close); const high = Number(item.high_price ?? Math.max(open, close)); const low = Number(item.low_price ?? Math.min(open, close)); const candleX = x(index); const step = values.length > 1 ? plotW / (values.length - 1) : plotW; const bodyWidth = Math.max(3, Math.min(10, step * 0.55)); const rising = close >= open; ctx.strokeStyle = rising ? '#ff647c' : '#4f9cff'; ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(candleX, y(high)); ctx.lineTo(candleX, y(low)); ctx.stroke(); const top = Math.min(y(open), y(close)); const bodyHeight = Math.max(2, Math.abs(y(open) - y(close))); ctx.fillRect(candleX - bodyWidth / 2, top, bodyWidth, bodyHeight); }); ctx.globalAlpha = 1; ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--muted').trim() || '#91a0bd'; ctx.textAlign = 'center'; [0, Math.floor((values.length - 1) / 2), values.length - 1].forEach(index => { const date = candles[index]?.date || candles[index]?.trade_date || ''; ctx.fillText(String(date).slice(0, 10), x(index), height - 8); }); } catch (error) { chart.innerHTML = `<p class="chart-error">${error.message || '차트를 불러오지 못했습니다.'}</p>`; } }
document.addEventListener('click', event => { const card = event.target.closest('.recommend-card'); if (!card || event.target.closest('button')) return; const symbol = card.querySelector('small')?.textContent.trim(); const name = card.querySelector('strong')?.textContent.trim() || symbol; if (!symbol) return; selectRecommendation(symbol, name); const chart = $('recommendationChart'); if (chart.dataset.symbol === symbol && chart.querySelector('canvas')) { chart.innerHTML = ''; delete chart.dataset.symbol; return; } chart.dataset.symbol = symbol; showRecommendationChart(symbol, name); });
const money = (value) => `${Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0, minimumFractionDigits: 0 })} 원`;
document.addEventListener('keydown', event => {
  if (event.target.matches('.recommend-card') && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    event.target.click();
  }
});
const message = (id, text, error = false) => { $(id).textContent = text; $(id).className = error ? 'error' : ''; };
const priceHistory = {};
const candleHistory = {};
const latestQuotes = {};
let strategyHelp;
const historyTable = document.createElement('div');
historyTable.className = 'history-table';
document.querySelector('#quoteResult').after(historyTable);
document.querySelector('footer').insertAdjacentHTML('beforebegin', '<section class="grid extra-panels"><article><h2>계좌 요약</h2><div id="accountSummary">계좌 정보를 불러오는 중...</div></article><article class="recommendation-panel"><h2>추천 종목 TOP 5 <button id="findRecommendations" class="secondary">후보찾기</button></h2><p class="subtle">가상매매 후보입니다. 실제 주문은 발생하지 않습니다.</p><div id="recommendations" class="recommendations">목록을 불러오는 중...</div></article></section>');
const recommendationChart = document.createElement('div'); recommendationChart.id = 'recommendationChart'; recommendationChart.className = 'recommendation-chart'; document.querySelector('#recommendations').after(recommendationChart);
$('findRecommendations').addEventListener('click', loadDynamicRecommendations);
loadDynamicRecommendations();
const extraStyle = document.createElement('style'); extraStyle.textContent = '.extra-panels{margin-top:16px}.subtle{color:#91a0bd;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.metrics span{display:block;color:#91a0bd;font-size:12px;margin-bottom:6px}.metrics strong{font-size:18px}.positive{color:#36d29a}.negative{color:#ff6b78}small{color:#91a0bd}@media(max-width:520px){.metrics{grid-template-columns:1fr 1fr}}'; document.head.appendChild(extraStyle);
const recommendationStyle = document.createElement('style'); recommendationStyle.textContent = '.recommendations{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.recommend-card{min-width:0;padding:14px;border:1px solid #30405f;border-radius:12px;background:#18243e;cursor:pointer;transition:.2s}.recommend-card:hover{border-color:#6d91ff;transform:translateY(-2px)}.recommend-rank{color:#36d29a;font-size:11px;font-weight:800}.recommend-card strong{display:block;font-size:15px;margin:9px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.recommend-card small{color:#91a0bd}.recommend-card b{display:block;font-size:18px;margin:14px 0;color:#fff}.recommend-card p{min-height:34px;margin:0 0 10px;color:#91a0bd;font-size:11px}.recommend-card:focus-visible{outline:2px solid #6d91ff;outline-offset:3px}.recommend-card .secondary{float:none;width:100%}.recommendation-chart{margin-top:18px;min-height:20px}.recommendation-chart h3{font-size:14px;margin:0 0 10px}.recommendation-chart canvas{width:100%;height:230px;background:#101a31;border-radius:10px}body.light .recommend-card{background:#fff4f9;border-color:#f1d5e4}body.light .recommend-card b{color:#30233a}body.light .recommendation-chart canvas{background:#fff0f6}@media(max-width:900px){.recommendations{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.recommendations{grid-template-columns:repeat(2,1fr)}}'; document.head.appendChild(recommendationStyle);

function renderHistory(symbol) {
  const candles = candleHistory[symbol] || [];
  if (!candles.length) return;
  historyTable.innerHTML = `<h3>${symbol} 최근 7거래일 시세</h3><table><thead><tr><th>날짜</th><th>시가</th><th>고가</th><th>저가</th><th>종가</th></tr></thead><tbody>${candles.slice().reverse().slice(0, 7).map(c => `<tr><td>${new Date(c.timestamp).toLocaleDateString('ko-KR')}</td><td>${money(c.open_price)}</td><td>${money(c.high_price)}</td><td>${money(c.low_price)}</td><td><strong>${money(c.close_price)}</strong></td></tr>`).join('')}</tbody></table>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || '요청에 실패했습니다.');
  return data;
}

const orderStockNames = new Map();
const orderNameRetryAt = new Map();
const orderNamesPending = new Set();
let latestOrderHistory = [];
const isAutomaticOrder = order => order.source ? order.source === 'AUTO' : /^sma-(buy|sell)-/.test(order.client_order_id || '');
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));

function renderOrderHistory(orders) {
  latestOrderHistory = orders;
  const automaticOrders = orders.filter(isAutomaticOrder).slice().reverse();
  if (!automaticOrders.length) {
    $('orders').innerHTML = '<p class="subtle">아직 자동매매 내역이 없습니다. 매수·매도 체결 시 이곳에 표시됩니다.</p>';
    return;
  }
  const rows = automaticOrders.map(order => {
    const name = order.symbol_name || orderStockNames.get(order.symbol) || '종목명 확인 중';
    const date = new Date(order.created_at);
    const time = Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false });
    const quantity = Number(order.filled_quantity ?? order.quantity);
    const amount = order.total_amount ?? Number(order.price) * quantity;
    const buy = order.side === 'BUY';
    const status = { FILLED: '체결 완료', REJECTED: '주문 거절' }[order.status] || order.status;
    return `<tr><td>${escapeText(time)}</td><td><strong class="trade-stock-name">${escapeText(name)}</strong><small>${escapeText(order.symbol)}</small></td><td><span class="trade-side ${buy ? 'trade-buy' : 'trade-sell'}">${buy ? '매수' : '매도'}</span></td><td class="numeric">${quantity.toLocaleString('ko-KR', { maximumFractionDigits: 8 })}주</td><td class="numeric">${money(order.price)}</td><td class="numeric"><strong>${money(amount)}</strong></td><td>${escapeText(status)}</td></tr>`;
  }).join('');
  $('orders').innerHTML = `<table><thead><tr><th scope="col">체결 시각</th><th scope="col">종목명</th><th scope="col">구분</th><th scope="col" class="numeric">체결 수량</th><th scope="col" class="numeric">체결 단가</th><th scope="col" class="numeric">거래금액</th><th scope="col">상태</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function resolveOrderNames(orders, strategy) {
  if (strategy.symbol_name) orderStockNames.set(strategy.symbol, strategy.symbol_name);
  orders.forEach(order => { if (order.symbol_name) orderStockNames.set(order.symbol, order.symbol_name); });
  const symbols = [...new Set(orders.filter(isAutomaticOrder).map(order => order.symbol))];
  symbols.forEach(async symbol => {
    if (orderStockNames.has(symbol) || orderNamesPending.has(symbol) || Date.now() < (orderNameRetryAt.get(symbol) || 0)) return;
    orderNamesPending.add(symbol);
    try {
      const matches = await api(`/api/v1/stocks/search?q=${encodeURIComponent(symbol)}`);
      const stock = matches.find(item => item.symbol === symbol);
      if (stock?.name) {
        orderStockNames.set(symbol, stock.name);
        renderOrderHistory(latestOrderHistory);
      }
    } catch { /* Keep the trade visible even when stock-name lookup is unavailable. */ }
    finally { orderNamesPending.delete(symbol); orderNameRetryAt.set(symbol, Date.now() + 60000); }
  });
}

function render(account, orders, strategy) {
  currentStrategyStatus = strategy;
  $('cash').textContent = money(account.cash);
  $('positionCount').textContent = account.positions.length;
  $('orderCount').textContent = orders.length;
  syncStrategyControls();
  $('strategyState').textContent = strategy.running ? (strategy.symbol === 'AUTO' ? '시장 스캔 중' : `${strategy.symbol} 실행 중`) : '중지';
  if (!pendingStrategyAction) {
    if (strategy.last_error) message('strategyMessage', strategy.last_error, true);
    else if (strategy.running) {
      const signals = { BUY_VOLUME_MOMENTUM: '상승률·거래량 신호로 매수', SELL_MOMENTUM_FADE: '상승·거래량 신호 약화로 매도', SELL_STOP_LOSS: '손절 기준 도달로 매도', BUDGET_LIMIT: '잔여 한도 부족 · 매수 대기', HOLD_MOMENTUM: '상승·거래량 신호 유지 · 보유', NO_SIGNAL: '조건을 만족하는 종목 탐색 중' };
      const progress = signals[strategy.last_signal] || '시장 랭킹 분석 중';
      message('strategyMessage', `${strategy.symbol_name || strategy.symbol} PAPER 자동매매 · ${progress} · 오늘 사용 ${money(account.daily_auto_buy_used ?? 0)} / 잔여 ${money(account.daily_auto_buy_remaining ?? 0)}`);
    } else message('strategyMessage', '자동매매가 중지되어 있습니다. 시작 버튼을 누르면 시세 분석과 자동 주문을 시작합니다.');
  }
  if (strategyHelp) strategyHelp.textContent = `국내 전체 시장 거래량 상위권과 당일 상승률 1% 이상 종목이 겹칠 때 점수화합니다. ${strategy.poll_interval_seconds || 60}초마다 확인하며, 매수 한도는 하루 시작 시 가용금액의 40%이고 손실 3% 또는 상승·거래량 신호 이탈 시 매도합니다.`;
  $('positions').innerHTML = account.positions.length
    ? `<table><tr><th>종목</th><th>수량</th><th>현재가</th><th>평가손익</th></tr>${account.positions.map(p => { const current = latestQuotes[p.symbol] || Number(p.average_price); const pnl = (current - Number(p.average_price)) * Number(p.quantity); return `<tr><td>${p.symbol}</td><td>${p.quantity}</td><td>${money(current)}</td><td class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}${money(pnl)}</td></tr>`; }).join('')}</table>`
    : '없음';
  resolveOrderNames(orders, strategy);
  renderOrderHistory(orders);
  const positionValue = account.positions.reduce((total, position) => total + Number(position.quantity) * (latestQuotes[position.symbol] || Number(position.average_price)), 0);
  const totalValue = Number(account.cash) + positionValue;
  const pnl = totalValue - Number(account.initial_cash);
  const recommendedAmount = Number(account.daily_auto_buy_limit ?? 0);
  const returnRate = Number(account.initial_cash) > 0 ? pnl / Number(account.initial_cash) * 100 : 0;
  $('accountSummary').innerHTML = `<div class="metrics"><div><span>가용계좌 금액</span><strong>${money(account.cash)}</strong></div><div title="하루 첫 자동매매 시작 시 가용금액의 40%로 확정되는 일일 매수 한도"><span>하루 추천 사용금액(40%)</span><strong>${money(recommendedAmount)}</strong></div><div><span>평가손익</span><strong class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}${money(pnl)}</strong></div><div><span>수익률</span><strong class="${pnl >= 0 ? 'positive' : 'negative'}">${returnRate.toFixed(2)}%</strong></div></div>`;
  document.querySelectorAll('#recommendations .recommend-card').forEach(card => {
    const price = Number(card.dataset.price || 0);
    const quantity = price > 0 ? Math.max(0, Math.floor(Number(account.daily_auto_buy_remaining ?? 0) / price)) : 0;
    const label = card.querySelector('.recommend-quantity');
    if (label) label.textContent = price > 0 ? `최대 ${quantity}주 매수 가능` : '현재가 연결 후 수량 계산';
  });
}


async function refresh() {
  const request = ++refreshSequence;
  const command = strategyCommandSequence;
  const [account, orders, strategy] = await Promise.all([api('/api/v1/account'), api('/api/v1/orders'), api('/api/v1/strategies/status')]);
  await Promise.all(account.positions.map(async (position) => {
    try {
      const quote = await api(`/api/v1/quotes/${encodeURIComponent(position.symbol)}`);
      latestQuotes[position.symbol] = Number(quote.price);
    } catch {}
  }));
  if (request === refreshSequence && command === strategyCommandSequence) render(account, orders, strategy);
}

let liveTimer = null;
async function loadLiveQuote() {
  const symbol = $('lookupSymbol').value.trim();
  try {
    const quotes = await api(`/api/v1/quotes-batch/live?symbols=${encodeURIComponent(symbol)}`);
    for (const quote of quotes) {
      latestQuotes[quote.symbol] = Number(quote.price);
      if (!priceHistory[quote.symbol] || priceHistory[quote.symbol].length < 2) {
        const candles = await api(`/api/v1/candles/${encodeURIComponent(quote.symbol)}?count=60`);
        candleHistory[quote.symbol] = candles;
        priceHistory[quote.symbol] = candles.map(candle => Number(candle.close_price));
      } else {
        priceHistory[quote.symbol].push(Number(quote.price));
        priceHistory[quote.symbol] = priceHistory[quote.symbol].slice(-60);
      }
    }
    renderHistory(quotes[0].symbol);
    await refresh();
    $('quoteResult').innerHTML = `<p class="quote-complete">조회 완료</p><table class="quote-table"><thead><tr><th>종목번호</th><th>주식명</th><th>현재가</th><th>통화</th></tr></thead><tbody>${quotes.map(quote => `<tr><td><strong>${quote.symbol}</strong></td><td>${quote.name || '종목명 없음'}</td><td class="quote-price">${money(quote.price)}</td><td>${quote.currency || 'KRW'}</td></tr>`).join('')}</tbody></table>`;
  } catch (error) {
    $('quoteResult').textContent = error.message;
  }
}

$('quoteLookupForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  await loadLiveQuote();
  if (liveTimer) clearInterval(liveTimer);
  liveTimer = setInterval(loadLiveQuote, 5000);
});
$('lookupSymbol').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); $('quoteLookupForm').requestSubmit(); } });

$('refreshButton').onclick = refresh;
refresh().catch(error => message('strategyMessage', error.message, true));
document.querySelector('#strategyButton').textContent = '자동매매 시작';
document.querySelector('#killButton').textContent = '자동매매 중지';
strategyHelp = $('strategyHelp');
const strategyStyle = document.createElement('style');
strategyStyle.textContent = '.selected-strategy-stock{margin:10px 0;color:#91a0bd;font-size:13px}.recommend-card.selected{border-color:#6d91ff;box-shadow:0 0 0 2px #6d91ff55}body.light .recommend-card.selected{border-color:#d74c83;box-shadow:0 0 0 2px #d74c8355}button:disabled{opacity:.5;cursor:not-allowed;transform:none}';
document.head.appendChild(strategyStyle);
const selectedStrategyStock = document.createElement('p');
selectedStrategyStock.id = 'selectedStrategyStock';
selectedStrategyStock.className = 'selected-strategy-stock';
document.querySelector('#strategyButton').before(selectedStrategyStock);
syncStrategyControls();
document.querySelector('#strategyButton').onclick = async () => {
  if (pendingStrategyAction) return;
  const command = ++strategyCommandSequence;
  pendingStrategyAction = 'start';
  syncStrategyControls();
  message('strategyMessage', '추천 종목과 시세 연결을 확인하고 자동매매를 준비하고 있습니다…');
  try {
    const status = await api('/api/v1/strategies/sma/start', { method: 'POST' });
    if (command !== strategyCommandSequence) return;
    currentStrategyStatus = status;
    pendingStrategyAction = '';
    syncStrategyControls();
    message('strategyMessage', '국내 전체 시장의 상승률·거래량 상위 후보를 분석해 PAPER 자동매매를 시작했습니다.');
    await refresh();
  } catch (error) { if (command === strategyCommandSequence) message('strategyMessage', error.message, true); }
  finally {
    if (command === strategyCommandSequence) { pendingStrategyAction = ''; syncStrategyControls(); }
  }
};
strategyHelp.textContent = '추천 종목은 참고용입니다. 자동매매는 국내 전체 시장의 상승률·거래량 상위 후보를 분석하며, 하루 매수 한도는 가용금액의 40%입니다.';
document.querySelector('#killButton').onclick = async () => {
  if (pendingStrategyAction === 'stop') return;
  const command = ++strategyCommandSequence;
  pendingStrategyAction = 'stop';
  syncStrategyControls();
  message('strategyMessage', '자동매매를 중지하고 있습니다…');
  try {
    currentStrategyStatus = await api('/api/v1/strategies/sma/stop', { method: 'POST' });
    pendingStrategyAction = '';
    syncStrategyControls();
    message('strategyMessage', '자동매매를 중지했습니다. 보유 주식은 유지됩니다.');
    await refresh();
  } catch (error) { message('strategyMessage', error.message, true); }
  finally {
    if (command === strategyCommandSequence) { pendingStrategyAction = ''; syncStrategyControls(); }
  }
};
setInterval(async () => {
  try { await refresh(); } catch (error) { message('strategyMessage', `상태 확인 실패: ${error.message}`, true); }
}, 5000);
