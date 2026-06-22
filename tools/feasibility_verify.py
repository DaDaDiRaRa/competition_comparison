"""
feasibility_verify.py — feasibility_export 블록 무료 검증 (API 호출 없음)

기존 _brief.json 샘플 1건을 읽어 build_feasibility_export 를 적용(merge 단계와 동일
함수)하고, A~E 항목이 정상 생성되며 기존 키가 안 깨지는지 확인.

usage:
    $env:PYTHONUTF8 = "1"
    backend\\venv\\Scripts\\python.exe tools\\feasibility_verify.py
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.feasibility_export import build_feasibility_export  # noqa: E402

BRIEFS = r"C:\Temp\CompTestDB\_briefs"
_results = []


def chk(cid, ok, detail=""):
    _results.append((cid, bool(ok), detail))


def main():
    # 서술 필드(주차 등)가 풍부한 feas fixture 우선, 없으면 v10
    hits = [p for p in glob.glob(BRIEFS + r"\*.json") if "feas" in Path(p).name] \
        or [p for p in glob.glob(BRIEFS + r"\*.json") if "v10" in Path(p).name]
    if not hits:
        print("FATAL: feas/v10 fixture 없음")
        sys.exit(1)
    f = sorted(hits)[-1]
    d = json.load(open(f, encoding="utf-8"))
    print(f"fixture: {f}")

    import copy
    snap = copy.deepcopy(d)
    fe = build_feasibility_export(d)

    # 무결성: 빌드는 읽기 전용 (brief_data 전체 불변 — 이미 저장된 feasibility_export 포함)
    chk("READONLY", d == snap, "build 가 brief_data 를 변형하지 않음")

    chk("SCHEMA", fe.get("schema_version") == 2, f"schema_version={fe.get('schema_version')}")

    sites = fe.get("sites") or []
    # A: site_id 통일
    chk("A_site_id", len(sites) >= 1 and all(s.get("site_id") for s in sites),
        f"site_ids={[s.get('site_id') for s in sites]}")
    # B: 주소 채움
    chk("B_address", all(s.get("address") for s in sites),
        " | ".join(f"{s['site_id']}={s.get('address')}" for s in sites))
    # C: 인증 코드화
    c = fe.get("certifications") or {}
    chk("C_cert", c.get("green_building") is not None or c.get("zeb_grade") is not None
        or c.get("renewable_pct") is not None,
        f"green={c.get('green_building')} zeb={c.get('zeb_grade')} "
        f"renew={c.get('renewable_pct')} bf={c.get('bf_grade')}")
    # D: 건축법 용도
    chk("D_uses", any(s.get("building_law_uses") for s in sites),
        " | ".join(f"{s['site_id']}={s.get('building_law_uses')}" for s in sites))
    # E: 사업 규모 노출
    chk("E_scale",
        fe.get("construction_cost_100m_won") is not None
        or fe.get("design_cost_100m_won") is not None
        or fe.get("construction_period_months") is not None,
        f"cost={fe.get('construction_cost_100m_won')} "
        f"design={fe.get('design_cost_100m_won')} "
        f"period={fe.get('construction_period_months')}")

    # 2차 — 키 존재 (값은 null 일 수 있음)
    keys2 = ("required_parking_count", "parking_note", "zone_use", "zone_use_raw",
             "limits_determined_by")
    chk("2_keys", all(all(k in s for k in keys2) for s in sites),
        "sites 에 2차 필드(parking/zone/limits) 키 존재")
    chk("2_limits", all(s.get("limits_determined_by") in ("심의", "법정") for s in sites),
        " | ".join(f"{s['site_id']}={s.get('limits_determined_by')}" for s in sites))
    park = " | ".join(f"{s['site_id']}={s.get('required_parking_count')}" for s in sites)
    zone = " | ".join(f"{s['site_id']}={s.get('zone_use') or '(raw)'}" for s in sites)
    chk("2_parking", True, park)
    chk("2_zone", True, zone)

    print("=" * 74)
    for cid, ok, detail in _results:
        print(f"[{'PASS' if ok else 'FAIL'}] {cid:12} {detail}")
    npass = sum(1 for _, ok, _ in _results if ok)
    print("=" * 74)
    print(f"PASS: {npass}  FAIL: {len(_results) - npass}")
    print()
    print(json.dumps(fe, ensure_ascii=False, indent=2))
    sys.exit(0 if npass == len(_results) else 1)


if __name__ == "__main__":
    main()
