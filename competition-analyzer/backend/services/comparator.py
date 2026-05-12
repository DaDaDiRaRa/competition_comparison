import asyncio
import json

from config import settings, COMPARISON_AXES, COMPARISON_AXES_META, axes_for
from services.llm_client import call_messages
from services.utils import parse_json_response


def _build_axes_strings(facility_type: str) -> dict:
    axes_meta = axes_for(facility_type)
    axes_keys = list(axes_meta.keys())
    axes_key_str = "|".join(axes_keys)
    axis_definitions = "\n".join(
        f"- {k}: {v['description']}" for k, v in axes_meta.items()
    )
    null_axes_block = ",\n".join(
        f'      "{k}": {{"grade":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""}}'
        for k in axes_keys
    )
    null_axes_diagnose = ",\n".join(
        f'    "{k}":{{"grade":null,"strengths":[],"weaknesses":[],"recommendations":[],"evidence":""}}'
        for k in axes_keys
    )
    brief_compliance_block = ",\n".join(
        f'    "{k}":"yes|partial|no|unclear"' for k in axes_keys
    )
    return {
        "axes_key_str": axes_key_str,
        "axis_definitions": axis_definitions,
        "null_axes_block": null_axes_block,
        "null_axes_diagnose": null_axes_diagnose,
        "brief_compliance_block": brief_compliance_block,
    }


def _make_blind_static(facility_type: str) -> str:
    """Pass 1 (블라인드 채점) 정적 prefix.
    회사명 익명화(A안/B안...) + 결과 라벨 제거 상태에서 순수 분석적 채점만 수행.
    `cache_control: ephemeral` 마킹 대상."""
    ax = _build_axes_strings(facility_type)
    return (
        f"TASK: blind_comparative_scoring\n"
        f"COMPARISON_AXES: {ax['axes_key_str']}\n"
        "OUTPUT_FORMAT: json_only\n"
        "TEMPERATURE: 0\n"
        "\n"
        "INSTRUCTIONS (data follows after this section):\n"
        "Submissions are anonymized (A안, B안, ...). You do NOT know which won or lost.\n"
        "Score each submission purely on analytical merit. Cite actual data from extracted content.\n"
        "Do NOT speculate about competition outcomes.\n"
        "\n"
        "COMPARE_EACH_SUBMISSION_AGAINST_BRIEF_AND_EACH_OTHER per axis.\n"
        "\n"
        "AXIS_DEFINITIONS:\n"
        f"{ax['axis_definitions']}\n"
        "\n"
        f"axis_keys: {ax['axes_key_str']}\n"
        "\n"
        "GRADING (5 levels, no numeric scores):\n"
        '- "A": clearly best / strongly exceeds brief on this axis\n'
        '- "B": good / meets or slightly exceeds brief\n'
        '- "C": adequate / meets brief at typical level\n'
        '- "D": below average / partially meets brief\n'
        '- "E": poor / misses brief or has significant weakness\n'
        "Use only A/B/C/D/E. Do NOT output numeric values.\n"
        "\n"
        "CITATION RULE (MANDATORY):\n"
        "Each item in STRENGTHS and WEAKNESSES MUST end with a page reference in the form '(p.N)'\n"
        "where N is the source page number from the input data's _page field (e.g. '남향 배치율 87% 우수 (p.12)').\n"
        "If multiple pages support the same point, use '(p.N,M)'. If page is genuinely unknown, write '(p.?)'.\n"
        "Items without page citations are invalid — re-anchor to specific pages.\n"
        "\n"
        "STRENGTHS: {max_strengths} items, each a specific Korean phrase (~{strength_chars} chars) + page citation\n"
        "WEAKNESSES: {max_weaknesses} items, each a specific Korean phrase (~{strength_chars} chars) + page citation\n"
        "BRIEF_COMPLIANCE: yes|partial|no|unclear per axis\n"
        "NOTES: max_{notes_chars}_chars, specific evidence-based observation (Korean), include (p.N) if applicable\n"
        "blind_ranking: ordered list of submission labels, best first, based on overall analytical merit (count of 상 > 중 > 하)\n"
        "\n"
        "OUTPUT_ONLY_JSON:\n"
        "{\n"
        '  "submissions": {\n'
        '    "<label>": {\n'
        f"{ax['null_axes_block']}\n"
        "    }\n"
        "  },\n"
        '  "blind_ranking": ["<label1>","<label2>"]\n'
        "}"
    )


