"""
metrics.py — (gt, pred) 쌍 비교 + 전체 집계
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from .comparators import numeric_compare, categorical_compare


# ── 페이지 분류 비교 ───────────────────────────────────────────────────────────

def compare_pages(gt: dict, pred: dict) -> dict:
    """
    gt["pages_by_type"]  vs  pred["page_map"]
    page_map 엔트리: {page, primary_type, secondary_type, confidence, ...}

    top-2: primary_type 또는 secondary_type이 정답이면 correct.
    _ambiguous 목록의 페이지는 분모에서 제외.
    """
    gt_page_type: dict[int, str] = {}
    for ptype, pages in (gt.get("pages_by_type") or {}).items():
        if ptype.startswith("_") or not isinstance(pages, list):
            continue
        for p in pages:
            if isinstance(p, int):
                gt_page_type[p] = ptype

    ambiguous = {
        item["page"]
        for item in (gt.get("pages_by_type") or {}).get("_ambiguous", [])
        if isinstance(item, dict) and "page" in item
    }

    pred_map: dict[int, dict] = {}
    for entry in (pred.get("page_map") or []):
        pnum = entry.get("page")
        if pnum is not None:
            pred_map[pnum] = entry

    top1_correct = top2_correct = total = 0
    per_type: dict[str, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    misclassified: list[dict] = []

    for page_num, gt_type in gt_page_type.items():
        if page_num in ambiguous:
            continue
        total += 1
        entry = pred_map.get(page_num, {})
        pred_primary = entry.get("primary_type")
        pred_secondary = entry.get("secondary_type")

        if pred_primary == gt_type:
            top1_correct += 1
            top2_correct += 1
            per_type[gt_type]["tp"] += 1
        elif pred_secondary == gt_type:
            top2_correct += 1
            per_type[gt_type]["fn"] += 1
            if pred_primary:
                per_type[pred_primary]["fp"] += 1
            misclassified.append({
                "page": page_num, "gt": gt_type,
                "pred_primary": pred_primary, "pred_secondary": pred_secondary,
                "top1_miss": True, "top2_hit": True,
            })
        else:
            per_type[gt_type]["fn"] += 1
            if pred_primary:
                per_type[pred_primary]["fp"] += 1
            misclassified.append({
                "page": page_num, "gt": gt_type,
                "pred_primary": pred_primary, "pred_secondary": pred_secondary,
                "top1_miss": True, "top2_hit": False,
            })

    return {
        "top1_correct": top1_correct,
        "top2_correct": top2_correct,
        "total": total,
        "ambiguous_excluded": len(ambiguous & set(gt_page_type.keys())),
        "per_type": {k: dict(v) for k, v in per_type.items()},
        "misclassified": misclassified,
    }


# ── 정량 비교 ──────────────────────────────────────────────────────────────────

def compare_quantitative(gt: dict, pred: dict, tolerances: dict) -> dict:
    """
    gt["quantitative_truth"] + gt["field_presence"]  vs  pred["_quantitative"]
    """
    qt = gt.get("quantitative_truth") or {}
    fp_flags = gt.get("field_presence") or {}
    pred_q = pred.get("_quantitative") or {}
    num_tol = tolerances.get("numeric") or {}

    all_fields = set(qt.keys()) | {k for k, v in fp_flags.items() if v and not k.startswith("_")}
    field_fp_count = 0
    results: dict[str, dict] = {}

    for field in all_fields:
        if field.startswith("_"):
            continue
        gt_truth = qt.get(field)
        gt_val = gt_truth.get("value") if isinstance(gt_truth, dict) else gt_truth
        pred_val = pred_q.get(field)
        gt_present = fp_flags.get(field, field in qt)

        tol = num_tol.get(field, {})
        cmp = numeric_compare(pred_val, gt_val, tol.get("abs", 0.0), tol.get("rel", 0.0))
        cmp["gt_present"] = bool(gt_present)
        cmp["pred_present"] = pred_val is not None
        cmp["completion"] = bool(gt_present and pred_val is not None)
        cmp["fp"] = bool(not gt_present and pred_val is not None)
        if cmp["fp"]:
            field_fp_count += 1
        results[field] = cmp

    return {"fields": results, "field_fp_count": field_fp_count}


# ── 범주형 비교 ────────────────────────────────────────────────────────────────

def _flatten_categorical(pred: dict) -> dict[str, Any]:
    """extracted_data 전체를 순회해 범주형 필드 수집."""
    target_keys = {"structure_system", "zoning", "mass_type", "certification", "concept_keywords"}
    found: dict[str, Any] = {}
    ext = pred.get("extracted_data") or {}
    for section in ext.values():
        items = section if isinstance(section, list) else [section]
        for item in items:
            if not isinstance(item, dict):
                continue
            for k in target_keys:
                if k in item and k not in found:
                    found[k] = item[k]
    # Also check top-level keys (merge_extracted_data stores by type_key)
    for section_key, section_val in pred.items():
        if section_key.startswith("_") or not isinstance(section_val, (dict, list)):
            continue
        items = section_val if isinstance(section_val, list) else [section_val]
        for item in items:
            if not isinstance(item, dict):
                continue
            for k in target_keys:
                if k in item and k not in found:
                    found[k] = item[k]
    return found


def compare_categorical(gt: dict, pred: dict, tolerances: dict) -> dict:
    gt_cat = gt.get("categorical_truth") or {}
    pred_cat = _flatten_categorical(pred)
    cat_tol = tolerances.get("categorical") or {}
    results: dict[str, dict] = {}

    for field, gt_val in gt_cat.items():
        if field.startswith("_") or gt_val is None:
            continue
        pred_val = pred_cat.get(field)
        cfg = cat_tol.get(field, {})
        cmp = categorical_compare(pred_val, gt_val, cfg.get("method", "exact"), cfg.get("threshold", 0.6))
        results[field] = cmp

    return {"fields": results}


# ── 전체 집계 ──────────────────────────────────────────────────────────────────

def aggregate(sample_results: list[dict]) -> dict:
    """샘플별 결과 리스트 → ACCURACY_METRICS에 채울 수치 dict."""
    if not sample_results:
        return {}

    # ── 페이지 분류 ──
    total_pages = sum(r["page"]["total"] for r in sample_results)
    top1_c = sum(r["page"]["top1_correct"] for r in sample_results)
    top2_c = sum(r["page"]["top2_correct"] for r in sample_results)
    ambig_ex = sum(r["page"]["ambiguous_excluded"] for r in sample_results)

    type_stats: dict[str, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for r in sample_results:
        for ptype, s in r["page"].get("per_type", {}).items():
            type_stats[ptype]["tp"] += s["tp"]
            type_stats[ptype]["fp"] += s["fp"]
            type_stats[ptype]["fn"] += s["fn"]

    per_type_f1 = []
    for ptype, s in sorted(type_stats.items()):
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_type_f1.append({
            "type": ptype, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
        })
    macro_f1 = (sum(x["f1"] for x in per_type_f1) / len(per_type_f1)) if per_type_f1 else 0.0

    # ── 정량 완성률 + 일치율 ──
    num_completion: dict[str, list[int]] = defaultdict(list)
    num_match: dict[str, list[int]] = defaultdict(list)
    num_abs_err: dict[str, list[float]] = defaultdict(list)
    num_rel_err: dict[str, list[float]] = defaultdict(list)
    total_gt_absent = 0
    total_field_fp = 0

    for r in sample_results:
        for field, d in r["quantitative"].get("fields", {}).items():
            if d["gt_present"]:
                num_completion[field].append(1 if d["pred_present"] else 0)
            if d.get("match") is not None:
                num_match[field].append(1 if d["match"] else 0)
            if d.get("abs_err") is not None:
                num_abs_err[field].append(d["abs_err"])
            if d.get("rel_err") is not None and d["rel_err"] != float("inf"):
                num_rel_err[field].append(d["rel_err"])
            if not d["gt_present"]:
                total_gt_absent += 1
        total_field_fp += r["quantitative"].get("field_fp_count", 0)

    all_comp_vals = [v for vals in num_completion.values() for v in vals]
    field_completion_rate = sum(all_comp_vals) / len(all_comp_vals) if all_comp_vals else 0.0
    per_field_completion = {f: round(sum(v)/len(v), 3) for f, v in num_completion.items() if v}
    per_field_match = {f: round(sum(v)/len(v), 3) for f, v in num_match.items() if v}
    per_field_mean_rel_err = {f: round(sum(v)/len(v)*100, 2) for f, v in num_rel_err.items() if v}
    per_field_max_rel_err  = {f: round(max(v)*100, 2) for f, v in num_rel_err.items() if v}

    # ── 범주형 일치율 ──
    cat_match: dict[str, list[int]] = defaultdict(list)
    for r in sample_results:
        for field, d in r.get("categorical", {}).get("fields", {}).items():
            if d.get("match") is not None:
                cat_match[field].append(1 if d["match"] else 0)
    per_cat_match = {f: round(sum(v)/len(v), 3) for f, v in cat_match.items() if v}

    # ── FP 비율 ──
    total_pred_fp_pages = sum(s["fp"] for s in type_stats.values())
    page_fp_rate = total_pred_fp_pages / total_pages if total_pages > 0 else 0.0
    field_fp_rate = total_field_fp / total_gt_absent if total_gt_absent > 0 else 0.0

    # ── PDF 품질별 분류 정확도 ──
    quality_groups: dict[str, list] = defaultdict(list)
    for r in sample_results:
        q = r.get("pdf_quality", "unknown")
        if r["page"]["total"] > 0:
            quality_groups[q].append(r["page"]["top1_correct"] / r["page"]["total"])
    quality_acc = {q: round(sum(v)/len(v), 3) for q, v in quality_groups.items()}

    return {
        "page_classification_accuracy_top1": round(top1_c / total_pages, 3) if total_pages else None,
        "page_classification_accuracy_top2": round(top2_c / total_pages, 3) if total_pages else None,
        "page_macro_f1": round(macro_f1, 3),
        "per_type_f1": sorted(per_type_f1, key=lambda x: x["f1"]),
        "field_completion_rate": round(field_completion_rate, 3),
        "per_field_completion": per_field_completion,
        "per_field_match_rate": per_field_match,
        "per_field_mean_rel_err_pct": per_field_mean_rel_err,
        "per_field_max_rel_err_pct": per_field_max_rel_err,
        "categorical_match_rate": per_cat_match,
        "false_positive_rate_page": round(page_fp_rate, 3),
        "false_positive_rate_field": round(field_fp_rate, 3),
        "total_pages_evaluated": total_pages,
        "ambiguous_pages_excluded": ambig_ex,
        "total_samples": len(sample_results),
        "quality_breakdown": quality_acc,
    }
