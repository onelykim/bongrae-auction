"""
데이터셋(스냅샷) 관리 + 일일 자동 갱신.

동작:
  - 앱은 항상 '메모리 데이터셋'을 바라본다.
  - refresh() : 온비드에서 최신 물건을 받아오고 국토부 실거래가로 시세를 보강한 뒤
                data/snapshot.json 에 저장하고 메모리에 반영.
  - 서버 시작 시 스냅샷이 있으면 로드, 없으면 1회 refresh.
  - 스케줄러(main.py)가 매일 정해진 시각에 refresh() 를 호출.

이렇게 하면 사용자 요청마다 외부 API를 때리지 않고, 하루 1회 갱신된 데이터를
빠르게 서빙할 수 있다(무료 API 트래픽 절약 + 응답 속도).
"""

from __future__ import annotations
import json
import time
from pathlib import Path

import onbid
import realprice

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT = DATA_DIR / "snapshot.json"

_state: dict = {"listings": [], "generated_at": None, "mode": "sample"}


def _build(with_price: bool = True) -> tuple[list[dict], str]:
    """전체 물건을 수집(온비드 live 또는 샘플). with_price=True면 국토부 실거래가로 시세 보강.
    시세 보강은 시간 예산(25초)을 두어 무료 서버에서 기동이 지연되지 않게 합니다."""
    listings, mode = onbid.get_listings()  # 필터 없이 전체
    listings = [dict(x) for x in listings]
    if with_price and realprice.SERVICE_KEY:
        budget_start = time.monotonic()
        for x in listings:
            if time.monotonic() - budget_start > 25:
                break
            rp = realprice.market_price_for(x)
            if rp:
                x["market_price_m2"] = rp
                x["market_source"] = "국토부 실거래가"
    return listings, mode


def refresh(with_price: bool = True) -> dict:
    listings, mode = _build(with_price=with_price)
    _state.update(listings=listings, generated_at=int(time.time()), mode=mode)
    _save()
    print(f"[dataset] 갱신 완료: {len(listings)}건 (mode={mode}, 시세보강={with_price})")
    return meta()


def _save() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps({
            "listings": _state["listings"],
            "generated_at": _state["generated_at"],
            "mode": _state["mode"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def load() -> bool:
    if SNAPSHOT.exists():
        try:
            d = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            _state.update(
                listings=d.get("listings", []),
                generated_at=d.get("generated_at"),
                mode=d.get("mode", "sample"),
            )
            return bool(_state["listings"])
        except Exception as exc:  # noqa: BLE001
            print(f"[dataset] 스냅샷 로드 실패: {exc}")
    return False


def ensure_loaded() -> None:
    """앱 시작 시 호출. 스냅샷이 있으면 로드, 없으면 '빠른 수집'(시세보강 생략)으로
    즉시 목록을 채워 기동을 지연시키지 않습니다. 시세는 이후 백그라운드/일일 갱신이 채웁니다."""
    if _state["listings"]:
        return
    if not load():
        refresh(with_price=False)


def all_listings() -> list[dict]:
    ensure_loaded()
    return _state["listings"]


def meta() -> dict:
    return {
        "generated_at": _state["generated_at"],
        "mode": _state["mode"],
        "count": len(_state["listings"]),
        "has_realprice_key": bool(realprice.SERVICE_KEY),
        "has_onbid_key": bool(onbid.SERVICE_KEY),
    }
