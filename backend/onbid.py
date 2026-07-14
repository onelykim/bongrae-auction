"""
데이터 계층 — 차세대 온비드 '부동산 물건목록' OpenAPI 직접 연동.

API: 한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스 (data.go.kr 15157207)
  엔드포인트: https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2
  필수 파라미터: prptDivCd(재산유형), pvctTrgtYn(수의계약가능여부)
  응답: header/body/items/item[...] + totalCount

키(ONBID_SERVICE_KEY)가 없거나 호출 실패 시 sample_data 로 폴백합니다.
정규화 스키마는 analysis.py / 프런트와 공유(sample_data.py 상단 주석 참고).
"""

from __future__ import annotations
import os
from concurrent.futures import ThreadPoolExecutor

from sample_data import generate_listings

SERVICE_KEY = os.environ.get("ONBID_SERVICE_KEY", "").strip()
ENDPOINT = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"

# 재산유형코드(복수 콤마): 0007 압류재산(경매식 저감·유찰 구조 → 기본값),
#   0006 유입, 0008 수탁, 0005 기타일반(신탁·최저가≥감정가일 수 있음),
#   0003 금융권담보, 0002 공유, 0010 국유, 0013 파산.
# 더 다양하게 보려면 Render 환경변수 ONBID_PRPT_DIV 로 조정(예: "0007,0006,0008").
PROPERTY_TYPES = os.environ.get("ONBID_PRPT_DIV", "0007")
PER = 100
PAGES = int(os.environ.get("ONBID_PAGES", "12"))   # 최대 수집 페이지(회차 중복 감안)


# ---------------------------------------------------------------- helpers
def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def _parse_date(s) -> str | None:
    """cltrBidEndDt 'YYYYMMDDHHMM' -> 'YYYY-MM-DD'. 2999.. 등 미정 placeholder는 None."""
    s = str(s or "")
    if len(s) < 8 or not s[:8].isdigit():
        return None
    if int(s[:4]) >= 2900:
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _map_category(mcls: str, scls: str) -> str:
    t = f"{mcls} {scls}"
    if "아파트" in t:
        return "아파트"
    if "오피스텔" in t:
        return "오피스텔"
    if "근린" in t:
        return "근린생활시설"
    if any(k in t for k in ("상가", "업무용", "점포", "숙박")):
        return "상가"
    if any(k in t for k in ("공장", "창고", "제조", "산업")):
        return "공장"
    if any(k in t for k in ("주택", "다세대", "연립", "빌라", "다가구", "아파트형")):
        return "단독주택"
    if any(k in t for k in ("토지", "대지", "임야", "전답", "답", "잡종지", "농지", "과수원", "목장", "공장용지")):
        return "토지"
    return (mcls or scls or "기타").strip() or "기타"


_RENTABLE = {"상가", "오피스텔", "근린생활시설"}


def normalize_onbid_row(x: dict) -> dict:
    cid = str(x.get("onbidCltrno") or x.get("pbctCdtnNo") or "")
    name = (x.get("onbidCltrNm") or "물건").strip()
    mcls = x.get("cltrUsgMclsCtgrNm") or ""
    scls = x.get("cltrUsgSclsCtgrNm") or ""
    category = _map_category(mcls, scls)
    disposal = x.get("dspsMthodNm") or "매각"
    sido = x.get("lctnSdnm") or ""
    sigungu = x.get("lctnSggnm") or ""
    emd = x.get("lctnEmdNm") or ""
    appraisal = _to_int(x.get("apslEvlAmt"))
    min_bid = _to_int(x.get("lowstBidPrcIndctCont"))
    fail = _to_int(x.get("usbdNft"))
    bld = _to_int(x.get("bldSqms")) or 0
    land = _to_int(x.get("landSqms")) or 0
    area = round(float(x.get("bldSqms") or x.get("landSqms") or 0), 1) or None
    deadline = _parse_date(x.get("cltrBidEndDt"))

    est_rent = None
    if category in _RENTABLE and min_bid:
        est_rent = int(round(min_bid * 0.05 / 12 / 10000)) * 10000  # 표면 5% 가정 추정

    rights = {"지분_매각": (x.get("alcYn") == "Y")}
    addr = " ".join(p for p in (sido, sigungu, emd) if p).strip() or name

    return {
        "id": "O" + cid,
        "name": name,
        "category": category,
        "source": "온비드",
        "disposal": disposal,
        "sido": sido,
        "sigungu": sigungu,
        "address": addr,
        "lat": None,
        "lng": None,
        "appraisal": appraisal or min_bid,
        "min_bid": min_bid or appraisal,
        "fail_count": fail,
        "area_m2": area,
        "deadline": deadline,
        "est_monthly_rent": est_rent,
        "rights": rights,
        "market_price_m2": None,          # realprice(국토부)가 채움
        "org": x.get("orgNm") or "",
        "status": x.get("pbctStatNm") or "",
    }


