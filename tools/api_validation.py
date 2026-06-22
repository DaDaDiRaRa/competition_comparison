"""
api_validation.py — P0-3 / P1-3 / P2-3 / KI 검증 (memory project_api_validation_deferred 기준)

두 _brief.json fixture 를 읽어 결정적 assertion 수행 (추가 API 호출 없음):
  - 영등포 (복잡형, public + v10 라벨)
  - 종로구청 (단순형, public + 종로구청 라벨)

usage:
    $env:PYTHONUTF8 = "1"
    backend\\venv\\Scripts\\python.exe tools\\api_validation.py
"""
import glob
import json
import sys
from pathlib import Path

BRIEFS = r"C:\Temp\CompTestDB\_briefs"

# 계층 구조를 나타내는 row_type (subtotal 류 제외)
_HIER_TYPES = {"site_total", "facility", "division", "bureau", "space"}

_results = []  # (id, status, detail) — status: "PASS" | "FAIL" | "N/A"


def check(cid, passed, detail=""):
    _results.append((cid, "PASS" if passed else "FAIL", detail))


def na(cid, detail=""):
    _results.append((cid, "N/A", detail))


def _load(pattern):
    hits = [p for p in glob.glob(BRIEFS + r"\*.json") if pattern in Path(p).name]
    if not hits:
        return None, None
    f = sorted(hits)[-1]
    return f, json.load(open(f, encoding="utf-8"))


def _area_stats(d):
    """brief_program[] 전체에서 area_rows 통계 집계."""
    rt = {}
    area_filled = 0
    shared = 0
    bp = d.get("brief_program") or []
    if isinstance(bp, dict):
        bp = [bp]
    for pg in bp:
        for r in (pg.get("area_rows") or []):
            t = r.get("row_type")
            rt[t] = rt.get(t, 0) + 1
            if r.get("area") is not None:
                area_filled += 1
        shared += len(pg.get("shared_areas") or [])
    hier_levels = sorted(set(rt) & _HIER_TYPES)
    return {"row_type": rt, "hier_levels": hier_levels,
            "area_filled": area_filled, "shared": shared}


