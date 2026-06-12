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

from config import settings, axes_keys_for, facility_label
from services.comparator import _trim_extracted, _trim_brief
from services.llm_client import call_messages
from services.utils import parse_json_response

logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are a senior architect analyzing a single competition proposal in depth. "
    "Output Korean. Respond ONLY with valid JSON matching the schema. "
    "Every strength/weakness/improvement MUST cite the source page in (p.N) format. "
    "Be specific and evidence-based — quote concrete numbers, materials, room names "
    "from the extracted data. Avoid generic boilerplate."
)


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
        f"USER_META: {meta_json}\n"
        "\n"
        f"BRIEF (지침서 — 있을 수 있음): {brief_json}\n"
        "\n"
        f"EXTRACTED_SUBMISSION_DATA: {extracted_json}\n"
        "\n"
        "─────────── INSTRUCTIONS ───────────\n"
        "1) 평가축별 심층 분석: 각 축마다 strengths 5~10개, weaknesses 3~8개. "
        "각 항목은 '(p.N) 근거 한 줄' 형식. 모호한 칭찬·일반론 금지. "
        "추출 데이터에 등장하는 실제 수치·재료·실명·동선을 직접 인용.\n"
        "2) 컨셉 narrative: 이 제안서의 디자인 의도·핵심 컨셉·스토리 구조를 3~5문장으로. "
        "USER_META의 memo와 tags를 자연스럽게 반영. 아카이브 자연어 검색의 핵심 소스이므로 "
        "단순 요약이 아니라 검색 가능한 키워드가 풍부한 문장으로.\n"
        "3) design_intent: 디자인 의도 한 문장 (검색·요약용).\n"
        "4) key_differentiators: 이 제안서가 같은 시설유형 평균 대비 두드러지는 점 3~7개.\n"
        "5) improvement_points: 결과와 무관하게 '다음 유사 공모 시 강조하거나 보강할 포인트' 5~10개. "
        "lose면 패턴 추측 기반 약점 보강, win/contracted면 다음에도 재사용할 강점 + 더 강조할 부분.\n"
        "6) search_keywords: 8~15개. 자연어 검색에 걸리도록 한국어 명사구 위주. "
        "facility_type·procurement_type·핵심 컨셉·차별화 요소·발주처 성격·기억할 만한 키워드 포함. "
        "단순 일반어(설계·건축·프로젝트) 금지.\n"
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
        '  "search_keywords": ["...", ...]\n'
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
            "_error": str(e),
        }
