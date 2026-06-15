"""Shared grade helpers — no LLM calls, no HTML rendering."""
from __future__ import annotations

LEGACY_GRADE_MAP: dict[str, str] = {"상": "B", "중": "C", "하": "D"}

# (foreground, background) tuples — used by all three report generators
GRADE_COLORS: dict[str, tuple[str, str]] = {
    "A": ("#16a34a", "#dcfce7"),
    "B": ("#0891b2", "#cffafe"),
    "C": ("#ca8a04", "#fef3c7"),
    "D": ("#ea580c", "#fed7aa"),
    "E": ("#dc2626", "#fee2e2"),
}

# fg-only variant — used by diagnosis ring/donut charts
GRADE_RING_COLORS: dict[str, str] = {k: fg for k, (fg, _) in GRADE_COLORS.items()}


def to_grade(d, *, check_overall: bool = False) -> str | None:
    """Extract A-E grade from an axis or diagnosis dict.

    check_overall=True  → also checks overall_grade / overall_score keys
                          (used by diagnosis_report_generator for top-level diagnosis dicts)
    check_overall=False → axis dicts only have grade / score
                          (used by report_generator and myproject_report_generator)
    """
    if not isinstance(d, dict):
        return None
    g = d.get("grade")
    if check_overall and not g:
        g = d.get("overall_grade")
    if g in ("A", "B", "C", "D", "E"):
        return g
    if g in LEGACY_GRADE_MAP:
        return LEGACY_GRADE_MAP[g]
    s = d.get("score")
    if check_overall and s is None:
        s = d.get("overall_score")
    if s is None:
        return None
    try:
        s = float(s)
    except (TypeError, ValueError):
        return None
    if s >= 8.5:
        return "A"
    if s >= 7.0:
        return "B"
    if s >= 5.0:
        return "C"
    if s >= 3.0:
        return "D"
    return "E"
