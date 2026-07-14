"""
경매·공매 물건 취합/필터/분석 웹앱 - 백엔드 (FastAPI).

실행:
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
    -> http://localhost:8000

환경변수(선택):
    ONBID_SERVICE_KEY   온비드(공매) 실데이터. 없으면 샘플.
    MOLIT_SERVICE_KEY   국토부 실거래가. 없으면 시세 추정치.
    KAKAO_JS_KEY        카카오맵 JavaScript 키. 없으면 지도 대신 안내.
    SITE_PASSWORD       접속 공유 비밀번호. 설정 시 사이트 잠김. 없으면 공개.
    REFRESH_HOUR        일일 자동 갱신 시각(0~23, 기본 6 = 새벽 6시).
    DISABLE_SCHEDULER   "1" 이면 내장 스케줄러 비활성(외부 크론 사용 시).
"""

from __future__ import annotations
import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import onbid
import analysis
import dataset

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
KAKAO_JS_KEY = os.environ.get("KAKAO_JS_KEY", "").strip()
REFRESH_HOUR = int(os.environ.get("REFRESH_HOUR", "6"))
# 공유 비밀번호(선택). 설정하면 사이트 전체가 잠기고, 접속 시 브라우저가 암호를 물어봄.
# 없으면 공개 상태로 동작.
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "").strip()

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: 스냅샷 로드(없으면 1회 수집)
    dataset.ensure_loaded()
    # 일일 자동 갱신 스케줄러
    if os.environ.get("DISABLE_SCHEDULER") != "1":
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            global _scheduler
            _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
            _scheduler.add_job(dataset.refresh, "cron", hour=REFRESH_HOUR, minute=0,
                               id="daily_refresh")
            _scheduler.start()
            print(f"[scheduler] 매일 {REFRESH_HOUR:02d}:00 (KST) 자동 갱신 예약됨")
        except Exception as exc:  # noqa: BLE001
            print(f"[scheduler] 비활성(패키지 없음/오류): {exc}")
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="봉래의 경매찾기", version="2.1", lifespan=lifespan)


# ------------------------------------------------------------------ 공유 비밀번호 잠금
@app.middleware("http")
async def password_gate(request: Request, call_next):
    """SITE_PASSWORD 가 설정된 경우, 헬스체크를 제외한 모든 요청에 HTTP Basic 암호 요구.
    아이디는 아무거나, 비밀번호만 일치하면 통과(친구들과 하나의 공유 암호)."""
    if SITE_PASSWORD and request.url.path != "/api/health":
        ok = False
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(pw, SITE_PASSWORD)
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            return Response(
                content="🔒 봉래의 경매찾기 — 접속하려면 공유 비밀번호가 필요합니다.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Bongrae Auction"'},
                media_type="text/plain; charset=utf-8",
            )
    return await call_next(request)


# ------------------------------------------------------------------ API
@app.get("/api/health")
def health():
    m = dataset.meta()
    return {"status": "ok", **m}


@app.get("/api/meta")
def get_meta():
    return {**dataset.meta(), "kakao": bool(KAKAO_JS_KEY), "refresh_hour": REFRESH_HOUR}


@app.get("/api/regions")
def regions():
    return onbid.region_options()


@app.get("/api/listings")
def listings(
    sido: str | None = Query(None),
    sigungu: str | None = Query(None),
    category: str | None = Query(None),
    disposal: str | None = Query(None),
    sort: str = Query("deadline"),
):
    items = onbid.filter_items(dataset.all_listings(), sido, sigungu, category, disposal)
    enriched = []
    for x in items:
        inv = analysis.analyze_investment(x)
        rights = analysis.analyze_rights(x)
        enriched.append({
            **x,
            "_score": inv["투자매력도_점수"],
            "_discount": inv["감정가대비_할인율_pct"],
            "_yield": inv.get("표면수익률_pct"),
            "_risk": rights["위험등급"],
        })
    keys = {
        "deadline": lambda r: r["deadline"] or "9999",
        "score": lambda r: -(r["_score"] or 0),
        "discount": lambda r: -(r["_discount"] or 0),
        "yield": lambda r: -(r["_yield"] or 0),
        "min_bid": lambda r: r["min_bid"] or 0,
    }
    enriched.sort(key=keys.get(sort, keys["deadline"]))
    return {"mode": dataset.meta()["mode"], "count": len(enriched), "items": enriched}


@app.get("/api/stats")
def stats(
    sido: str | None = Query(None),
    sigungu: str | None = Query(None),
    category: str | None = Query(None),
    disposal: str | None = Query(None),
):
    items = onbid.filter_items(dataset.all_listings(), sido, sigungu, category, disposal)
    return {"mode": dataset.meta()["mode"], **analysis.region_stats(items)}


@app.get("/api/listings/{pid}/analysis")
def item_analysis(pid: str):
    item = next((x for x in dataset.all_listings() if x["id"] == pid), None)
    if not item:
        return JSONResponse(status_code=404, content={"error": "물건을 찾을 수 없습니다."})
    return {
        "item": item,
        "투자지표": analysis.analyze_investment(item),
        "권리분석": analysis.analyze_rights(item),
        "시세입지": analysis.analyze_market(item),
    }


@app.post("/api/refresh")
def refresh_now():
    """수동 '새로고침' — 지금 즉시 최신 데이터 수집."""
    return dataset.refresh()


# ------------------------------------------------------------------ 프런트
@app.get("/", response_class=HTMLResponse)
def index():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    # 카카오맵 키 주입(없으면 빈 값 -> 프런트에서 안내 표시)
    html = html.replace("__KAKAO_JS_KEY__", KAKAO_JS_KEY)
    return HTMLResponse(html)
