"""
run_harness.py — 추출 정확도 평가 CLI

사용법:
  # 캐시 사용 (LLM 비용 없음) — 이미 predicted_cache/ 에 결과가 있을 때
  python tools/eval/run_harness.py --skip-extraction

  # PDF 재추출 후 평가 (⚠️ LLM 비용 발생 ~$0.27/PDF)
  python tools/eval/run_harness.py --pdf-dir path/to/pdfs

  # 샘플 수 제한 + 특정 시설유형만
  python tools/eval/run_harness.py --pdf-dir pdfs/ --max-samples 5 --facility-type residential

  # 캐시 무시하고 전체 재추출
  python tools/eval/run_harness.py --pdf-dir pdfs/ --force-rerun
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_EVAL = Path(__file__).parent

sys.path.insert(0, str(_EVAL))

from lib.loaders import scan_ground_truth, load_predicted_cache, save_predicted_cache, load_tolerance
from lib.metrics import compare_pages, compare_quantitative, compare_categorical, aggregate


# ── 보고서 렌더링 ──────────────────────────────────────────────────────────────

def _md_table(headers: list[str], rows: list[list]) -> str:
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
              for i, h in enumerate(headers)]
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    head = "| " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    body = "\n".join(
        "| " + " | ".join(str(r[i]).ljust(widths[i]) for i in range(len(headers))) + " |"
        for r in rows
    )
    return f"{head}\n{sep}\n{body}"


def render_markdown(agg: dict, sample_results: list[dict], ts: str) -> str:
    lines = [
        f"# 추출 정확도 리포트",
        f"생성: {ts}  |  샘플: {agg.get('total_samples', 0)}건  "
        f"|  평가 페이지: {agg.get('total_pages_evaluated', 0)}",
        "",
        "---",
        "",
        "## 1. 요약 지표",
        "",
        _md_table(
            ["지표", "값"],
            [
                ["page_classification_accuracy (top-1)",
                 f"{agg.get('page_classification_accuracy_top1', 'N/A'):.3f}" if agg.get("page_classification_accuracy_top1") is not None else "N/A"],
                ["page_classification_accuracy (top-2)",
                 f"{agg.get('page_classification_accuracy_top2', 'N/A'):.3f}" if agg.get("page_classification_accuracy_top2") is not None else "N/A"],
                ["page_macro_f1",             f"{agg.get('page_macro_f1', 0):.3f}"],
                ["field_completion_rate",      f"{agg.get('field_completion_rate', 0):.3f}"],
                ["false_positive_rate (page)", f"{agg.get('false_positive_rate_page', 0):.3f}"],
                ["false_positive_rate (field환각)", f"{agg.get('false_positive_rate_field', 0):.3f}"],
                ["ambiguous_pages_excluded",   str(agg.get("ambiguous_pages_excluded", 0))],
            ],
        ),
        "",
        "### PDF 품질별 분류 정확도",
        "",
    ]
    qb = agg.get("quality_breakdown") or {}
    if qb:
        lines.append(_md_table(
            ["pdf_quality", "top1_accuracy"],
            [[q, f"{v:.3f}"] for q, v in sorted(qb.items())],
        ))
    else:
        lines.append("_(데이터 없음)_")

    lines += [
        "",
        "---",
        "",
        "## 2. 정량 필드별 일치율 / 오차",
        "",
    ]
    match_rates = agg.get("per_field_match_rate") or {}
    completion  = agg.get("per_field_completion") or {}
    mean_err    = agg.get("per_field_mean_rel_err_pct") or {}
    max_err     = agg.get("per_field_max_rel_err_pct") or {}
    all_fields  = sorted(set(match_rates) | set(completion))

    if all_fields:
        lines.append(_md_table(
            ["필드", "완성률", "일치율", "평균_상대오차_%", "최대_상대오차_%"],
            [
                [
                    f,
                    f"{completion.get(f, '—'):.3f}" if isinstance(completion.get(f), float) else "—",
                    f"{match_rates.get(f, '—'):.3f}" if isinstance(match_rates.get(f), float) else "—",
                    f"{mean_err.get(f, '—'):.2f}" if isinstance(mean_err.get(f), float) else "—",
                    f"{max_err.get(f, '—'):.2f}" if isinstance(max_err.get(f), float) else "—",
                ]
                for f in all_fields
            ],
        ))
    else:
        lines.append("_(정량 비교 데이터 없음 — GT에 quantitative_truth 채워넣기 필요)_")

    lines += [
        "",
        "### 범주형 필드 일치율",
        "",
    ]
    cat = agg.get("categorical_match_rate") or {}
    if cat:
        lines.append(_md_table(
            ["필드", "일치율"],
            [[f, f"{v:.3f}"] for f, v in sorted(cat.items())],
        ))
    else:
        lines.append("_(범주형 비교 데이터 없음)_")

    lines += [
        "",
        "---",
        "",
        "## 3. 페이지 유형별 F1",
        "",
    ]
    f1_rows = agg.get("per_type_f1") or []
    if f1_rows:
        lines.append(_md_table(
            ["유형", "TP", "FP", "FN", "precision", "recall", "F1"],
            [[r["type"], r["tp"], r["fp"], r["fn"], r["precision"], r["recall"], r["f1"]]
             for r in sorted(f1_rows, key=lambda x: x["f1"])],
        ))
    else:
        lines.append("_(페이지 분류 비교 데이터 없음 — GT에 pages_by_type 채워넣기 필요)_")

    lines += [
        "",
        "---",
        "",
        "## 4. 샘플별 요약",
        "",
        _md_table(
            ["competition_id", "slug", "ft", "quality", "page_top1", "field_comp", "field_fp"],
            [
                [
                    r["competition_id"], r["slug"],
                    r.get("facility_type", ""), r.get("pdf_quality", ""),
                    f"{r['page']['top1_correct']}/{r['page']['total']}",
                    f"{sum(1 for d in r['quantitative']['fields'].values() if d['completion'])}/"
                    f"{sum(1 for d in r['quantitative']['fields'].values() if d['gt_present'])}",
                    str(r["quantitative"].get("field_fp_count", 0)),
                ]
                for r in sample_results
            ],
        ) if sample_results else "_(샘플 없음)_",
        "",
        "---",
        "",
    ]

    lines += [
        "## 5. Brief competition analyzer.md §8 ACCURACY_METRICS 붙여넣기 블록",
        "",
        "```yaml",
        f"- page_classification_accuracy : "
        f"{agg.get('page_classification_accuracy_top1', 'TBD'):.3f} "
        f"(top-1, n={agg.get('total_pages_evaluated', '?')}p / "
        f"{agg.get('total_samples', '?')} PDFs, "
        f"macro_F1={agg.get('page_macro_f1', 'TBD'):.3f})"
        if agg.get("page_classification_accuracy_top1") is not None
        else "- page_classification_accuracy : TBD",
        f"- field_completion_rate        : "
        f"{agg.get('field_completion_rate', 0):.3f} overall"
        + _categorical_summary(cat),
        f"- field_match_rate (정량)      : "
        + "  ".join(f"{f}={v:.3f}" for f, v in sorted((agg.get("per_field_match_rate") or {}).items())),
        f"- false_positive_rate          : "
        f"{agg.get('false_positive_rate_page', 'TBD'):.3f} (page-level), "
        f"{agg.get('false_positive_rate_field', 'TBD'):.3f} (field-level 환각)"
        if agg.get("false_positive_rate_page") is not None
        else "- false_positive_rate          : TBD",
        f"- test_sample_count            : "
        f"{agg.get('total_samples', '?')} PDFs / ? competitions / ? facility types",
        f"- pdf_quality_distribution     : "
        + " / ".join(f"{q}={v:.3f}" for q, v in sorted(qb.items())),
        "- known_failure_modes          : 이미지 전용 스캔 PDF(텍스트 레이어 없음) /",
        "                                  비표준 면적표 레이아웃 /",
        "                                  재건축·일반 혼합 공모 오분류",
        "```",
    ]

    return "\n".join(lines)


def _categorical_summary(cat: dict) -> str:
    if not cat:
        return ""
    return " (" + ", ".join(f"{f}={v:.3f}" for f, v in sorted(cat.items())) + ")"


# ── 메인 ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="추출 정확도 평가 하네스",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--gt-dir", default=str(_EVAL / "ground_truth"),
                   help="Ground truth JSON 디렉터리 (기본: tools/eval/ground_truth/)")
    p.add_argument("--pdf-dir", default=None,
                   help="PDF 파일 디렉터리 (추출 필요 시). 미지정 시 GT 파일 옆에서 탐색.")
    p.add_argument("--cache-dir", default=str(_EVAL / "predicted_cache"),
                   help="예측 캐시 디렉터리 (기본: tools/eval/predicted_cache/)")
    p.add_argument("--output-dir", default=str(_EVAL / "reports"),
                   help="리포트 출력 디렉터리 (기본: tools/eval/reports/)")
    p.add_argument("--tolerance-file", default=str(_EVAL / "tolerance.json"),
                   help="허용 오차 설정 파일 (기본: tools/eval/tolerance.json)")
    p.add_argument("--max-samples", type=int, default=None,
                   help="처리할 최대 GT 샘플 수 (비용 제어용)")
    p.add_argument("--facility-type", default=None,
                   help="특정 시설유형만 평가 (예: residential)")
    p.add_argument("--skip-extraction", action="store_true",
                   help="LLM 추출 건너뜀 — 캐시만 사용. 캐시 없는 샘플은 스킵.")
    p.add_argument("--force-rerun", action="store_true",
                   help="캐시 무시하고 전체 재추출 ⚠️ LLM 비용 발생")
    return p.parse_args()


def _find_pdf(gt: dict, gt_file_dir: Path, pdf_dir: Path | None) -> Path | None:
    filename = (gt.get("meta") or {}).get("source_pdf", "")
    if not filename:
        return None
    candidates = [
        pdf_dir / filename if pdf_dir else None,
        gt_file_dir / filename,
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


def main():
    args = parse_args()
    gt_dir      = Path(args.gt_dir)
    cache_dir   = Path(args.cache_dir)
    output_dir  = Path(args.output_dir)
    tol_file    = Path(args.tolerance_file)
    pdf_dir     = Path(args.pdf_dir) if args.pdf_dir else None

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Competition Analyzer — 추출 정확도 평가 하네스")
    print("=" * 60)
    print(f"GT 디렉터리   : {gt_dir}")
    print(f"캐시 디렉터리 : {cache_dir}")
    print(f"출력 디렉터리 : {output_dir}")
    if args.skip_extraction:
        print("모드          : 캐시 전용 (LLM 호출 없음)")
    elif args.force_rerun:
        print("모드          : 전체 재추출 ⚠️ LLM 비용 발생")
    else:
        print("모드          : 캐시 우선 (캐시 없으면 추출 ⚠️)")
    if args.max_samples:
        print(f"샘플 제한     : {args.max_samples}건")
    print()

    tolerance = load_tolerance(tol_file)

    gt_samples = list(scan_ground_truth(gt_dir, facility_type=args.facility_type))
    if not gt_samples:
        print("[ERROR] GT 파일을 찾을 수 없습니다.")
        print(f"  {gt_dir} 하위에 *_gt.json 파일을 만들어주세요.")
        print(f"  템플릿: {gt_dir}/TEMPLATE_gt.json")
        sys.exit(1)

    if args.max_samples:
        gt_samples = gt_samples[:args.max_samples]

    print(f"GT 샘플 {len(gt_samples)}건 로드 완료")
    print()

    # ── 파이프라인 import (추출 모드 시만) ──
    if not args.skip_extraction:
        from run_pipeline import get_or_extract

    sample_results = []
    skipped = 0

    for i, (comp_id, slug, gt) in enumerate(gt_samples, 1):
        print(f"[{i}/{len(gt_samples)}] {comp_id} / {slug}")
        facility_type = (gt.get("meta") or {}).get("facility_type", "unknown")

        # predicted 로드 또는 추출
        if args.skip_extraction:
            pred = load_predicted_cache(cache_dir, comp_id, slug)
            if pred is None:
                print(f"  [SKIP] 캐시 없음 — --skip-extraction 모드")
                skipped += 1
                continue
            print(f"  [cache] {comp_id}_{slug}.json")
        else:
            gt_file_dir = gt_dir / facility_type / comp_id
            pdf_path = _find_pdf(gt, gt_file_dir, pdf_dir)
            cache_path = cache_dir / f"{comp_id}_{slug}.json"

            if pdf_path is None and not cache_path.exists():
                print(f"  [SKIP] PDF 파일 없음: {(gt.get('meta') or {}).get('source_pdf', '?')}")
                skipped += 1
                continue

            if pdf_path and (args.force_rerun or not cache_path.exists()):
                pred = get_or_extract(pdf_path, facility_type, cache_path, force=args.force_rerun)
            else:
                pred = load_predicted_cache(cache_dir, comp_id, slug)
                if pred is None:
                    print(f"  [SKIP] 캐시도 없고 PDF도 없음")
                    skipped += 1
                    continue
                print(f"  [cache] {comp_id}_{slug}.json")

        # 비교
        page_cmp  = compare_pages(gt, pred)
        quant_cmp = compare_quantitative(gt, pred, tolerance)
        cat_cmp   = compare_categorical(gt, pred, tolerance)

        pt = page_cmp["total"]
        p1 = page_cmp["top1_correct"]
        print(f"  page  top1={p1}/{pt} ({p1/pt:.1%} )" if pt else "  page  n/a")
        comp_n = sum(1 for d in quant_cmp["fields"].values() if d["completion"])
        pres_n = sum(1 for d in quant_cmp["fields"].values() if d["gt_present"])
        print(f"  quant completion={comp_n}/{pres_n}  FP={quant_cmp['field_fp_count']}")

        sample_results.append({
            "competition_id": comp_id,
            "slug": slug,
            "facility_type": facility_type,
            "pdf_quality": (gt.get("meta") or {}).get("pdf_quality", "unknown"),
            "page": page_cmp,
            "quantitative": quant_cmp,
            "categorical": cat_cmp,
        })

    print()
    print(f"처리 완료: {len(sample_results)}건  /  스킵: {skipped}건")

    if not sample_results:
        print("[WARN] 비교 결과가 없습니다. GT 파일과 캐시/PDF를 확인하세요.")
        sys.exit(0)

    # ── 집계 ──
    agg = aggregate(sample_results)

    print()
    print("── 집계 결과 ──────────────────────────────────────")
    print(f"  page top-1 accuracy : {agg.get('page_classification_accuracy_top1', 'N/A')}")
    print(f"  field completion    : {agg.get('field_completion_rate', 'N/A')}")
    print(f"  FP (page/field)     : {agg.get('false_positive_rate_page', 'N/A')} / "
          f"{agg.get('false_positive_rate_field', 'N/A')}")

    # ── 저장 ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_path = output_dir / f"{ts}_summary.json"
    summary_path.write_text(
        json.dumps({"generated_at": ts, "aggregate": agg}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    per_sample_path = output_dir / f"{ts}_per_sample.json"
    # misclassified 리스트를 포함하되 page_map은 제외 (파일 크기 절감)
    per_sample_path.write_text(
        json.dumps({"generated_at": ts, "samples": sample_results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_md = render_markdown(agg, sample_results, ts)
    report_path = output_dir / f"{ts}_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    brief_block = _extract_brief_block(report_md)
    brief_path = output_dir / f"{ts}_brief_block.md"
    brief_path.write_text(brief_block, encoding="utf-8")

    print()
    print("── 출력 파일 ──────────────────────────────────────")
    print(f"  {summary_path}")
    print(f"  {per_sample_path}")
    print(f"  {report_path}")
    print(f"  {brief_path}  ← Brief competition analyzer.md §8에 붙여넣기")
    print()


def _extract_brief_block(md: str) -> str:
    marker = "## 5. Brief competition analyzer.md §8 ACCURACY_METRICS 붙여넣기 블록"
    idx = md.find(marker)
    if idx == -1:
        return md
    return md[idx:]


if __name__ == "__main__":
    main()
