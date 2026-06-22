"""
순수 함수 단위 테스트 — LLM / PDF / 네트워크 의존 없음.

대상:
  - parse_json_response         (services/utils.py)
  - merge_extracted_data        (services/data_extractor.py)
  - _compute_gap_analysis       (services/comparator.py)
  - to_grade / LEGACY_GRADE_MAP (services/grade_helpers.py)
      check_overall=False  → axis dict 전용 (report_generator 동작)
      check_overall=True   → overall_grade/overall_score 폴백 추가 (diagnosis 동작)
  - validate_brief              (services/brief_validator.py)
"""
import json
import pytest

from services.utils import parse_json_response
from services.data_extractor import merge_extracted_data
from services.comparator import _compute_gap_analysis
from services.grade_helpers import to_grade, LEGACY_GRADE_MAP
from services.brief_validator import validate_brief
from config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# parse_json_response
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseJsonResponse:

    def test_clean_object(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}

    def test_clean_array(self):
        result = parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_clean_nested(self):
        payload = '{"x": {"y": [1, 2]}, "z": null}'
        assert parse_json_response(payload) == {"x": {"y": [1, 2]}, "z": None}

    def test_json_fence_with_language(self):
        text = '```json\n{"key": "value"}\n```'
        assert parse_json_response(text) == {"key": "value"}

    def test_json_fence_without_language(self):
        text = '```\n{"key": "value"}\n```'
        assert parse_json_response(text) == {"key": "value"}

    def test_json_buried_in_prose(self):
        text = '분석 결과입니다.\n{"score": 9}\n이상입니다.'
        assert parse_json_response(text) == {"score": 9}

    def test_array_buried_in_prose(self):
        text = '결과: [1, 2, 3] 입니다.'
        assert parse_json_response(text) == [1, 2, 3]

    def test_trailing_comma_in_object(self):
        text = '{"a": 1, "b": 2,}'
        assert parse_json_response(text) == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self):
        text = '[1, 2, 3,]'
        assert parse_json_response(text) == [1, 2, 3]

    def test_trailing_comma_buried_in_prose(self):
        text = '아래 참고: {"grade": "A", "notes": "good",} 끝.'
        result = parse_json_response(text)
        assert result == {"grade": "A", "notes": "good"}

    def test_unicode_values(self):
        text = '{"이름": "건원", "등급": "A"}'
        assert parse_json_response(text) == {"이름": "건원", "등급": "A"}

    def test_empty_object(self):
        assert parse_json_response('{}') == {}

    def test_empty_array(self):
        assert parse_json_response('[]') == []

    def test_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response('')

    def test_pure_prose_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response('분석 결과가 없습니다.')

    def test_only_fence_no_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response('```json\n이것은 JSON이 아닙니다\n```')

    def test_whitespace_only_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response('   \n\t  ')


