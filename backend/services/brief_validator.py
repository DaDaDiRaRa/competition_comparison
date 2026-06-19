"""
brief_validator.py — 지침서 추출 데이터 결정론적 검증 (LLM 호출 없음)

validate_brief(brief_data, requirements) -> dict

  brief_data   : _brief.json 전체 dict
                 (merge_extracted_data 결과 + page_map + _requirements + _quantitative)
  requirements : brief_data["_requirements"]  (extract_brief_requirements 결과)

검출 규칙 (코드 기반):
  points_mismatch  — 배점 합계 불일치 / null 항목
  duplicate        — 동일 axis + 유사 description 중복 요구사항
  omission         — 핵심 정량 수치 null / 심사기준 미추출
  area_cross_check — room_program 합 vs total_required_area 불일치
  low_confidence   — page_map 분류 신뢰도 낮은 페이지

TODO v2 (LLM 판단 필요):
  semantic_conflict — 두 요구사항이 서로 모순
                      (예: "친환경 최우선" + "일반 마감재만 허용"처럼
                       의미상 충돌하는 requirements 쌍 감지)
"""
from __future__ import annotations

from config import facility_conflict_keywords
from services.utils import _first  # 공유 dict 헬퍼 (_as_list 는 본 모듈에서 미사용)

# ── 상수 ──────────────────────────────────────────────────────────────────────
_CONFIDENCE_LOW = 0.55      # 이 미만이면 low_confidence 플래그
_AREA_TOLERANCE = 0.12      # 12% 이내 오차는 허용 (공용면적·구조체 allowance)
_DUP_JACCARD = 0.60         # 단어 Jaccard 이 이상이면 중복으로 간주
_POINTS_EPSILON = 1.0       # 배점 합계 허용 오차 (±1점)

_CHECKED_RULES = [
    "points_mismatch",
    "duplicate",
    "omission",
    "area_cross_check",
    "low_confidence",
    "facility_keyword_conflict",
    # TODO v2: "semantic_conflict",
]


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────
# _first / _as_list 는 services.utils 단일 소스 (위 import).

def _any_nonnull(*pairs: tuple[dict, str]) -> bool:
    """(dict, key) 쌍 중 하나라도 non-None 값이 있으면 True."""
    return any(isinstance(d, dict) and d.get(k) is not None for d, k in pairs)


