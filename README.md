# 경매·공매 물건 취합 · 분석 웹앱

상가·부동산 등의 **공매(온비드) 물건을 취합**하고, **지역별로 필터링**해서 보고,
각 물건의 **투자지표·권리분석·주변시세·지역통계**를 분석해주는 웹앱입니다.
**지도(카카오맵)**, **국토부 실거래가 시세**, **매일 자동 업데이트**, **친구 공유(배포)**를 지원합니다.

바로 열어보기: `frontend/index.html` 을 브라우저로 열면 **내장 샘플 데이터**로 모든
기능(필터·분석·통계·지도 안내)이 동작합니다. 실데이터·지도·공유는 아래를 따라 키를 넣고 배포하면 됩니다.

---

## 구성

```
gyeongmae-app/
├─ frontend/index.html      단일 파일 UI (필터·리스트·분석·통계·지도)
├─ backend/
│  ├─ main.py               FastAPI (API + 프런트 서빙 + 일일 스케줄러)
│  ├─ onbid.py              온비드(공매) 물건 수집 + 정규화 + 필터
│  ├─ realprice.py          국토부 아파트 실거래가 → 주변시세
│  ├─ analysis.py           분석 4종(투자지표/권리분석/시세입지/지역통계)
│  ├─ dataset.py            스냅샷 저장/로드 + 갱신(캐시)
│  ├─ refresh_data.py       외부 크론/Actions용 1회 갱신 CLI
│  ├─ sample_data.py        샘플 물건 생성기
│  └─ requirements.txt
├─ Dockerfile / .dockerignore   컨테이너 배포
├─ render.yaml              Render.com 원클릭 배포 설정
├─ .github/workflows/daily-refresh.yml   GitHub Actions 일일 갱신
├─ run.sh                   로컬 실행
└─ README.md
```

## 1) 로컬 실행

```bash
bash run.sh          # 가상환경 생성 + 설치 + 실행
# 또는
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
→ <http://localhost:8000>

## 2) 실데이터·지도 키 (모두 무료)

세 가지 키를 환경변수로 넣으면 실데이터/지도가 켜집니다. 없으면 각각 샘플·추정치·안내로 대체됩니다.

| 환경변수 | 용도 | 발급처 |
|---|---|---|
| `ONBID_SERVICE_KEY` | 온비드 공매 물건 | [data.go.kr](https://www.data.go.kr) → "온비드" 활용신청 |
| `MOLIT_SERVICE_KEY` | 국토부 아파트 실거래가(주변시세) | [data.go.kr](https://www.data.go.kr) → "아파트 매매 실거래가" 활용신청 |
| `KAKAO_JS_KEY` | 카카오맵(지도 탭) | [Kakao Developers](https://developers.kakao.com) → 앱 생성 → 플랫폼 Web에 도메인 등록 → **JavaScript 키** |

```bash
export ONBID_SERVICE_KEY="..."
export MOLIT_SERVICE_KEY="..."
export KAKAO_JS_KEY="..."
uvicorn main:app --reload
```

> 카카오맵은 **JavaScript 키 + 도메인 등록**이 함께 필요합니다. 로컬은 `http://localhost:8000`,
> 배포 후에는 실제 도메인(예: `https://내앱.onrender.com`)을 플랫폼 Web에 추가하세요.

## 3) 매일 자동 업데이트 (3가지 방법 제공)

- **① 서버 내장 스케줄러(기본)** — 앱이 켜져 있으면 매일 `REFRESH_HOUR`(기본 06시, KST)에 자동 갱신.
  끄려면 `DISABLE_SCHEDULER=1`.
- **② 화면 새로고침 버튼** — 상단 `↻ 새로고침` = 지금 즉시 최신 수집(`POST /api/refresh`).
- **③ 외부 크론 / GitHub Actions** — `.github/workflows/daily-refresh.yml` 이 매일 06시(KST)에
  `backend/refresh_data.py` 를 돌려 `data/snapshot.json` 을 갱신·커밋. (무료 호스팅과 궁합이 좋음)
  → GitHub 저장소 Settings → Secrets 에 `ONBID_SERVICE_KEY`, `MOLIT_SERVICE_KEY` 등록.