# ---------------------------------------------------------------- 실데이터
def _fetch_page(page: int) -> list[dict]:
    """한 페이지 조회. 오류가 나도 예외를 던지지 않고 빈 리스트를 반환(부분 성공 허용)."""
    try:
        import requests
        params = {
            "serviceKey": SERVICE_KEY,
            "pageNo": page,
            "numOfRows": PER,
            "resultType": "json",
            "prptDivCd": PROPERTY_TYPES,
            "pvctTrgtYn": "N",
        }
        r = requests.get(ENDPOINT, params=params, timeout=15)
        data = r.json()
        body = data.get("body") or {}
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        return items
    except Exception as exc:  # noqa: BLE001
        print(f"[onbid] page {page} 조회 실패: {exc}")
        return []


def _fetch_real() -> list[dict] | None:
    """차세대 온비드에서 부동산 물건을 수집(여러 페이지 동시). 실패 시 None."""
    if not SERVICE_KEY:
        return None
    try:
        import requests  # noqa: F401  (존재 확인)
    except ImportError:
        return None
    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            pages = list(ex.map(_fetch_page, range(1, PAGES + 1)))
        raw = [row for page in pages for row in page]
        if not raw:
            return None   # 전부 실패/무자료 → 샘플로 폴백(빈 'live' 방지)
        # 같은 물건(onbidCltrno)의 여러 회차 중 최저가가 가장 낮은(=진행 많이 된) 한 건만
        best: dict[str, dict] = {}
        for row in raw:
            key = str(row.get("onbidCltrno"))
            cur = best.get(key)
            if cur is None or _to_int(row.get("lowstBidPrcIndctCont")) < _to_int(cur.get("lowstBidPrcIndctCont")):
                best[key] = row
        return [normalize_onbid_row(r) for r in best.values()]
    except Exception as exc:  # noqa: BLE001
        print(f"[onbid] 실데이터 조회 실패 -> 샘플 폴백: {exc}")
        return None


# ---------------------------------------------------------------- 공통
_SAMPLE = None


def _sample_cache() -> list[dict]:
    global _SAMPLE
    if _SAMPLE is None:
        _SAMPLE = generate_listings()
    return _SAMPLE


def filter_items(items: list[dict],
                 sido: str | None = None,
                 sigungu: str | None = None,
                 category: str | None = None,
                 disposal: str | None = None) -> list[dict]:
    def keep(x: dict) -> bool:
        if sido and x["sido"] != sido:
            return False
        if sigungu and sigungu not in (x.get("sigungu") or ""):
            return False
        if category and x["category"] != category:
            return False
        if disposal and x["disposal"] != disposal:
            return False
        return True
    return [x for x in items if keep(x)]


def get_listings(sido: str | None = None,
                 sigungu: str | None = None,
                 category: str | None = None,
                 disposal: str | None = None,
                 max_rows: int = 0) -> tuple[list[dict], str]:
    """전체(또는 필터된) 물건과 모드('live'|'sample')를 반환."""
    live = _fetch_real()
    if live is not None:
        data, mode = live, "live"
    else:
        data, mode = list(_sample_cache()), "sample"
    return filter_items(data, sido, sigungu, category, disposal), mode


def region_options(items: list[dict] | None = None) -> list[dict]:
    from collections import defaultdict
    items = items if items else list(_sample_cache())
    tree: dict[str, set] = defaultdict(set)
    for x in items:
        if x.get("sido"):
            tree[x["sido"]].add(x.get("sigungu") or "")
    return [{"sido": s, "sigungu": sorted(v)} for s, v in sorted(tree.items())]
