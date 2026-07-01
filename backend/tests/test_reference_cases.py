"""tests/test_reference_cases.py — services.reference_cases 순수 함수 테스트.

LLM 호출 없음(결정론 조회/선별만) — 임시 DB 디렉토리에 db_manager 저장 함수로
fixture 를 만들고 collect_reference_context 의 정렬·상한·빈 케이스를 검증한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings
from services.db_manager import save_project_meta, save_submission, save_comparison
from services.reference_cases import collect_reference_context


FT = "test_facility"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    return tmp_path


def _make_submission(company: str, result: str, competition_id: str, main_strategy: str = "") -> dict:
    return {
        "company": company,
        "result": result,
        "competition_id": competition_id,
        "extracted_data": {
            "concept": [{
                "concept_name_ko": f"{company} 컨셉",
                "main_strategy": main_strategy,
                "sub_strategies": ["a", "b", "c", "d"],
            }],
        },
    }


class TestEmptyDB:
    def test_no_data_returns_empty(self, db):
        assert collect_reference_context(FT) == {}

    def test_blank_facility_type_returns_empty(self, db):
        assert collect_reference_context("") == {}


class TestCaseExcerpts:
    def test_winning_submission_with_strategy_included(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "win", _make_submission("A사", "win", "c1", "저층 개방형"))

        ctx = collect_reference_context(FT)
        assert ctx["case_excerpts"], "당선 발췌가 있어야 함"
        case = ctx["case_excerpts"][0]
        assert case["company"] == "A사"
        assert case["main_strategy"] == "저층 개방형"
        assert case["competition_name"] == "테스트공모"
        assert len(case["sub_strategies"]) <= 3

    def test_losing_submission_excluded_from_case_excerpts(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "B사", "lose", _make_submission("B사", "lose", "c1", "탈락 전략"))

        ctx = collect_reference_context(FT)
        assert ctx == {}, "낙선만 있으면 case_excerpts/pattern 모두 비어 전체 {} 여야 함"

    def test_empty_main_strategy_skipped(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "win", _make_submission("A사", "win", "c1", ""))

        ctx = collect_reference_context(FT)
        assert ctx == {}

    def test_capped_at_three(self, db):
        for i in range(5):
            cid = f"c{i}"
            save_project_meta(cid, FT, f"공모{i}", "", "", "", merge=True)
            save_submission(FT, cid, f"사{i}", "win", _make_submission(f"사{i}", "win", cid, f"전략{i}"))

        ctx = collect_reference_context(FT)
        assert len(ctx["case_excerpts"]) == 3

    def test_contracted_result_also_counts_as_winner(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "contracted", _make_submission("A사", "contracted", "c1", "수의계약 전략"))

        ctx = collect_reference_context(FT)
        assert ctx["case_excerpts"][0]["main_strategy"] == "수의계약 전략"


class TestConceptComparisonExcerpts:
    def test_comparison_axis_text_included(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "win", _make_submission("A사", "win", "c1", "전략"))
        save_comparison(FT, "c1", {
            "concept_comparison": {
                "site_planning": "A사는 저층 개방형을, B사는 고층 집약형을 채택했다 (p.5)",
            }
        })

        ctx = collect_reference_context(FT)
        excerpts = ctx["concept_comparison_excerpts"]
        assert excerpts
        assert excerpts[0]["axis"] == "site_planning"
        assert "저층 개방형" in excerpts[0]["text"]

    def test_short_text_filtered_out(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "win", _make_submission("A사", "win", "c1", "전략"))
        save_comparison(FT, "c1", {"concept_comparison": {"axis1": "짧음"}})

        ctx = collect_reference_context(FT)
        assert ctx["concept_comparison_excerpts"] == []

    def test_capped_at_four(self, db):
        save_project_meta("c1", FT, "테스트공모", "", "", "", merge=True)
        save_submission(FT, "c1", "A사", "win", _make_submission("A사", "win", "c1", "전략"))
        save_comparison(FT, "c1", {
            "concept_comparison": {
                f"axis{i}": f"충분히 긴 비교 서술문입니다 축{i}" for i in range(6)
            }
        })

        ctx = collect_reference_context(FT)
        assert len(ctx["concept_comparison_excerpts"]) == 4


class TestFacilityTypeIsolation:
    def test_other_facility_type_not_mixed_in(self, db):
        save_project_meta("c1", "other_facility", "다른시설공모", "", "", "", merge=True)
        save_submission("other_facility", "c1", "A사", "win", _make_submission("A사", "win", "c1", "다른시설 전략"))

        assert collect_reference_context(FT) == {}