def _token_jaccard(a: str, b: str) -> float:
    """공백 분리 단어 Jaccard 유사도 (한국어 포함)."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _flag(type_: str, severity: str, message: str, location: str) -> dict:
    return {"type": type_, "severity": severity, "message": message, "location": location}


# ── 규칙별 검증 함수 ──────────────────────────────────────────────────────────

def _check_points_mismatch(brief_data: dict, requirements: dict) -> list[dict]:
    """배점 합계 불일치 / 진짜 미기재 항목 검출.

    null 점수 분류:
      - shared_with non-empty → 공유 점수 (정상, 무경고)
      - 합계가 만점과 일치 → 정성평가 항목 (정상, 무경고)
      - 합계 불일치 + null 존재 → null 이 누락 원인일 수 있어 medium 경고
    """
    flags: list[dict] = []

    # ── Primary: brief_evaluation.evaluation_categories (새 BRIEF taxonomy 경로) ──
    be = _first(brief_data, "brief_evaluation")
    categories = [c for c in be.get("evaluation_categories", []) if isinstance(c, dict)]

    if categories:
        stated_total = be.get("total_points")
        expected = stated_total if isinstance(stated_total, (int, float)) else 100
        numeric = [c["points"] for c in categories if isinstance(c.get("points"), (int, float))]
        computed = sum(numeric) if numeric else None
        sum_ok = computed is not None and abs(computed - expected) <= _POINTS_EPSILON

        if computed is not None and not sum_ok:
            diff = computed - expected
            flags.append(_flag(
                "points_mismatch", "high",
                f"배점 합계 {computed:.0f}점 ≠ 만점 {expected:.0f}점 (차이 {diff:+.0f}점)",
                "brief_evaluation.evaluation_categories",
            ))

        truly_missing = [
            c.get("name") or f"항목{i + 1}"
            for i, c in enumerate(categories)
            if c.get("points") is None and not (c.get("shared_with") or [])
        ]
        if truly_missing and not sum_ok:
            flags.append(_flag(
                "points_mismatch", "medium",
                f"배점 미기재 항목 {len(truly_missing)}개: "
                f"{', '.join(truly_missing[:3])}{'...' if len(truly_missing) > 3 else ''}",
                "brief_evaluation.evaluation_categories",
            ))
        return flags

    # ── Fallback: _requirements.evaluation_criteria (레거시 / 구 AREA_TABLE 경로) ──
    criteria = [c for c in requirements.get("evaluation_criteria", []) if isinstance(c, dict)]
    if not criteria:
        return flags

    numeric = [c["points"] for c in criteria if isinstance(c.get("points"), (int, float))]
    computed = sum(numeric) if numeric else None
    sum_ok = computed is not None and abs(computed - 100) <= _POINTS_EPSILON

    if computed is not None and not sum_ok:
        flags.append(_flag(
            "points_mismatch", "high",
            f"배점 합계 {computed:.0f}점 ≠ 100점 (차이 {computed - 100:+.0f}점)",
            "_requirements.evaluation_criteria",
        ))

    truly_missing = [
        c.get("item") or f"항목{i + 1}"
        for i, c in enumerate(criteria)
        if c.get("points") is None and not (c.get("shared_with") or [])
    ]
    if truly_missing and not sum_ok:
        flags.append(_flag(
            "points_mismatch", "medium",
            f"배점 미기재 항목 {len(truly_missing)}개: "
            f"{', '.join(truly_missing[:3])}{'...' if len(truly_missing) > 3 else ''}",
            "_requirements.evaluation_criteria",
        ))

    return flags


def _check_duplicate(requirements: dict) -> list[dict]:
    """동일 axis + 유사 description 중복 요구사항 검출."""
    flags: list[dict] = []
    reqs = [r for r in requirements.get("requirements", []) if isinstance(r, dict)]

    for i in range(len(reqs)):
        for j in range(i + 1, len(reqs)):
            r1, r2 = reqs[i], reqs[j]
            if r1.get("axis") != r2.get("axis"):
                continue
            d1, d2 = r1.get("description", ""), r2.get("description", "")
            sim = _token_jaccard(d1, d2)
            if sim >= _DUP_JACCARD:
                flags.append(_flag(
                    "duplicate", "medium",
                    f"axis '{r1['axis']}' 중복 요구사항 (유사도 {sim:.0%}): "
                    f"[{i}] \"{d1[:25]}\" / [{j}] \"{d2[:25]}\"",
                    f"_requirements.requirements[{i},{j}]",
                ))

    return flags


def _check_omission(brief_data: dict, requirements: dict) -> list[dict]:
    """핵심 정량 수치 null / 심사기준 비어있음 검출."""
    flags: list[dict] = []

    quant = brief_data.get("_quantitative") or {}
    bp    = _first(brief_data, "brief_program")
    br    = _first(brief_data, "brief_regulations")
    at    = _first(brief_data, "area_table")

    # brief_project_info의 sites[]에서 첫 non-null 값 추출 (부지가 여러 개면 하나만 있어도 인정)
    # 키 이름이 brief_program과 다름: building_coverage_pct / floor_area_ratio_pct / floor_area_sqm
    bpi = _first(brief_data, "brief_project_info")
    bpi_sites = (bpi.get("sites") or []) if isinstance(bpi, dict) else []
    def _first_site_val(key: str):
        for s in bpi_sites:
            if isinstance(s, dict) and s.get(key) is not None:
                return s.get(key)
        return None
    bpi_summary = {
        "floor_area_sqm":         _first_site_val("floor_area_sqm"),
        "building_coverage_pct":  _first_site_val("building_coverage_pct"),
        "floor_area_ratio_pct":   _first_site_val("floor_area_ratio_pct"),
    }

    # 연면적
    if not _any_nonnull(
        (quant, "total_floor_area_sqm"),
        (bp,    "total_required_floor_area_sqm"),
        (at,    "total_required_area_sqm"),
        (at,    "total_required_floor_area_sqm"),
        (bpi_summary, "floor_area_sqm"),
    ):
        flags.append(_flag(
            "omission", "high",
            "연면적(총 요구 면적) 수치 미추출 — 면적 프로그램 페이지 확인 필요",
            "_quantitative.total_floor_area_sqm",
        ))

    # 건폐율 한도
    if not _any_nonnull(
        (quant, "building_coverage_ratio_pct"),
        (bp,    "building_coverage_limit_pct"),
        (br,    "building_coverage_ratio_limit_pct"),
        (at,    "building_coverage_limit_pct"),
        (bpi_summary, "building_coverage_pct"),
    ):
        flags.append(_flag(
            "omission", "medium",
            "건폐율 한도 수치 미추출",
            "_quantitative.building_coverage_ratio_pct",
        ))

    # 용적률 한도
    if not _any_nonnull(
        (quant, "floor_area_ratio_pct"),
        (bp,    "floor_area_ratio_limit_pct"),
        (br,    "floor_area_ratio_limit_pct"),
        (at,    "floor_area_ratio_limit_pct"),
        (bpi_summary, "floor_area_ratio_pct"),
    ):
        flags.append(_flag(
            "omission", "medium",
            "용적률 한도 수치 미추출",
            "_quantitative.floor_area_ratio_pct",
        ))

    # 심사기준(배점표) 비어있음
    be = _first(brief_data, "brief_evaluation")
    has_categories = bool(be.get("evaluation_categories"))
    has_criteria   = bool(requirements.get("evaluation_criteria"))
    if not has_categories and not has_criteria:
        flags.append(_flag(
            "omission", "high",
            "심사기준(배점표) 미추출 — 지침서에 BRIEF_EVALUATION 페이지가 없거나 추출 실패",
            "brief_evaluation.evaluation_categories",
        ))

    return flags


def _check_area_cross(brief_data: dict) -> list[dict]:
    """room_program 합 vs total_required_area 불일치 검출."""
    flags: list[dict] = []

    # ── 새 BRIEF 경로 ──
    bp = _first(brief_data, "brief_program")
    rooms       = [r for r in bp.get("rooms", []) if isinstance(r, dict)]
    total_target: float | None = bp.get("total_required_floor_area_sqm")

    # ── 레거시 경로 fallback ──
    if not rooms or total_target is None:
        at = _first(brief_data, "area_table")
        if not rooms:
            rooms = [r for r in at.get("room_program", []) if isinstance(r, dict)]
        if total_target is None:
            total_target = at.get("total_required_area_sqm") or at.get("total_required_floor_area_sqm")

    if not rooms or total_target is None or total_target <= 0:
        return flags

    room_areas = [
        r.get("required_area_sqm") or r.get("area_sqm")
        for r in rooms
    ]
    valid = [a for a in room_areas if isinstance(a, (int, float)) and a > 0]
    if not valid:
        return flags

    room_sum = sum(valid)
    ratio    = room_sum / total_target
    deviation = abs(ratio - 1.0)

    if deviation > _AREA_TOLERANCE:
        direction = "초과" if ratio > 1 else "부족"
        severity  = "high" if deviation > 0.25 else "medium"
        flags.append(_flag(
            "area_cross_check", severity,
            f"실별 면적 합 {room_sum:,.0f}㎡ vs 총 요구 면적 {total_target:,.0f}㎡ "
            f"({ratio:.0%}, {deviation:.0%} {direction})",
            "brief_program.rooms vs brief_program.total_required_floor_area_sqm",
        ))

    return flags


def _check_facility_keyword_conflict(brief_data: dict) -> list[dict]:
    """시설유형과 충돌하는 키워드가 brief_evaluation에 나오면 LLM 환각 경고.

    영등포구 청사(public) 사례: page 18 평가항목 sub_items에 "본 연구원의 특성",
    "연구원의 전체성" 같은 학습 데이터 환각이 섞임. 청사 공모에 평가기준이
    "연구원" 단어를 포함할 수 없으므로 충돌로 감지.

    검사 범위: brief_evaluation.evaluation_categories[*]의 name + sub_items.
    competition_name이나 sites.facilities 같은 메타 필드는 검사하지 않음
    (실제로 다른 시설을 가리키는 정상 표현일 수 있음).
    """
    flags: list[dict] = []
    facility_type = (brief_data.get("_brief_meta") or {}).get("facility_type", "")
    keywords = facility_conflict_keywords(facility_type)
    if not keywords:
        return flags

    be = _first(brief_data, "brief_evaluation")
    categories = [c for c in be.get("evaluation_categories", []) if isinstance(c, dict)]
    if not categories:
        return flags

    # category name + sub_items 텍스트만 모음 — 평가기준에 나오면 환각 가능성
    texts: list[tuple[str, str]] = []  # (text, location)
    for idx, cat in enumerate(categories):
        name = cat.get("name") or ""
        if name:
            texts.append((name, f"brief_evaluation.evaluation_categories[{idx}].name"))
        for si_idx, si in enumerate(cat.get("sub_items") or []):
            if isinstance(si, str) and si:
                texts.append((si, f"brief_evaluation.evaluation_categories[{idx}].sub_items[{si_idx}]"))

    # 키워드별 매치 집계 — 같은 키워드 여러 번 매치돼도 한 번만 경고
    matched: dict[str, list[str]] = {}  # keyword → [snippet1, snippet2, ...]
    for text, location in texts:
        for kw in keywords:
            if kw in text:
                matched.setdefault(kw, []).append(text[:40])
                break  # 한 텍스트당 첫 키워드만 (중복 경고 방지)

    for kw, snippets in matched.items():
        flags.append(_flag(
            "facility_keyword_conflict", "high",
            f"시설유형 '{facility_type}'과 충돌하는 키워드 '{kw}' 발견 — "
            f"LLM 환각 의심. 예: \"{snippets[0]}...\" "
            f"(총 {len(snippets)}건). 심사기준 추출 결과를 PDF와 대조 권장.",
            "brief_evaluation.evaluation_categories",
        ))

    return flags


def _check_low_confidence(brief_data: dict) -> list[dict]:
    """page_map 분류 신뢰도 낮은 페이지 검출."""
    flags: list[dict] = []
    page_map = brief_data.get("page_map") or []

    for p in page_map:
        if not isinstance(p, dict):
            continue
        conf = p.get("confidence")
        if not isinstance(conf, (int, float)):
            continue
        if conf < _CONFIDENCE_LOW:
            flags.append(_flag(
                "low_confidence", "low",
                f"p.{p['page']} 분류 신뢰도 {conf:.0%} "
                f"(타입: {p.get('primary_type', '?')}) — 추출 결과 수동 확인 권장",
                f"page_map.p{p['page']}",
            ))

    return flags


# ── 공개 API ──────────────────────────────────────────────────────────────────

def validate_brief(brief_data: dict, requirements: dict) -> dict:
    """
    지침서 추출 데이터 결정론적 검증. LLM 호출 없음.

    Args:
        brief_data:   _brief.json 전체 dict
        requirements: brief_data["_requirements"] (extract_brief_requirements 결과)

    Returns:
        {
            "validation": {
                "flags": [{"type", "severity", "message", "location"}, ...],
                "summary": {"high": n, "medium": n, "low": n},
                "checked_rules": [...]
            }
        }
    """
    if not isinstance(requirements, dict):
        requirements = {}
    flags: list[dict] = []
    flags.extend(_check_points_mismatch(brief_data, requirements))
    flags.extend(_check_duplicate(requirements))
    flags.extend(_check_omission(brief_data, requirements))
    flags.extend(_check_area_cross(brief_data))
    flags.extend(_check_facility_keyword_conflict(brief_data))
    flags.extend(_check_low_confidence(brief_data))

    summary = {"high": 0, "medium": 0, "low": 0}
    for f in flags:
        summary[f["severity"]] += 1

    return {
        "validation": {
            "flags": flags,
            "summary": summary,
            "checked_rules": _CHECKED_RULES,
        }
    }
