"""
data_health.py — 운영 DB(또는 스냅샷) 무결성 건강검진 (API 호출 없음, LLM 0콜)

제출물 `_quantitative` 내부 정합성 + 결측 맵 + comparison 스키마/rubric 드리프트
+ 패턴 지표별 표본수(N) 갭을 한 번에 점검한다. 추출·비교가 데이터를 쌓을수록
무료로 반복 실행해 "환각 수치·구버전 드리프트가 패턴에 유입되기 전" 잡는 용도.

설계 원칙:
- 읽기 전용. 어떤 파일도 수정/생성하지 않는다 (리포트만 stdout).
- LLM 0콜. 전부 결정론 산술/스키마 검사.
- 관대하게 (영등포 false-positive 교훈): 명백한 모순만 "결함", 나머지는 "경고".
- HARD 결함(수치 모순 + 인용 범위초과) 개수를 exit code 로 반환 → CI 훅 가능.

usage:
    backend\\venv\\Scripts\\python.exe tools\\data_health.py [--db-path PATH]
    # --db-path 생략 시 config.settings.db_path (Cloud Run 에선 /data = 버킷 마운트)
"""
import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

# 허용 범위 (관대하게 — 명백히 비현실적인 값만 잡는다)
BOUNDS = {
    "building_coverage_ratio_pct": (0, 100),
    "floor_area_ratio_pct": (0, 1500),
    "floors_above": (0, 120),
    "floors_below": (0, 12),
    "parking_count": (0, 50000),
}
COVERAGE_TOL_PP = 3.0   # 건폐율 입력값 vs 계산값 허용 오차(%p)
FAR_TOL_PP = 5.0        # 용적률 입력값 vs 계산값 허용 오차(%p)
QUANT_FIELDS = [
    "site_area_sqm", "building_area_sqm", "total_floor_area_sqm",
    "building_coverage_ratio_pct", "floor_area_ratio_pct",
    "floors_above", "floors_below", "parking_count",
]
CITE_RE = re.compile(r"\(p\.?\s*([0-9][0-9,\s]*|\?)\)")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _prefix_of(fname):
    stem = os.path.basename(fname)[:-5]  # drop .json
    for suf in ("_win", "_lose", "_contracted"):
        if stem.endswith(suf):
            return stem[:-len(suf)]
    return stem


def _competition_dirs(db):
    out = []
    for ft in sorted(os.listdir(db)):
        ftp = os.path.join(db, ft)
        if not os.path.isdir(ftp) or ft.startswith("_"):
            continue
        for comp in sorted(os.listdir(ftp)):
            cp = os.path.join(ftp, comp)
            if os.path.isdir(cp):
                out.append((ft, comp, cp))
    return out


