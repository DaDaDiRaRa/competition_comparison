import asyncio
import json
from json import JSONDecodeError

from config import settings, COMPARISON_AXES
from services.llm_client import call_messages
from services.utils import parse_json_response

COMPARE_PROMPT_TEMPLATE = """\
TASK: multi_document_comparison
COMPARISON_AXES: concept|mass|landscape|program|facade|technical|quantitative
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

axis_keys: concept|mass|landscape|program|facade|technical|quantitative

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
      "concept": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "mass": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "landscape": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "program": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "facade": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "technical": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""},
      "quantitative": {"score":null,"strengths":[],"weaknesses":[],"brief_compliance":"unclear","notes":""}
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
    "concept":"yes|partial|no|unclear",
    "mass":"yes|partial|no|unclear",
    "landscape":"yes|partial|no|unclear",
    "program":"yes|partial|no|unclear",
    "facade":"yes|partial|no|unclear",
    "technical":"yes|partial|no|unclear",
    "quantitative":"yes|partial|no|unclear"
  },
  "pattern_deviation": {
    "page_distribution_gaps": [],
    "missing_page_types": [],
    "quantitative_gaps": {}
  },
  "axes": {
    "concept":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "mass":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "landscape":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "program":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "facade":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "technical":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]},
    "quantitative":{"score":null,"strengths":[],"weaknesses":[],"recommendations":[]}
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


_LIMITS_API = dict(
    max_strengths="5", max_weaknesses="5", strength_chars="15-30",
    notes_chars="120", max_global="5", global_chars="50",
)
_LIMITS_SDK = dict(
    max_strengths="3", max_weaknesses="3", strength_chars="15",
    notes_chars="60", max_global="3", global_chars="40",
)


def _build_compare_prompt(brief_data: dict, submissions: list[dict]) -> str:
    limits = _LIMITS_SDK if settings.provider == "sdk" else _LIMITS_API
    sub_map = {s["company"]: _trim_extracted(s.get("extracted_data", {})) for s in submissions}
    results_map = {s["company"]: s.get("result", "unknown") for s in submissions}
    return (COMPARE_PROMPT_TEMPLATE
            .replace("{brief_json}", _compact(_trim_brief(brief_data)))
            .replace("{results_json}", _compact(results_map))
            .replace("{submissions_json}", _compact(sub_map))
            .replace("{max_strengths}", limits["max_strengths"])
            .replace("{max_weaknesses}", limits["max_weaknesses"])
            .replace("{strength_chars}", limits["strength_chars"])
            .replace("{notes_chars}", limits["notes_chars"])
            .replace("{max_global}", limits["max_global"])
            .replace("{global_chars}", limits["global_chars"]))


def _run_compare_sync(brief_data: dict, submissions: list[dict]) -> dict:
    prompt = _build_compare_prompt(brief_data, submissions)
    raw_text = call_messages(
        model=settings.model_id,
        max_tokens=32000,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return parse_json_response(raw_text)
    except JSONDecodeError as e:
        if settings.provider == "sdk":
            n = len(submissions)
            raise RuntimeError(
                f"SDK 출력 한도 초과로 비교 결과가 잘렸습니다 "
                f"(제출작 {n}개, 응답 {len(raw_text):,}자). "
                "app_settings.json에서 provider를 'api'로 변경하거나 "
                "제출작 수를 줄이세요."
            ) from e
        raise


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
