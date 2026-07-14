"""교차비교 구조화 데이터 저장/재조회 회귀 테스트 (MATURITY 로드맵 #4).

HTML 옆에 comparison JSON 을 저장해 LLM 재호출 없이 재렌더·이력이 가능한지,
list 의 has_data 플래그가 구/신 리포트를 구분하는지 잠근다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings
from services.db_manager import (
    save_cross_compare_report, save_cross_compare_data,
    load_cross_compare_data, list_cross_compare_reports,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    return tmp_path


_FN = "20260714_120000_projA_vs_projB.html"
_DATA = {
    "meta": {"competition_name": "교차비교 — A vs B", "facility_type": "public"},
    "items": [{"facility_type": "public", "competition_id": "c1", "company": "A"}],
    "submissions": [{"company": "A", "total_pages": 10}],
    "comparison": {"submissions": {"A": {}}, "concept_comparison": {}},
    "created_at": "20260714_120000",
}


class TestSaveLoadRoundtrip:
    def test_roundtrip(self, db):
        save_cross_compare_data(_FN, _DATA)
        loaded = load_cross_compare_data(_FN)
        assert loaded["comparison"]["submissions"] == {"A": {}}
        assert loaded["created_at"] == "20260714_120000"

    def test_stored_as_json_stem(self, db):
        save_cross_compare_data(_FN, _DATA)
        assert (db / "_cross_reports" / "20260714_120000_projA_vs_projB.json").exists()

    def test_missing_returns_empty(self, db):
        assert load_cross_compare_data("nope.html") == {}


class TestHasDataFlag:
    def test_new_report_has_data_true(self, db):
        save_cross_compare_report(_FN, "<html>x</html>")
        save_cross_compare_data(_FN, _DATA)
        reports = list_cross_compare_reports()
        assert len(reports) == 1
        assert reports[0]["has_data"] is True

    def test_legacy_report_has_data_false(self, db):
        # 구 리포트 = HTML만 (JSON 없음)
        save_cross_compare_report(_FN, "<html>x</html>")
        reports = list_cross_compare_reports()
        assert reports[0]["has_data"] is False
