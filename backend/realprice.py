"""
국토교통부 아파트 매매 실거래가 연동 (공공데이터포털 무료 API).

목적: 물건 주변 '인근 실거래 ㎡당 단가'를 추정치가 아닌 실제 거래 기반으로 계산.

API: 국토교통부_아파트 매매 실거래가 자료
  엔드포인트: https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
  주요 파라미터: serviceKey, LAWD_CD(법정동 시군구 5자리), DEAL_YMD(계약연월 YYYYMM)
  응답: 거래금액(만원), 전용면적(㎡), 법정동, 아파트명 등

키 발급: data.go.kr 에서 '아파트 매매 실거래가' 활용신청 후
        환경변수 MOLIT_SERVICE_KEY 에 설정. 없으면 None 을 반환해 기존 추정치를 사용.
"""

from __future__ import annotations
import os
from functools import lru_cache

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "").strip()
ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

# 샘플 지역 시군구 -> 법정동 시군구코드(LAWD_CD, 5자리). 필요 시 계속 추가.
LAWD_CD = {
    "서울특별시 강남구": "11680",
    "서울특별시 송파구": "11710",
    "서울특별시 마포구": "11440",
    "서울특별시 노원구": "11350",
    "경기도 성남시 분당구": "41135",
    "경기도 수원시 영통구": "41117",
    "경기도 고양시 일산동구": "41285",
    "경기도 화성시": "41590",
    "인천광역시 연수구": "28185",
    "인천광역시 부평구": "28237",
    "부산광역시 해운대구": "26350",
    "부산광역시 부산진구": "26230",
    "대구광역시 수성구": "27260",
    "대전광역시 유성구": "30200",
    "충청남도 천안시 서북구": "44133",
    "강원특별자치도 춘천시": "51110",
}


def _recent_yyyymm(n: int = 3) -> list[str]:
    """최근 n개월 계약연월(테스트/재현성을 위해 고정 기준일 사용)."""
    base_y, base_m = 2026, 6
    out = []
    for i in range(n):
        m = base_m - i
        y = base_y
        while m <= 0:
            m += 12
            y -= 1
        out.append(f"{y}{m:02d}")
    return out


@lru_cache(maxsize=256)
def _fetch_month(lawd_cd: str, ymd: str) -> tuple:
    """해당 시군구/월의 (전용면적, 거래금액원) 리스트. 실패 시 빈 튜플."""
    if not SERVICE_KEY:
        return tuple()
    try:
        import requests  # 지연 임포트
        import xml.etree.ElementTree as ET
    except ImportError:
        return tuple()
    try:
        params = {
            "serviceKey": SERVICE_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": ymd,
            "numOfRows": "500",
            "pageNo": "1",
        }
        r = requests.get(ENDPOINT, params=params, timeout=8)
        root = ET.fromstring(r.content)
        rows = []
        for item in root.iter("item"):
            def t(tag):
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else ""
            # 태그명은 신/구 버전에 따라 다를 수 있어 후보를 모두 시도
            amt = t("dealAmount") or t("거래금액")
            area = t("excluUseAr") or t("전용면적")
            if not amt or not area:
                continue
            won = int(amt.replace(",", "")) * 10000
            rows.append((float(area), won))
        return tuple(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"[realprice] 조회 실패({lawd_cd}/{ymd}): {exc}")
        return tuple()


def market_price_m2(sido: str, sigungu: str) -> int | None:
    """시군구 최근 실거래 기준 ㎡당 평균단가(원). 데이터 없으면 None."""
    key = f"{sido} {sigungu}"
    lawd = LAWD_CD.get(key)
    if not lawd or not SERVICE_KEY:
        return None
    unit_prices = []
    for ymd in _recent_yyyymm(3):
        for area, won in _fetch_month(lawd, ymd):
            if area > 0:
                unit_prices.append(won / area)
    if not unit_prices:
        return None
    return int(round(sum(unit_prices) / len(unit_prices)))


def market_price_for(item: dict) -> int | None:
    """물건에 대한 실거래 ㎡당 단가. 실패 시 None(기존 추정치 유지)."""
    return market_price_m2(item.get("sido", ""), item.get("sigungu", ""))
