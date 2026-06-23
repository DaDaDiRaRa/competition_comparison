"""
quant_validator + merge_extracted_data 훅 회귀 테스트 — LLM/PDF/네트워크 의존 없음.

대상:
  - services.quant_validator.validate_quantitative  (단일 소스 정합성 규칙)
  - merge_extracted_data 의 _quantitative_flags 부착 (제안서만, brief 제외)

픽스처는 실데이터 감사(2026-06-23)에서 적발된 케이스:
  - 하안주공 1011 당선작: 건폐율 27.46% vs 건축/대지 81.6% + 총연면적<용적률함의
  - public/a 낙선: 총연면적<용적률함의 (site_area 오추출)
"""
import pytest

from services.quant_validator import validate_quantitative, has_errors
from services.data_extractor import merge_extracted_data
from services.pattern_builder import _build_quant_stats


def _rules(flags):
    return {f["rule"] for f in flags}


# ═══════════════════════════════════════════════════════════════════════════════
# validate_quantitative — 정상(플래그 없어야 함)

class TestClean:

    def test_kunwon_public_consistent(self):
        # 영등포 당선작 실값 — 모든 항등식 일치
        q = {
            "total_floor_area_sqm": 58817.45, "site_area_sqm": 7498.0,
            "building_area_sqm": 4131.36, "building_coverage_ratio_pct": 55.1,
            "floor_area_ratio_pct": 455.51, "floors_above": 20, "floors_below": 5,
            "parking_count": 430,
        }
        assert validate_quantitative(q) == []

    def test_residential_with_above_ground(self):
        # 경북도청 당선작 — 지상연면적으로 용적률 검증 통과
        q = {
            "total_floor_area_sqm": 181982.08, "area_above_ground_sqm": 129505.66,
            "site_area_sqm": 56401.0, "building_area_sqm": 6061.89,
            "building_coverage_ratio_pct": 10.75, "floor_area_ratio_pct": 229.62,
            "floors_above": 29, "floors_below": 2, "parking_count": 1738,
        }
        assert validate_quantitative(q) == []

    def test_missing_fields_no_false_positive(self):
        # 결측 필드는 검사 스킵 — false positive 금지
        assert validate_quantitative({"site_area_sqm": 5000}) == []
        assert validate_quantitative({"floors_above": 30}) == []
        assert validate_quantitative({}) == []

    def test_non_dict_input(self):
        assert validate_quantitative(None) == []
        assert validate_quantitative("nope") == []
        assert validate_quantitative([1, 2]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# validate_quantitative — 결함 적발

class TestDefects:

    def test_haanjugong_coverage_and_far(self):
        # 하안주공 1011 실값 — 건폐율 모순 + 총연면적<용적률함의 동시
        q = {
            "total_floor_area_sqm": 29341.01, "site_area_sqm": 130924.5,
            "building_area_sqm": 106850.0, "building_coverage_ratio_pct": 27.46,
            "floor_area_ratio_pct": 327.89, "floors_above": 45, "parking_count": 6895,
        }
        flags = validate_quantitative(q)
        rules = _rules(flags)
        assert "coverage_mismatch" in rules
        assert "floor_area_below_far_implied" in rules
        assert has_errors(flags)

    def test_public_a_floor_area_below_far(self):
        # public/a 실값 근사 — site_area 오추출로 총연면적<용적률함의
        q = {"total_floor_area_sqm": 67971.0, "site_area_sqm": 69628.0,
             "floor_area_ratio_pct": 449.38}
        assert "floor_area_below_far_implied" in _rules(validate_quantitative(q))

    def test_building_gt_site(self):
        flags = validate_quantitative({"site_area_sqm": 1000.0, "building_area_sqm": 1500.0})
        assert "building_gt_site" in _rules(flags)

    def test_coverage_mismatch_only(self):
        # 건폐율만 어긋남 (건축/대지는 50%인데 입력 20%)
        q = {"site_area_sqm": 1000.0, "building_area_sqm": 500.0,
             "building_coverage_ratio_pct": 20.0}
        assert _rules(validate_quantitative(q)) == {"coverage_mismatch"}

    def test_consistent_coverage_no_flag(self):
        # 건축/대지 = 입력 건폐율과 일치 → 무결
        q = {"site_area_sqm": 1000.0, "building_area_sqm": 500.0,
             "building_coverage_ratio_pct": 50.0}
        assert validate_quantitative(q) == []

    def test_out_of_bounds(self):
        assert "out_of_bounds" in _rules(validate_quantitative({"building_coverage_ratio_pct": 150.0}))
        assert "out_of_bounds" in _rules(validate_quantitative({"floors_above": 200}))
        assert "out_of_bounds" in _rules(validate_quantitative({"floors_below": 30}))

    def test_coverage_gt_far_is_warning(self):
        # 건폐율 60% > 용적률 50% (다층이면 비정상) — 경고이지 error 아님
        q = {"site_area_sqm": 1000.0, "building_area_sqm": 600.0,
             "building_coverage_ratio_pct": 60.0, "floor_area_ratio_pct": 50.0}
        flags = validate_quantitative(q)
        assert "coverage_gt_far" in _rules(flags)
        assert not has_errors(flags)  # warn 만 있으면 error 아님

    def test_far_above_ground_mismatch(self):
        # 지상연면적 기준 용적률 불일치
        q = {"site_area_sqm": 1000.0, "area_above_ground_sqm": 1000.0,
             "floor_area_ratio_pct": 300.0}  # 계산 100% vs 입력 300%
        assert "far_above_ground_mismatch" in _rules(validate_quantitative(q))


# ═══════════════════════════════════════════════════════════════════════════════
# merge_extracted_data 훅 — 제안서만 _quantitative_flags 부착, brief 제외

class TestMergeHook:

    def test_proposal_inconsistent_attaches_flags(self):
        cls = [{"page": 1, "primary_type": "AREA_TABLE"}]
        ext = [{"page": 1, "data": {
            "site_area_sqm": 130924.5, "building_area_sqm": 106850.0,
            "building_coverage_ratio_pct": 27.46, "floor_area_ratio_pct": 327.89,
            "total_floor_area_sqm": 29341.01,
        }}]
        result = merge_extracted_data(cls, ext)
        flags = result.get("_quantitative_flags")
        assert flags, "불일치 제안서인데 _quantitative_flags 없음"
        assert "coverage_mismatch" in _rules(flags)

    def test_proposal_clean_no_flags_key(self):
        cls = [{"page": 1, "primary_type": "AREA_TABLE"}]
        ext = [{"page": 1, "data": {
            "site_area_sqm": 7498.0, "building_area_sqm": 4131.36,
            "building_coverage_ratio_pct": 55.1, "floor_area_ratio_pct": 455.51,
            "total_floor_area_sqm": 58817.45,
        }}]
        result = merge_extracted_data(cls, ext)
        assert "_quantitative_flags" not in result  # 무결 → 키 자체 없음

    def test_brief_inconsistent_is_skipped(self):
        # 동일 불일치라도 brief 결과면 검증 스킵 (gate: not is_brief)
        cls = [{"page": 1, "primary_type": "BRIEF_PROGRAM"}]
        ext = [{"page": 1, "data": {
            "total_required_floor_area_sqm": 29341.01,
            "site_area_sqm": 130924.5,
            "floor_area_ratio_limit_pct": 327.89,
        }}]
        result = merge_extracted_data(cls, ext)
        assert "_quantitative_flags" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# pattern_builder — error 플래그 필드를 패턴 집계에서 제외

class TestPatternBuilderExcludesFlagged:

    def _sub(self, quant, flags=None):
        ed = {"_quantitative": quant}
        if flags is not None:
            ed["_quantitative_flags"] = flags
        return {"extracted_data": ed}

    def test_error_flagged_fields_excluded(self):
        good = self._sub({"building_coverage_ratio_pct": 50.0, "site_area_sqm": 1000.0})
        bad = self._sub(
            {"building_coverage_ratio_pct": 20.0, "building_area_sqm": 500.0, "site_area_sqm": 1000.0},
            [{"rule": "coverage_mismatch", "severity": "error",
              "fields": ["building_coverage_ratio_pct", "building_area_sqm", "site_area_sqm"]}],
        )
        stats = _build_quant_stats([good, bad])
        # 결함의 건폐율(20)·대지(1000)는 제외 → 정상값만 집계
        assert stats["building_coverage_ratio_pct"]["n"] == 1
        assert stats["building_coverage_ratio_pct"]["mean"] == 50.0
        assert stats["site_area_sqm"]["n"] == 1  # bad 의 site 도 flag fields → 제외
        assert "building_area_sqm" not in stats  # bad 만 갖고 있었고 제외됨 → 통계 없음

    def test_warn_flag_not_excluded(self):
        sub = self._sub({"floors_above": 30},
                        [{"rule": "coverage_gt_far", "severity": "warn", "fields": ["floors_above"]}])
        assert _build_quant_stats([sub])["floors_above"]["n"] == 1  # warn 은 유지

    def test_no_flags_unchanged(self):
        sub = self._sub({"parking_count": 100})
        assert _build_quant_stats([sub])["parking_count"]["n"] == 1

    def test_legacy_record_without_flags_revalidated(self):
        # 플래그 훅 도입 이전 추출된 구 레코드(_quantitative_flags 키 없음)도
        # 집계 시점 재검증으로 정화 — 하안주공 실값(건폐율 모순 + 총연면적<용적률함의)
        bad_legacy = self._sub({
            "total_floor_area_sqm": 29341.01, "site_area_sqm": 130924.5,
            "building_area_sqm": 106850.0, "building_coverage_ratio_pct": 27.46,
            "floor_area_ratio_pct": 327.89, "floors_above": 45, "parking_count": 6895,
        })  # flags 인자 없음 → 저장 플래그 부재
        stats = _build_quant_stats([bad_legacy])
        # 모순 연루 필드는 재검증으로 제외
        for f in ("building_coverage_ratio_pct", "building_area_sqm",
                  "site_area_sqm", "total_floor_area_sqm", "floor_area_ratio_pct"):
            assert f not in stats, f"{f} 재검증 제외 실패(구 레코드 유입)"
        # 모순과 무관한 필드는 유지
        assert stats["floors_above"]["mean"] == 45
        assert stats["parking_count"]["mean"] == 6895