# ═══════════════════════════════════════════════════════════════════════════════
# merge_extracted_data
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeExtractedData:

    def test_both_empty(self):
        result = merge_extracted_data([], [])
        assert result["_by_type"] == {}
        assert result["_quantitative"] == {}

    def test_single_page_no_extraction(self):
        cls = [{"page": 1, "primary_type": "COVER"}]
        result = merge_extracted_data(cls, [])
        assert result["cover"]["_page"] == 1
        assert result["_by_type"]["COVER"]["count"] == 1

    def test_single_page_with_data(self):
        cls = [{"page": 1, "primary_type": "CONCEPT"}]
        ext = [{"page": 1, "data": {"keywords": ["green", "public"], "massing_type": "탑형"}}]
        result = merge_extracted_data(cls, ext)
        assert result["concept"]["keywords"] == ["green", "public"]
        assert result["concept"]["_page"] == 1

    def test_single_page_type_returns_dict_not_list(self):
        cls = [{"page": 3, "primary_type": "AREA_TABLE"}]
        ext = [{"page": 3, "data": {"total_floor_area_sqm": 10000}}]
        result = merge_extracted_data(cls, ext)
        # 한 페이지 → dict (리스트 아님)
        assert isinstance(result["area_table"], dict)

    def test_multiple_pages_same_type_returns_list(self):
        cls = [
            {"page": 1, "primary_type": "FLOOR_PLAN"},
            {"page": 2, "primary_type": "FLOOR_PLAN"},
        ]
        result = merge_extracted_data(cls, [])
        assert isinstance(result["floor_plan"], list)
        assert len(result["floor_plan"]) == 2

    def test_duplicate_page_numbers_skipped(self):
        cls = [
            {"page": 1, "primary_type": "COVER"},
            {"page": 1, "primary_type": "COVER"},  # 중복
        ]
        result = merge_extracted_data(cls, [])
        assert result["_by_type"]["COVER"]["count"] == 1

    def test_ext_data_list_wrapped(self):
        cls = [{"page": 5, "primary_type": "CONCEPT"}]
        # 모델이 배열 반환한 경우
        ext = [{"page": 5, "data": ["keyword1", "keyword2"]}]
        result = merge_extracted_data(cls, ext)
        assert "_items" in result["concept"]
        assert result["concept"]["_items"] == ["keyword1", "keyword2"]

    def test_quantitative_from_area_table(self):
        cls = [{"page": 10, "primary_type": "AREA_TABLE"}]
        ext = [{"page": 10, "data": {
            "total_floor_area_sqm": 45000,
            "floor_area_ratio_pct": 250.0,
            "building_coverage_ratio_pct": 40.0,
            "floors_above": 25,
            "floors_below": 3,
        }}]
        result = merge_extracted_data(cls, ext)
        q = result["_quantitative"]
        assert q["total_floor_area_sqm"] == 45000
        assert q["floor_area_ratio_pct"] == 250.0
        assert q["floors_above"] == 25
        assert q["floors_below"] == 3

    def test_quantitative_from_site_plan_fallback(self):
        cls = [{"page": 2, "primary_type": "SITE_PLAN"}]
        ext = [{"page": 2, "data": {"site_area_sqm": 12000, "building_area_sqm": 4800}}]
        result = merge_extracted_data(cls, ext)
        q = result["_quantitative"]
        assert q["site_area_sqm"] == 12000
        assert q["building_area_sqm"] == 4800

    def test_area_table_wins_over_site_plan(self):
        """AREA_TABLE 값이 SITE_PLAN 값보다 우선해야 한다."""
        cls = [
            {"page": 5, "primary_type": "AREA_TABLE"},
            {"page": 2, "primary_type": "SITE_PLAN"},
        ]
        ext = [
            {"page": 5, "data": {"total_floor_area_sqm": 45000}},
            {"page": 2, "data": {"total_floor_area_sqm": 99999}},  # SITE_PLAN 값
        ]
        result = merge_extracted_data(cls, ext)
        assert result["_quantitative"]["total_floor_area_sqm"] == 45000  # AREA_TABLE 승

    def test_site_plan_supplements_missing_area_table_fields(self):
        """AREA_TABLE에 없는 필드는 SITE_PLAN에서 보완."""
        cls = [
            {"page": 5, "primary_type": "AREA_TABLE"},
            {"page": 2, "primary_type": "SITE_PLAN"},
        ]
        ext = [
            {"page": 5, "data": {"total_floor_area_sqm": 45000}},
            {"page": 2, "data": {"site_area_sqm": 12000}},  # AREA_TABLE에 없는 필드
        ]
        result = merge_extracted_data(cls, ext)
        q = result["_quantitative"]
        assert q["total_floor_area_sqm"] == 45000
        assert q["site_area_sqm"] == 12000  # SITE_PLAN에서 보완

    def test_quantitative_none_values_not_written(self):
        cls = [{"page": 1, "primary_type": "AREA_TABLE"}]
        ext = [{"page": 1, "data": {"total_floor_area_sqm": None, "floors_above": 10}}]
        result = merge_extracted_data(cls, ext)
        assert "total_floor_area_sqm" not in result["_quantitative"]
        assert result["_quantitative"]["floors_above"] == 10

    def test_page_key_added_to_combined_data(self):
        cls = [{"page": 7, "primary_type": "SECTION"}]
        ext = [{"page": 7, "data": {"floor_height_m": 3.2}}]
        result = merge_extracted_data(cls, ext)
        assert result["section"]["_page"] == 7

    def test_multiple_types(self):
        cls = [
            {"page": 1, "primary_type": "COVER"},
            {"page": 2, "primary_type": "CONCEPT"},
            {"page": 3, "primary_type": "AREA_TABLE"},
        ]
        ext = [{"page": 3, "data": {"floors_above": 15}}]
        result = merge_extracted_data(cls, ext)
        assert "cover" in result
        assert "concept" in result
        assert "area_table" in result
        assert result["_quantitative"]["floors_above"] == 15


