"""brief_validator smoke test — python tools/test_brief_validator.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.brief_validator import validate_brief


def test_empty_input():
    result = validate_brief({}, {})
    v = result["validation"]
    assert set(v.keys()) == {"flags", "summary", "checked_rules"}
    assert isinstance(v["flags"], list)
    # omission 규칙이 연면적/건폐율/용적률/심사기준 4개 플래그를 발동함
    types = [f["type"] for f in v["flags"]]
    assert all(t == "omission" for t in types)
    print(f"[PASS] empty input - {len(v['flags'])} omission flags, summary={v['summary']}")


def test_points_mismatch_null_and_sum():
    bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
        {"name": "배치계획", "points": 30},
        {"name": "공간계획", "points": 30},
        {"name": "경관", "points": 20},
        {"name": "기술", "points": None},
    ]}}
    r = validate_brief(bd, {})["validation"]
    types = [f["type"] for f in r["flags"]]
    # null 항목(medium) + 합계 불일치 80 != 100(high)
    assert types.count("points_mismatch") == 2
    severities = {f["severity"] for f in r["flags"] if f["type"] == "points_mismatch"}
    assert "high" in severities and "medium" in severities
    print("[PASS] points_mismatch null+sum")


def test_points_match_no_flag():
    bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
        {"name": "A", "points": 40},
        {"name": "B", "points": 60},
    ]}}
    r = validate_brief(bd, {})["validation"]
    assert not any(f["type"] == "points_mismatch" for f in r["flags"])
    print("[PASS] points_match -> no flag")


def test_omission_fires_without_values():
    bd = {"_quantitative": {}, "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]}}
    r = validate_brief(bd, {})["validation"]
    msgs = [f["message"] for f in r["flags"]]
    assert any("연면적" in m for m in msgs)
    assert any("건폐율" in m for m in msgs)
    assert any("용적률" in m for m in msgs)
    print("[PASS] omission fires")


def test_omission_suppressed_by_brief_program():
    bd = {
        "_quantitative": {},
        "brief_program": {
            "total_required_floor_area_sqm": 5000,
            "building_coverage_limit_pct": 60,
            "floor_area_ratio_limit_pct": 200,
        },
        "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]},
    }
    r = validate_brief(bd, {})["validation"]
    omit = [f for f in r["flags"] if f["type"] == "omission"]
    assert not any("연면적" in f["message"] for f in omit)
    assert not any("건폐율" in f["message"] for f in omit)
    assert not any("용적률" in f["message"] for f in omit)
    print("[PASS] omission suppressed by brief_program values")


def test_area_cross_high():
    bd = {"brief_program": {
        "total_required_floor_area_sqm": 1000,
        "rooms": [{"name": "A", "required_area_sqm": 650}, {"name": "B", "required_area_sqm": 650}],
    }}
    r = validate_brief(bd, {})["validation"]
    ac = [f for f in r["flags"] if f["type"] == "area_cross_check"]
    assert ac and ac[0]["severity"] == "high"
    print("[PASS] area_cross_check high")


def test_area_cross_within_tolerance():
    bd = {"brief_program": {
        "total_required_floor_area_sqm": 1000,
        "rooms": [{"name": "A", "required_area_sqm": 500}, {"name": "B", "required_area_sqm": 500}],
    }}
    r = validate_brief(bd, {})["validation"]
    assert not any(f["type"] == "area_cross_check" for f in r["flags"])
    print("[PASS] area_cross_check within tolerance -> no flag")


def test_area_cross_legacy_path():
    bd = {"area_table": {
        "total_required_area_sqm": 1000,
        "room_program": [{"name": "A", "area_sqm": 400}, {"name": "B", "area_sqm": 300}],
        # 합=700, 30% 부족 -> medium
    }}
    r = validate_brief(bd, {})["validation"]
    ac = [f for f in r["flags"] if f["type"] == "area_cross_check"]
    # 700/1000 = 0.3 deviation > 0.25 threshold -> high
    assert ac and ac[0]["severity"] == "high"
    print("[PASS] area_cross_check legacy path high")


def test_low_confidence():
    bd = {"page_map": [
        {"page": 1, "primary_type": "BRIEF_DESIGN_GUIDE", "confidence": 0.9},
        {"page": 2, "primary_type": "BRIEF_PROGRAM", "confidence": 0.4},
        {"page": 3, "primary_type": "BRIEF_EVALUATION", "confidence": 0.3},
    ]}
    r = validate_brief(bd, {})["validation"]
    lc = [f for f in r["flags"] if f["type"] == "low_confidence"]
    assert len(lc) == 2
    pages = {f["location"] for f in lc}
    assert "page_map.p2" in pages and "page_map.p3" in pages
    print("[PASS] low_confidence 2 pages")


def test_duplicate_same_axis():
    reqs = {"requirements": [
        {"axis": "program_planning", "description": "다양한 공간 프로그램 계획"},
        {"axis": "program_planning", "description": "다양한 프로그램 공간 계획"},
        {"axis": "site_response",    "description": "주변 맥락 고려"},
    ]}
    r = validate_brief({}, reqs)["validation"]
    dup = [f for f in r["flags"] if f["type"] == "duplicate"]
    assert len(dup) == 1
    print("[PASS] duplicate same axis")


def test_duplicate_different_axis_no_flag():
    reqs = {"requirements": [
        {"axis": "program_planning", "description": "다양한 공간 프로그램 계획"},
        {"axis": "site_response",    "description": "다양한 공간 프로그램 계획"},
    ]}
    r = validate_brief({}, reqs)["validation"]
    assert not any(f["type"] == "duplicate" for f in r["flags"])
    print("[PASS] duplicate different axis -> no flag")


def test_output_schema():
    result = validate_brief(
        {"page_map": [{"page": 1, "primary_type": "BRIEF_DESIGN_GUIDE", "confidence": 0.3}]},
        {}
    )
    v = result["validation"]
    for flag in v["flags"]:
        assert set(flag.keys()) == {"type", "severity", "message", "location"}
        assert flag["severity"] in {"high", "medium", "low"}
    total = sum(v["summary"].values())
    assert total == len(v["flags"])
    assert "points_mismatch" in v["checked_rules"]
    print("[PASS] output schema")


if __name__ == "__main__":
    tests = [
        test_empty_input,
        test_points_mismatch_null_and_sum,
        test_points_match_no_flag,
        test_omission_fires_without_values,
        test_omission_suppressed_by_brief_program,
        test_area_cross_high,
        test_area_cross_within_tolerance,
        test_area_cross_legacy_path,
        test_low_confidence,
        test_duplicate_same_axis,
        test_duplicate_different_axis_no_flag,
        test_output_schema,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(failed)
