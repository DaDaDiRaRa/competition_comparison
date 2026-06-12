"""MyProjectMode 단일 제출물 심층 분석.

경쟁공모는 N개를 비교해야 해서 제출물당 토큰을 절약해야 하지만, MyProjectMode는
항상 1개이므로 토큰 예산이 여유롭다. 이를 활용해 평가축 deep evidence + 컨셉
narrative + 검색 키워드를 풍부하게 추출 → 아카이브 자연어 검색 품질 강화.

LLM 호출 1회 (max_tokens=16000). 출력은 _deep.json으로 저장되어
myproject_report_generator.py가 HTML로 렌더링하고, archive_search.py가 FTS5
인덱스의 extra_meta 컬럼에 search_keywords + concept_narrative를 추가 인덱싱한다.
"""

import json
import logging

from config import settings, axes_keys_for, facility_label, axis_rubric_for
from services.comparator import _trim_extracted, _trim_brief
from services.llm_client import call_messages
from services.utils import parse_json_response

logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are a senior architect analyzing a single competition proposal in depth. "
    "Output Korean. Respond ONLY with valid JSON matching the schema. "
    "Every strength/weakness/improvement MUST cite the source page in (p.N) format. "
    "Be specific and evidence-based — quote concrete numbers, materials, room names "
    "from the extracted data. Avoid generic boilerplate. "
    "Apply the per-axis RUBRIC strictly — do not invent your own grading scale."
)


def _build_axis_rubric_block(facility_type: str, axes_keys: list[str]) -> str:
    """평가축별 rubric을 LLM 프롬프트용 문자열로 직렬화.

    각 축마다: label · 핵심 신호(signals) · A~E 등급 정의 · 시설특화 hint.
    "왜 이 등급인지" LLM이 자기검증 가능한 수준의 룰북.
    """
    lines = []
    for k in axes_keys:
        r = axis_rubric_for(facility_type, k)
        lines.append(f"\n■ {k} — {r['label_ko']}")
        if r.get("description"):
            lines.append(f"  설명: {r['description']}")
        signals = r.get("signals") or []
        if signals:
            sig_lines = "\n".join(f"   · {s}" for s in signals)
            lines.append(f"  PDF에서 볼 신호:\n{sig_lines}")
        rubric = r.get("rubric") or {}
        if rubric:
            rub_lines = "\n".join(
                f"   {g}: {rubric[g]}" for g in ("A", "B", "C", "D", "E") if g in rubric
            )
            lines.append(f"  등급 기준:\n{rub_lines}")
        if r.get("rubric_hint"):
            lines.append(f"  시설특화 hint: {r['rubric_hint']}")
    return "\n".join(lines)