# ═══════════════════════════════════════════════════════════════════════════════
# _compute_gap_analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeGapAnalysis:

    def test_empty_ranking_unknown(self):
        result = _compute_gap_analysis([], {"A": "win"}, "")
        assert result["alignment"] == "unknown"
        assert result["blind_top1"] is None

    def test_empty_results_map_unknown(self):
        result = _compute_gap_analysis(["A", "B"], {}, "")
        assert result["alignment"] == "unknown"
        assert result["actual_winners"] == []

    def test_both_empty_unknown(self):
        result = _compute_gap_analysis([], {}, "")
        assert result["alignment"] == "unknown"

    def test_top1_matches_only_winner_high(self):
        # 2팀: A 당선, ranking [A, B] → top_half={A}, top1=A match, ratio=1.0 → high
        result = _compute_gap_analysis(["A", "B"], {"A": "win", "B": "lose"}, "notes")
        assert result["alignment"] == "high"
        assert result["top1_matches_winner"] is True
        assert result["blind_top1"] == "A"
        assert "A" in result["actual_winners"]

    def test_top1_mismatch_winner_not_in_top_half_low(self):
        # 2팀: A 당선, ranking [B, A] → top_half={B}, top1=B no match, ratio=0 → low
        result = _compute_gap_analysis(["B", "A"], {"A": "win", "B": "lose"}, "")
        assert result["alignment"] == "low"
        assert result["top1_matches_winner"] is False

    def test_top1_mismatch_but_winner_in_top_half_partial(self):
        # 3팀: A 당선, ranking [B, A, C] → top_half_size=2 → {B,A}
        # blind_top1=B, top1_match=False, winners_in_top=1, ratio=1.0
        # top1_match=False → 조건 1 실패, ratio>=0.5 → partial
        result = _compute_gap_analysis(
            ["B", "A", "C"],
            {"A": "win", "B": "lose", "C": "lose"},
            "gap",
        )
        assert result["alignment"] == "partial"
        assert result["top1_matches_winner"] is False

    def test_winner_in_top_half_all_miss_low(self):
        # 3팀: A 당선, ranking [C, B, A] → top_half={C,B}, ratio=0 → low
        result = _compute_gap_analysis(
            ["C", "B", "A"],
            {"A": "win", "B": "lose", "C": "lose"},
            "",
        )
        assert result["alignment"] == "low"

    def test_contracted_counts_as_winner(self):
        result = _compute_gap_analysis(
            ["A", "B"], {"A": "contracted", "B": "lose"}, ""
        )
        assert "A" in result["actual_winners"]
        assert result["alignment"] == "high"

    def test_gap_notes_none_becomes_empty_string(self):
        result = _compute_gap_analysis(["A"], {"A": "win"}, None)
        assert result["notes"] == ""

    def test_gap_notes_preserved(self):
        result = _compute_gap_analysis(["A"], {"A": "win"}, "some gap note")
        assert result["notes"] == "some gap note"

    def test_multiple_winners_all_in_top_half_high(self):
        # 4팀: A, B 당선, ranking [A, B, C, D]
        # top_half_size=max(1,(4+1)//2)=2 → {A, B}
        # top1=A match, ratio=2/2=1.0 → high
        result = _compute_gap_analysis(
            ["A", "B", "C", "D"],
            {"A": "win", "B": "win", "C": "lose", "D": "lose"},
            "",
        )
        assert result["alignment"] == "high"
        assert len(result["actual_winners"]) == 2

    def test_multiple_winners_partial_in_top_half_partial(self):
        # 4팀: A, B 당선, ranking [C, A, B, D]
        # top_half_size=2 → {C, A}
        # top1=C, top1_match=False
        # winners_in_top: A in {C,A} → 1, B not → 0  → ratio=1/2=0.5
        # top1_match=False, ratio>=0.5 → partial
        result = _compute_gap_analysis(
            ["C", "A", "B", "D"],
            {"A": "win", "B": "contracted", "C": "lose", "D": "lose"},
            "",
        )
        assert result["alignment"] == "partial"

    def test_return_keys_complete(self):
        result = _compute_gap_analysis(["A"], {"A": "win"}, "x")
        assert set(result.keys()) == {
            "blind_top1", "actual_winners", "top1_matches_winner", "alignment", "notes"
        }


# ═══════════════════════════════════════════════════════════════════════════════
# to_grade — check_overall=False (axis dict 전용, report_generator 동작)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToGradeAxisOnly:
    """to_grade(d): grade + score만 체크 (overall_* 무시)."""

    @pytest.mark.parametrize("grade", ["A", "B", "C", "D", "E"])
    def test_new_grade_passthrough(self, grade):
        assert to_grade({"grade": grade}) == grade

    def test_legacy_상_to_B(self):
        assert to_grade({"grade": "상"}) == "B"

    def test_legacy_중_to_C(self):
        assert to_grade({"grade": "중"}) == "C"

    def test_legacy_하_to_D(self):
        assert to_grade({"grade": "하"}) == "D"

    @pytest.mark.parametrize("score,expected", [
        (10.0, "A"),
        (8.5,  "A"),   # 경계: ≥8.5 → A
        (8.4,  "B"),
        (7.0,  "B"),   # 경계: ≥7.0 → B
        (6.9,  "C"),
        (5.0,  "C"),   # 경계: ≥5.0 → C
        (4.9,  "D"),
        (3.0,  "D"),   # 경계: ≥3.0 → D
        (2.9,  "E"),
        (0.0,  "E"),
    ])
    def test_score_to_grade(self, score, expected):
        assert to_grade({"score": score}) == expected

    def test_score_as_string(self):
        assert to_grade({"score": "9.0"}) == "A"

    def test_score_bad_string_returns_none(self):
        assert to_grade({"score": "invalid"}) is None

    def test_empty_dict_returns_none(self):
        assert to_grade({}) is None

    def test_not_dict_returns_none(self):
        assert to_grade(None) is None
        assert to_grade("A") is None
        assert to_grade(42) is None

    def test_unknown_grade_no_score_returns_none(self):
        assert to_grade({"grade": "X"}) is None

    def test_overall_grade_NOT_checked_by_default(self):
        # check_overall 기본값(False)이면 overall_grade 무시
        assert to_grade({"overall_grade": "A"}) is None

    def test_grade_takes_priority_over_score(self):
        assert to_grade({"grade": "A", "score": 1.0}) == "A"

    def test_legacy_map_coverage(self):
        assert set(LEGACY_GRADE_MAP.keys()) == {"상", "중", "하"}
        assert LEGACY_GRADE_MAP["상"] == "B"
        assert LEGACY_GRADE_MAP["중"] == "C"
        assert LEGACY_GRADE_MAP["하"] == "D"