def _make_reveal_static(facility_type: str) -> str:
    """Pass 2 (결과 공개 후 사유 분석) 정적 prefix.
    Pass 1의 블라인드 점수 + 실제 당선/낙선만 받아 사후 해석 수행.
    원본 extracted_data를 재전송하지 않으므로 Pass 1 결과 내부의 strengths/weaknesses/notes를 인용 근거로 사용."""
    return (
        "TASK: post_hoc_outcome_analysis\n"
        "OUTPUT_FORMAT: json_only\n"
        "TEMPERATURE: 0\n"
        "\n"
        "INSTRUCTIONS (data follows after this section):\n"
        "You will be given:\n"
        "- BLIND_GRADES: per-axis grade (상/중/하) + strengths/weaknesses/notes produced WITHOUT knowing actual results\n"
        "- ACTUAL_RESULTS: real competition outcome (win/lose) for each submission\n"
        "\n"
        "IMPORTANT: Raw submission data is NOT provided. Use only the strengths/weaknesses/notes already\n"
        "captured in BLIND_GRADES.submissions[company] as your evidence. Preserve original page citations\n"
        "(p.N) when quoting. Do NOT invent new facts or page numbers.\n"
        "\n"
        "Your task:\n"
        "1. winner_strengths: aggregate the strongest recurring strengths of actual winner(s) from BLIND_GRADES\n"
        "2. loser_weaknesses: aggregate common weaknesses of actual losers from BLIND_GRADES\n"
        "3. key_differentiators: what separated winners from losers (cite axes where winners earned 상 while losers earned 하)\n"
        "4. gap_notes: brief reflection on whether the blind ranking matched the actual outcome\n"
        "   - If aligned (blind top == actual winner): note that design quality likely drove the decision\n"
        "   - If diverged: hypothesize undocumented external factors (정무적·발주처 선호·시공사 관계 등)\n"
        "\n"
        "key_differentiators: max_{max_global} sentences (~{global_chars} chars each)\n"
        "winner_strengths: max_{max_global} sentences (~{global_chars} chars each)\n"
        "loser_weaknesses: max_{max_global} sentences (~{global_chars} chars each)\n"
        "gap_notes: 1-2 sentences (~80 chars total) in Korean\n"
        "\n"
        "OUTPUT_ONLY_JSON:\n"
        "{\n"
        '  "key_differentiators": ["<max_3>"],\n'
        '  "winner_strengths": ["<max_3>"],\n'
        '  "loser_weaknesses": ["<max_3>"],\n'
        '  "gap_notes": "<Korean ~80chars>"\n'
        "}"
    )


def _make_diagnose_static(facility_type: str) -> str:
    """진단 프롬프트의 정적 prefix — 동일 facility_type에서 항상 같음."""
    ax = _build_axes_strings(facility_type)
    return (
        "TASK: new_submission_diagnosis\n"
        "FACILITY_TYPE: {facility_type}\n"
        "OUTPUT_FORMAT: json_only\n"
        "TEMPERATURE: 0\n"
        "\n"
        "INSTRUCTIONS (data follows after this section):\n"
        "GRADING (5 levels, no numeric scores): A=best/clearly exceeds, B=good/meets+, C=adequate/typical, D=below avg/partial, E=poor/misses.\n"
        "Use only A/B/C/D/E for axis grade and overall_grade. Do NOT output numeric values.\n"
        "\n"
        "CITATION RULE (MANDATORY):\n"
        "Each item in strengths/weaknesses/recommendations MUST end with a page reference '(p.N)' from MY_SUBMISSION_DATA._page.\n"
        "Use '(p.?)' only when truly unknown. Items without page citations are invalid.\n"
        "\n"
        "DIAGNOSE_MY_SUBMISSION:\n"
        "1. brief_compliance: check each axis against BRIEF_REQUIREMENTS\n"
        "2. requirement_mapping: for each item in BRIEF_REQUIREMENTS.requirements, assess compliance with short evidence (include p.N)\n"
        "3. pattern_deviation: compare page_distribution and key metrics vs winning_patterns; if loser_stats present in patterns, flag metrics closer to loser range than winner range\n"
        "4. axis grades: assign A/B/C/D/E per axis, cite evidence from MY_SUBMISSION_DATA with (p.N)\n"
        "5. strengths: top_3 strong points + (p.N)\n"
        "6. weaknesses: top_3 weak points + (p.N) (include loser-pattern warnings if applicable)\n"
        "7. recommendations: top_3 actionable improvement points (keyword_style) + (p.N) if anchored to specific page\n"
        "8. overall_grade: A/B/C/D/E reflecting majority axis grade balance\n"
        "\n"
        "OUTPUT_ONLY_JSON:\n"
        "{\n"
        '  "brief_compliance": {\n'
        f"{ax['brief_compliance_block']}\n"
        "  },\n"
        '  "requirement_mapping": [\n'
        '    {"requirement": "<Korean 30chars>", "axis": "<axis_key>", "status": "yes|partial|no|unclear", "evidence": "<Korean 30chars (p.N)>"}\n'
        "  ],\n"
        '  "pattern_deviation": {\n'
        '    "page_distribution_gaps": [],\n'
        '    "missing_page_types": [],\n'
        '    "quantitative_gaps": {}\n'
        "  },\n"
        '  "axes": {\n'
        f"{ax['null_axes_diagnose']}\n"
        "  },\n"
        '  "overall_grade": null,\n'
        '  "strengths": [],\n'
        '  "weaknesses": [],\n'
        '  "recommendations": []\n'
        "}"
    )


