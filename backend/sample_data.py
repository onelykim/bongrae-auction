"""
샘플 경매/공매 물건 데이터 생성기.

공공데이터포털 온비드 API 키가 없을 때(또는 데모 목적)에 사용됩니다.
실제 온비드 응답 필드를 참고하되, 앱 전체에서 쓰는 '정규화 스키마'로 만듭니다.

정규화 스키마 (backend/onbid.py 의 normalize 와 동일):
    id            물건 고유 ID
    name          물건명
    category      물건 종류 (상가/아파트/오피스텔/토지/단독주택/공장/근린생활)
    source        데이터 출처 (온비드 / 법원경매(예시))
    disposal      처분방식 (매각 / 임대)
    sido          시도
    sigungu       시군구
    address       전체 주소
    lat, lng      좌표 (지도/입지용, 없으면 None)
    appraisal     감정가 (원)
    min_bid       최저입찰가 (원)
    fail_count    유찰 횟수
    area_m2       면적 (제곱미터)
    deadline      입찰 마감일 (YYYY-MM-DD)
    est_monthly_rent  추정 월임대료 (원, 수익률 계산용 / 없으면 None)
    rights            권리 관련 플래그 (권리분석용 dict)
    market_price_m2   인근 실거래 추정 단가 (원/㎡, 시세비교용 / 없으면 None)
"""

from __future__ import annotations
import hashlib
import random
from datetime import date, timedelta

# (시도, 시군구, 대표 좌표, ㎡당 인근 실거래 추정단가[만원])
REGIONS = [
    ("서울특별시", "강남구", 37.5172, 127.0473, 2650),
    ("서울특별시", "송파구", 37.5145, 127.1060, 1780),
    ("서울특별시", "마포구", 37.5638, 126.9084, 1520),
    ("서울특별시", "노원구", 37.6542, 127.0568, 980),
    ("경기도", "성남시 분당구", 37.3829, 127.1188, 1650),
    ("경기도", "수원시 영통구", 37.2595, 127.0466, 890),
    ("경기도", "고양시 일산동구", 37.6584, 126.7745, 780),
    ("경기도", "화성시", 37.1996, 126.8314, 620),
    ("인천광역시", "연수구", 37.4106, 126.6784, 850),
    ("인천광역시", "부평구", 37.5074, 126.7218, 680),
    ("부산광역시", "해운대구", 35.1631, 129.1636, 1120),
    ("부산광역시", "부산진구", 35.1626, 129.0530, 720),
    ("대구광역시", "수성구", 35.8580, 128.6300, 980),
    ("대전광역시", "유성구", 36.3620, 127.3560, 760),
    ("충청남도", "천안시 서북구", 36.8890, 127.1360, 540),
    ("강원특별자치도", "춘천시", 37.8813, 127.7300, 480),
]

CATEGORIES = [
    # (종류, 처분방식, 면적범위㎡, 감정가배수(㎡당단가 대비), 임대수익가능여부)
    ("상가", "매각", (33, 165), 1.15, True),
    ("근린생활시설", "매각", (50, 300), 1.05, True),
    ("아파트", "매각", (59, 135), 1.00, True),
    ("오피스텔", "매각", (23, 60), 0.95, True),
    ("단독주택", "매각", (80, 260), 0.85, False),
    ("토지", "매각", (200, 2000), 0.40, False),
    ("공장", "매각", (300, 1500), 0.55, False),
    ("상가", "임대", (33, 132), 1.15, True),
]

SOURCES = ["온비드", "온비드", "온비드", "법원경매(예시)"]


def _won(만원: float) -> int:
    return int(round(만원)) * 10000


def generate_listings(seed: int = 42, n: int = 64) -> list[dict]:
    rnd = random.Random(seed)
    today = date(2026, 7, 14)
    listings: list[dict] = []

    for i in range(n):
        sido, sigungu, lat, lng, price_m2_만 = rnd.choice(REGIONS)
        cat, disposal, (amin, amax), mult, rentable = rnd.choice(CATEGORIES)
        source = rnd.choice(SOURCES)

        area = round(rnd.uniform(amin, amax), 1)
        # 좌표에 소량 노이즈
        jlat = lat + rnd.uniform(-0.02, 0.02)
        jlng = lng + rnd.uniform(-0.02, 0.02)

        # 감정가 = ㎡당단가 * 면적 * 물건배수 * (지역/개별 변동)
        base_m2 = price_m2_만 * mult * rnd.uniform(0.82, 1.12)
        appraisal = _won(base_m2 * area)

        # 유찰 횟수(0~4). 유찰 1회당 통상 20~30% 저감
        fail = rnd.choices([0, 1, 2, 3, 4], weights=[30, 30, 22, 12, 6])[0]
        step = rnd.choice([0.20, 0.30])  # 지역별 저감율(수도권 20%, 지방 30% 흔함)
        min_ratio = (1 - step) ** fail
        min_bid = _won(appraisal / 10000 * min_ratio)

        deadline = today + timedelta(days=rnd.randint(2, 45))

        # 추정 월임대료: 임대가능 물건만. 대략 연 4~6% 환산의 월세로 역산.
        est_rent = None
        if rentable:
            annual_yield = rnd.uniform(0.038, 0.062)
            est_rent = int(round(min_bid * annual_yield / 12 / 10000)) * 10000

        # 권리분석용 플래그(공매/경매 위험요소를 단순화한 합성값)
        rights = {
            "대항력_임차인": rnd.random() < 0.22,      # 인수 위험
            "선순위_임차보증금": rnd.random() < 0.18,   # 인수 위험
            "가처분_가등기": rnd.random() < 0.08,       # 말소 안 될 수 있음
            "법정지상권_여지": cat in ("토지",) and rnd.random() < 0.30,
            "유치권_신고": rnd.random() < 0.10,
            "지분_매각": rnd.random() < 0.09,           # 지분물건
            "맹지_여부": cat == "토지" and rnd.random() < 0.25,
            "명도_필요": disposal == "매각" and rnd.random() < 0.6,
        }

        market_m2 = _won(price_m2_만 * rnd.uniform(0.9, 1.1))

        raw_id = f"{i}-{sido}-{sigungu}-{cat}-{appraisal}"
        pid = "S" + hashlib.md5(raw_id.encode()).hexdigest()[:8].upper()

        listings.append({
            "id": pid,
            "name": f"{sigungu} {cat} ({area:.0f}㎡)",
            "category": cat,
            "source": source,
            "disposal": disposal,
            "sido": sido,
            "sigungu": sigungu,
            "address": f"{sido} {sigungu} {rnd.randint(1, 999)}-{rnd.randint(1, 99)}",
            "lat": round(jlat, 5),
            "lng": round(jlng, 5),
            "appraisal": appraisal,
            "min_bid": min_bid,
            "fail_count": fail,
            "area_m2": area,
            "deadline": deadline.isoformat(),
            "est_monthly_rent": est_rent,
            "rights": rights,
            "market_price_m2": market_m2,
        })

    return listings


if __name__ == "__main__":
    import json
    data = generate_listings()
    print(f"{len(data)}건 생성")
    print(json.dumps(data[0], ensure_ascii=False, indent=2))