# ═══════════════════════════════════════════════════════════════════════════════
# to_grade — check_overall=True (diagnosis 동작: overall_grade / overall_score 폴백)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToGradeWithOverall:
    """to_grade(d, check_overall=True): overall_grade + overall_score도 체크."""

    @pytest.mark.parametrize("grade", ["A", "B", "C", "D", "E"])
    def test_new_grade_passthrough(self, grade):
        assert to_grade({"grade": grade}, check_overall=True) == grade

    def test_overall_grade_checked(self):
        assert to_grade({"overall_grade": "B"}, check_overall=True) == "B"

    def test_grade_wins_over_overall_grade(self):
        assert to_grade({"grade": "A", "overall_grade": "E"}, check_overall=True) == "A"

    def test_overall_score_fallback(self):
        assert to_grade({"overall_score": 7.5}, check_overall=True) == "B"

    def test_score_wins_over_overall_score(self):
        assert to_grade({"score": 9.0, "overall_score": 1.0}, check_overall=True) == "A"

    def test_legacy_grades(self):
        assert to_grade({"grade": "상"}, check_overall=True) == "B"
        assert to_grade({"grade": "중"}, check_overall=True) == "C"
        assert to_grade({"grade": "하"}, check_overall=True) == "D"

    @pytest.mark.parametrize("score,expected", [
        (8.5, "A"),
        (7.0, "B"),
        (5.0, "C"),
        (3.0, "D"),
        (2.9, "E"),
    ])
    def test_score_boundaries(self, score, expected):
        assert to_grade({"score": score}, check_overall=True) == expected

    def test_empty_dict_returns_none(self):
        assert to_grade({}, check_overall=True) is None

    def test_not_dict_returns_none(self):
        assert to_grade(None, check_overall=True) is None
        assert to_grade("B", check_overall=True) is None


# ═══════════════════════════════════════════════════════════════════════════════
# validate_brief  (services/brief_validator.py)
# LLM / PDF 의존 없음. 전 규칙 결정론적.
# ═══════════════════════════════════════════════════════════════════════════════

def _flags_of(result: dict, type_: str) -> list[dict]:
    return [f for f in result["validation"]["flags"] if f["type"] == type_]


def _summary(result: dict) -> dict:
    return result["validation"]["summary"]


class TestBriefValidatorSchema:
    """출력 스키마 / checked_rules 완전성."""

    def test_output_keys(self):
        r = validate_brief({}, {})
        assert set(r.keys()) == {"validation"}
        assert set(r["validation"].keys()) == {"flags", "summary", "checked_rules"}

    def test_flag_keys(self):
        r = validate_brief(
            {"page_map": [{"page": 1, "primary_type": "BRIEF_DESIGN_GUIDE", "confidence": 0.2}]},
            {},
        )
        for f in r["validation"]["flags"]:
            assert set(f.keys()) == {"type", "severity", "message", "location"}

    def test_severity_values(self):
        r = validate_brief(
            {"page_map": [{"page": 1, "primary_type": "X", "confidence": 0.1}]},
            {},
        )
        for f in r["validation"]["flags"]:
            assert f["severity"] in {"high", "medium", "low"}

    def test_summary_sums_to_flag_count(self):
        r = validate_brief({}, {})
        v = r["validation"]
        assert sum(v["summary"].values()) == len(v["flags"])

    def test_checked_rules_contains_all_five(self):
        rules = validate_brief({}, {})["validation"]["checked_rules"]
        for rule in ("points_mismatch", "duplicate", "omission",
                     "area_cross_check", "low_confidence"):
            assert rule in rules


