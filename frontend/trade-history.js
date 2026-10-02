const historyOrders = document.getElementById('historyOrders');
const historyCount = document.getElementById('historyCount');
const historyMessage = document.getElementById('historyMessage');
const historyRefreshButton = document.getElementById('historyRefreshButton');
document.body.classList.toggle('light', localStorage.getItem('theme') === 'light');
let historyLoading = false;

async function refreshHistory() {
  if (historyLoading) return;
  historyLoading = true;
  historyRefreshButton.disabled = true;
  historyOrders.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/v1/orders');
    if (!response.ok) throw new Error('매매내역을 불러오지 못했습니다. 새로고침해 주세요.');
    const orders = await response.json();
    if (!Array.isArray(orders)) throw new Error('매매내역 응답을 확인할 수 없습니다. 새로고침해 주세요.');
    historyOrders.innerHTML = orderHistoryTable(orders);
    historyCount.textContent = `전체 ${orders.length.toLocaleString('ko-KR')}건 · 최신 매매순`;
    historyMessage.classList.remove('error');
    historyMessage.textContent = `${new Date().toLocaleTimeString('ko-KR')} 갱신`;
  } catch (error) {
    if (!historyOrders.innerHTML) historyCount.textContent = '매매내역 조회 실패';
    historyMessage.classList.add('error');
    historyMessage.textContent = error.message;
  } finally {
    historyLoading = false;
    historyRefreshButton.disabled = false;
    historyOrders.setAttribute('aria-busy', 'false');
  }
}

historyRefreshButton.addEventListener('click', refreshHistory);
refreshHistory();
setInterval(refreshHistory, 30000);
