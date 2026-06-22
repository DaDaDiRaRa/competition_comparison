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
    _parse_parking, _collect_parking_statements,
    _normalize_zone_use, _limits_determined_by,
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
        "special_conditions": [
            "'건축물의 건폐율, 용적률, 높이'는 서울시 도시계획위원회 심의를 통해 결정된 사항임",
        ],
        "sites": [
            {"site_id": "부지1", "address": "서울특별시 영등포구 당산동3가 385",
             "facilities": ["구청", "어린이집(노유자시설)"],
             "zoning": "도시지역, 준공업지역, 공원, 도로(접합)",
             "site_area_sqm": 7498, "floor_area_ratio_pct": 460,
             "building_coverage_pct": 60, "max_height_m": 100},
            {"site_id": "부지2", "address": "",
             "facilities": ["보건소", "센터(주민편의시설)"],
             "zoning": "지목 대지로 변경 예정",
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
    # 2차 소스 — 주차(서술)
    "brief_design_massing": {
        "parking_requirements": [
            "공사 중 보행 안전에 유의한다.",                              # 카운트 없음
            "현 구청 본관 광장(70대 내외) 운영 계획.",                    # 운영/현황 → 제외
            "'부지1(구청·구의회)' 부설주차장으로 430대(지하)를 계획한다.",  # 부지1 → 430
            "자주식 주차장으로 계획하며 총 460대 이상을 확보한다.",        # 전체 요구 (generic)
        ],
    },
}


class TestBuildFeasibilityExport:
    def test_schema_version(self):
        fe = build_feasibility_export(_SAMPLE)
        assert fe["schema_version"] == SCHEMA_VERSION == 2

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
        assert fe["schema_version"] == 2
        assert fe["sites"] == []
        assert fe["certifications"]["green_building"] is None

    def test_site_metrics_carried(self):
        fe = build_feasibility_export(_SAMPLE)
        s0 = fe["sites"][0]
        assert s0["site_area_sqm"] == 7498
        assert s0["floor_area_ratio_pct"] == 460
        assert s0["building_coverage_pct"] == 60

    # ── 2차 ───────────────────────────────────────────────────────────────
    def test_parking_per_site(self):
        fe = build_feasibility_export(_SAMPLE)
        by = {s["site_id"]: s for s in fe["sites"]}
        assert by["부지1"]["required_parking_count"] == 430        # 부지1 귀속
        assert "430대" in by["부지1"]["parking_note"]
        assert by["부지2"]["required_parking_count"] is None        # site-specific 없음
        assert "460대" in by["부지2"]["parking_note"]               # 전체 요구 문구 note

    def test_zone_use_normalized(self):
        fe = build_feasibility_export(_SAMPLE)
        by = {s["site_id"]: s for s in fe["sites"]}
        assert by["부지1"]["zone_use"] == "준공업지역"
        assert by["부지1"]["zone_use_raw"] is None
        # 부지2 zoning 서술형 → 추측 금지: null + 원문
        assert by["부지2"]["zone_use"] is None
        assert by["부지2"]["zone_use_raw"] == "지목 대지로 변경 예정"

    def test_limits_determined_by_simui(self):
        fe = build_feasibility_export(_SAMPLE)
        assert all(s["limits_determined_by"] == "심의" for s in fe["sites"])


# ── 2차 C: 주차 파서 ──────────────────────────────────────────────────────────
class TestParseParking:
    def test_buji_marker_attribution(self):
        per, gen = _parse_parking(["'부지1' 부설주차장으로 430대를 계획한다."])
        assert per["부지1"][0] == 430

    def test_nearest_buji_before_count(self):
        # 부지2 가 먼저 언급돼도 카운트 직전 마커(부지1)에 귀속
        s = "'부지2'가 둘러싸인 특성상 '부지1' 부설주차장으로 430대(지하)를 계획한다."
        per, gen = _parse_parking([s])
        assert "부지1" in per and "부지2" not in per

    def test_generic_total(self):
        per, gen = _parse_parking(["자주식 주차장으로 계획하며 총 460대 이상을 확보한다."])
        assert per == {} and "460대" in gen

    def test_operational_statement_skipped(self):
        per, gen = _parse_parking(["현 구청 본관 광장(70대 내외) 운영 계획."])
        assert per == {} and gen is None

    def test_no_requirement_kw_skipped(self):
        # 카운트는 있으나 요구 키워드 없음 → 무시
        per, gen = _parse_parking(["주차 5대 사진 참조."])
        assert per == {} and gen is None

    def test_collect_from_massing(self):
        bd = {"brief_design_massing": {"parking_requirements": ["'부지1' 460대 이상 확보한다."]}}
        stmts = _collect_parking_statements(bd)
        assert stmts and "460대" in stmts[0]


# ── 2차 D: 용도지역 정규화 ────────────────────────────────────────────────────
class TestNormalizeZoneUse:
    def test_standard_matched(self):
        assert _normalize_zone_use("도시지역, 준공업지역, 공원") == ("준공업지역", None)

    def test_longest_match(self):
        zu, raw = _normalize_zone_use("제2종일반주거지역")
        assert zu == "제2종일반주거지역" and raw is None

    def test_no_match_keeps_raw(self):
        assert _normalize_zone_use("지목 대지로 변경 예정") == (None, "지목 대지로 변경 예정")

    def test_list_zoning(self):
        assert _normalize_zone_use(["도시지역", "일반상업지역"])[0] == "일반상업지역"

    def test_empty_safe(self):
        assert _normalize_zone_use("") == (None, None)
        assert _normalize_zone_use(None) == (None, None)


# ── 2차 E: 심의 결정 플래그 ───────────────────────────────────────────────────
class TestLimitsDeterminedBy:
    def test_simui_detected(self):
        sc = ["'건축물의 건폐율, 용적률, 높이'는 도시계획위원회 심의를 통해 결정된 사항임"]
        assert _limits_determined_by(sc) == "심의"

    def test_simui_without_limit_kw_is_beopjeong(self):
        # 심의 언급이 있어도 건폐율/용적률/높이 와 무관하면 법정
        assert _limits_determined_by(["공개공지는 심의 결정사항"]) == "법정"

    def test_default_beopjeong(self):
        assert _limits_determined_by(["착수일로부터 15개월"]) == "법정"

    def test_empty_beopjeong(self):
        assert _limits_determined_by([]) == "법정"


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
        assert result["feasibility_export"]["schema_version"] == 2
        assert result["feasibility_export"]["construction_cost_100m_won"] == 100

    def test_submission_has_no_feasibility_export(self):
        # 비-brief (제출물) 페이지 타입 → feasibility_export 미생성
        classifications = [{"page": 1, "primary_type": "CONCEPT"}]
        extractions = [{"page": 1, "type": "CONCEPT", "data": {"summary": "x"}}]
        result = merge_extracted_data(classifications, extractions)
        assert "feasibility_export" not in result