class TestBriefValidatorPointsMismatch:
    """points_mismatch 규칙."""

    def test_all_points_present_and_sum_matches_no_flag(self):
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 60},
            {"name": "B", "points": 40},
        ]}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_sum_mismatch_is_high(self):
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 60},
            {"name": "B", "points": 50},  # 합 110 != 100
        ]}}
        flags = _flags_of(validate_brief(bd, {}), "points_mismatch")
        assert any(f["severity"] == "high" for f in flags)

    def test_null_with_sum_match_treated_as_qualitative(self):
        # 합계가 만점과 일치하면 null 항목은 정성평가로 간주 — 무경고
        # (영등포 통합신청사 케이스: 설계의 적정성·창의성 등 점수 없는 정성 항목)
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 100},
            {"name": "B", "points": None},
        ]}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_null_with_shared_with_no_flag(self):
        # shared_with 가 있으면 점수 공유 (영등포: 공간계획 → 배치계획 40점 합산)
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "배치계획", "points": 40, "shared_with": ["공간계획"]},
            {"name": "공간계획", "points": None, "shared_with": ["배치계획"]},
            {"name": "기술계획", "points": 60},
        ]}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_yeongdeungpo_mixed_null_pattern_no_flag(self):
        # 영등포 통합신청사 실제 케이스: 7개 카테고리, 4개 numeric, 3개 null
        # (1개 shared_with, 2개 정성평가). numeric 합 100 == total 100 → 무경고
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "과업의 목적",            "points": 20},
            {"name": "배치계획",               "points": 40, "shared_with": ["공간계획"]},
            {"name": "공간계획",               "points": None, "shared_with": ["배치계획"]},
            {"name": "기술계획",               "points": 20},
            {"name": "설계의 적정성",          "points": None},
            {"name": "경관 및 주변과의 조화",  "points": 20},
            {"name": "창의성 및 공공성",       "points": None},
        ]}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_null_plus_sum_mismatch_gives_two_flags(self):
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "배치", "points": 30},
            {"name": "공간", "points": 30},
            {"name": "경관", "points": 20},
            {"name": "기술", "points": None},
        ]}}
        flags = _flags_of(validate_brief(bd, {}), "points_mismatch")
        assert len(flags) == 2
        severities = {f["severity"] for f in flags}
        assert "high" in severities and "medium" in severities

    def test_null_with_shared_with_excluded_from_missing_count(self):
        # 합계 불일치 (high) 발생 시 shared_with 있는 null 은 missing 카운트에서 제외
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 40, "shared_with": ["B"]},
            {"name": "B", "points": None, "shared_with": ["A"]},  # 공유 — missing 아님
            {"name": "C", "points": 30},
            {"name": "D", "points": None},                          # 진짜 missing
        ]}}
        flags = _flags_of(validate_brief(bd, {}), "points_mismatch")
        # 합 70 ≠ 100 → high
        assert any(f["severity"] == "high" for f in flags)
        # missing 메시지에 D 만 포함, B 제외
        medium_msgs = [f["message"] for f in flags if f["severity"] == "medium"]
        assert any("1개" in m and "D" in m for m in medium_msgs)

    def test_epsilon_tolerance_no_flag(self):
        # ±1점 이내 → 플래그 없음
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 99},
            {"name": "B", "points": 1},
        ]}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_empty_categories_no_points_mismatch_flag(self):
        # evaluation_categories가 없으면 omission이 발동하지 points_mismatch는 아님
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": []}}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")

    def test_fallback_to_requirements_criteria(self):
        # brief_evaluation.evaluation_categories가 없으면 _requirements 폴백
        reqs = {"evaluation_criteria": [
            {"item": "A", "points": 70},
            {"item": "B", "points": 50},  # 합 120 != 100
        ]}
        flags = _flags_of(validate_brief({}, reqs), "points_mismatch")
        assert any(f["severity"] == "high" for f in flags)

    def test_fallback_criteria_null_with_sum_match_no_flag(self):
        # fallback 경로도 합계 일치 시 null 은 정성평가로 간주
        reqs = {"evaluation_criteria": [
            {"item": "A", "points": 100},
            {"item": "B", "points": None},
        ]}
        assert not _flags_of(validate_brief({}, reqs), "points_mismatch")

    def test_fallback_criteria_null_with_sum_mismatch_medium(self):
        # 합계 불일치 시 null 항목 미기재로 medium 경고
        reqs = {"evaluation_criteria": [
            {"item": "A", "points": 60},
            {"item": "B", "points": None},   # 합 60 ≠ 100 → high + medium
        ]}
        flags = _flags_of(validate_brief({}, reqs), "points_mismatch")
        severities = {f["severity"] for f in flags}
        assert "high" in severities and "medium" in severities

    def test_primary_path_takes_priority_over_fallback(self):
        # brief_evaluation.evaluation_categories가 있으면 requirements.evaluation_criteria 무시
        bd = {"brief_evaluation": {"total_points": 100, "evaluation_categories": [
            {"name": "A", "points": 50},
            {"name": "B", "points": 50},  # 합 100 == 100 → primary path no flag
        ]}}
        reqs = {"evaluation_criteria": [{"item": "X", "points": 200}]}  # 폴백 있어도 무시
        assert not _flags_of(validate_brief(bd, reqs), "points_mismatch")

    def test_total_points_inferred_as_100_when_absent(self):
        # total_points 없으면 100으로 간주
        bd = {"brief_evaluation": {"evaluation_categories": [
            {"name": "A", "points": 60},
            {"name": "B", "points": 50},  # 합 110 != 100
        ]}}
        flags = _flags_of(validate_brief(bd, {}), "points_mismatch")
        assert any(f["severity"] == "high" for f in flags)

    def test_brief_evaluation_as_list_uses_first(self):
        bd = {"brief_evaluation": [
            {"total_points": 100, "evaluation_categories": [
                {"name": "A", "points": 60},
                {"name": "B", "points": 40},
            ]}
        ]}
        assert not _flags_of(validate_brief(bd, {}), "points_mismatch")


