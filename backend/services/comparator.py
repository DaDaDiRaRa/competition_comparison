import asyncio
import json
import logging

from config import settings, axes_for, axes_keys_for, build_axis_rubric_block, RUBRIC_VERSION
from services.llm_client import call_messages
from services.utils import parse_json_response
from services.citation_check import (
    check_comparison as check_citations_comparison,
    check_diagnosis as check_citations_diagnosis,
)

logger = logging.getLogger(__name__)

# 모델 출력 토큰 상한 (Sonnet). Pass 2 리빌 max_tokens 산정 시 이 값을 넘지 않게 클램프.
_MODEL_OUTPUT_CAP = 32000


def _build_axes_strings(facility_type: str) -> dict:
    axes_meta = axes_for(facility_type)
    axes_keys = list(axes_meta.keys())
    axes_key_str = "|".join(axes_keys)
    axis_definitions = "\n".join(
        f"- {k}: {v['description']}" for k, v in axes_meta.items()
    )
    null_axes_block = ",\n".join(
        f'      "{k}": {{"grade":null,"grade_justification":"","strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""}}'
        for k in axes_keys
    )
    null_axes_diagnose = ",\n".join(
        f'    "{k}":{{"grade":null,"grade_justification":"","strengths":[],"weaknesses":[],"recommendations":[],"evidence":""}}'
        for k in axes_keys
    )
    brief_compliance_block = ",\n".join(
        f'    "{k}":"yes|partial|no|unclear"' for k in axes_keys
    )
    concept_comparison_block = ",\n".join(
        f'    "{k}": "<Korean ~150-250chars with (p.N) citations — or empty string if fewer than 2 submissions have data for this axis>"'
        for k in axes_keys
    )
    return {
        "axes_key_str": axes_key_str,
        "axis_definitions": axis_definitions,
        "null_axes_block": null_axes_block,
        "null_axes_diagnose": null_axes_diagnose,
        "brief_compliance_block": brief_compliance_block,
        "concept_comparison_block": concept_comparison_block,
    }


