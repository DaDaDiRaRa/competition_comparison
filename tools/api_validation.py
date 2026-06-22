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


def _load_all(pattern):
    """패턴 매칭 fixture 전부 로드 → [(path, data), ...] (이름 정렬)."""
    out = []
    for p in sorted(glob.glob(BRIEFS + r"\*.json")):
        if pattern in Path(p).name:
            try:
                out.append((p, json.load(open(p, encoding="utf-8"))))
            except Exception:
                pass
    return out


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

    # 종로구청 fixture 들 (main 지침서 + 세부지침서). area_table 검증은 면적표 있는
    # fixture (세부지침서), KI-1 은 배점표 있는 fixture (main 지침서) 를 각각 선택.
    jn_all = _load_all("종로")
    jn_prog = None   # 면적표 있는 fixture → P1-3
    f_jn_prog = None
    best_area = -1
    for p, data in jn_all:
        st = _area_stats(data)
        if st["area_filled"] > best_area:
            best_area, jn_prog, f_jn_prog = st["area_filled"], data, p

    print(f"영등포 fixture     : {f_yd}")
    print(f"종로 fixture (전체) : {[Path(p).stem for p, _ in jn_all]}")
    print(f"종로 area fixture   : {Path(f_jn_prog).stem if f_jn_prog else None} (area_filled={best_area})")
    print("=" * 78)

    if not yd:
        print("FATAL: 영등포 fixture 없음")
        sys.exit(1)
    if not jn_all:
        print("FATAL: 종로 fixture 없음 — 분석 먼저 실행 필요")
        sys.exit(1)

    jn = jn_prog  # P1-3 area 검증용 (면적표 있는 fixture)
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
    # NOTE: 당초 "종로구청=단순형" 전제는 틀림. 종로구청 세부지침서도 통합청사라
    # 5단 계층(시설→구분→부서→과→실)으로 영등포와 동일하게 복잡. P1-3-1 을
    # "두 번째 독립 문서의 다단 계층 정상 추출" 로 재정의. 진짜 단순형(1~2단) 케이스
    # 는 여전히 미확보 — 소규모 단일시설 지침서 확보 시 별도 검증.
    jn_has_program = bool(jn.get("brief_program")) and jn_area["area_filled"] > 0
    # P1-3-2: 영등포 복잡형 — 계층 깊이 ≥ 3
    check("P1-3-2", len(yd_area["hier_levels"]) >= 3,
          f"영등포 hier_levels={yd_area['hier_levels']} ({len(yd_area['hier_levels'])}단)")
    # P1-3-1: 종로구청 세부지침서 — 다단 계층 정상 추출 (≥2단 + dept 채워짐)
    if jn_has_program:
        check("P1-3-1",
              len(jn_area["hier_levels"]) >= 2,
              f"종로 세부지침서 hier_levels={jn_area['hier_levels']} ({len(jn_area['hier_levels'])}단). "
              f"※ 단순형 가정 오류 — 종로도 복잡형(통합청사), 진짜 단순형 케이스 미확보")
    else:
        na("P1-3-1", "종로 면적표 fixture 없음 — 세부지침서 분석 필요")
    # P1-3-3: 기준면적(A) 채워진 행 양쪽 > 0
    check("P1-3-3", yd_area["area_filled"] > 0 and jn_area["area_filled"] > 0,
          f"영등포 area_filled={yd_area['area_filled']}, 종로 세부 area_filled={jn_area['area_filled']}")
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
    # 영등포 + 종로 배점표 있는 fixture (main 지침서). 세부지침서는 배점표 없어 N/A.
    ki_targets = [("영등포", yd)]
    for p, data in jn_all:
        be = (data.get("brief_evaluation") or {})
        if isinstance(be, list):
            be = be[0] if be else {}
        if be.get("total_points") is not None or be.get("evaluation_categories"):
            ki_targets.append((f"종로:{Path(p).stem.split('_')[-2]}", data))
    for label, d in ki_targets:
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
