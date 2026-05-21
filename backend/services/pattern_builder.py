import json
import statistics
from collections import Counter

from config import settings
from services.db_manager import get_winning_submissions, get_losing_submissions, save_pattern, list_projects, load_comparison
from services.llm_client import call_messages
from services.utils import parse_json_response


def _mean_std(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "std": None, "n": 0}
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean, 2), "std": round(std, 2), "n": len(values)}


def _build_page_distribution_stats(submissions: list[dict]) -> dict:
    all_types: list[str] = []
    distributions: dict[str, list[int]] = {}

    for sub in submissions:
        dist = sub.get("page_distribution", {})
        total = sub.get("total_pages", 0) or 1
        for pt, count in dist.items():
            if pt not in distributions:
                distributions[pt] = []
            distributions[pt].append(count)
            # Ratio version
            ratio_key = f"{pt}_ratio"
            if ratio_key not in distributions:
                distributions[ratio_key] = []
            distributions[ratio_key].append(round(count / total, 3))

    return {k: _mean_std(v) for k, v in distributions.items()}


def _build_quant_stats(submissions: list[dict]) -> dict:
    fields = [
        "total_floor_area_sqm", "site_area_sqm", "building_area_sqm",
        "floor_area_ratio_pct", "building_coverage_ratio_pct",
        "floors_above", "floors_below", "parking_count",
    ]
    collected: dict[str, list[float]] = {f: [] for f in fields}
    for sub in submissions:
        quant = sub.get("extracted_data", {}).get("_quantitative", {})
        for f in fields:
            val = quant.get(f)
            if val is not None:
                try:
                    collected[f].append(float(val))
                except (TypeError, ValueError):
                    pass
    return {f: _mean_std(v) for f, v in collected.items() if v}


def _build_keyword_freq(submissions: list[dict]) -> dict:
    counter: Counter = Counter()
    for sub in submissions:
        concept = sub.get("extracted_data", {}).get("concept", {})
        if isinstance(concept, list):
            concept = concept[0] if concept else {}
        for kw in concept.get("keywords", []):
            counter[kw] += 1
    total = len(submissions)
    return {kw: round(count / total, 2) for kw, count in counter.most_common(20)}


def _build_mass_type_dist(submissions: list[dict]) -> dict:
    counter: Counter = Counter()
    for sub in submissions:
        concept = sub.get("extracted_data", {}).get("concept", {})
        if isinstance(concept, list):
            concept = concept[0] if concept else {}
        mt = concept.get("mass_type")
        if mt:
            counter[mt] += 1
    total = len(submissions) or 1
    return {k: round(v / total, 2) for k, v in counter.items()}


_QUALITATIVE_SYSTEM = (
    "You are an architectural competition analyst. "
    "Summarize recurring patterns from multiple past competitions. "
    "Respond ONLY in JSON. Use Korean for all text fields."
)

_QUALITATIVE_PROMPT_TEMPLATE = """\
TASK: summarize_qualitative_patterns
FACILITY_TYPE: {facility_type}
N_COMPETITIONS: {n}

RAW_INSIGHTS (from {n} past competitions):
{insights_json}

Identify the TOP-5 recurring patterns in each category.
Be specific and actionable (~30 chars each in Korean).

OUTPUT_ONLY_JSON:
{
  "winner_patterns": ["<top_5_recurring_winner_strengths>"],
  "loser_patterns": ["<top_5_recurring_loser_weaknesses>"],
  "key_differentiators": ["<top_5_factors_separating_winners>"]
}"""


def _collect_comparison_insights(facility_type: str) -> list[dict]:
    """facility_type의 모든 _comparison.json에서 qualitative 인사이트를 수집."""
    insights = []
    for proj in list_projects(facility_type):
        comp_id = proj.get("competition_id", "")
        if not comp_id:
            continue
        comp = load_comparison(facility_type, comp_id)
        if not comp:
            continue
        entry = {
            "competition_name": proj.get("competition_name", comp_id),
            "winner_strengths": comp.get("winner_strengths", []),
            "loser_weaknesses": comp.get("loser_weaknesses", []),
            "key_differentiators": comp.get("key_differentiators", []),
        }
        if entry["winner_strengths"] or entry["loser_weaknesses"]:
            insights.append(entry)
    return insights


def _summarize_qualitative_insights(facility_type: str, raw_insights: list[dict]) -> dict:
    """과거 비교분석 결과를 LLM으로 요약해 재사용 가능한 패턴으로 압축."""
    if not raw_insights:
        return {"winner_patterns": [], "loser_patterns": [], "key_differentiators": []}
    prompt = (_QUALITATIVE_PROMPT_TEMPLATE
              .replace("{facility_type}", facility_type)
              .replace("{n}", str(len(raw_insights)))
              .replace("{insights_json}",
                       json.dumps(raw_insights, ensure_ascii=False, separators=(",", ":"))))
    try:
        raw = call_messages(
            model=settings.model_id_classify,
            max_tokens=2000,
            temperature=0,
            system=_QUALITATIVE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json_response(raw)
    except Exception:
        return {"winner_patterns": [], "loser_patterns": [], "key_differentiators": []}


def build_pattern_from_submissions(facility_type: str, submissions: list[dict]) -> dict:
    """제출물 리스트(승자/특정 선택 모두)로부터 패턴 통계 생성. 디스크 저장 안 함."""
    if not submissions:
        return {"facility_type": facility_type, "win_count": 0, "patterns": {}}
    return {
        "facility_type": facility_type,
        "win_count": len(submissions),
        "page_distribution": _build_page_distribution_stats(submissions),
        "quantitative": _build_quant_stats(submissions),
        "concept_keywords": _build_keyword_freq(submissions),
        "mass_types": _build_mass_type_dist(submissions),
    }


def build_pattern(facility_type: str) -> dict:
    winners = get_winning_submissions(facility_type)
    pattern = build_pattern_from_submissions(facility_type, winners)
    if winners:
        raw_insights = _collect_comparison_insights(facility_type)
        if raw_insights:
            pattern["qualitative_insights"] = _summarize_qualitative_insights(
                facility_type, raw_insights
            )

        losers = get_losing_submissions(facility_type)
        if losers:
            pattern["loser_stats"] = {
                "lose_count": len(losers),
                "page_distribution": _build_page_distribution_stats(losers),
                "quantitative": _build_quant_stats(losers),
                "concept_keywords": _build_keyword_freq(losers),
            }

        save_pattern(facility_type, pattern)
    return pattern