class TestBriefValidatorDuplicate:
    """duplicate 규칙."""

    def test_similar_same_axis_is_flagged(self):
        reqs = {"requirements": [
            {"axis": "program_planning", "description": "다양한 공간 프로그램 계획"},
            {"axis": "program_planning", "description": "다양한 프로그램 공간 계획"},
        ]}
        assert _flags_of(validate_brief({}, reqs), "duplicate")

    def test_similar_different_axis_no_flag(self):
        reqs = {"requirements": [
            {"axis": "program_planning", "description": "다양한 공간 프로그램 계획"},
            {"axis": "site_response",    "description": "다양한 프로그램 공간 계획"},
        ]}
        assert not _flags_of(validate_brief({}, reqs), "duplicate")

    def test_dissimilar_same_axis_no_flag(self):
        reqs = {"requirements": [
            {"axis": "program_planning", "description": "주차 대수 기준 준수"},
            {"axis": "program_planning", "description": "친환경 자재 사용 계획"},
        ]}
        assert not _flags_of(validate_brief({}, reqs), "duplicate")

    def test_three_items_two_duplicates_one_flag(self):
        reqs = {"requirements": [
            {"axis": "concept_clarity", "description": "창의적 공간 개념 제안"},
            {"axis": "concept_clarity", "description": "창의적 개념 공간 제안"},  # dup of [0]
            {"axis": "concept_clarity", "description": "환경 친화적 설계 방향"},   # unique
        ]}
        flags = _flags_of(validate_brief({}, reqs), "duplicate")
        assert len(flags) == 1

    def test_empty_requirements_no_flag(self):
        assert not _flags_of(validate_brief({}, {}), "duplicate")
        assert not _flags_of(validate_brief({}, {"requirements": []}), "duplicate")

    def test_single_requirement_no_flag(self):
        reqs = {"requirements": [{"axis": "program_planning", "description": "A B C"}]}
        assert not _flags_of(validate_brief({}, reqs), "duplicate")

    def test_flag_location_contains_indices(self):
        reqs = {"requirements": [
            {"axis": "program_planning", "description": "동일 공간 계획 제안"},
            {"axis": "program_planning", "description": "동일 계획 공간 제안"},
        ]}
        flag = _flags_of(validate_brief({}, reqs), "duplicate")[0]
        assert "0" in flag["location"] and "1" in flag["location"]