def main():
    f_yd, yd = _load("v10")           # 영등포 (복잡형)
    f_jn, jn = _load("종로구청")        # 종로구청 (단순형)

    print(f"영등포 fixture : {f_yd}")
    print(f"종로구청 fixture: {f_jn}")
    print("=" * 78)

    if not yd:
        print("FATAL: 영등포 fixture 없음")
        sys.exit(1)
    if not jn:
        print("FATAL: 종로구청 fixture 없음 — 분석 먼저 실행 필요")
        sys.exit(1)

    yd_area = _area_stats(yd)
    jn_area = _area_stats(jn)

    # ── P0-3: BRIEF_PROJECT_INFO 파이프라인 (영등포) ──────────────────────
    bpi = yd.get("brief_project_info") or {}
    sites = bpi.get("sites") or []
    q = yd.get("_quantitative") or {}
    # P0-3-3: 병합 dict 에 수치 non-null
    check("P0-3-3", q.get("site_area_sqm") is not None and len(sites) > 0,
          f"site_area_sqm={q.get('site_area_sqm')}, sites={len(sites)}")
    # P0-3-5: 복수부지 행 분리
    site_with_area = [s for s in sites if s.get("site_area_sqm") is not None]
    check("P0-3-5", len(sites) >= 2 and len(site_with_area) >= 2,
          f"sites={len(sites)}, with_area={len(site_with_area)} "
          f"({[s.get('site_id') for s in sites]})")

    # ── P1-3: area_table 계층 ─────────────────────────────────────────────
    # 종로구청 main 지침서에 면적 프로그램표가 있는지 (없으면 단순형 검증 N/A — 세부지침서 필요)
    jn_has_program = bool(jn.get("brief_program")) and jn_area["area_filled"] > 0
    # P1-3-2: 영등포 복잡형 — 계층 깊이 ≥ 3
    check("P1-3-2", len(yd_area["hier_levels"]) >= 3,
          f"영등포 hier_levels={yd_area['hier_levels']} ({len(yd_area['hier_levels'])}단)")
    # P1-3-1: 종로구청 단순형 — 면적표가 있어야 검증 가능
    if jn_has_program:
        check("P1-3-1",
              len(jn_area["hier_levels"]) <= 3 and len(jn_area["hier_levels"]) < len(yd_area["hier_levels"]),
              f"종로구청 hier_levels={jn_area['hier_levels']} ({len(jn_area['hier_levels'])}단) "
              f"vs 영등포 {len(yd_area['hier_levels'])}단")
    else:
        na("P1-3-1", "종로구청 main 지침서에 BRIEF_PROGRAM/면적표 없음 — 시설별 세부지침서 필요")
    # P1-3-3: 기준면적(A) 채워진 행 (영등포 확정, 종로는 면적표 있을 때만)
    if jn_has_program:
        check("P1-3-3", yd_area["area_filled"] > 0 and jn_area["area_filled"] > 0,
              f"영등포 area_filled={yd_area['area_filled']}, 종로 area_filled={jn_area['area_filled']}")
    else:
        check("P1-3-3a(영등포)", yd_area["area_filled"] > 0,
              f"영등포 area_filled={yd_area['area_filled']}")
        na("P1-3-3b(종로)", "면적표 부재 — 세부지침서 필요")
    # P1-3-5: shared_areas 섹션 (영등포 존재 확인 — 종로는 정보용)
    check("P1-3-5", yd_area["shared"] > 0,
          f"영등포 shared={yd_area['shared']}, 종로 shared={jn_area['shared']} (종로는 정보용)")

    # ── P2-3: BRIEF_DESIGN_* 분류·추출 (영등포) ───────────────────────────
    design_types = [k for k in yd if k.startswith("brief_design_")]
    check("P2-3-1", len(design_types) >= 3,
          f"design types present: {design_types}")
    bs = yd.get("brief_design_sustain") or {}
    if isinstance(bs, list):
        bs = bs[0] if bs else {}
    certs = bs.get("required_certifications") or []
    cert_grade = [c for c in certs if c.get("required_grade")]
    check("P2-3-3", len(cert_grade) > 0,
          f"certs with required_grade: {[(c.get('name'), c.get('required_grade')) for c in cert_grade]}")
    check("P2-3-4", bs.get("renewable_energy_min_pct") is not None,
          f"renewable_energy_min_pct={bs.get('renewable_energy_min_pct')}")

    # ── KI: 기존 Known Issues ─────────────────────────────────────────────
    for label, d in (("영등포", yd), ("종로구청", jn)):
        be = d.get("brief_evaluation") or {}
        if isinstance(be, list):
            be = be[0] if be else {}
        tp = be.get("total_points")
        cats = be.get("evaluation_categories") or []
        psum = sum(c.get("points") for c in cats if isinstance(c.get("points"), (int, float)))
        warn = d.get("points_sum_warning")
        # KI-1: 배점 합계 100 근접 (≤110 안전망 내, 경고 없음)
        ok = (tp is None or tp <= 110) and psum <= 110 and not warn
        check(f"KI-1[{label}]", ok,
              f"total_points={tp}, sum={psum}, warning={warn}")

    # ── 결과 출력 ─────────────────────────────────────────────────────────
    print()
    npass = sum(1 for _, s, _ in _results if s == "PASS")
    nfail = sum(1 for _, s, _ in _results if s == "FAIL")
    nna = sum(1 for _, s, _ in _results if s == "N/A")
    for cid, s, detail in _results:
        print(f"[{s:4}] {cid:16} {detail}")
    print("=" * 78)
    print(f"PASS: {npass}  FAIL: {nfail}  N/A: {nna}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
