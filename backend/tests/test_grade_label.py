"""3단계 표시 라벨 회귀 테스트 (임원 요청 — A~E 내부 유지, 표시만 우수/보통/미흡).

내부 등급은 A~E 그대로(순위·차별화·패턴 계산), 리포트/UI 뱃지에만 3단계 라벨 노출.
색도 3단계로 collapse(같은 단어에 다른 색 방지). 백엔드 generator 렌더까지 확인.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import axes_for
from services.grade_helpers import grade_label, grade_label_colors, grade_label_ring, GRADE_COLORS
from services.report_generator import generate_comparison_report
from services.diagnosis_report_generator import generate_diagnosis_report

AX = list(axes_for("public").keys())[0]


class TestGradeLabelMapping:
    def test_three_level_labels(self):
        assert grade_label("A") == "우수" and grade_label("B") == "우수"
        assert grade_label("C") == "보통"
        assert grade_label("D") == "미흡" and grade_label("E") == "미흡"
        assert grade_label(None) == "" and grade_label("Z") == ""

    def test_color_collapsed_to_three(self):
        # 우수=A색, 보통=C색, 미흡=E색 (A/B 같은 색, D/E 같은 색)
        assert grade_label_colors("A") == grade_label_colors("B") == GRADE_COLORS["A"]
        assert grade_label_colors("C") == GRADE_COLORS["C"]
        assert grade_label_colors("D") == grade_label_colors("E") == GRADE_COLORS["E"]
        assert grade_label_ring("B") == GRADE_COLORS["A"][0]


class TestReportsShowWords:
    def _cell(self, g):
        return {"grade": g, "strengths": ["좋음 (p.3)"], "weaknesses": [],
                "brief_compliance": "partial", "notes": "명확 (p.7)"}

    def test_compare_badge_word(self):
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "현대", "result": "win", "total_pages": 10, "extracted_data": {}},
                {"company": "삼성", "result": "lose", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"현대": {AX: self._cell("A")}, "삼성": {AX: self._cell("D")}},
                "concept_comparison": {}, "winner_strengths": [], "loser_weaknesses": [],
                "gap_analysis": {}}
        html = generate_comparison_report(meta, subs, comp)
        assert "우수" in html and "미흡" in html
        # 등급 뱃지에 A~E letter 가 단독으로 노출되지 않음 (회사명 등과 구분 위해 뱃지 스팬 확인)
        assert 'letter-spacing:0.5px">우수</span>' in html

    def test_diagnosis_ring_word(self):
        diag = {"facility_type": "public", "overall_grade": "C",
                "axes": {AX: {"grade": "A", "strengths": ["s (p.1)"]}}}
        html = generate_diagnosis_report(diag)
        assert "보통" in html and "우수" in html  # 종합 C→보통, 축 A→우수
