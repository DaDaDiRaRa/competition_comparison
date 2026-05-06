import asyncio
import json

import anthropic

from config import settings, COMPARISON_AXES
from services.utils import parse_json_response

COMPARE_PROMPT_TEMPLATE = """\
TASK: multi_document_comparison
COMPARISON_AXES: concept|mass|landscape|program|facade|technical|quantitative
OUTPUT_FORMAT: json_only
TEMPERATURE: 0

BRIEF_DATA:
{brief_json}

SUBMISSIONS:
{submissions_json}

COMPARE_EACH_SUBMISSION_AGAINST_BRIEF_AND_EACH_OTHER:
For each axis evaluate all submissions.

axis_keys: concept|mass|landscape|program|facade|technical|quantitative

SCORING: 0.0-10.0 per axis per submission
STRENGTHS: max_3_keywords
WEAKNESSES: max_3_keywords
BRIEF_COMPLIANCE: yes|partial|no|unclear per axis

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
  "key_differentiators": ["<max_5>"]
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


_ANALYST_SYSTEM = (
    "You are an expert architectural competition analyst. "
    "Compare multiple design competition entries based on structured extracted data. "
    "Be specific, cite actual data, identify genuine strengths and weaknesses. "
    "Respond ONLY in the specified JSON format. Use Korean for all text fields."
)


def _run_compare_sync(brief_data: dict, submissions: list[dict]) -> dict:
    sub_map = {s["company"]: s.get("extracted_data", {}) for s in submissions}
    prompt = COMPARE_PROMPT_TEMPLATE.format(
        brief_json=_compact(brief_data),
        submissions_json=_compact(sub_map),
    )
    client = anthropic.Anthropic(api_key=settings.api_key)
    response = client.messages.create(
        model=settings.model_id,
        max_tokens=4096,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(response.content[0].text)


async def compare_submissions(brief_data: dict, submissions: list[dict]) -> dict:
    return await asyncio.to_thread(_run_compare_sync, brief_data, submissions)


def _run_diagnose_sync(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    prompt = DIAGNOSE_PROMPT_TEMPLATE.format(
        facility_type=facility_type,
        patterns_json=_compact(winning_patterns),
        brief_json=_compact(brief_data),
        submission_json=_compact(submission_data),
    )
    client = anthropic.Anthropic(api_key=settings.api_key)
    response = client.messages.create(
        model=settings.model_id,
        max_tokens=4096,
        temperature=0,
        system=_ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(response.content[0].text)


async def diagnose_submission(
    facility_type: str,
    winning_patterns: dict,
    brief_data: dict,
    submission_data: dict,
) -> dict:
    return await asyncio.to_thread(
        _run_diagnose_sync, facility_type, winning_patterns, brief_data, submission_data
    )