class TestBriefValidatorOmission:
    """omission 규칙."""

    def test_all_null_fires_four_flags(self):
        # _quantitative 빈 dict + brief_evaluation 없음 → 연면적 high, 건폐 medium, 용적 medium, 심사기준 high
        r = validate_brief({"_quantitative": {}}, {})
        flags = _flags_of(r, "omission")
        severities = [f["severity"] for f in flags]
        assert severities.count("high") == 2
        assert severities.count("medium") == 2

    def test_brief_program_suppresses_area_flags(self):
        bd = {
            "_quantitative": {},
            "brief_program": {
                "total_required_floor_area_sqm": 5000,
                "building_coverage_limit_pct": 60,
                "floor_area_ratio_limit_pct": 200,
            },
            "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]},
        }
        flags = _flags_of(validate_brief(bd, {}), "omission")
        messages = [f["message"] for f in flags]
        assert not any("연면적" in m for m in messages)
        assert not any("건폐율" in m for m in messages)
        assert not any("용적률" in m for m in messages)

    def test_brief_regulations_suppresses_coverage_far(self):
        bd = {
            "_quantitative": {},
            "brief_program": {"total_required_floor_area_sqm": 5000},
            "brief_regulations": {
                "building_coverage_ratio_limit_pct": 60,
                "floor_area_ratio_limit_pct": 200,
            },
            "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]},
        }
        flags = _flags_of(validate_brief(bd, {}), "omission")
        messages = [f["message"] for f in flags]
        assert not any("건폐율" in m for m in messages)
        assert not any("용적률" in m for m in messages)

    def test_quantitative_suppresses_area_flags(self):
        bd = {
            "_quantitative": {
                "total_floor_area_sqm": 4500,
                "building_coverage_ratio_pct": 55,
                "floor_area_ratio_pct": 180,
            },
            "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]},
        }
        assert not _flags_of(validate_brief(bd, {}), "omission")

    def test_area_table_fallback_suppresses_area(self):
        bd = {
            "_quantitative": {},
            "area_table": {"total_required_area_sqm": 3000},
            "brief_evaluation": {"evaluation_categories": [{"name": "A", "points": 100}]},
        }
        flags = _flags_of(validate_brief(bd, {}), "omission")
        assert not any("연면적" in f["message"] for f in flags)

    def test_evaluation_categories_empty_fires_high(self):
        bd = {
            "brief_evaluation": {"evaluation_categories": []},
            "_quantitative": {
                "total_floor_area_sqm": 1000,
                "building_coverage_ratio_pct": 60,
                "floor_area_ratio_pct": 200,
            },
        }
        flags = _flags_of(validate_brief(bd, {}), "omission")
        assert any("심사기준" in f["message"] and f["severity"] == "high" for f in flags)

    def test_evaluation_criteria_fallback_suppresses_eval_omission(self):
        bd = {
            "_quantitative": {
                "total_floor_area_sqm": 1000,
                "building_coverage_ratio_pct": 60,
                "floor_area_ratio_pct": 200,
            },
        }
        reqs = {"evaluation_criteria": [{"item": "A", "points": 100}]}
        flags = _flags_of(validate_brief(bd, reqs), "omission")
        assert not any("심사기준" in f["message"] for f in flags)

    def test_brief_evaluation_as_list(self):
        bd = {
            "_quantitative": {
                "total_floor_area_sqm": 1000,
                "building_coverage_ratio_pct": 60,
                "floor_area_ratio_pct": 200,
            },
            "brief_evaluation": [{"evaluation_categories": [{"name": "A", "points": 100}]}],
        }
        assert not _flags_of(validate_brief(bd, {}), "omission")


class TestBriefValidatorAreaCrossCheck:
    """area_cross_check 규칙."""

    def test_exact_match_no_flag(self):
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 600},
                      {"name": "B", "required_area_sqm": 400}],
        }}
        assert not _flags_of(validate_brief(bd, {}), "area_cross_check")

    def test_within_tolerance_no_flag(self):
        # 합 = 1100, 10% 초과이지만 12% 이내
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 600},
                      {"name": "B", "required_area_sqm": 500}],
        }}
        assert not _flags_of(validate_brief(bd, {}), "area_cross_check")

    def test_over_tolerance_is_medium(self):
        # 합 = 1200, 20% 초과 → medium
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 700},
                      {"name": "B", "required_area_sqm": 500}],
        }}
        flags = _flags_of(validate_brief(bd, {}), "area_cross_check")
        assert flags and flags[0]["severity"] == "medium"

    def test_over_25pct_is_high(self):
        # 합 = 1300, 30% 초과 → high
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 700},
                      {"name": "B", "required_area_sqm": 600}],
        }}
        flags = _flags_of(validate_brief(bd, {}), "area_cross_check")
        assert flags and flags[0]["severity"] == "high"

    def test_under_tolerance_is_flagged(self):
        # 합 = 700, 30% 부족 → high
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 400},
                      {"name": "B", "required_area_sqm": 300}],
        }}
        flags = _flags_of(validate_brief(bd, {}), "area_cross_check")
        assert flags and flags[0]["severity"] == "high"

    def test_missing_total_no_flag(self):
        bd = {"brief_program": {
            "rooms": [{"name": "A", "required_area_sqm": 500}],
        }}
        assert not _flags_of(validate_brief(bd, {}), "area_cross_check")

    def test_empty_rooms_no_flag(self):
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [],
        }}
        assert not _flags_of(validate_brief(bd, {}), "area_cross_check")

    def test_rooms_with_null_areas_excluded(self):
        # None 값 제외 후 합 = 500, 50% 부족 → high
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 500},
                      {"name": "B", "required_area_sqm": None}],
        }}
        flags = _flags_of(validate_brief(bd, {}), "area_cross_check")
        assert flags and flags[0]["severity"] == "high"

    def test_legacy_area_table_path(self):
        # brief_program 없을 때 area_table 폴백
        bd = {"area_table": {
            "total_required_area_sqm": 1000,
            "room_program": [{"name": "A", "area_sqm": 400},
                             {"name": "B", "area_sqm": 300}],
        }}
        flags = _flags_of(validate_brief(bd, {}), "area_cross_check")
        assert flags  # 30% 부족 → high

    def test_legacy_uses_area_sqm_field(self):
        bd = {"area_table": {
            "total_required_area_sqm": 1000,
            "room_program": [{"name": "A", "area_sqm": 500},
                             {"name": "B", "area_sqm": 490}],  # 합 990, <2% → no flag
        }}
        assert not _flags_of(validate_brief(bd, {}), "area_cross_check")

    def test_flag_message_contains_sqm_values(self):
        bd = {"brief_program": {
            "total_required_floor_area_sqm": 1000,
            "rooms": [{"name": "A", "required_area_sqm": 1400}],
        }}
        flag = _flags_of(validate_brief(bd, {}), "area_cross_check")[0]
        assert "1,400" in flag["message"] or "1400" in flag["message"]
        assert "1,000" in flag["message"] or "1000" in flag["message"]


