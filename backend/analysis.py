"""
물건 분석 모듈 (4종).

1) 수익률·투자지표   analyze_investment(item)
2) 권리분석          analyze_rights(item)
3) 주변시세·입지      analyze_market(item)
4) 지역통계          region_stats(items)

주의: 공매/경매 실제 투자 판단은 등기부등본·현장확인이 필수입니다.
아래 지표는 공개 데이터로 계산 가능한 '참고용 추정치'이며 투자자문이 아닙니다.
"""

from __future__ import annotations
from collections import Counter, defaultdict


def _pct(n: float) -> float:
    return round(n * 100, 1)


# ---------------------------------------------------------------- 1) 투자지표
def analyze_investment(item: dict) -> dict:
    appraisal = item.get("appraisal") or 0
    min_bid = item.get("min_bid") or 0
    fail = item.get("fail_count") or 0
    rent = item.get("est_monthly_rent")

    min_ratio = (min_bid / appraisal) if appraisal else None
    discount = (1 - min_ratio) if min_ratio is not None else None

    # 예상 낙찰가: 최저가와 감정가 사이. 유찰이 많을수록 최저가 근처.
    # 낙찰가율 가정 = 최저가율 + (감정가와의 간극)*경합계수
    if appraisal and min_bid:
        compete = max(0.0, 0.55 - fail * 0.08)  # 유찰 많으면 경합 완화
        expected_bid = min_bid + (appraisal - min_bid) * compete
    else:
        expected_bid = min_bid or appraisal

    result = {
        "감정가": appraisal,
        "최저입찰가": min_bid,
        "유찰횟수": fail,
        "최저가율_pct": _pct(min_ratio) if min_ratio is not None else None,
        "감정가대비_할인율_pct": _pct(discount) if discount is not None else None,
        "예상낙찰가": int(round(expected_bid)),
        "예상낙찰가율_pct": _pct(expected_bid / appraisal) if appraisal else None,
    }

    # 임대수익률 (임대가능 물건)
    if rent and expected_bid:
        annual = rent * 12
        gross_yield = annual / expected_bid
        # 취득부대비용(취득세·명도·수선) 대략 7% 가정
        total_cost = expected_bid * 1.07
        net_yield = (annual * 0.9) / total_cost  # 공실·관리 10% 차감
        result.update({
            "추정월임대료": rent,
            "표면수익률_pct": _pct(gross_yield),
            "실질수익률_추정_pct": _pct(net_yield),
        })

    # 종합 점수(0~100): 할인율·유찰·수익률 가중
    score = 50.0
    if discount is not None:
        score += min(discount * 100, 40) * 0.6
    if rent and expected_bid:
        score += min(result["표면수익률_pct"], 8) * 3
    score -= fail * 2  # 유찰 과다는 물건 하자 신호일 수 있어 소폭 감점
    result["투자매력도_점수"] = int(max(0, min(100, round(score))))
    return result


# ---------------------------------------------------------------- 2) 권리분석
_RIGHT_RULES = [
    # (플래그, 등급, 설명)
    ("대항력_임차인", "위험", "대항력 있는 임차인 → 보증금 인수 가능성. 배당요구·전입일 확인 필수."),
    ("선순위_임차보증금", "위험", "말소기준권리보다 앞선 보증금은 낙찰자가 인수할 수 있음."),
    ("가처분_가등기", "위험", "선순위 가처분·가등기는 낙찰 후에도 말소되지 않을 수 있음."),
    ("유치권_신고", "주의", "유치권 신고 → 성립 여부·피담보채권 확인 필요(인수 위험)."),
    ("법정지상권_여지", "주의", "토지·건물 소유자 상이 → 법정지상권 성립 여지 검토."),
    ("지분_매각", "주의", "지분 물건 → 공유자 우선매수·사용수익 제약."),
    ("맹지_여부", "주의", "도로에 접하지 않은 맹지 → 건축·활용 제약, 환금성 저하."),
    ("명도_필요", "참고", "점유자 명도 필요 → 인도명령/명도비용·기간 감안."),
]