def _build_prompt(
    facility_type: str,
    axes_keys: list[str],
    extracted: dict,
    brief: dict | None,
    meta_extra: dict,
    company: str,
    result: str,
) -> str:
    """단일 제출물 심층 분석 프롬프트."""
    facility_kr = facility_label(facility_type)
    result_kr = {"win": "당선", "contracted": "수의계약", "lose": "참여 (낙선)"}.get(result, result)
    axes_csv = ", ".join(axes_keys)
    rubric_block = _build_axis_rubric_block(facility_type, axes_keys)

    extracted_json = json.dumps(_trim_extracted(extracted or {}), ensure_ascii=False)
    brief_json = json.dumps(_trim_brief(brief or {}), ensure_ascii=False) if brief else "{}"
    meta_json = json.dumps({
        "procurement_type": meta_extra.get("procurement_type", ""),
        "project_phase": meta_extra.get("project_phase", ""),
        "role": meta_extra.get("role", ""),
        "partners": meta_extra.get("partners", ""),
        "tags": meta_extra.get("tags", []),
        "memo": meta_extra.get("memo", ""),
        "gross_floor_area": meta_extra.get("gross_floor_area", ""),
        "floors": meta_extra.get("floors", ""),
        "units": meta_extra.get("units", ""),
    }, ensure_ascii=False)

    return (
        "TASK: deep_single_submission_analysis\n"
        "OUTPUT: json_only\n"
        "\n"
        f"FACILITY_TYPE: {facility_type} ({facility_kr})\n"
        f"COMPANY: {company}\n"
        f"RESULT: {result} ({result_kr})\n"
        f"AXES: {axes_csv}\n"
        "\n"
        "─────────── AXIS RUBRIC (시설유형 맞춤) ───────────\n"
        "아래 rubric을 엄격히 적용해라. 등급은 'PDF에서 볼 신호'의 충족 정도와 '등급 기준'의\n"
        "행과 직접 매칭해서 부여하고, strengths/weaknesses는 그 신호들을 인용해서 작성한다.\n"
        f"{rubric_block}\n"
        "\n"
        f"USER_META (있을 수 있는 사용자 입력 — 빈 값은 네가 추출해서 채워야 함): {meta_json}\n"
        "\n"
        f"BRIEF (지침서 — 있을 수 있음): {brief_json}\n"
        "\n"
        f"EXTRACTED_SUBMISSION_DATA: {extracted_json}\n"
        "\n"
        "─────────── INSTRUCTIONS ───────────\n"
        "1) 평가축별 심층 분석: 각 축마다 strengths 5~10개, weaknesses 3~8개. "
        "각 항목은 '(p.N) 근거 한 줄' 형식. 모호한 칭찬·일반론 금지. "
        "추출 데이터에 등장하는 실제 수치·재료·실명·동선을 직접 인용. "
        "**grade는 위 AXIS RUBRIC의 'PDF에서 볼 신호' 충족 개수와 '등급 기준' 행에 직접 매칭해서 부여**. "
        "예: 신호 6개 중 5개 충족 + A 기준 행과 일치 → A. 시설특화 hint가 있으면 그 기준을 우선 적용.\n"
        "2) 컨셉 narrative: 이 제안서의 디자인 의도·핵심 컨셉·스토리 구조를 3~5문장으로. "
        "아카이브 자연어 검색의 핵심 소스이므로 단순 요약이 아니라 검색 가능한 키워드가 풍부한 문장으로.\n"
        "3) design_intent: 디자인 의도 한 문장 (검색·요약용).\n"
        "4) key_differentiators: 이 제안서가 같은 시설유형 평균 대비 두드러지는 점 3~7개.\n"
        "5) improvement_points: 결과와 무관하게 '다음 유사 공모 시 강조하거나 보강할 포인트' 5~10개. "
        "lose면 패턴 추측 기반 약점 보강, win/contracted면 다음에도 재사용할 강점 + 더 강조할 부분.\n"
        "6) search_keywords: 8~15개. 자연어 검색에 걸리도록 한국어 명사구 위주. "
        "facility_type·procurement_type·핵심 컨셉·차별화 요소·발주처 성격·기억할 만한 키워드 포함. "
        "단순 일반어(설계·건축·프로젝트) 금지.\n"
        "7) auto_meta: PDF에서 직접 추출/추론한 프로젝트 메타데이터.\n"
        "   - procurement_type: 다음 중 하나 — 'competition'(경쟁공모/설계공모) | 'negotiated'(수의계약) | "
        "     'invited'(지명공모/초청) | 'turnkey'(턴키/기술제안/일괄입찰) | 'private'(민간발주) | "
        "     'other'(기타) | ''(불명확하면 빈 문자열). 표지·제출 안내문·BRIEF에서 단서를 찾아라.\n"
        "   - project_phase: 'planning'|'concept'|'basic_design'|'detailed_design'|'cm'|'' 중 하나. "
        "     일반 설계공모는 'concept' 또는 'basic_design'. 단서가 없으면 빈 문자열.\n"
        "   - role: 'lead'(주관사)|'consortium'(컨소시엄 일원)|'subcontractor'(협력사)|''. 표지·credits에서 단서.\n"
        "   - partners: 컨소시엄·협력사명 자유 텍스트. 단독이면 빈 문자열.\n"
        "   - gross_floor_area: 연면적 (예: '12,500㎡' '32,400m²'). 개요/면적표/사업개요 페이지에서 추출.\n"
        "   - floors: 층수 (예: '지상 8층/지하 2층'). 건축개요·단면도에서 추출.\n"
        "   - units: 세대수/실수 (주거: '320세대', 호텔: '180실', 학교: '24학급', 그 외 시설은 빈 문자열).\n"
        "   - tags: 5~10개 한국어 키워드 리스트. 프로젝트 특성을 짧게 (예: '리모델링','친환경','도시재생').\n"
        "   - summary: 1~2문장 짧은 프로젝트 설명. 발주처·시설성격·핵심 특성 포함. "
        "     아카이브 카드 부제로 노출되므로 자연스러운 한국어로.\n"
        "   USER_META에 사용자가 명시한 값이 있으면 그대로 두고, 빈 값만 너의 추출로 채워라.\n"
        "\n"
        "─────────── OUTPUT SCHEMA ───────────\n"
        "{\n"
        '  "concept_narrative": "3~5문장 narrative",\n'
        '  "design_intent": "한 문장 의도",\n'
        '  "axes_evidence": {\n'
        '    "<axis_key>": {\n'
        '      "grade": "A|B|C|D|E",\n'
        '      "strengths": ["(p.N) ...", ...],\n'
        '      "weaknesses": ["(p.N) ...", ...]\n'
        "    }, ...\n"
        "  },\n"
        '  "key_differentiators": ["...", ...],\n'
        '  "improvement_points": ["...", ...],\n'
        '  "search_keywords": ["...", ...],\n'
        '  "auto_meta": {\n'
        '    "procurement_type": "competition|negotiated|invited|turnkey|private|other|"",\n'
        '    "project_phase": "planning|concept|basic_design|detailed_design|cm|"",\n'
        '    "role": "lead|consortium|subcontractor|"",\n'
        '    "partners": "...", "gross_floor_area": "...", "floors": "...", "units": "...",\n'
        '    "tags": ["...", "..."], "summary": "..."\n'
        "  }\n"
        "}\n"
        "\n"
        "STRICT: respond ONLY with the JSON. No prose before/after."
    )