def _make_blind_static(facility_type: str) -> str:
    """Pass 1 (블라인드 채점) 정적 prefix.
    회사명 익명화(A안/B안...) + 결과 라벨 제거 상태에서 순수 분석적 채점만 수행.
    `cache_control: ephemeral` 마킹 대상."""
    ax = _build_axes_strings(facility_type)
    rubric_block = build_axis_rubric_block(facility_type)
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
        "If a submission's data contains a '_brief_context' field, judge THAT submission's "
        "brief_compliance against its own '_brief_context' (its competition's requirements); "
        "otherwise use the shared BRIEF_DATA block.\n"
        "\n"
        "─────────── AXIS RUBRIC (시설유형 맞춤 룰북) ───────────\n"
        "각 제출물에 등급을 부여할 때 아래 rubric을 엄격히 적용한다.\n"
        "임의 기준 만들지 말고, 신호 충족 개수와 등급 기준 행에 직접 매칭한다.\n"
        f"{rubric_block}\n"
        "\n"
        f"axis_keys: {ax['axes_key_str']}\n"
        "\n"
        "GRADING SUMMARY: 위 rubric의 A~E 중 하나만 출력. 숫자 점수 금지.\n"
        "A=신호 대부분 충족 + A 기준 행 일치 / B=다수 충족·일부 일반론 / "
        "C=절반 충족·평이 / D=일부 누락 / E=대부분 누락. 시설특화 hint가 있으면 우선 적용.\n"
        "\n"
        "GRADE_JUSTIFICATION (자기검증, 필수):\n"
        "각 제출물·각 축마다 grade_justification 필드에 1줄로 등급 부여 근거 명시.\n"
        "형식: '신호 X/Y개 충족 (충족: ... / 미충족: ...) → <등급> 기준 행과 일치'.\n"
        "신호 이름은 rubric 그대로 짧게 인용. 임원 검토 시 '왜 이 등급?' 즉시 확인용.\n"
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
        "blind_ranking: ordered list of submission labels, best first, based on overall analytical merit (count of A > B > C > D > E)\n"
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
    ax = _build_axes_strings(facility_type)
    return (
        "TASK: post_hoc_outcome_analysis\n"
        "OUTPUT_FORMAT: json_only\n"
        "TEMPERATURE: 0\n"
        "\n"
        "INSTRUCTIONS (data follows after this section):\n"
        "You will be given:\n"
        "- BLIND_GRADES: per-axis grade (A/B/C/D/E) + strengths/weaknesses/notes produced WITHOUT knowing actual results\n"
        "- ACTUAL_RESULTS: real competition outcome (win/lose) for each submission\n"
        "\n"
        "IMPORTANT: Raw submission data is NOT provided. Use only the strengths/weaknesses/notes already\n"
        "captured in BLIND_GRADES.submissions[company] as your evidence. Preserve original page citations\n"
        "(p.N) when quoting. Do NOT invent new facts or page numbers.\n"
        "\n"
        "SPECIFICITY RULE (applies to all lists below): cite the CONCRETE design move / number / strategy,\n"
        "never generic praise. BAD: '공간 구성이 우수'. GOOD: '남향 배치율 87%로 채광 극대화 (p.12)'.\n"
        "Every item ends with a (p.N) citation reused verbatim from BLIND_GRADES. Do NOT invent facts or pages.\n"
        "\n"
        "Your task:\n"
        "1. winner_strengths: the strongest RECURRING, SPECIFIC strengths of actual winner(s) from BLIND_GRADES.\n"
        "2. loser_weaknesses: the common, SPECIFIC weaknesses of actual losers from BLIND_GRADES.\n"
        "3. key_differentiators (MOST IMPORTANT — this is the report's headline): for each axis that actually\n"
        "   SEPARATED win from lose, write ONE explicit CONTRAST — winner's move vs losers' move — then why it\n"
        "   decided the outcome. Format: '<축 라벨>: 당선작은 ~한 무브(p.N)로 앞섰고, 낙선작은 ~한 한계(p.M) —\n"
        "   이 대비가 당락을 갈랐다.' Only include axes where the winner's grade clearly beats the losers'\n"
        "   (winner 상 vs loser 하). Rank by decisiveness, MOST decisive first. Ground BOTH sides strictly in\n"
        "   BLIND_GRADES (winner strengths + loser weaknesses) and reuse their (p.N). Never invent.\n"
        "4. gap_notes: brief reflection on whether the blind ranking matched the actual outcome\n"
        "   - If aligned (blind top == actual winner): note that design quality likely drove the decision\n"
        "   - If diverged: hypothesize undocumented external factors (정무적·발주처 선호·시공사 관계 등)\n"
        "5. concept_comparison: for EACH axis below, write ONE Korean paragraph that compares how EVERY\n"
        "   submission approached that axis — concept, design direction, concrete content (NOT just grades).\n"
        "   This is independent of win/lose framing: describe what each company actually proposed and how\n"
        "   they differ, e.g. '<회사A>는 ~한 배치(p.N), <회사B>는 ~한 접근(p.M)으로 ...'.\n"
        "   Base every claim strictly on BLIND_GRADES.submissions[company][axis].strengths/weaknesses/notes —\n"
        "   reuse their (p.N) citations verbatim, never invent new facts or pages.\n"
        "   Always include every axis_key below. If an axis has fewer than 2 submissions with actual data,\n"
        "   set its value to an empty string \"\" instead — never fabricate a paragraph just to fill the key.\n"
        "\n"
        f"axis_keys: {ax['axes_key_str']}\n"
        "\n"
        "key_differentiators: max_{max_kd} items (~{kd_chars} chars each) — the decisive win↔lose contrasts, most decisive first\n"
        "winner_strengths: max_{max_wl} items (~{wl_chars} chars each), SPECIFIC + (p.N)\n"
        "loser_weaknesses: max_{max_wl} items (~{wl_chars} chars each), SPECIFIC + (p.N)\n"
        "gap_notes: 1-2 sentences (~80 chars total) in Korean\n"
        "concept_comparison: one entry per axis_key, each ~150-250 chars Korean, citing every submission that has data\n"
        "\n"
        "OUTPUT_ONLY_JSON:\n"
        "{\n"
        '  "key_differentiators": ["<max_4 contrast statements>"],\n'
        '  "winner_strengths": ["<max_3>"],\n'
        '  "loser_weaknesses": ["<max_3>"],\n'
        '  "gap_notes": "<Korean ~80chars>",\n'
        '  "concept_comparison": {\n'
        f"{ax['concept_comparison_block']}\n"
        "  }\n"
        "}"
    )