def analyze_rights(item: dict) -> dict:
    rights = item.get("rights") or {}
    findings = []
    danger = warn = 0
    for flag, level, desc in _RIGHT_RULES:
        if rights.get(flag):
            findings.append({"항목": flag, "등급": level, "설명": desc})
            if level == "위험":
                danger += 1
            elif level == "주의":
                warn += 1

    if danger >= 1:
        grade, label = "고위험", "인수·소멸 여부를 반드시 확인해야 하는 권리 존재"
    elif warn >= 2:
        grade, label = "중위험", "복수의 주의 항목 존재 — 정밀 검토 권장"
    elif warn == 1:
        grade, label = "저위험", "일부 주의 항목 — 통상 범위"
    else:
        grade, label = "양호", "표시된 특이 권리 없음(단, 등기부 직접 확인 권장)"

    return {
        "위험등급": grade,
        "요약": label,
        "위험항목수": danger,
        "주의항목수": warn,
        "findings": findings,
        "면책": "합성/공개데이터 기반 참고용입니다. 실제 입찰 전 등기부등본·매각물건명세서·현장조사가 필수입니다.",
    }


# ---------------------------------------------------------------- 3) 시세·입지
def analyze_market(item: dict) -> dict:
    area = item.get("area_m2")
    min_bid = item.get("min_bid") or 0
    market_m2 = item.get("market_price_m2")

    out: dict = {
        "면적_㎡": area,
        "면적_평": round(area / 3.3058, 1) if area else None,
    }
    if area and min_bid:
        out["최저가_㎡당"] = int(round(min_bid / area))
    if area and market_m2:
        out["인근실거래_㎡당_추정"] = market_m2
        listing_m2 = min_bid / area if area else 0
        if listing_m2:
            gap = 1 - listing_m2 / market_m2
            out["시세대비_최저가_괴리_pct"] = _pct(gap)
            out["시세대비_평가"] = (
                "시세 대비 저평가(차익 여지)" if gap > 0.15
                else "시세와 유사" if gap > -0.05
                else "시세 대비 고가(주의)"
            )
    out["입지참고"] = (
        f"{item.get('sido','')} {item.get('sigungu','')} 소재. "
        "교통·상권·학군 등 상세 입지는 지도/로드뷰 및 현장확인 권장."
    )
    out["출처참고"] = "인근 실거래 단가는 추정치이며, 국토부 실거래가 API 연동으로 정밀화 가능."
    return out


# ---------------------------------------------------------------- 4) 지역통계
def region_stats(items: list[dict]) -> dict:
    if not items:
        return {"물건수": 0}

    by_region = defaultdict(list)
    for x in items:
        by_region[f"{x['sido']} {x['sigungu']}"].append(x)

    def avg(vals):
        vals = [v for v in vals if v]
        return int(round(sum(vals) / len(vals))) if vals else 0

    region_rows = []
    for region, xs in by_region.items():
        ratios = [(x["min_bid"] / x["appraisal"]) for x in xs if x.get("appraisal")]
        region_rows.append({
            "지역": region,
            "물건수": len(xs),
            "평균감정가": avg([x["appraisal"] for x in xs]),
            "평균최저가율_pct": _pct(sum(ratios) / len(ratios)) if ratios else None,
            "평균유찰": round(sum(x["fail_count"] for x in xs) / len(xs), 1),
        })
    region_rows.sort(key=lambda r: r["물건수"], reverse=True)

    cat_counter = Counter(x["category"] for x in items)
    fail_counter = Counter(x["fail_count"] for x in items)

    all_ratios = [(x["min_bid"] / x["appraisal"]) for x in items if x.get("appraisal")]

    return {
        "물건수": len(items),
        "평균감정가": avg([x["appraisal"] for x in items]),
        "평균최저가율_pct": _pct(sum(all_ratios) / len(all_ratios)) if all_ratios else None,
        "평균유찰": round(sum(x["fail_count"] for x in items) / len(items), 1),
        "지역별": region_rows,
        "용도별분포": [{"category": k, "count": v} for k, v in cat_counter.most_common()],
        "유찰분포": [{"fail": k, "count": v} for k, v in sorted(fail_counter.items())],
    }
