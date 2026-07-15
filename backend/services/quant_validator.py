"""
quant_validator.py — `_quantitative` 내부 정합성 결정론 검증 (LLM 0콜, 숫자 수정 없음).

추출 직후(`data_extractor.merge_extracted_data`)와 무료 감사 도구(`tools/data_health.py`)가
공유하는 **단일 소스**. 건축 면적·비율의 수학적 항등식을 검사해 추출 오류(필드 오결합·
환각)를 **플래그로만** 표시한다. 절대 값을 바꾸지 않는다 — 영등포 false-positive 교훈 +
feasibility_export "추가만/수정 없음" 원칙. 관대하게: 명백한 모순·비현실 값만 잡는다.

검사 규칙(항등식):
  - 건폐율(%)   = 100 × 건축면적 / 대지면적
  - 용적률(%)   = 100 × 지상연면적 / 대지면적
       지상연면적이 없으면 약식: 총연면적 ≥ 용적률 함의 지상면적 (총연면적 ≥ 지상연면적이므로)
  - 건축면적 ≤ 대지면적
  - 각 비율/층수/주차 현실 범위

flag 스키마: {"rule": str, "severity": "error"|"warn", "fields": [str...], "detail": str(한국어)}
"""

from services.report_theme import warning_band

# 허용 오차/범위 (관대 — false positive 회피). 값 수정 시 회귀: tests/test_quant_validator.py
COVERAGE_TOL_PP = 3.0    # 건폐율 입력 vs 계산 허용 오차(%포인트)
FAR_TOL_PP = 5.0         # 용적률 입력 vs 지상연면적 계산 허용 오차(%포인트)
FLOOR_AREA_SLACK = 0.9   # 총연면적 ≥ 0.9 × 용적률함의 지상면적 (반올림·부분 여유)
BUILDING_SITE_SLACK = 1.02   # 건축면적 ≤ 대지면적 × 1.02 (측정·반올림 여유)

BOUNDS = {
    "building_coverage_ratio_pct": (0, 100),
    "floor_area_ratio_pct": (0, 1500),
    "floors_above": (0, 120),
    "floors_below": (0, 12),
    "parking_count": (0, 50000),
}


def _num(v):
    """숫자(부울 제외)만 반환, 아니면 None."""
    if isinstance(v, bool):
        return None
    return v if isinstance(v, (int, float)) else None


