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

# ── 3단계 표시 라벨 (내부는 A~E 유지, 임원용 표시만 단어) ──────────────────────
# A~E 5단계는 순위·차별화·패턴 계산의 내부 신호로 그대로 두고, 리포트/UI 뱃지에만
# 우수/보통/미흡 3단계를 노출한다(임원 정밀도 논쟁 최소화, 2026-07 임원 요청).
# 같은 단어에 다른 색이 붙지 않도록 색도 3단계로 collapse (우수=A색·보통=C색·미흡=E색).
GRADE_LABEL_3: dict[str, str] = {"A": "우수", "B": "우수", "C": "보통", "D": "미흡", "E": "미흡"}
_LABEL_COLOR_KEY: dict[str, str] = {"A": "A", "B": "A", "C": "C", "D": "E", "E": "E"}


def grade_label(grade) -> str:
    """A~E → '우수|보통|미흡' 표시 라벨. 알 수 없으면 ''."""
    return GRADE_LABEL_3.get(grade, "")


def grade_label_colors(grade) -> tuple[str, str]:
    """3단계 라벨 색 (fg, bg). 우수=초록·보통=앰버·미흡=빨강. 알 수 없으면 회색."""
    return GRADE_COLORS.get(_LABEL_COLOR_KEY.get(grade, ""), ("#6b7280", "#f3f4f6"))


def grade_label_ring(grade) -> str:
    """3단계 라벨 링/전경색."""
    return grade_label_colors(grade)[0]


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
