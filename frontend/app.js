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
const recommendedStocks = [{name:'삼성전자',symbol:'005930'},{name:'SK하이닉스',symbol:'000660'},{name:'NAVER',symbol:'035420'},{name:'현대차',symbol:'005380'},{name:'카카오',symbol:'035720'}];
let searchTimer;
$('lookupSymbol').addEventListener('input', () => { clearTimeout(searchTimer); const query = $('lookupSymbol').value.trim(); if (!query) { suggestionBox.innerHTML = ''; suggestionBox.style.display = 'none'; return; } searchTimer = setTimeout(async () => { let items = []; try { items = await api(`/api/v1/stocks/search?q=${encodeURIComponent(query)}`); } catch { items = []; } if (!items.length) items = fallbackStocks.filter(item => item.name.includes(query) || item.symbol.includes(query)); suggestionBox.innerHTML = items.map(item => `<button type="button" data-symbol="${item.symbol}"><span><b>${item.name}</b><br><small>${item.symbol} · ${item.market}</small></span><span>›</span></button>`).join(''); suggestionBox.style.display = items.length ? 'block' : 'none'; suggestionBox.querySelectorAll('button').forEach(button => button.onclick = () => { $('lookupSymbol').value = button.dataset.symbol; suggestionBox.innerHTML = ''; suggestionBox.style.display = 'none'; }); }, 300); });
function safeMarketTime(value) { const date = value ? new Date(value) : null; return date && !Number.isNaN(date.getTime()) && date.getFullYear() >= 2000 ? date.toLocaleString('ko-KR') : new Date().toLocaleString('ko-KR') + ' (조회 시각)'; }
async function loadMarketStatus() { try { const items = await api('/api/v1/market-indicators'); const kospi = items.find(item => item.symbol === 'KOSPI'); $('marketStatus').innerHTML = `<span>코스피</span><strong>${kospi ? Number(kospi.lastPrice).toLocaleString('ko-KR', {maximumFractionDigits:2}) : '-'}</strong><small>${kospi ? safeMarketTime(kospi.timestamp) : '데이터 없음'}</small>`; } catch (error) { $('marketStatus').innerHTML = `<span>코스피</span><strong class="error">조회 실패</strong><small>${error.message}</small>`; } }
loadMarketStatus();
async function loadRecommendations() { try { const account = await api('/api/v1/account'); const budget = Number(account.initial_cash) * 0.4; const quotes = await api(`/api/v1/quotes-batch/live?symbols=${recommendedStocks.map(stock => stock.symbol).join(',')}`); const quoteMap = Object.fromEntries(quotes.map(quote => [quote.symbol, quote])); $('recommendations').innerHTML = recommendedStocks.map((stock, index) => { const quote = quoteMap[stock.symbol]; const price = quote ? Number(quote.price) : 0; const quantity = price ? Math.max(1, Math.floor(budget / 5 / price)) : 0; return `<div class="recommend-card"><div class="recommend-rank">#${index + 1} · 참고</div><strong>${stock.name}</strong><small>${stock.symbol}</small><b>${price ? money(price) : '시세 없음'}</b><p>추천금액 기준 약 ${quantity}주</p></div>`; }).join(''); } catch (error) { $('recommendations').textContent = error.message; } }
// 추천 목록은 일봉 상승률·거래량 기반 동적 API를 사용합니다.
async function loadDynamicRecommendations() {
  const retryButton = $('findRecommendations');
  retryButton.disabled = true;
  retryButton.textContent = '불러오는 중...';
  $('recommendations').textContent = '거래 데이터를 분석하고 있습니다...';
  try {
    const account = await api('/api/v1/account');
    const budget = Number(account.initial_cash) * 0.4;
    const items = await api('/api/v1/recommendations');
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
      return `<div class="recommend-card"><div class="recommend-rank">#${index + 1} · ${item.score}점</div><strong>${item.name}</strong><small>${item.symbol}</small><b>${price ? money(price) : '시세 대기 중'}</b><p>등락률 ${item.change_rate}% · 거래량 ${item.volume}배<br>${price ? `최대 ${quantity}주 매수 가능` : '현재가 연결 후 수량 계산'}</p><button class="recommend-buy" data-symbol="${item.symbol}" data-quantity="${quantity}" ${price ? '' : 'disabled'}>PAPER 매수</button></div>`;
    }).join('');
    document.querySelectorAll('#recommendations .recommend-card').forEach(card => {
      const symbol = card.querySelector('small')?.textContent.trim();
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'recommend-auto-start';
      button.dataset.symbol = symbol;
      button.textContent = '자동매매 시작';
      card.append(button);
    });
  } catch (error) {
    $('recommendations').textContent = `추천 종목을 불러오지 못했습니다. ${error.message}`;
  } finally {
    retryButton.disabled = false;
    retryButton.textContent = '후보 찾기';
  }
}
document.addEventListener('click', async (event) => {
  const button = event.target.closest('.recommend-auto-start');
  if (!button || button.disabled) return;
  event.stopImmediatePropagation();
  const symbol = button.dataset.symbol;
  button.disabled = true;
  button.textContent = '시작 요청 중...';
  try {
    await api(`/api/v1/strategies/sma/start?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' });
    message('strategyMessage', `${symbol} 자동매매를 시작했습니다. 전략 상태를 확인 중입니다.`);
    await refresh();
  } catch (error) {
    message('strategyMessage', error.message, true);
    button.disabled = false;
    button.textContent = '다시 시도';
  }
});
async function refreshRecommendationQuantities() { try { const account = await api('/api/v1/account'); const budget = Number(account.initial_cash) * 0.4; const quotes = await api(`/api/v1/quotes-batch/live?symbols=${recommendedStocks.map(stock => stock.symbol).join(',')}`); const quoteMap = Object.fromEntries(quotes.map(q => [q.symbol, q])); document.querySelectorAll('.recommend-card').forEach((card, index) => { const stock = recommendedStocks[index]; const price = Number(quoteMap[stock.symbol]?.price || 0); const quantity = price ? Math.floor(budget / price) : 0; const text = card.querySelector('p'); if (text) text.innerHTML = `추천 사용금액 ${money(budget)}<br>최대 ${quantity}주 매수 가능`; const button = card.querySelector('.recommend-buy'); if (button) button.dataset.quantity = String(quantity); }); } catch {} }
// 동적 추천 API가 점수와 수량을 함께 렌더링하므로 별도 덮어쓰기를 하지 않습니다.
setTimeout(() => { document.querySelectorAll('.recommend-card').forEach(card => { const button = card.querySelector('.recommend-buy'); const text = card.querySelector('p'); if (button && text) text.textContent = `최대 ${button.dataset.quantity || 0}주 매수 가능`; }); }, 2500);
setTimeout(() => { document.querySelectorAll('.recommend-card').forEach((card, index) => { if (!card.querySelector('.recommend-buy')) { const button = document.createElement('button'); button.className = 'recommend-buy'; button.textContent = 'PAPER 매수'; button.dataset.symbol = recommendedStocks[index].symbol; button.dataset.quantity = '1'; card.appendChild(button); } }); }, 1200);
document.addEventListener('click', async (event) => { const button = event.target.closest('.recommend-buy'); if (!button) return; try { const symbol = button.dataset.symbol; const quantity = button.dataset.quantity; const quotes = await api(`/api/v1/quotes-batch/live?symbols=${symbol}`); await api('/api/v1/quotes', { method: 'POST', body: JSON.stringify({ symbol, price: String(quotes[0].price) }) }); await api('/api/v1/orders', { method: 'POST', body: JSON.stringify({ symbol, side: 'BUY', quantity, client_order_id: `recommend-${symbol}-${Date.now()}` }) }); button.textContent = '매수 완료'; await refresh(); } catch (error) { button.textContent = '시세 조회 후 매수'; } });
async function showRecommendationChart(symbol, name) { const chart = $('recommendationChart'); chart.innerHTML = '<p>차트를 불러오는 중...</p>'; try { const candles = await api(`/api/v1/candles/${encodeURIComponent(symbol)}?count=30`); if (!candles.length) throw new Error('차트 데이터가 없습니다.'); chart.innerHTML = `<h3>${name} (${symbol}) 최근 거래일 종가</h3><canvas id="recommendationCanvas" height="230"></canvas>`; const canvas = $('recommendationCanvas'); const dpr = window.devicePixelRatio || 1; const width = Math.max(canvas.clientWidth, 320); const height = 230; canvas.width = width * dpr; canvas.height = height * dpr; const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); const values = candles.map(item => Number(item.close_price)).filter(Number.isFinite); const min = Math.min(...values); const max = Math.max(...values); const pad = { left: 82, right: 14, top: 18, bottom: 30 }; const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom; const y = value => pad.top + (max === min ? plotH / 2 : (max - value) / (max - min) * plotH); const x = index => pad.left + (values.length === 1 ? plotW / 2 : index / (values.length - 1) * plotW); ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--border').trim() || '#30405f'; ctx.lineWidth = 1; for (let i = 0; i < 4; i += 1) { const gy = pad.top + i * plotH / 3; ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(width - pad.right, gy); ctx.stroke(); } ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--muted').trim() || '#91a0bd'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right'; for (let i = 0; i < 4; i += 1) { const value = max - (max - min) * i / 3; ctx.fillText(Math.round(value).toLocaleString('ko-KR'), pad.left - 8, pad.top + i * plotH / 3 + 4); } ctx.strokeStyle = '#61a6ff'; ctx.lineWidth = 2.5; ctx.beginPath(); values.forEach((value, index) => { const pointX = x(index); const pointY = y(value); if (index === 0) ctx.moveTo(pointX, pointY); else ctx.lineTo(pointX, pointY); }); ctx.stroke(); ctx.fillStyle = '#61a6ff'; values.forEach((value, index) => { ctx.beginPath(); ctx.arc(x(index), y(value), 2.5, 0, Math.PI * 2); ctx.fill(); }); ctx.globalAlpha = 0.92; candles.forEach((item, index) => { const close = Number(item.close_price); const open = Number(item.open_price ?? close); const high = Number(item.high_price ?? Math.max(open, close)); const low = Number(item.low_price ?? Math.min(open, close)); const candleX = x(index); const step = values.length > 1 ? plotW / (values.length - 1) : plotW; const bodyWidth = Math.max(3, Math.min(10, step * 0.55)); const rising = close >= open; ctx.strokeStyle = rising ? '#ff647c' : '#4f9cff'; ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(candleX, y(high)); ctx.lineTo(candleX, y(low)); ctx.stroke(); const top = Math.min(y(open), y(close)); const bodyHeight = Math.max(2, Math.abs(y(open) - y(close))); ctx.fillRect(candleX - bodyWidth / 2, top, bodyWidth, bodyHeight); }); ctx.globalAlpha = 1; ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--muted').trim() || '#91a0bd'; ctx.textAlign = 'center'; [0, Math.floor((values.length - 1) / 2), values.length - 1].forEach(index => { const date = candles[index]?.date || candles[index]?.trade_date || ''; ctx.fillText(String(date).slice(0, 10), x(index), height - 8); }); } catch (error) { chart.innerHTML = `<p class="chart-error">${error.message || '차트를 불러오지 못했습니다.'}</p>`; } }
document.addEventListener('click', event => { const card = event.target.closest('.recommend-card'); if (!card || event.target.closest('.recommend-buy')) return; const symbol = card.querySelector('small')?.textContent.trim(); const name = card.querySelector('strong')?.textContent.trim() || symbol; const chart = $('recommendationChart'); if (symbol && chart.dataset.symbol === symbol && chart.querySelector('canvas')) { chart.innerHTML = ''; delete chart.dataset.symbol; return; } if (symbol) { chart.dataset.symbol = symbol; showRecommendationChart(symbol, name); } });
const money = (value) => `${Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0, minimumFractionDigits: 0 })} 원`;
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
const recommendationStyle = document.createElement('style'); recommendationStyle.textContent = '.recommendations{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.recommend-card{min-width:0;padding:14px;border:1px solid #30405f;border-radius:12px;background:#18243e;cursor:pointer;transition:.2s}.recommend-card:hover{border-color:#6d91ff;transform:translateY(-2px)}.recommend-rank{color:#36d29a;font-size:11px;font-weight:800}.recommend-card strong{display:block;font-size:15px;margin:9px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.recommend-card small{color:#91a0bd}.recommend-card b{display:block;font-size:18px;margin:14px 0;color:#fff}.recommend-card p{min-height:34px;margin:0 0 10px;color:#91a0bd;font-size:11px}.recommend-buy{width:100%;height:36px;padding:0;font-size:11px}.recommend-card .secondary{float:none;width:100%}.recommendation-chart{margin-top:18px;min-height:20px}.recommendation-chart h3{font-size:14px;margin:0 0 10px}.recommendation-chart canvas{width:100%;height:230px;background:#101a31;border-radius:10px}body.light .recommend-card{background:#fff4f9;border-color:#f1d5e4}body.light .recommend-card b{color:#30233a}body.light .recommendation-chart canvas{background:#fff0f6}@media(max-width:900px){.recommendations{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.recommendations{grid-template-columns:repeat(2,1fr)}}'; document.head.appendChild(recommendationStyle);

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

function render(account, orders, strategy) {
  $('cash').textContent = money(account.cash);
  $('positionCount').textContent = account.positions.length;
  $('orderCount').textContent = orders.length;
  document.querySelectorAll('.recommend-auto-start').forEach(button => {
    const active = strategy.running && strategy.symbol === button.dataset.symbol;
    button.textContent = active ? '자동매매 실행 중' : strategy.running ? '이 종목으로 변경' : '자동매매 시작';
    button.disabled = active;
  });
  $('strategyState').textContent = strategy.running ? `${strategy.symbol} 실행 중` : '중지';
  if (strategyHelp) strategyHelp.textContent = `PAPER 자동매매: ${strategy.poll_interval_seconds || 60}초마다 현재가를 확인합니다. 최근 3회 평균이 5회 평균보다 높으면 1주 매수하고, 낮으면 보유량을 매도합니다.`;
  if (strategy.last_error) message('strategyMessage', strategy.last_error, true);
  else if (strategy.running) message('strategyMessage', `${strategy.symbol} PAPER 자동매매 · 시세 샘플 ${strategy.price_samples}/5`);
  $('strategyState').textContent = strategy.running ? '실행 중' : '중지';
  $('strategyState').textContent = strategy.running ? `${strategy.symbol} 실행 중` : '중지';
  if (strategy.last_error) message('strategyMessage', strategy.last_error, true);
  else if (strategy.running) message('strategyMessage', `${strategy.symbol} PAPER 자동매매 · 시세 샘플 ${strategy.price_samples}/5`);
  if (strategyHelp) strategyHelp.textContent = `추천 종목 카드에서 선택하세요. PAPER 자동매매는 ${strategy.poll_interval_seconds || 60}초마다 시세를 확인해 3회 평균과 5회 평균을 비교합니다.`;
  $('positions').innerHTML = account.positions.length
    ? `<table><tr><th>종목</th><th>수량</th><th>현재가</th><th>평가손익</th></tr>${account.positions.map(p => { const current = latestQuotes[p.symbol] || Number(p.average_price); const pnl = (current - Number(p.average_price)) * Number(p.quantity); return `<tr><td>${p.symbol}</td><td>${p.quantity}</td><td>${money(current)}</td><td class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}${money(pnl)}</td></tr>`; }).join('')}</table>`
    : '없음';
  $('orders').innerHTML = orders.length
    ? `<table><tr><th>종목</th><th>구분</th><th>수량</th><th>가격</th><th>상태</th></tr>${orders.slice().reverse().map(o => `<tr><td>${o.symbol}</td><td>${o.side === 'BUY' ? '매수' : '매도'}</td><td>${o.quantity}</td><td>${money(o.price)}</td><td>${o.status}</td></tr>`).join('')}</table>`
    : '없음';
  const positionValue = account.positions.reduce((total, position) => total + Number(position.quantity) * (latestQuotes[position.symbol] || Number(position.average_price)), 0);
  const totalValue = Number(account.cash) + positionValue;
  const pnl = totalValue - Number(account.initial_cash);
  const recommendedAmount = Number(account.initial_cash) * 0.4;
  $('accountSummary').innerHTML = `<div class="metrics"><div><span>가상계좌 금액</span><strong>${money(account.initial_cash)}</strong></div><div><span>추천 사용금액 (40%)</span><strong>${money(recommendedAmount)}</strong></div><div><span>총 평가금액</span><strong>${money(totalValue)}</strong></div><div><span>가용 현금</span><strong>${money(account.cash)}</strong></div><div><span>평가손익</span><strong class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}${money(pnl)}</strong></div><div><span>수익률</span><strong class="${pnl >= 0 ? 'positive' : 'negative'}">${(pnl / Number(account.initial_cash) * 100).toFixed(2)}%</strong></div></div>`;
}


async function refresh() {
  const [account, orders, strategy] = await Promise.all([api('/api/v1/account'), api('/api/v1/orders'), api('/api/v1/strategies/status')]);
  await Promise.all(account.positions.map(async (position) => {
    try {
      const quote = await api(`/api/v1/quotes/${encodeURIComponent(position.symbol)}`);
      latestQuotes[position.symbol] = Number(quote.price);
    } catch {}
  }));
  render(account, orders, strategy);
}

let liveTimer = null;
async function loadLiveQuote() {
  const symbol = $('lookupSymbol').value.trim();
  try {
    const quotes = await api(`/api/v1/quotes-batch/live?symbols=${encodeURIComponent(symbol)}`);
    for (const quote of quotes) {
      latestQuotes[quote.symbol] = Number(quote.price);
      // 실시간 가격을 PAPER 주문 엔진에도 반영해 조회 직후 주문할 수 있게 한다.
      await api('/api/v1/quotes', { method: 'POST', body: JSON.stringify({ symbol: quote.symbol, price: String(quote.price) }) });
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

$('orderForm').addEventListener('submit', async (event) => { event.preventDefault(); try { const order = await api('/api/v1/orders', { method: 'POST', body: JSON.stringify({ symbol: $('orderSymbol').value, side: $('side').value, quantity: $('quantity').value }) }); message('orderMessage', `${order.side === 'BUY' ? '매수' : '매도'} 체결 완료`); await refresh(); } catch (error) { message('orderMessage', error.message, true); } });
$('strategyButton').onclick = async () => { try { const symbol = $('lookupSymbol').value.split(',')[0].trim(); const result = await api(`/api/v1/strategies/sma/start?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' }); message('strategyMessage', result.last_signal ? `${result.last_signal} 신호 발생` : '시세 데이터 5개가 필요합니다.'); await refresh(); } catch (error) { message('strategyMessage', error.message, true); } };
$('killButton').onclick = async () => { await api('/api/v1/system/kill-switch', { method: 'POST' }); message('strategyMessage', '전략을 중지했습니다.'); await refresh(); };
$('refreshButton').onclick = refresh;
refresh().catch(error => message('strategyMessage', error.message, true));
const strategySymbolInput = document.createElement('input');
strategySymbolInput.id = 'strategySymbol';
strategySymbolInput.value = '005930';
strategySymbolInput.maxLength = 20;
strategySymbolInput.placeholder = '종목코드';
strategySymbolInput.setAttribute('aria-label', '자동매매 종목코드');
const strategyInputLabel = document.createElement('label');
strategyInputLabel.className = 'strategy-symbol-label';
strategyInputLabel.textContent = '종목코드';
strategyInputLabel.append(strategySymbolInput);
const strategyControls = document.createElement('div');
strategyControls.className = 'strategy-controls';
strategyControls.append(strategyInputLabel);
document.querySelector('#strategyButton').before(strategyControls);
document.querySelector('#strategyButton').textContent = '자동매매 시작';
document.querySelector('#killButton').textContent = '중지 / Kill switch';
strategyHelp = document.createElement('p');
strategyHelp.className = 'subtle';
strategyHelp.textContent = 'PAPER 자동매매: 60초마다 현재가를 확인합니다. 최근 3회 평균이 5회 평균보다 높으면 1주 매수하고, 낮으면 보유량을 매도합니다.';
document.querySelector('#strategyMessage').before(strategyHelp);
const strategyStyle = document.createElement('style');
strategyStyle.textContent = '.strategy-controls{display:flex;align-items:center;margin:8px 0}.strategy-symbol-label{display:flex;align-items:center;gap:8px;color:#91a0bd;font-size:12px}.strategy-controls input{width:150px}.strategy-help{font-size:12px;line-height:1.6}button:disabled{opacity:.5;cursor:not-allowed;transform:none}';
document.head.appendChild(strategyStyle);
document.querySelector('#strategyButton').onclick = async () => {
  try {
    const symbol = strategySymbolInput.value.trim();
    if (!symbol) throw new Error('자동매매 종목코드를 입력하세요.');
    await api(`/api/v1/strategies/sma/start?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' });
    message('strategyMessage', `${symbol} PAPER 자동매매를 시작했습니다.`);
    await refresh();
  } catch (error) { message('strategyMessage', error.message, true); }
};
strategyControls.remove();
document.querySelector('#strategyButton').remove();
strategyHelp.textContent = '추천 종목 카드에서 자동매매할 종목을 선택하세요. PAPER 모드에서만 주문합니다.';
document.querySelector('#killButton').onclick = async () => {
  try {
    await api('/api/v1/system/kill-switch', { method: 'POST' });
    message('strategyMessage', '자동매매를 중지했습니다.');
    await refresh();
  } catch (error) { message('strategyMessage', error.message, true); }
};
setInterval(async () => {
  try { const status = await api('/api/v1/strategies/status'); if (status.running) await refresh(); } catch {}
}, 5000);
const autoRecommendationStyle = document.createElement('style');
autoRecommendationStyle.textContent = '.recommend-auto-start{width:100%;height:34px;margin-top:7px;padding:0 8px;background:#263758;color:#c6d7ff;border:1px solid #40547b;box-shadow:none;font-size:11px}.recommend-auto-start:hover{background:#31466f}.recommend-auto-start:disabled{opacity:.65;cursor:default}body.light .recommend-auto-start{background:#fff0f6;color:#8b4265;border-color:#e8b8cf}';
document.head.appendChild(autoRecommendationStyle);