def _make_diagnose_static(facility_type: str) -> str:
    """진단 프롬프트의 정적 prefix — 동일 facility_type에서 항상 같음."""
    ax = _build_axes_strings(facility_type)
    rubric_block = build_axis_rubric_block(facility_type)
    return (
        "TASK: new_submission_diagnosis\n"
        "FACILITY_TYPE: {facility_type}\n"
        "OUTPUT_FORMAT: json_only\n"
        "TEMPERATURE: 0\n"
        "\n"
        "INSTRUCTIONS (data follows after this section):\n"
        "\n"
        "─────────── AXIS RUBRIC (시설유형 맞춤 룰북) ───────────\n"
        "각 축 등급은 아래 rubric의 신호 충족 개수 + 등급 기준 행에 직접 매칭하여 부여.\n"
        "임의 기준 만들지 말 것. 시설특화 hint가 있으면 그 기준 우선 적용.\n"
        f"{rubric_block}\n"
        "\n"
        "GRADING SUMMARY: A~E 중 하나만 출력. 숫자 금지. overall_grade도 동일 5단계.\n"
        "\n"
        "GRADE_JUSTIFICATION (자기검증, 필수):\n"
        "각 축의 grade_justification 필드에 1줄로 등급 부여 근거 명시.\n"
        "형식: '신호 X/Y개 충족 (충족: ... / 미충족: ...) → <등급> 기준 행과 일치'.\n"
        "신호 이름은 위 rubric 그대로 짧게 인용. 임원 검토 시 '왜 이 등급?' 즉시 확인용.\n"
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
        # 교차비교 전용: 제출물이 서로 다른 공모 소속이라 공통 지침서가 없을 때,
        # 각 제출물에 자기 공모 지침서 요약을 실어 보낸다 (단일 공모 flow엔 부재).
        "_brief_context",
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
              .replace("{max_kd}", "4")       # key_differentiators — 헤드라인 대비, 여유
              .replace("{kd_chars}", "70")
              .replace("{max_wl}", "3")        # winner_strengths/loser_weaknesses — 구체·간결
              .replace("{wl_chars}", "45"))
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
    try:
        blind_result = parse_json_response(blind_raw)
    except Exception as e:
        raise ValueError(f"블라인드 채점 JSON 파싱 실패: {e}\n원문(앞 200자): {blind_raw[:200]}")
    blind_result = _deanonymize_blind_result(blind_result, reverse_map)

    # ── Pass 2: 결과 공개 후 사후 분석 ────────────────────────────────────────
    reveal_static, reveal_dynamic = _build_reveal_prompt_parts(
        submissions, blind_result, ft
    )
    # concept_comparison은 축마다 "모든 제출물을 인용하는 문단 하나"라 축 개수·제출물 개수에
    # 비례해 커진다 — 고정값 대신 두 값 기반으로 여유 있게 산정 (한글은 문자당 토큰 소모가 커서
    # 보수적으로 2.5 토큰/자 가정). 축소 방향 회귀 방지를 위해 8192를 하한으로 유지.
    axis_count = len(axes_keys_for(ft))
    sub_count = len(submissions)
    concept_chars_estimate = axis_count * (250 + 60 * sub_count)
    full_estimate = int(concept_chars_estimate * 2.5) + 1500
    reveal_max_tokens = min(_MODEL_OUTPUT_CAP, max(8192, full_estimate))
    # 오버플로우 가드: 산정 토큰이 모델 출력 상한을 넘으면 컨셉 서술이 축약될 수 있음 — 사용자 고지.
    capped = full_estimate > _MODEL_OUTPUT_CAP

    reveal_result: dict = {}
    coverage_note = ""
    try:
        reveal_raw = call_messages(
            model=settings.model_id,
            max_tokens=reveal_max_tokens,
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
    except Exception as e:
        # Pass 2 실패를 치명적으로 두지 않는다 — Pass 1(축별 등급·강점·약점·블라인드 순위)은
        # 유효하므로 사후 분석만 비우고 사용자에게 고지 (전부 잃지 않게). 대규모 교차비교 방어.
        logger.warning("Pass 2 리빌 분석 실패 — Pass 1 결과로 축소 진행: %s", e)
        coverage_note = ("제출물·축 규모가 커 사후 분석(컨셉 비교·차별화 요약)을 완성하지 "
                         "못했습니다. 축별 등급·강점·약점은 정상입니다.")

    # ── 병합 ─────────────────────────────────────────────────────────────────
    results_map = {s["company"]: s.get("result", "unknown") for s in submissions}
    blind_ranking = blind_result.get("blind_ranking", [])
    gap_analysis = _compute_gap_analysis(
        blind_ranking, results_map, reveal_result.get("gap_notes", "")
    )

    # concept_comparison 전 축 키 보장 (부분·잘린 응답 방어 — 누락 축은 "")
    concept = reveal_result.get("concept_comparison")
    concept = concept if isinstance(concept, dict) else {}
    for k in axes_keys_for(ft):
        concept.setdefault(k, "")
    if capped and not coverage_note:
        coverage_note = ("제출물 수가 많아 일부 축의 컨셉 비교가 축약됐을 수 있습니다 "
                         "(전체 축·전체 제출물은 모두 포함).")

    result = {
        "submissions": blind_result.get("submissions", {}),
        # ranking/blind_ranking: 결과 화면에는 더 이상 노출하지 않음(2026-07-01) —
        # gap_analysis 계산용으로만 내부 유지. archive_search/pattern_builder 등
        # 기존 소비자가 있어 필드 자체는 보존.
        "ranking": blind_ranking,
        "blind_ranking": blind_ranking,
        "key_differentiators": reveal_result.get("key_differentiators", []),
        "concept_comparison": concept,
        "winner_strengths": reveal_result.get("winner_strengths", []),
        "loser_weaknesses": reveal_result.get("loser_weaknesses", []),
        "gap_analysis": gap_analysis,
    }
    if coverage_note:
        result["_coverage_note"] = coverage_note
    # 인용 사후검증 (LLM 0): (p.N)이 실재 페이지인지 코드로 확인, 환각 쪽번호만 flag.
    # 비치명 — 실패해도 비교 결과 유지.
    try:
        result["_citation_flags"] = check_citations_comparison(result, submissions)
    except Exception:
        result["_citation_flags"] = []
    return result


async def compare_submissions(brief_data: dict, submissions: list[dict], facility_type: str = "") -> dict:
    result = await asyncio.to_thread(_run_compare_sync, brief_data, submissions, facility_type)
    result["rubric_version"] = RUBRIC_VERSION
    return result


def _run_diagnose_sync(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    winning_patterns = winning_patterns or {}
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
    try:
        result = parse_json_response(raw_text)
    except Exception as e:
        raise ValueError(f"진단 JSON 파싱 실패: {e}\n원문(앞 200자): {raw_text[:200]}")
    if not isinstance(result, dict):
        # LLM 이 최상위 배열 등 비-dict 반환 시 아래 result[...] 대입이 TypeError → 의도된 에러로 변환
        raise ValueError(f"진단 JSON 이 객체가 아님 (type={type(result).__name__})\n원문(앞 200자): {raw_text[:200]}")
    # 인용 사후검증 (LLM 0): 환각 쪽번호만 flag. 비치명.
    try:
        result["_citation_flags"] = check_citations_diagnosis(result, submission_data)
    except Exception:
        result["_citation_flags"] = []
    # 요구 완결성 감사 (LLM 0): 지침서 요구 중 매트릭스에 안 나온 것. 매트릭스는 안 고친다.
    # LLM 이 requirement_mapping 에 무엇을 넣을지 고르므로, 빠진 줄은 표만 봐선 안 보인다.
    from services.requirement_coverage import check_diagnosis as _check_req_coverage
    result["_requirement_coverage"] = _check_req_coverage(result, brief_data)
    return result


async def diagnose_submission(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    result = await asyncio.to_thread(
        _run_diagnose_sync, facility_type, winning_patterns, brief_data, submission_data
    )
    result["rubric_version"] = RUBRIC_VERSION
    return result
