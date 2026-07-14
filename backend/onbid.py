"""
데이터 계층.

실데이터: 공공데이터포털 '온비드' 공식 OpenAPI (무료).
  - 활용신청 후 발급받은 serviceKey 를 환경변수 ONBID_SERVICE_KEY 로 넣으면 실데이터 사용.
  - PublicDataReader(캠코 래퍼)가 있으면 그것으로, 없으면 requests 로 직접 호출.
샘플: 키가 없거나 호출 실패 시 sample_data.generate_listings() 로 폴백.

온비드 API 참고 (한국자산관리공사, data.go.kr):
  서비스 '캠코공매물건' / '물건정보' / '이용기관공매물건'
  주요 파라미터: SIDO(시도), SGK(시군구), EMD(읍면동),
                DPSL_MTD_CD(0001 매각/0002 임대),
                CTGR_HIRK_ID(상위용도, 부동산 10000)
  주요 응답필드: CLTR_NM(물건명), CTGR_FULL_NM(분류),
                APSL_ASES_AVG_AMT(감정가), MIN_BID_PRC(최저입찰가),
                PBCT_CLTR_STAT_NM(상태), LDNM_ADRS(주소) 등
"""

from __future__ import annotations
import os
from functools import lru_cache

from sample_data import generate_listings

SERVICE_KEY = os.environ.get("ONBID_SERVICE_KEY", "").strip()

# 온비드 상위 용도명 -> 우리 category 매핑(실데이터 정규화 시 사용)
_CATEGORY_KEYWORDS = [
    ("아파트", "아파트"),
    ("오피스텔", "오피스텔"),
    ("상가", "상가"),
    ("근린", "근린생활시설"),
    ("주택", "단독주택"),
    ("토지", "토지"),
    ("대지", "토지"),
    ("전", "토지"),
    ("답", "토지"),
    ("임야", "토지"),
    ("공장", "공장"),
]


def _guess_category(name: str, full: str) -> str:
    text = f"{name} {full}"
    for kw, cat in _CATEGORY_KEYWORDS:
        if kw in text:
            return cat
    return "기타"


def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def normalize_onbid_row(row: dict) -> dict:
    """온비드 응답 1건 -> 정규화 스키마. 필드가 없으면 안전하게 기본값."""
    name = row.get("CLTR_NM") or row.get("PLNM_NO") or "물건"
    full = row.get("CTGR_FULL_NM", "")
    appraisal = _to_int(row.get("APSL_ASES_AVG_AMT") or row.get("MIN_BID_PRC"))
    min_bid = _to_int(row.get("MIN_BID_PRC"))
    addr = row.get("LDNM_ADRS") or row.get("NMRD_ADRS") or ""
    sido = addr.split(" ")[0] if addr else ""
    sigungu = " ".join(addr.split(" ")[1:3]) if addr else ""
    fail = _to_int(row.get("PBCT_FRST_DPSL_NALMT") or 0)  # 근사(제공시)

    pid = str(row.get("CLTR_NO") or row.get("PLNM_NO") or name)
    return {
        "id": "O" + pid,
        "name": name,
        "category": _guess_category(name, full),
        "source": "온비드",
        "disposal": "임대" if str(row.get("DPSL_MTD_NM", "")).startswith("임대") else "매각",
        "sido": sido,
        "sigungu": sigungu,
        "address": addr,
        "lat": None,
        "lng": None,
        "appraisal": appraisal or min_bid,
        "min_bid": min_bid or appraisal,
        "fail_count": fail,
        "area_m2": _to_int(row.get("CLTR_MNL_AR") or 0) or None,
        "deadline": (row.get("PBCT_CLS_DTM") or "")[:10],
        "est_monthly_rent": None,
        "rights": {},
        "market_price_m2": None,
    }


def _fetch_real(sido: str | None, sigungu: str | None,
                disposal: str, max_rows: int) -> list[dict] | None:
    """PublicDataReader 로 실데이터 조회. 실패하면 None 반환(폴백 유도)."""
    if not SERVICE_KEY:
        return None
    try:
        import PublicDataReader as pdr  # type: ignore
    except ImportError:
        return None
    try:
        api = pdr.Kamco(SERVICE_KEY)
        params = {
            "DPSL_MTD_CD": "0002" if disposal == "임대" else "0001",
            "CTGR_HIRK_ID": "10000",  # 부동산
        }
        if sido:
            params["SIDO"] = sido
        if sigungu:
            params["SGK"] = sigungu
        df = api.get_data("물건정보", "통합용도별물건목록", **params)
        if df is None or len(df) == 0:
            return []
        rows = df.head(max_rows).to_dict(orient="records")
        return [normalize_onbid_row(r) for r in rows]
    except Exception as exc:  # noqa: BLE001 - 실패 시 조용히 샘플 폴백
        print(f"[onbid] 실데이터 조회 실패 -> 샘플 폴백: {exc}")
        return None


@lru_cache(maxsize=1)
def _sample_cache() -> tuple:
    return tuple(generate_listings())


def filter_items(items: list[dict],
                 sido: str | None = None,
                 sigungu: str | None = None,
                 category: str | None = None,
                 disposal: str | None = None) -> list[dict]:
    """이미 수집된 목록에 필터 조건을 적용(외부 호출 없음)."""
    def keep(x: dict) -> bool:
        if sido and x["sido"] != sido:
            return False
        if sigungu and sigungu not in x["sigungu"]:
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
                 max_rows: int = 300) -> tuple[list[dict], str]:
    """
    필터 조건으로 물건 목록을 반환.
    returns (listings, mode)  mode = 'live' | 'sample'
    """
    live = _fetch_real(sido, sigungu, disposal or "매각", max_rows)
    if live is not None:
        data, mode = live, "live"
    else:
        data, mode = list(_sample_cache()), "sample"
    return filter_items(data, sido, sigungu, category, disposal), mode


def get_by_id(pid: str) -> dict | None:
    for x in _sample_cache():
        if x["id"] == pid:
            return x
    # 실데이터 모드에서는 목록 재조회가 필요하므로 여기선 샘플 우선
    return None


def region_options() -> list[dict]:
    """UI 지역 필터용 시도/시군구 목록(샘플 기준)."""
    from collections import defaultdict
    tree: dict[str, set] = defaultdict(set)
    for x in _sample_cache():
        tree[x["sido"]].add(x["sigungu"])
    return [{"sido": s, "sigungu": sorted(v)} for s, v in sorted(tree.items())]