def validate_quantitative(q: "dict | None") -> list:
    """`_quantitative` dict 의 내부 정합성 검사. 빈 list = 이상 없음.

    입력을 수정하지 않는다 (읽기 전용). 결측 필드는 해당 검사를 건너뛴다
    (없는 값으로 false positive 내지 않음).
    """
    if not isinstance(q, dict):
        return []
    flags: list = []
    sa = _num(q.get("site_area_sqm"))
    ba = _num(q.get("building_area_sqm"))
    tfa = _num(q.get("total_floor_area_sqm"))
    aag = _num(q.get("area_above_ground_sqm"))
    cov = _num(q.get("building_coverage_ratio_pct"))
    far = _num(q.get("floor_area_ratio_pct"))

    # 1) 건축면적 > 대지면적 (물리적 불가)
    if sa and ba and ba > sa * BUILDING_SITE_SLACK:
        flags.append({
            "rule": "building_gt_site", "severity": "error",
            "fields": ["building_area_sqm", "site_area_sqm"],
            "detail": f"건축면적 {ba:,.0f} > 대지면적 {sa:,.0f}㎡ (불가)",
        })
    # 2) 건폐율 = 100 × 건축 / 대지
    if sa and ba and cov is not None:
        calc = 100.0 * ba / sa
        if abs(calc - cov) > COVERAGE_TOL_PP:
            flags.append({
                "rule": "coverage_mismatch", "severity": "error",
                "fields": ["building_coverage_ratio_pct", "building_area_sqm", "site_area_sqm"],
                "detail": f"건폐율 입력 {cov}% vs 계산 {calc:.1f}% (건축 {ba:,.0f}/대지 {sa:,.0f})",
            })
    # 3) 용적률 = 100 × 지상연면적 / 대지 (지상연면적 있을 때 — 가장 엄밀)
    if sa and far is not None and aag:
        calc = 100.0 * aag / sa
        if abs(calc - far) > FAR_TOL_PP:
            flags.append({
                "rule": "far_above_ground_mismatch", "severity": "error",
                "fields": ["floor_area_ratio_pct", "area_above_ground_sqm", "site_area_sqm"],
                "detail": f"용적률 입력 {far}% vs 지상연면적 기준 {calc:.1f}%",
            })
    # 3b) 지상연면적 없으면 약식: 총연면적 ≥ 용적률 함의 지상면적 (총 ≥ 지상이므로 위반 시 모순)
    elif sa and far is not None and tfa:
        implied_above = far / 100.0 * sa
        if tfa < implied_above * FLOOR_AREA_SLACK:
            flags.append({
                "rule": "floor_area_below_far_implied", "severity": "error",
                "fields": ["total_floor_area_sqm", "floor_area_ratio_pct", "site_area_sqm"],
                "detail": f"총연면적 {tfa:,.0f} < 용적률 함의 지상면적 {implied_above:,.0f}㎡ "
                          f"(용적률 {far}% × 대지 {sa:,.0f})",
            })
    # 4) 현실 범위
    for fld, (lo, hi) in BOUNDS.items():
        v = _num(q.get(fld))
        if v is not None and not (lo <= v <= hi):
            flags.append({
                "rule": "out_of_bounds", "severity": "error",
                "fields": [fld],
                "detail": f"{fld}={v} (현실 범위 {lo}~{hi} 벗어남)",
            })
    # 5) 건폐율 > 용적률 (다층 건물이면 비정상) — 경고
    if cov is not None and far is not None and cov > far + 1:
        flags.append({
            "rule": "coverage_gt_far", "severity": "warn",
            "fields": ["building_coverage_ratio_pct", "floor_area_ratio_pct"],
            "detail": f"건폐율 {cov}% > 용적률 {far}% (다층 건물이면 비정상)",
        })
    return flags


# ── 렌더 헬퍼 (LLM 0 · 인라인 스타일 자체완결 — 리포트 generator 공유) ──────────

def flags_band_html(flags: "list | None", limit: int = 12) -> str:
    """`_quantitative_flags` 를 경고 밴드로. 없으면 ''. 자체완결 인라인 스타일(CSS 무의존).

    추출 수치의 내부 모순(건폐율≠건축/대지 등)을 투명하게 노출 — error=빨강, warn=주황.
    숫자 수정 0, 플래그만. 리포트 generator 공용 (citation_check.flags_band_html 와 동형).
    """
    import html
    flags = [f for f in (flags or []) if isinstance(f, dict) and f.get("detail")]
    if not flags:
        return ""
    errors = [f for f in flags if f.get("severity") == "error"]
    warns = [f for f in flags if f.get("severity") == "warn"]
    rows = []
    for f in (errors + warns)[:limit]:
        is_err = f.get("severity") == "error"
        chip = "모순" if is_err else "주의"
        color = "#c0392b" if is_err else "#b8860b"
        detail = html.escape(str(f.get("detail") or ""))
        rows.append(
            f'<li style="margin:3px 0"><span style="display:inline-block;font-size:11px;'
            f'font-weight:700;color:#fff;background:{color};border-radius:4px;'
            f'padding:1px 6px;margin-right:6px">{chip}</span>{detail}</li>'
        )
    return warning_band(
        '⚠ 정량 데이터 정합성 경고 — 추출 수치 간 모순 (추출 오류 가능, 원문 확인 필요)',
        "".join(rows),
    )


def has_errors(flags) -> bool:
    """error 심각도 플래그가 하나라도 있으면 True."""
    return any(isinstance(f, dict) and f.get("severity") == "error" for f in (flags or []))
