from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from dotenv import load_dotenv

from .models import Candle, Quote

load_dotenv()


class TossApiError(RuntimeError):
    pass


class TossClient:
    """토스증권 현재가 조회 클라이언트. 주문 API는 아직 호출하지 않는다."""

    def __init__(self) -> None:
        self.base_url = os.getenv("TOSS_API_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")
        self.client_id = os.getenv("TOSS_CLIENT_ID", "")
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET", "")
        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._stock_cache: list[dict] = []
        self._stock_cache_at = datetime.min.replace(tzinfo=timezone.utc)
        self._token_lock = asyncio.Lock()

    async def _request(self, method: str, path: str, *, timeout: float = 10, **kwargs) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.RequestError as exc:
            raise TossApiError(
                "Toss API 연결에 실패했습니다. 인터넷 연결과 TOSS_API_BASE_URL 설정을 확인하세요."
            ) from exc

    async def _access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise TossApiError("TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET 설정이 필요합니다.")
        async with self._token_lock:
            now = datetime.now(timezone.utc)
            if self._token and now < self._expires_at:
                return self._token
            response = await self._request(
                "POST",
                "/oauth2/token",
                data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            )
        if response.status_code >= 400:
            raise TossApiError(f"토큰 발급 실패: HTTP {response.status_code}")
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = now + timedelta(seconds=max(30, int(payload.get("expires_in", 3600)) - 60))
        return self._token

    async def quote(self, symbol: str) -> Quote:
        token = await self._access_token()
        response = await self._request("GET", "/api/v1/prices", params={"symbols": symbol}, headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise TossApiError(f"현재가 조회 실패: HTTP {response.status_code}")
        result = response.json().get("result", [])
        if not result:
            raise TossApiError("종목 현재가를 찾을 수 없습니다.")
        item = result[0]
        return Quote(symbol=item["symbol"], price=Decimal(str(item["lastPrice"])), timestamp=datetime.fromisoformat(item["timestamp"]))

    async def stock_names(self, symbols: list[str]) -> dict[str, str]:
        token = await self._access_token()
        response = await self._request("GET", "/api/v1/stocks", params={"symbols": ",".join(symbols)}, headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            return {}
        items = response.json().get("result", [])
        names: dict[str, str] = {}
        for item in items:
            symbol = item.get("symbol")
            name = item.get("name") or item.get("stockName") or item.get("displayName")
            if symbol and name:
                names[symbol] = name
        return names

    async def search_stocks(self, query: str) -> list[dict]:
        token = await self._access_token()
        now = datetime.now(timezone.utc)
        if not self._stock_cache or now - self._stock_cache_at > timedelta(hours=24):
            results: list[dict] = []
            for market in ("KOSPI", "KOSDAQ"):
                response = await self._request("GET", "/api/v1/stocks", timeout=20, params={"market": market, "status": "ACTIVE"}, headers={"Authorization": f"Bearer {token}"})
                if response.status_code >= 400:
                    raise TossApiError(f"{market} 종목 목록 조회 실패: HTTP {response.status_code}")
                for item in response.json().get("result", []):
                    results.append({"symbol": item.get("symbol", ""), "name": item.get("name", ""), "market": market})
            self._stock_cache = results
            self._stock_cache_at = now
        query_lower = query.lower()
        query_upper = query.upper()
        return [item for item in self._stock_cache if query_lower in item["name"].lower() or query_upper in item["symbol"].upper()][:20]

    async def candles(self, symbol: str, count: int = 60) -> list[Candle]:
        token = await self._access_token()
        response = await self._request("GET", "/api/v1/candles", params={"symbol": symbol, "interval": "1d", "count": min(count, 200)}, headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise TossApiError(f"캔들 조회 실패: HTTP {response.status_code}")
        items = response.json().get("result", {}).get("candles", [])
        return [Candle(symbol=symbol, timestamp=datetime.fromisoformat(item["timestamp"]), close_price=Decimal(str(item["closePrice"])), open_price=Decimal(str(item["openPrice"])), high_price=Decimal(str(item["highPrice"])), low_price=Decimal(str(item["lowPrice"])), volume=Decimal(str(item.get("volume", 0)))) for item in reversed(items)]

    async def rankings(self, ranking_type: str, duration: str = "realtime", count: int = 100) -> list[dict]:
        """Return a market-wide Korean ranking from Toss OpenAPI."""
        token = await self._access_token()
        response = await self._request(
            "GET",
            "/api/v1/rankings",
            params={
                "type": ranking_type,
                "marketCountry": "KR",
                "duration": duration,
                "excludeInvestmentCaution": "true",
                "count": min(max(count, 1), 100),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code >= 400:
            raise TossApiError(f"주식 랭킹 조회 실패: HTTP {response.status_code}")
        return response.json().get("result", {}).get("rankings", [])

    async def market_prices(self, symbols: str = "KOSPI,KOSDAQ") -> list[dict]:
        token = await self._access_token()
        response = await self._request("GET", "/api/v1/market-indicators/prices", params={"symbols": symbols}, headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise TossApiError(f"시장지표 조회 실패: HTTP {response.status_code}")
        return response.json().get("result", [])
