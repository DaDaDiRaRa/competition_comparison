import asyncio
import json

from config import settings, COMPARISON_AXES
from services.llm_client import call_messages
from services.utils import parse_json_response

COMPARE_PROMPT_TEMPLATE = """\
TASK: multi_document_comparison
COMPARISON_AXES: business_viability|member_benefit|product_competitiveness|site_planning|community|design_brand|constructability|firm_capability
OUTPUT_FORMAT: json_only
TEMPERATURE: 0

BRIEF_DATA:
{brief_json}

ACTUAL_RESULTS:
{results_json}

SUBMISSIONS:
{submissions_json}

ACTUAL_RESULTS shows the real competition outcome (win/lose) for each submission.
Use this when writing winner_strengths (based on actual winners) and loser_weaknesses (based on actual losers).
Ranking and scores are your analytical assessment and may differ from actual results.

COMPARE_EACH_SUBMISSION_AGAINST_BRIEF_AND_EACH_OTHER:
For each axis evaluate all submissions. Cite actual data from the extracted content.

AXIS_DEFINITIONS:
- business_viability: 조합원 자산가치 증가·분담금·일반분양 세대수·평당분양가·용적률 인센티브
- member_benefit: 남향배치율·조망권 확보율·실사용면적 증가율·조합원동 위치
- product_competitiveness: 평형 다양성·단위세대 차별화(3면개방·5BAY)·펜트하우스 특화·천장고
- site_planning: 배치 전략·보행차량분리·동간거리·데크 활용·랜드마크성
- community: 세대당 면적·프로그램 수·스카이 커뮤니티·차별화 시설
- design_brand: 브랜드 아이덴티티·매스 독창성·외관 마감재·랜드마크 디자인
- constructability: 공기 단축·공사비 절감·지하주차 효율·공법 리스크
- firm_capability: 정비사업 실적·유사 프로젝트·재무안정성·디자인 어워드

axis_keys: business_viability|member_benefit|product_competitiveness|site_planning|community|design_brand|constructability|firm_capability

SCORING: 0.0-10.0 per axis per submission (use decimals, e.g. 7.3)
STRENGTHS: {max_strengths} items, each a specific Korean phrase (~{strength_chars} chars), cite actual data
WEAKNESSES: {max_weaknesses} items, each a specific Korean phrase (~{strength_chars} chars), cite actual data
BRIEF_COMPLIANCE: yes|partial|no|unclear per axis
NOTES: max_{notes_chars}_chars, specific evidence-based observation with actual numbers/names where available (Korean)
key_differentiators: max_{max_global} sentences (~{global_chars} chars each) explaining what separated winners from losers
winner_strengths: max_{max_global} sentences (~{global_chars} chars each) on why winner won
loser_weaknesses: max_{max_global} sentences (~{global_chars} chars each) on common loser failure patterns

OUTPUT_ONLY_JSON:
{
  "submissions": {
    "<company_name>": {
      "business_viability": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "member_benefit": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "product_competitiveness": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "site_planning": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "community": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "design_brand": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "constructability": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "firm_capability": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""}
    }
  },
  "ranking": ["<company1>","<company2>"],
  "key_differentiators": ["<max_5>"],
  "winner_strengths": ["<max_5>"],
  "loser_weaknesses": ["<max_5>"]
}"""

DIAGNOSE_PROMPT_TEMPLATE = """\
TASK: new_submission_diagnosis
FACILITY_TYPE: {facility_type}
OUTPUT_FORMAT: json_only
TEMPERATURE: 0

WINNING_PATTERNS (from DB, same facility type):
{patterns_json}

BRIEF_DATA:
{brief_json}

MY_SUBMISSION_DATA:
{submission_json}

DIAGNOSE_MY_SUBMISSION:
1. brief_compliance: check each axis against brief requirements
2. pattern_deviation: compare page_distribution and key metrics vs winning_patterns
3. axis_scores: score each axis 0.0-10.0
4. strengths: top_3 strong points
5. weaknesses: top_3 weak points
6. recommendations: top_5 actionable improvement points (keyword_style)
7. overall_score: weighted_average

OUTPUT_ONLY_JSON:
{
  "brief_compliance": {
    "business_viability":"yes|partial|no|unclear",
    "member_benefit":"yes|partial|no|unclear",
    "product_competitiveness":"yes|partial|no|unclear",
    "site_planning":"yes|partial|no|unclear",
    "community":"yes|partial|no|unclear",
    "design_brand":"yes|partial|no|unclear",
    "constructability":"yes|partial|no|unclear",
    "firm_capability":"yes|partial|no|unclear"
  },
  "pattern_deviation": {
    "page_distribution_gaps": [],
    "missing_page_types": [],
    "quantitative_gaps": {}
  },
  "axes": {
    "business_viability":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "member_benefit":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "product_competitiveness":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "site_planning":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "community":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "design_brand":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "constructability":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "firm_capability":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]}
  },
  "overall_score": null,
  "strengths": [],
  "weaknesses": [],
  "recommendations": []
}"""


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
    # combined_data 내의 _page 필드 제거 (불필요한 메타)
    for key, val in trimmed.items():
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    item.pop("_page", None)
        elif isinstance(val, dict):
            val.pop("_page", None)
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


def _build_compare_prompt(brief_data: dict, submissions: list[dict]) -> str:
    sub_map = {s["company"]: _trim_extracted(s.get("extracted_data", {})) for s in submissions}
    results_map = {s["company"]: s.get("result", "unknown") for s in submissions}
    return (COMPARE_PROMPT_TEMPLATE
            .replace("{brief_json}", _compact(_trim_brief(brief_data)))
            .replace("{results_json}", _compact(results_map))
            .replace("{submissions_json}", _compact(sub_map))
            .replace("{max_strengths}", "5")
            .replace("{max_weaknesses}", "5")
            .replace("{strength_chars}", "15-30")
            .replace("{notes_chars}", "120")
            .replace("{max_global}", "5")
            .replace("{global_chars}", "50"))


def _run_compare_sync(brief_data: dict, submissions: list[dict]) -> dict:
    prompt = _build_compare_prompt(brief_data, submissions)
    raw_text = call_messages(
        model=settings.model_id,
        max_tokens=32000,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(raw_text)


async def compare_submissions(brief_data: dict, submissions: list[dict]) -> dict:
    return await asyncio.to_thread(_run_compare_sync, brief_data, submissions)


def _run_diagnose_sync(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    prompt = (DIAGNOSE_PROMPT_TEMPLATE
              .replace("{facility_type}", facility_type)
              .replace("{patterns_json}", _compact(winning_patterns))
              .replace("{brief_json}", _compact(brief_data))
              .replace("{submission_json}", _compact(submission_data)))
    raw_text = call_messages(
        model=settings.model_id,
        max_tokens=8192,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
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