def check_numeric(db):
    """A. submission별 _quantitative 내부 정합성 + 결측 맵."""
    defects, warns, rows, subs = [], [], [], {}
    for ft, comp, cp in _competition_dirs(db):
        subdir = os.path.join(cp, "submissions")
        if not os.path.isdir(subdir):
            continue
        for f in sorted(glob.glob(os.path.join(subdir, "*.json"))):
            if f.endswith("_deep.json") or "_report" in f:
                continue
            try:
                sub = json.load(open(f, encoding="utf-8"))
            except Exception as e:
                warns.append(f"[로드실패] {f}: {e}")
                continue
            q = (sub.get("extracted_data", {}) or {}).get("_quantitative", {}) or {}
            tp = sub.get("total_pages")
            pfx = _prefix_of(f)
            subs[(ft, comp, pfx)] = {"q": q, "total_pages": tp, "result": sub.get("result")}
            tag = f"{ft}/{comp[:18]}/{pfx}({sub.get('result')})"

            sa, ba = _num(q.get("site_area_sqm")), _num(q.get("building_area_sqm"))
            tfa, aag = _num(q.get("total_floor_area_sqm")), _num(q.get("area_above_ground_sqm"))
            cov, far = _num(q.get("building_coverage_ratio_pct")), _num(q.get("floor_area_ratio_pct"))

            # 1) 건축면적 > 대지면적 (물리적 불가)
            if sa and ba and ba > sa * 1.02:
                defects.append(f"[건축>대지] {tag}: 건축 {ba:,.0f} > 대지 {sa:,.0f}㎡")
            # 2) 건폐율 = 100×건축/대지 교차검증
            if sa and ba and cov is not None:
                calc = 100.0 * ba / sa
                if abs(calc - cov) > COVERAGE_TOL_PP:
                    defects.append(f"[건폐율 모순] {tag}: 입력 {cov}% vs 계산 {calc:.1f}% "
                                   f"(건축{ba:,.0f}/대지{sa:,.0f})")
            # 3) 용적률 정합성: 지상연면적(있으면) = 100×용적률/대지
            if sa and far is not None and aag:
                calc = 100.0 * aag / sa
                if abs(calc - far) > FAR_TOL_PP:
                    defects.append(f"[용적률 모순] {tag}: 입력 {far}% vs 지상연면적 기준 {calc:.1f}%")
            # 3b) 지상연면적 없으면: 총연면적 >= 용적률 함의 지상면적 이어야 (총>=지상)
            elif sa and far is not None and tfa:
                implied_above = far / 100.0 * sa
                if tfa < implied_above * 0.9:
                    defects.append(f"[연면적<용적률함의] {tag}: 총연면적 {tfa:,.0f} < "
                                   f"용적률 함의 지상면적 {implied_above:,.0f}㎡ (용적률 {far}%×대지)")
            # 4) 범위
            for fld, (lo, hi) in BOUNDS.items():
                v = _num(q.get(fld))
                if v is not None and not (lo <= v <= hi):
                    defects.append(f"[범위초과] {tag}: {fld}={v} (허용 {lo}~{hi})")
            # 5) 건폐율 > 용적률 (다층이면 비정상)
            if cov is not None and far is not None and cov > far + 1:
                warns.append(f"[건폐율>용적률] {tag}: 건폐율 {cov}% > 용적률 {far}%")

            rows.append((ft, pfx, sub.get("result"), q))
    return defects, warns, rows, subs


def check_drift(db, subs):
    """B. comparison별 스키마/rubric 드리프트 + 인용 무결성."""
    defects, lines = [], []
    for ft, comp, cp in _competition_dirs(db):
        cf = os.path.join(cp, "_comparison.json")
        if not os.path.exists(cf):
            continue
        c = json.load(open(cf, encoding="utf-8"))
        cmp_subs = c.get("submissions", {}) or {}
        tpmap = {pfx: v["total_pages"] for (a, b, pfx), v in subs.items() if a == ft and b == comp}
        fmt = "?"
        cite_tot = cite_bad = sw_items = 0
        for company, axes in cmp_subs.items():
            if not isinstance(axes, dict):
                continue
            tp = tpmap.get(company)
            for ax in axes.values():
                if not isinstance(ax, dict):
                    continue
                if "grade" in ax:
                    fmt = "grade(A-E)"
                elif "score" in ax:
                    fmt = "score(0-10)"
                for fld in ("strengths", "weaknesses"):
                    items = ax.get(fld, []) or []
                    sw_items += len(items)
                    for item in items:
                        for m in CITE_RE.findall(str(item)):
                            cite_tot += 1
                            for n in re.findall(r"\d+", m):
                                if tp and int(n) > tp:
                                    cite_bad += 1
        cov = (cite_tot / sw_items * 100) if sw_items else 0
        has_gap = bool(c.get("gap_analysis"))
        has_blind = bool(c.get("blind_ranking"))
        rv = c.get("rubric_version") or "없음"
        flags = []
        if fmt == "score(0-10)":
            flags.append("구버전 점수체계")
        if cov < 50:
            flags.append(f"인용 {cov:.0f}%")
        if not has_gap:
            flags.append("gap_analysis 없음")
        if rv == "없음":
            flags.append("rubric_version 없음")
        lines.append(f"• {ft}/{comp[:30]}\n"
                     f"    포맷={fmt} gap={'O' if has_gap else 'X'} blind={'O' if has_blind else 'X'} "
                     f"rubric_version={rv} | s/w {sw_items}개 중 인용 {cite_tot}개({cov:.0f}%) 범위초과 {cite_bad}")
        if cite_bad:
            defects.append(f"[인용 범위초과] {ft}/{comp[:24]}: {cite_bad}개 (page > total_pages)")
        if flags:
            lines.append("    ⚠ " + " · ".join(flags))
    return defects, lines