def _compact(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _trim_extracted(data: dict) -> dict:
    """extracted_data에서 비교에 필요한 핵심 필드만 추출해 토큰을 줄인다."""
    keep_keys = {
        "concept", "toc_hero", "site_plan", "floor_plan", "section",
        "elevation", "area_table", "sustainability", "circulation",
        "special_space", "_quantitative",
        "unit_plan", "incentive_table", "branding",
        # 재건축 전용 타입 (Patch #1·#2에서 추가)
        "business_viability", "area_increase", "view_analysis",
        "community_program", "company_portfolio", "construction_plan",
        "unit_plan_penthouse", "site_context", "landscape",
    }
    trimmed = {k: v for k, v in data.items() if k in keep_keys}
    # _by_type 등 내부 집계 키 제거
    trimmed.pop("_by_type", None)
    # _page는 보존 — LLM의 strengths/weaknesses (p.N) 인용 근거로 사용됨
    return trimmed


def _trim_brief(data: dict) -> dict:
    """brief_data에서 비교에 필요한 핵심 필드만 추출한다."""
    keep_keys = {
        "special_space", "area_table", "circulation", "_quantitative",
        "total_pages", "page_distribution",
    }
    trimmed = {k: v for k, v in data.items() if k in keep_keys}
    trimmed.pop("_by_type", None)
    trimmed.pop("page_map", None)
    return trimmed


_ANALYST_SYSTEM = (
    "You are an expert architectural competition analyst. "
    "Compare multiple design competition entries based on structured extracted data. "
    "Be specific, cite actual data, identify genuine strengths and weaknesses. "
    "Respond ONLY in the specified JSON format. Use Korean for all text fields."
)


def _anonymize_submissions(submissions: list[dict]) -> tuple[list[dict], dict]:
    """제출물 회사명을 A안/B안/... 익명 라벨로 치환.
    Returns (anon_subs, anon_to_real_map)."""
    labels = [f"{chr(65 + i)}안" for i in range(26)]  # A안 ~ Z안
    reverse_map: dict = {}
    anon_subs: list[dict] = []
    for i, s in enumerate(submissions):
        anon = labels[i] if i < len(labels) else f"안{i + 1}"
        reverse_map[anon] = s["company"]
        anon_sub = dict(s)
        anon_sub["company"] = anon
        # result 라벨도 제거 (블라인드 보장)
        anon_sub.pop("result", None)
        anon_subs.append(anon_sub)
    return anon_subs, reverse_map


def _build_blind_prompt_parts(
    brief_data: dict, anon_submissions: list[dict], facility_type: str
) -> tuple[str, str]:
    """Pass 1: 익명화된 제출물 + 결과 미공개."""
    sub_map = {s["company"]: _trim_extracted(s.get("extracted_data", {})) for s in anon_submissions}
    static = (_make_blind_static(facility_type)
              .replace("{max_strengths}", "3")
              .replace("{max_weaknesses}", "3")
              .replace("{strength_chars}", "10-20")
              .replace("{notes_chars}", "80"))
    dynamic = (
        "BRIEF_DATA:\n" + _compact(_trim_brief(brief_data)) + "\n\n"
        "SUBMISSIONS:\n" + _compact(sub_map)
    )
    return static, dynamic


def _build_reveal_prompt_parts(
    submissions: list[dict],
    blind_result: dict,
    facility_type: str,
) -> tuple[str, str]:
    """Pass 2: 결과 매핑 + Pass 1 결과만 전달.
    원본 extracted_data·brief는 재전송하지 않음 — Pass 1 결과 내부 strengths/weaknesses가 근거."""
    results_map = {s["company"]: s.get("result", "unknown") for s in submissions}
    static = (_make_reveal_static(facility_type)
              .replace("{max_global}", "3")
              .replace("{global_chars}", "35"))
    dynamic = (
        "ACTUAL_RESULTS:\n" + _compact(results_map) + "\n\n"
        "BLIND_GRADES (from Pass 1, identities now revealed):\n" + _compact(blind_result)
    )
    return static, dynamic


def _deanonymize_blind_result(blind_result: dict, reverse_map: dict) -> dict:
    """Pass 1 결과의 익명 라벨을 실제 회사명으로 복원."""
    if "submissions" in blind_result and isinstance(blind_result["submissions"], dict):
        blind_result["submissions"] = {
            reverse_map.get(anon, anon): axes
            for anon, axes in blind_result["submissions"].items()
        }
    if "blind_ranking" in blind_result and isinstance(blind_result["blind_ranking"], list):
        blind_result["blind_ranking"] = [
            reverse_map.get(anon, anon) for anon in blind_result["blind_ranking"]
        ]
    return blind_result


def _compute_gap_analysis(
    blind_ranking: list, results_map: dict, gap_notes: str
) -> dict:
    """Pass 1 ranking과 실제 결과의 정렬 정도를 Python에서 계산."""
    actual_winners = [c for c, r in results_map.items() if r in ("win", "contracted")]
    blind_top1 = blind_ranking[0] if blind_ranking else None
    top1_match = blind_top1 in actual_winners if blind_top1 else False

    if blind_ranking and actual_winners:
        n = len(blind_ranking)
        top_half_size = max(1, (n + 1) // 2)
        top_half = set(blind_ranking[:top_half_size])
        winners_in_top = sum(1 for w in actual_winners if w in top_half)
        ratio = winners_in_top / len(actual_winners)
        if top1_match and ratio >= 0.9:
            alignment = "high"
        elif ratio >= 0.5:
            alignment = "partial"
        else:
            alignment = "low"
    else:
        alignment = "unknown"

    return {
        "blind_top1": blind_top1,
        "actual_winners": actual_winners,
        "top1_matches_winner": top1_match,
        "alignment": alignment,
        "notes": gap_notes or "",
    }


def _run_compare_sync(brief_data: dict, submissions: list[dict], facility_type: str = "") -> dict:
    if not submissions:
        return {}
    ft = facility_type or submissions[0].get("facility_type", "")

    # ── Pass 1: 블라인드 채점 ────────────────────────────────────────────────
    anon_subs, reverse_map = _anonymize_submissions(submissions)
    blind_static, blind_dynamic = _build_blind_prompt_parts(brief_data, anon_subs, ft)
    blind_raw = call_messages(
        model=settings.model_id,
        max_tokens=32000,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": blind_static, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": blind_dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    blind_result = parse_json_response(blind_raw)
    blind_result = _deanonymize_blind_result(blind_result, reverse_map)

    # ── Pass 2: 결과 공개 후 사후 분석 ────────────────────────────────────────
    reveal_static, reveal_dynamic = _build_reveal_prompt_parts(
        submissions, blind_result, ft
    )
    reveal_raw = call_messages(
        model=settings.model_id,
        max_tokens=4096,  # Pass 2 출력 짧음 (점수 재산출 안함)
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": reveal_static, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": reveal_dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    reveal_result = parse_json_response(reveal_raw)

    # ── 병합 ─────────────────────────────────────────────────────────────────
    results_map = {s["company"]: s.get("result", "unknown") for s in submissions}
    blind_ranking = blind_result.get("blind_ranking", [])
    gap_analysis = _compute_gap_analysis(
        blind_ranking, results_map, reveal_result.get("gap_notes", "")
    )

    return {
        "submissions": blind_result.get("submissions", {}),
        "ranking": blind_ranking,            # 분석적 순위 (블라인드 기준)
        "blind_ranking": blind_ranking,      # 명시적 별칭
        "key_differentiators": reveal_result.get("key_differentiators", []),
        "winner_strengths": reveal_result.get("winner_strengths", []),
        "loser_weaknesses": reveal_result.get("loser_weaknesses", []),
        "gap_analysis": gap_analysis,
    }


async def compare_submissions(brief_data: dict, submissions: list[dict], facility_type: str = "") -> dict:
    return await asyncio.to_thread(_run_compare_sync, brief_data, submissions, facility_type)


def _run_diagnose_sync(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    qualitative = winning_patterns.get("qualitative_insights", {})
    requirements = brief_data.get("_requirements", {})
    static = _make_diagnose_static(facility_type).replace("{facility_type}", facility_type)
    dynamic = (
        "WINNING_PATTERNS (from DB, same facility type — includes loser_stats if available):\n"
        + _compact(winning_patterns) + "\n\n"
        "QUALITATIVE_INSIGHTS (recurring patterns from past competitions — use as context):\n"
        + _compact(qualitative) + "\n\n"
        "BRIEF_REQUIREMENTS (structured requirements from this competition's brief):\n"
        + _compact(requirements) + "\n\n"
        "BRIEF_DATA:\n" + _compact(brief_data) + "\n\n"
        "MY_SUBMISSION_DATA:\n" + _compact(submission_data)
    )
    raw_text = call_messages(
        model=settings.model_id,
        max_tokens=8192,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": static, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    return parse_json_response(raw_text)


async def diagnose_submission(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    return await asyncio.to_thread(
        _run_diagnose_sync, facility_type, winning_patterns, brief_data, submission_data
    )
