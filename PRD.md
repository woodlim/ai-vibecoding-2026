# 토스증권 자동매매 시스템 PRD

## 1. 목표

Python과 FastAPI로 토스증권 Open API를 연동해 국내·미국 주식의 시세 수집, 전략 실행, 가상매매, 주문·잔고 관리를 자동화한다.

초기에는 실제 주문을 제출하지 않는 `PAPER` 모드로 운영하고, 안정화·검증 후 제한적으로 `LIVE` 모드로 전환한다.

공식 문서: [토스증권 Open API](https://developers.tossinvest.com/docs)

## 2. 주요 API

- 인증: OAuth 2.0 Client Credentials, `POST /oauth2/token`
- 시세: 현재가, 호가, 체결, 캔들, 상·하한가
- 시장 정보: 종목, 환율, 시장 캘린더
- 계좌: 계좌 목록, 보유 자산, 매수 가능 금액, 매도 가능 수량
- 주문: 생성, 정정, 취소, 목록, 상세
- 조건주문: SINGLE, OCO, OTO
- WebSocket: 실시간 체결·호가·개인 주문 이벤트

계좌 API에는 `X-Tossinvest-Account` 헤더가 필요하다. 실시간 연결은 `wss://openapi-ws.tossinvest.com/ws/v1`를 사용하며 heartbeat와 재연결을 구현한다.

## 3. 운영 모드

### PAPER — 기본 모드

- 가상 초기 자금으로 자동매매
- 실시간 시세와 전략 신호 사용
- 수수료·슬리피지·부분 체결 반영
- 실제 토스증권 주문 API 호출 금지
- 가상 잔고·주문·손익을 별도 저장

### LIVE — 안정화 후 모드

- 기본 비활성화
- 관리자 명시적 승인 필요
- 소액·단일 계좌·화이트리스트 종목으로 시작
- 주문 금액·손실·보유 비중 한도 적용
- 오류·손실·잔고 불일치 시 즉시 중지

## 4. 기능 요구사항

### 인증·계좌

- 앱 자격 증명과 토큰을 환경변수/Secret Manager로 관리한다.
- TokenManager가 토큰 발급·캐시·갱신을 전담한다.
- 시작 시 계좌와 `accountSeq`를 확인한다.

### 시세·전략

- REST로 초기 데이터를 조회하고 WebSocket으로 실시간 데이터를 수신한다.
- 가격·수량은 `Decimal`로 처리한다.
- 장 운영시간과 휴장일을 확인한다.
- 추천 TOP 5는 정보 제공용이며 자동매매 대상과 분리한다. PAPER 자동매매는 국내 시장 거래량 상위 100개와 당일 상승률 상위 100개 랭킹의 교집합을 후보로 삼고, 상승률 1% 이상인 후보를 점수화한다.
- 테마별 분류 API는 사용하지 않는다. 보유 종목이 상승·거래량 후보에서 이탈하거나 매입 평균가 대비 3% 하락하면 PAPER 매도한다.
- 백테스트·PAPER·LIVE가 동일한 전략 인터페이스를 사용한다.

### 주문·위험 관리

- 주문 전 매수 가능 금액·매도 가능 수량·수수료를 확인한다.
- 모든 주문에 고유 `clientOrderId`를 사용해 중복 주문을 방지한다.
- 주문 상태와 부분 체결을 추적한다.
- 네트워크 타임아웃 후 재주문하지 않고 주문 상태를 조회한다.
- 종목·전략·계좌별 금액 한도, 일일 손실 한도, 동시 주문 한도를 적용한다.
- 긴급 주문 취소와 신규 주문 차단(kill switch)을 제공한다.

## 5. Python + FastAPI 구조

### 기술 스택

- Python 3.12+
- FastAPI + Uvicorn
- `httpx`, `websockets`
- Pydantic v2
- SQLAlchemy + Alembic
- 개발 SQLite, 운영 PostgreSQL
- pytest, pytest-asyncio

### 서비스 구성

```text
FastAPI API
 ├─ Auth / Account / Market / Order routes
 ├─ Strategy service
 ├─ Risk & Execution service
 └─ Health / Kill-switch

Background workers
 ├─ WebSocket market listener
 ├─ Strategy runner
 └─ Order/portfolio reconciler
```

권장 API:

- `GET /health/live`, `GET /health/ready`
- `GET /api/v1/markets/{symbol}/quote`
- `GET /api/v1/accounts/{account_seq}/holdings`
- `GET /api/v1/orders`
- `POST /api/v1/orders`
- `POST /api/v1/orders/{order_id}/cancel`
- `POST /api/v1/strategies/{strategy_id}/start|stop`
- `POST /api/v1/system/kill-switch`

실시간 수신과 전략 루프는 별도 비동기 worker로 실행한다. 모든 외부 I/O는 `async/await`를 사용하고, 종료 시 신규 주문을 먼저 차단한 뒤 worker와 DB를 정리한다.

## 6. 데이터와 보안

- 주문, 체결, 포지션, 시세 이벤트, 전략 실행 이력을 저장한다.
- 토큰·시크릿·계좌번호를 로그나 Git에 남기지 않는다.
- `development`, `paper`, `live` 환경과 DB를 분리한다.
- `429`는 `Retry-After`와 지수 백오프, `5xx`는 제한된 재시도를 적용한다.
- API 서버와 worker 장애 시 신규 주문을 차단한다.

## 7. 개발 순서

1. 인증, 계좌 조회, 현재가·캔들 조회
2. `simulator.py` 연동 및 백테스트
3. WebSocket 실시간 시세와 PAPER 매매
4. 주문·체결·잔고 동기화와 위험 관리
5. 안정화 검증 후 제한적 LIVE 운영

## 8. LIVE 전환 조건

- 충분한 기간의 PAPER 운영 결과 검토
- 수수료·슬리피지·부분 체결 검증
- WebSocket 단절·토큰 만료·API 제한 복구 테스트
- 중복 주문 방지와 잔고 재동기화 테스트 통과
- 위험 한도와 kill switch 확인
- 관리자 명시적 승인 및 전환 로그 기록

## 9. 완료 기준

- PAPER 모드가 기본값이며 실제 주문 API를 호출하지 않는다.
- 시세·계좌·주문·체결 상태를 조회하고 저장한다.
- WebSocket 재연결과 주문·잔고 재동기화가 동작한다.
- 동일 요청 재시도에서 중복 주문이 발생하지 않는다.
- 위험 한도 초과와 장애 발생 시 자동으로 신규 주문을 중지한다.
- LIVE 모드는 명시적 승인과 소액 제한을 거쳐야만 활성화된다.