class TestBriefValidatorLowConfidence:
    """low_confidence 규칙."""

    def test_high_confidence_no_flag(self):
        bd = {"page_map": [{"page": 1, "primary_type": "BRIEF_OVERVIEW", "confidence": 0.9}]}
        assert not _flags_of(validate_brief(bd, {}), "low_confidence")

    def test_at_threshold_no_flag(self):
        bd = {"page_map": [{"page": 1, "primary_type": "BRIEF_DESIGN_GUIDE", "confidence": 0.55}]}
        assert not _flags_of(validate_brief(bd, {}), "low_confidence")

    def test_below_threshold_is_flagged(self):
        bd = {"page_map": [{"page": 2, "primary_type": "BRIEF_PROGRAM", "confidence": 0.4}]}
        flags = _flags_of(validate_brief(bd, {}), "low_confidence")
        assert len(flags) == 1
        assert flags[0]["severity"] == "low"

    def test_location_contains_page_number(self):
        bd = {"page_map": [{"page": 7, "primary_type": "BRIEF_REGULATIONS", "confidence": 0.3}]}
        flag = _flags_of(validate_brief(bd, {}), "low_confidence")[0]
        assert "p7" in flag["location"]

    def test_multiple_low_pages(self):
        # threshold = 0.55: p1(0.9) ok, p2(0.3) low, p3(0.6) ok, p4(0.1) low
        bd = {"page_map": [
            {"page": 1, "primary_type": "BRIEF_OVERVIEW",     "confidence": 0.9},
            {"page": 2, "primary_type": "BRIEF_PROGRAM",      "confidence": 0.3},
            {"page": 3, "primary_type": "BRIEF_EVALUATION",   "confidence": 0.6},
            {"page": 4, "primary_type": "BRIEF_DESIGN_GUIDE", "confidence": 0.1},
        ]}
        flags = _flags_of(validate_brief(bd, {}), "low_confidence")
        assert len(flags) == 2
        pages = {f["location"] for f in flags}
        assert "page_map.p2" in pages and "page_map.p4" in pages

    def test_missing_confidence_field_skipped(self):
        bd = {"page_map": [{"page": 1, "primary_type": "BRIEF_OVERVIEW"}]}
        assert not _flags_of(validate_brief(bd, {}), "low_confidence")

    def test_empty_page_map_no_flag(self):
        assert not _flags_of(validate_brief({"page_map": []}, {}), "low_confidence")

    def test_message_contains_page_and_type(self):
        bd = {"page_map": [{"page": 5, "primary_type": "BRIEF_TECHNICAL", "confidence": 0.4}]}
        flag = _flags_of(validate_brief(bd, {}), "low_confidence")[0]
        assert "p.5" in flag["message"]
        assert "BRIEF_TECHNICAL" in flag["message"]


class TestSanitizeApiKey:
    """_sanitize_api_key 복붙 아티팩트 제거.

    회귀: 키 파일을 메모장/PowerShell utf8 로 저장하면 선두 UTF-8 BOM(﻿)이
    붙어 httpx 헤더 인코딩(ascii)에서 UnicodeEncodeError 발생. str.strip() 은 BOM 을
    제거하지 못하므로 명시적 제거 필요.
    """
    _s = staticmethod(settings._sanitize_api_key)

    def test_strips_utf8_bom(self):
        out = self._s("﻿sk-ant-abc123")
        assert out == "sk-ant-abc123"
        out.encode("ascii")  # ascii 인코딩 가능해야 (httpx 헤더)

    def test_strips_zero_width_chars(self):
        assert self._s("sk-ant-​abc⁠") == "sk-ant-abc"

    def test_strips_crlf_and_quotes(self):
        assert self._s('"sk-ant-xyz"\r\n') == "sk-ant-xyz"

    def test_strips_echo_n_prefix(self):
        assert self._s("-n sk-ant-xyz") == "sk-ant-xyz"

    def test_bom_plus_crlf_combo(self):
        out = self._s("﻿sk-ant-key\r\n")
        assert out == "sk-ant-key"
        out.encode("ascii")

    def test_clean_key_unchanged(self):
        assert self._s("sk-ant-clean") == "sk-ant-clean"

    def test_empty_and_none(self):
        assert self._s("") == ""
        assert self._s(None) == ""
