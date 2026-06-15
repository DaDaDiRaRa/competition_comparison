"""
comparators.py — 정량·범주형 필드 비교 헬퍼
"""
from __future__ import annotations
import re
from typing import Any


# ── 정량 비교 ──────────────────────────────────────────────────────────────────

def numeric_compare(pred: Any, gt: Any, abs_tol: float, rel_tol: float) -> dict:
    """
    abs_tol OR rel_tol 중 하나라도 만족하면 match=True.
    반환: {match, abs_err, rel_err, pred, gt}
      match=None  → 둘 중 하나가 없어서 비교 불가
    """
    if pred is None or gt is None:
        return {"match": None, "abs_err": None, "rel_err": None, "pred": pred, "gt": gt}
    try:
        p, g = float(pred), float(gt)
    except (TypeError, ValueError):
        return {"match": False, "abs_err": None, "rel_err": None, "pred": pred, "gt": gt}

    abs_err = abs(p - g)
    rel_err = abs_err / abs(g) if g != 0 else (0.0 if abs_err == 0 else float("inf"))
    match = (abs_tol >= 0 and abs_err <= abs_tol) or (rel_tol > 0 and rel_err <= rel_tol)
    return {
        "match": bool(match),
        "abs_err": round(abs_err, 3),
        "rel_err": round(rel_err, 4),
        "pred": p,
        "gt": g,
    }


# ── 범주형 비교 ────────────────────────────────────────────────────────────────

_STRUCTURE_KEYWORDS: dict[str, list[str]] = {
    "RC":  ["RC", "철근콘크리트", "RC조", "r.c", "reinforced concrete"],
    "SRC": ["SRC", "철골철근콘크리트"],
    "철골": ["철골", "강구조", "SS", "S조", "steel"],
    "CFT": ["CFT", "충전형강관"],
    "PC":  ["PC", "프리캐스트", "precast"],
    "목구조": ["목구조", "CLT", "목조", "timber"],
}


def _normalize(s: str) -> str:
    s = re.sub(r"\s+", "", str(s or ""))
    return re.sub(r"[^\w가-힣]", "", s).lower()


def _to_set(v: Any) -> set[str]:
    if isinstance(v, list):
        return {_normalize(x) for x in v if x}
    return {_normalize(x) for x in re.split(r"[,·\s/]+", str(v or "")) if x.strip()}


def jaccard(a: Any, b: Any) -> float:
    sa, sb = _to_set(a), _to_set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _keyword_match(pred: str, gt: str) -> bool:
    pred_n = _normalize(pred)
    gt_n = _normalize(gt)
    for canonical, aliases in _STRUCTURE_KEYWORDS.items():
        if any(_normalize(a) in gt_n for a in aliases):
            return any(_normalize(a) in pred_n for a in aliases)
    return pred_n == gt_n


def categorical_compare(pred: Any, gt: Any, method: str, threshold: float = 0.6) -> dict:
    """
    반환: {match, similarity, pred, gt}
      match=None → 둘 중 하나가 없어서 비교 불가
    """
    if pred is None or gt is None:
        return {"match": None, "similarity": None, "pred": pred, "gt": gt}

    if method in ("exact", "normalize"):
        m = _normalize(str(pred)) == _normalize(str(gt))
        return {"match": m, "similarity": 1.0 if m else 0.0, "pred": pred, "gt": gt}

    if method == "keyword":
        m = _keyword_match(str(pred), str(gt))
        return {"match": m, "similarity": 1.0 if m else 0.0, "pred": pred, "gt": gt}

    if method == "jaccard":
        sim = jaccard(pred, gt)
        return {"match": sim >= threshold, "similarity": round(sim, 3), "pred": pred, "gt": gt}

    return {"match": False, "similarity": 0.0, "pred": pred, "gt": gt}
