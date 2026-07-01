"""
reference_cases.py — 시설유형별 "기존 사례 참고자료" 결정론 조회.

`brief_advisor.interpret_brief()`(해설) 와 `brief_proposal.propose_project()`(제안서) 가
새 지침서를 분석할 때, 같은 시설유형의 과거 공모 데이터에서 참고할 만한 신호를 모아준다.
LLM 호출 없음 — 순수 조회/선별. 실패해도 `{}` 반환 (참고자료 없음과 동일 취급, 본 파이프라인
차단 금지).

세 소스:
  - pattern_summary              : `pattern_builder.build_pattern()` 이 만든 집계 통계
                                    (당선/낙선 키워드 빈도, LLM 요약 정성 패턴, 정량 평균).
  - case_excerpts                : 당선 제출물의 실제 컨셉 서술 (concept.main_strategy 등).
  - concept_comparison_excerpts  : 과거 비교분석의 축별 컨셉 비교 서술.

주의: 이 모듈이 반환하는 사례는 **다른 공모**의 것이다. 소비 측(브리프 해설/제안 프롬프트)이
"이 지침서의 사실 근거"로 인용하지 않도록 가드레일을 프롬프트에 명시해야 한다.
"""
from __future__ import annotations

from services.db_manager import (
    load_pattern,
    get_winning_submissions,
    list_projects,
    load_comparison,
)


_MAX_CASE_EXCERPTS = 3
_MAX_CONCEPT_COMPARISON_EXCERPTS = 4
_MIN_COMPARISON_TEXT_LEN = 10


def _pattern_summary(facility_type: str) -> dict:
    """시설유형 패턴에서 참고용 신호 추출. 없거나 N=0이면 {} 반환.

    brief_proposal._pattern_signals 의 이관본 — shape 동일.
    """
    try:
        pattern = load_pattern(facility_type)
        if not isinstance(pattern, dict):
            return {}
        win_n = pattern.get("win_count") or 0
        if win_n == 0:
            return {}
        qi = pattern.get("qualitative_insights") or {}
        ls = pattern.get("loser_stats") or {}
        lqi = ls.get("qualitative_insights") or {}
        lose_n = ls.get("lose_count") or 0
        return {
            "note": (
                f"동일 시설유형 과거 공모 당선 {win_n}건·낙선 {lose_n}건 집계 경향. "
                "직접 인용 금지 — 전략·제안 힌트로만 사용."
            ),
            "win_n": win_n,
            "lose_n": lose_n,
            "winner_keywords":     (pattern.get("concept_keywords") or [])[:8],
            "winner_patterns":     (qi.get("winner_patterns") or [])[:5],
            "loser_patterns":      (qi.get("loser_patterns") or [])[:5],
            "key_differentiators": (qi.get("key_differentiators") or [])[:4],
            "loser_keywords":      (ls.get("concept_keywords") or [])[:8],
        }
    except Exception:
        return {}


def _project_index(facility_type: str) -> list[dict]:
    """competition_id -> {competition_name, created_at} 매핑용, created_at 내림차순."""
    projects = list_projects(facility_type) or []
    projects = [p for p in projects if isinstance(p, dict) and p.get("competition_id")]
    projects.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return projects


def _case_excerpts(facility_type: str, limit: int = _MAX_CASE_EXCERPTS) -> list[dict]:
    try:
        proj_meta = {p["competition_id"]: p for p in _project_index(facility_type)}
        winners = get_winning_submissions(facility_type) or []

        def _sort_key(sub: dict) -> str:
            meta = proj_meta.get(sub.get("competition_id"), {})
            return meta.get("created_at") or ""

        winners.sort(key=_sort_key, reverse=True)

        excerpts: list[dict] = []
        for sub in winners:
            if len(excerpts) >= limit:
                break
            concept = (sub.get("extracted_data") or {}).get("concept")
            if isinstance(concept, list):
                concept = concept[0] if concept else {}
            if not isinstance(concept, dict):
                continue
            main_strategy = (concept.get("main_strategy") or "").strip()
            if not main_strategy:
                continue
            meta = proj_meta.get(sub.get("competition_id"), {})
            excerpts.append({
                "competition_name": meta.get("competition_name") or sub.get("competition_id", ""),
                "competition_id":   sub.get("competition_id", ""),
                "company":          sub.get("company", ""),
                "result":           sub.get("result", ""),
                "concept_name_ko":  concept.get("concept_name_ko") or "",
                "main_strategy":    main_strategy,
                "sub_strategies":   [s for s in (concept.get("sub_strategies") or []) if s][:3],
            })
        return excerpts
    except Exception:
        return []


def _concept_comparison_excerpts(
    facility_type: str, limit: int = _MAX_CONCEPT_COMPARISON_EXCERPTS
) -> list[dict]:
    try:
        excerpts: list[dict] = []
        for proj in _project_index(facility_type):
            if len(excerpts) >= limit:
                break
            cid = proj["competition_id"]
            comp = load_comparison(facility_type, cid)
            if not comp:
                continue
            concept_comparison = comp.get("concept_comparison") or {}
            if not isinstance(concept_comparison, dict):
                continue
            for axis, text in concept_comparison.items():
                if len(excerpts) >= limit:
                    break
                text = (text or "").strip()
                if len(text) < _MIN_COMPARISON_TEXT_LEN:
                    continue
                excerpts.append({
                    "competition_name": proj.get("competition_name") or cid,
                    "competition_id":   cid,
                    "axis":             axis,
                    "text":             text,
                })
        return excerpts
    except Exception:
        return []


def collect_reference_context(facility_type: str) -> dict:
    """시설유형 기준 기존 사례 참고자료 조회. 아무 자료 없으면 {} 반환.

    반환 shape: {facility_type, pattern_summary, case_excerpts, concept_comparison_excerpts}
    세 서브키 모두 비었으면 전체를 {} 로 반환 (호출부가 "참고자료 없음"으로 균일 처리).
    """
    if not facility_type:
        return {}
    pattern_summary = _pattern_summary(facility_type)
    case_excerpts = _case_excerpts(facility_type)
    concept_comparison_excerpts = _concept_comparison_excerpts(facility_type)

    if not (pattern_summary or case_excerpts or concept_comparison_excerpts):
        return {}

    return {
        "facility_type": facility_type,
        "pattern_summary": pattern_summary,
        "case_excerpts": case_excerpts,
        "concept_comparison_excerpts": concept_comparison_excerpts,
    }
