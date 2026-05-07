import statistics
from collections import Counter

from services.db_manager import get_winning_submissions, save_pattern


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


def build_pattern(facility_type: str) -> dict:
    winners = get_winning_submissions(facility_type)
    if not winners:
        return {
            "facility_type": facility_type,
            "win_count": 0,
            "patterns": {},
        }

    pattern = {
        "facility_type": facility_type,
        "win_count": len(winners),
        "page_distribution": _build_page_distribution_stats(winners),
        "quantitative": _build_quant_stats(winners),
        "concept_keywords": _build_keyword_freq(winners),
        "mass_types": _build_mass_type_dist(winners),
    }
    save_pattern(facility_type, pattern)
    return pattern