수집된 데이터는 `data/snapshot.json` 에 캐시되어, 요청마다 외부 API를 때리지 않고 빠르게 서빙됩니다.

## 4) 친구들과 공유 (인터넷 배포)

가장 쉬운 길은 **관리형 무료 호스팅**입니다. Docker 기반이라 어디든 올라갑니다.

### A. Render.com (추천, 원클릭)
1. 이 폴더를 GitHub 저장소로 push.
2. [Render](https://render.com) → **New + → Blueprint** → 저장소 선택 (`render.yaml` 자동 인식).
3. 배포 후 대시보드 **Environment** 에 `ONBID_SERVICE_KEY` / `MOLIT_SERVICE_KEY` / `KAKAO_JS_KEY` 입력.
4. 발급된 `https://<이름>.onrender.com` 주소를 친구에게 공유. (카카오 Web 도메인에 이 주소 추가!)

### B. Railway / Fly.io 등
같은 `Dockerfile` 로 배포됩니다. 플랫폼이 주는 `PORT` 를 그대로 사용합니다.

### C. 내 서버(VPS)에 Docker로
```bash
docker build -t gyeongmae .
docker run -d -p 80:8000 \
  -e ONBID_SERVICE_KEY=... -e MOLIT_SERVICE_KEY=... -e KAKAO_JS_KEY=... \
  -v $(pwd)/data:/app/data --name gyeongmae gyeongmae
```
`-v .../data` 로 스냅샷을 컨테이너 밖에 저장하면 재시작해도 데이터가 유지됩니다.

### 접속 비밀번호로 잠그기 (친구만 공유)
환경변수 `SITE_PASSWORD` 를 설정하면 사이트 전체가 잠기고, 접속 시 브라우저가 암호를 물어봅니다.
아이디는 아무거나, **비밀번호만 맞으면** 통과하는 방식이라 친구들과 암호 하나만 공유하면 됩니다.

```bash
export SITE_PASSWORD="원하는공유암호"
```
Render 등에서는 대시보드 Environment 에 `SITE_PASSWORD` 를 추가하면 됩니다.
비워두면 지금처럼 **주소를 아는 사람 누구나** 접속 가능한 공개 상태입니다.
(추후 개인별 로그인/회원 기능이 필요하면 이어서 붙일 수 있습니다.)

## API 요약

| 엔드포인트 | 설명 |
|---|---|
| `GET /api/health`, `GET /api/meta` | 모드·최종 업데이트 시각·키 설정 여부 |
| `GET /api/regions` | 시도/시군구 목록 |
| `GET /api/listings?sido=&sigungu=&category=&disposal=&sort=` | 필터링된 물건 목록(+요약지표) |
| `GET /api/stats?...` | 지역 통계 |
| `GET /api/listings/{id}/analysis` | 개별 물건 상세 분석 |
| `POST /api/refresh` | 지금 즉시 최신 데이터 수집 |

## 분석 항목

- **① 수익률·투자지표** — 최저가율, 감정가 대비 할인율, 예상 낙찰가/낙찰가율, 표면·실질 임대수익률, 투자매력도 점수.
- **② 권리분석** — 대항력 임차인·선순위 보증금·가처분/가등기·유치권·법정지상권·지분·맹지·명도 등 위험 체크리스트와 위험등급.
- **③ 주변시세·입지** — ㎡당 최저가, 국토부 실거래 대비 괴리율·평가(키 없으면 추정치).
- **④ 지역통계** — 용도별 분포, 유찰 분포, 지역별 물건수·평균감정가·최저가율.

## 향후 확장

- **법원경매** — 공식 API 공개/데이터 제휴 시 동일 스키마로 소스 추가.
- **관심물건 저장·알림**, **로그인/권한**, 상가·토지 실거래가(상업용) 소스 추가.

## 면책

표시되는 예상낙찰가·수익률·권리등급은 공개/샘플 데이터 기반 **참고용 추정치**이며 투자자문이 아닙니다.
실제 입찰 전 반드시 등기부등본·매각물건명세서·현장조사를 확인하세요.
