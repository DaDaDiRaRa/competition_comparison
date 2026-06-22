"""
test_feasibility_export.py — feasibility_export 정규화 블록 회귀 (LLM 없음).

연동 앱(arch-law-diagnose)이 읽는 블록. 항목 A~E 가 기존 추출값에서 안전하게
재구성되는지, 기존 키를 건드리지 않는지, 결측에도 안 깨지는지 검증.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.feasibility_export import (
    build_feasibility_export, _building_law_uses,
    _parse_site_addresses, _code_certifications, SCHEMA_VERSION,
)
from services.data_extractor import merge_extracted_data


# ── D: 건축법 용도 ────────────────────────────────────────────────────────────
class TestBuildingLawUses:
    def test_paren_use_extracted(self):
        assert _building_law_uses(["어린이집(노유자시설)", "구청"]) == ["노유자시설"]

    def test_multiple_uses_array(self):
        out = _building_law_uses(["어린이집(노유자시설)", "센터(주민편의시설)"])
        assert out == ["노유자시설", "주민편의시설"]

    def test_no_paren_skipped(self):
        assert _building_law_uses(["구청", "구의회", "부설주차장"]) == []

    def test_jutaek_kept(self):
        assert _building_law_uses(["빌라(단독주택)"]) == ["단독주택"]

    def test_non_use_paren_filtered(self):
        # 시설/주택 아닌 괄호는 용도로 보지 않음
        assert _building_law_uses(["공원(현 당산근린공원)"]) == []

    def test_dedup(self):
        assert _building_law_uses(["a(노유자시설)", "b(노유자시설)"]) == ["노유자시설"]

    def test_empty_safe(self):
        assert _building_law_uses(None) == []
        assert _building_law_uses([]) == []


# ── B: 주소 분해 + 접두 상속 ──────────────────────────────────────────────────
class TestParseSiteAddresses:
    def test_inherits_prefix(self):
        bs = [{"address": "서울특별시 영등포구 당산동3가 385(부지1), 당산동3가 370-4(부지2)"}]
        out = _parse_site_addresses(bs)
        assert out["부지1"] == "서울특별시 영등포구 당산동3가 385"
        assert out["부지2"] == "서울특별시 영등포구 당산동3가 370-4"   # 접두 상속

    def test_comma_inside_paren_ignored(self):
        bs = [{"address": "당산동3가 385 (부지1, 현 당산근린공원), 당산동3가 370-4 (부지2, 현 주차장)"}]
        out = _parse_site_addresses(bs)
        assert out["부지1"] == "당산동3가 385"
        assert out["부지2"] == "당산동3가 370-4"

    def test_first_occurrence_kept(self):
        bs = [
            {"address": "서울 강남구 역삼동 1(부지1)"},
            {"address": "역삼동 999(부지1)"},   # 덮어쓰지 않음
        ]
        assert _parse_site_addresses(bs)["부지1"] == "서울 강남구 역삼동 1"

    def test_no_marker_empty(self):
        assert _parse_site_addresses([{"address": "영등포구 일대"}]) == {}

    def test_empty_safe(self):
        assert _parse_site_addresses([]) == {}


# ── C: 인증 코드화 ────────────────────────────────────────────────────────────
class TestCodeCertifications:
    def test_full(self):
        sustain = {
            "required_certifications": [
                {"name": "녹색건축물 최우수등급", "required_grade": "최우수등급"},
                {"name": "제로에너지건축물(ZEB)", "required_grade": "3등급 이상"},
            ],
            "renewable_energy_min_pct": 36,
        }
        out = _code_certifications(sustain)
        assert out == {"green_building": "최우수", "zeb_grade": 3,
                       "renewable_pct": 36, "bf_grade": None}

    def test_green_woosu(self):
        out = _code_certifications({"required_certifications": [
            {"name": "녹색건축 우수등급", "required_grade": "우수"}]})
        assert out["green_building"] == "우수"

    def test_bf_detected(self):
        out = _code_certifications({"required_certifications": [
            {"name": "장애물 없는 생활환경(BF) 인증", "required_grade": "우수"}]})
        assert out["bf_grade"] == "우수"

    def test_all_null_when_absent(self):
        out = _code_certifications({})
        assert out == {"green_building": None, "zeb_grade": None,
                       "renewable_pct": None, "bf_grade": None}

    def test_renewable_non_numeric_nulled(self):
        out = _code_certifications({"renewable_energy_min_pct": "n/a"})
        assert out["renewable_pct"] is None


# ── 전체 빌드 + 무결성 ────────────────────────────────────────────────────────
_SAMPLE = {
    "brief_project_info": {
        "construction_cost_100m_won": 2686,
        "design_cost_100m_won": 124,
        "construction_period_months": 15,
        "sites": [
            {"site_id": "부지1", "address": "서울특별시 영등포구 당산동3가 385",
             "facilities": ["구청", "어린이집(노유자시설)"],
             "site_area_sqm": 7498, "floor_area_ratio_pct": 460,
             "building_coverage_pct": 60, "max_height_m": 100},
            {"site_id": "부지2", "address": "",
             "facilities": ["보건소", "센터(주민편의시설)"],
             "site_area_sqm": 2940, "floor_area_ratio_pct": 400,
             "building_coverage_pct": 50, "max_height_m": 50},
        ],
    },
    "brief_site": [
        {"address": "서울특별시 영등포구 당산동3가 385(부지1), 당산동3가 370-4(부지2)"},
    ],
    "brief_design_sustain": {
        "required_certifications": [
            {"name": "녹색건축물 최우수등급", "required_grade": "최우수등급"},
            {"name": "제로에너지건축물(ZEB)", "required_grade": "3등급 이상"},
        ],
        "renewable_energy_min_pct": 36,
    },
}


class TestBuildFeasibilityExport:
    def test_schema_version(self):
        fe = build_feasibility_export(_SAMPLE)
        assert fe["schema_version"] == SCHEMA_VERSION == 1

    def test_site_id_join(self):
        fe = build_feasibility_export(_SAMPLE)
        assert [s["site_id"] for s in fe["sites"]] == ["부지1", "부지2"]

    def test_address_fallback_to_brief_site(self):
        # 부지2 는 sites[].address 가 빈 문자열 → brief_site 분해값(접두 상속) 사용
        fe = build_feasibility_export(_SAMPLE)
        addrs = {s["site_id"]: s["address"] for s in fe["sites"]}
        assert addrs["부지1"] == "서울특별시 영등포구 당산동3가 385"
        assert addrs["부지2"] == "서울특별시 영등포구 당산동3가 370-4"

    def test_building_law_uses(self):
        fe = build_feasibility_export(_SAMPLE)
        uses = {s["site_id"]: s["building_law_uses"] for s in fe["sites"]}
        assert uses["부지1"] == ["노유자시설"]
        assert uses["부지2"] == ["주민편의시설"]

    def test_certifications_coded(self):
        fe = build_feasibility_export(_SAMPLE)
        assert fe["certifications"]["green_building"] == "최우수"
        assert fe["certifications"]["zeb_grade"] == 3
        assert fe["certifications"]["renewable_pct"] == 36

    def test_scale_exposed(self):
        fe = build_feasibility_export(_SAMPLE)
        assert fe["construction_cost_100m_won"] == 2686
        assert fe["design_cost_100m_won"] == 124
        assert fe["construction_period_months"] == 15

    def test_read_only_does_not_mutate(self):
        import copy
        snap = copy.deepcopy(_SAMPLE)
        build_feasibility_export(_SAMPLE)
        assert _SAMPLE == snap   # 기존 키 절대 수정 금지

    def test_empty_brief_data_safe(self):
        fe = build_feasibility_export({})
        assert fe["schema_version"] == 1
        assert fe["sites"] == []
        assert fe["certifications"]["green_building"] is None

    def test_site_metrics_carried(self):
        fe = build_feasibility_export(_SAMPLE)
        s0 = fe["sites"][0]
        assert s0["site_area_sqm"] == 7498
        assert s0["floor_area_ratio_pct"] == 460
        assert s0["building_coverage_pct"] == 60


# ── 파이프라인 통합 (merge_extracted_data 가드) ───────────────────────────────
class TestMergeIntegration:
    def test_brief_gets_feasibility_export(self):
        classifications = [{"page": 1, "primary_type": "BRIEF_PROJECT_INFO"}]
        extractions = [{"page": 1, "type": "BRIEF_PROJECT_INFO",
                        "data": {"construction_cost_100m_won": 100,
                                 "sites": [{"site_id": "부지1", "address": "서울 강남구 역삼동 1",
                                            "facilities": ["청사(업무시설)"]}]}}]
        result = merge_extracted_data(classifications, extractions)
        assert "feasibility_export" in result
        assert result["feasibility_export"]["schema_version"] == 1
        assert result["feasibility_export"]["construction_cost_100m_won"] == 100

    def test_submission_has_no_feasibility_export(self):
        # 비-brief (제출물) 페이지 타입 → feasibility_export 미생성
        classifications = [{"page": 1, "primary_type": "CONCEPT"}]
        extractions = [{"page": 1, "type": "CONCEPT", "data": {"summary": "x"}}]
        result = merge_extracted_data(classifications, extractions)
        assert "feasibility_export" not in result