async def deep_analyze(
    *,
    facility_type: str,
    extracted_data: dict,
    brief_data: dict | None,
    meta_extra: dict,
    company: str,
    result: str,
) -> dict:
    """단일 제출물 심층 분석. LLM 1회 호출.

    Returns:
        dict with keys: concept_narrative, design_intent, axes_evidence,
        key_differentiators, improvement_points, search_keywords.
        파싱 실패 시 빈 dict + 에러 로그.
    """
    axes_keys = axes_keys_for(facility_type)
    prompt = _build_prompt(
        facility_type, axes_keys, extracted_data, brief_data,
        meta_extra, company, result,
    )

    try:
        raw = call_messages(
            model=settings.model_id,
            max_tokens=16000,
            temperature=0.3,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = parse_json_response(raw)
        # axes_evidence가 누락된 경우 빈 dict로 폴백
        parsed.setdefault("axes_evidence", {})
        parsed.setdefault("concept_narrative", "")
        parsed.setdefault("design_intent", "")
        parsed.setdefault("key_differentiators", [])
        parsed.setdefault("improvement_points", [])
        parsed.setdefault("search_keywords", [])
        parsed.setdefault("auto_meta", {})
        return parsed
    except Exception as e:
        logger.exception("[myproject_analyzer] deep_analyze 실패: %s", e)
        return {
            "concept_narrative": "",
            "design_intent": "",
            "axes_evidence": {},
            "key_differentiators": [],
            "improvement_points": [],
            "search_keywords": [],
            "auto_meta": {},
            "_error": str(e),
        }