def check_patterns(db):
    """C. 패턴 지표별 표본수(N) 갭."""
    lines = []
    for pf in sorted(glob.glob(os.path.join(db, "_patterns", "*.json"))):
        p = json.load(open(pf, encoding="utf-8"))
        ft = os.path.basename(pf)[:-5]
        q = p.get("quantitative", {}) or {}
        ns = {k: v.get("n") for k, v in q.items()}
        wc = p.get("win_count")
        lc = (p.get("loser_stats") or {}).get("lose_count")
        distinct = sorted(set(v for v in ns.values() if v is not None))
        lines.append(f"• {ft}: win={wc} lose={lc} | 지표 N={ns}")
        if len(distinct) > 1:
            lines.append(f"    ⚠ 지표별 N 불균일 {distinct} — 일부 지표는 win_count 미만 표본으로 비교됨")
        if wc is not None and wc < 3:
            lines.append(f"    ⚠ win_count={wc} (<3): 정량 패턴 통계 신뢰도 낮음 — 진단 시 '참고용' 처리 권장")
    return lines


def main():
    ap = argparse.ArgumentParser(description="운영 DB 무결성 건강검진 (LLM 0콜)")
    ap.add_argument("--db-path", default=None, help="DB 루트 (생략 시 settings.db_path)")
    args = ap.parse_args()

    db = args.db_path
    if not db:
        try:
            from config import settings
            db = str(settings.db_path)
        except Exception as e:
            print(f"FATAL: --db-path 미지정 + settings 로드 실패: {e}")
            sys.exit(2)
    if not os.path.isdir(db):
        print(f"FATAL: DB 경로 없음: {db}")
        sys.exit(2)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("#" * 68)
    print("# DATA HEALTH CHECK  (read-only, 0 LLM calls)")
    print(f"# db: {db}")
    print("#" * 68)

    num_def, num_warn, rows, subs = check_numeric(db)
    drift_def, drift_lines = check_drift(db, subs)
    pat_lines = check_patterns(db)

    print(f"\n===== A. 수치 무결성 (제출물 {len(subs)}개) =====")
    if num_def:
        print(f"⚠ HARD 결함 {len(num_def)}건:")
        for x in num_def:
            print("   -", x)
    else:
        print("✓ 명백한 수치 모순 없음")
    for w in num_warn:
        print("   (경고)", w)

    print("\n-- 지표 결측 맵 (✓=있음 ·=없음) --")
    hdr = ["site", "bldg", "tfa", "cov", "far", "fl+", "fl-", "park"]
    print("  " + "submission".ljust(32) + " ".join(h.ljust(5) for h in hdr))
    for (ft, comp, pfx), v in subs.items():
        q = v["q"]
        cells = "".join(("  ✓  " if q.get(f) is not None else "  ·  ") for f in QUANT_FIELDS)
        print("  " + f"{ft[:4]}/{pfx}({v['result']})".ljust(32) + cells)

    print(f"\n===== B. 스키마/rubric 드리프트 (comparison) =====")
    for ln in drift_lines:
        print(ln)
    if drift_def:
        print("⚠ 인용 결함:")
        for x in drift_def:
            print("   -", x)

    print(f"\n===== C. 패턴 지표별 표본수(N) =====")
    for ln in pat_lines:
        print(ln)

    hard = len(num_def) + len(drift_def)
    print("\n" + "#" * 68)
    print(f"# 요약: HARD 결함 {hard}건 | 수치경고 {len(num_warn)}건 | "
          f"제출물 {len(subs)} | 비교 {len(drift_lines)}그룹")
    print("#" * 68)
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
