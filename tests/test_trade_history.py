from fastapi.testclient import TestClient

from app.main import app


def test_trade_history_navigation_and_resources_are_served():
    client = TestClient(app)
    dashboard = client.get("/")
    assert 'href="/trade-history"' in dashboard.text
    assert '>매매내역 보기</span>' in dashboard.text
    history = client.get("/trade-history")
    assert history.status_code == 200
    assert "전체 매매내역" in history.text
    assert 'href="/"' in history.text
    assert '>대시보드로 돌아가기</span>' in history.text
    assert '<script src="/app.js">' not in history.text
    for script in ("/order-history.js", "/trade-history.js"):
        assert f'src="{script}"' in history.text
        response = client.get(script)
        assert response.status_code == 200
        assert "text/javascript" in response.headers["content-type"]
