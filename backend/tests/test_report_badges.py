"""사실/해석 2층 분리 렌더 회귀 테스트 (MATURITY 로드맵 #7).

진단·비교 리포트가 추론(보강·사후요약)에 'AI 해석' 배지 + 범례를 붙여 사실(강점/약점/
근거, p.N 인용)과 구분하는 것을 잠근다. 데이터·프롬프트 불변, 렌더 레이어만.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.report_badges import ai_badge, fact_interp_legend
from services.diagnosis_report_generator import generate_diagnosis_report
from services.report_generator import generate_comparison_report


class TestBadgeHelpers:
    def test_ai_badge_default_label(self):
        assert "AI 해석" in ai_badge()

    def test_ai_badge_custom_label(self):
        assert "추론" in ai_badge("추론")

    def test_legend_mentions_both_layers(self):
        leg = fact_interp_legend()
        assert "사실" in leg and "AI 해석" in leg
        assert "p.N" in leg or "인용" in leg


class TestDiagnoseReport:
    def _report(self):
        diag = {
            "facility_type": "public",
            "axes": {"공간": {"grade": "B", "strengths": ["좋음 (p.3)"],
                              "weaknesses": ["약함 (p.4)"], "recommendations": ["개선 (p.5)"]}},
            "recommendations": ["전반 보강"],
        }
        return generate_diagnosis_report(diag)

    def test_has_legend(self):
        assert "제출물에서 직접 관찰" in self._report()

    def test_recommendations_badged(self):
        html = self._report()
        # 보강 포인트 섹션 + 축별 보강 라인 모두 배지
        assert html.count("AI 해석") >= 2

    def test_no_recommendations_no_badge_section(self):
        # 보강이 없으면 보강 섹션 자체가 없음 (배지는 범례에만)
        diag = {"facility_type": "public",
                "axes": {"공간": {"grade": "B", "strengths": ["좋음 (p.3)"]}}}
        html = generate_diagnosis_report(diag)
        # 범례 1회만 (섹션 배지 없음)
        assert html.count("AI 해석") == 1


class TestCompareReport:
    def _report(self, ws, lw):
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "A", "result": "win", "total_pages": 10, "extracted_data": {}}]
        comparison = {"submissions": {"A": {}}, "concept_comparison": {},
                      "winner_strengths": ws, "loser_weaknesses": lw, "gap_analysis": {}}
        return generate_comparison_report(meta, subs, comparison)

    def test_inference_sections_badged_and_legend(self):
        html = self._report(["배치 우수 (p.3)"], ["동선 미흡 (p.5)"])
        assert "제출물에서 직접 관찰" in html      # 범례
        assert html.count("AI 해석") == 3          # 범례 + 당선 + 낙선

    def test_legend_absent_without_inference(self):
        html = self._report([], [])
        assert "제출물에서 직접 관찰" not in html   # 사후 요약 없으면 범례도 없음
        assert "AI 해석" not in html
