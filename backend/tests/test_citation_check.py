"""인용 사후검증 회귀 테스트 (MATURITY 로드맵 #2).

(p.N) 인용이 문서 실제 쪽수를 벗어나는지 코드로 검증한다 (LLM 0 · 텍스트 수정 0).
관대 정책: 문서 안 페이지는 통과, 상한 밖만 flag, bound 미상이면 스킵.
"""
from services import citation_check as cc


class TestCollectPageBound:
    def test_total_pages_wins(self):
        assert cc.collect_page_bound({"total_pages": 12, "concept": {"_page": 3}}) == 12

    def test_falls_back_to_max_page(self):
        src = {"a": {"_page": 5}, "b": [{"_page": 9}, {"_page": 2}]}
        assert cc.collect_page_bound(src) == 9

    def test_none_when_no_signal(self):
        assert cc.collect_page_bound({"concept": {"x": 1}}) is None
        assert cc.collect_page_bound(None) is None

    def test_zero_total_pages_ignored(self):
        # total_pages=0 은 신호 아님 → _page 폴백
        assert cc.collect_page_bound({"total_pages": 0, "a": {"_page": 4}}) == 4


class TestCheckText:
    def test_flags_page_beyond_bound(self):
        flags = cc.check_text("남향 배치 우수 (p.47)", 12, "f")
        assert len(flags) == 1
        assert flags[0]["value"] == "p.47"
        assert flags[0]["page"] == 47 and flags[0]["bound"] == 12

    def test_valid_page_passes(self):
        assert cc.check_text("코어 분리 (p.3)", 12, "f") == []

    def test_boundary_page_passes(self):
        assert cc.check_text("끝장 (p.12)", 12, "f") == []

    def test_multi_page_citation(self):
        flags = cc.check_text("연계 (p.3,47)", 12, "f")
        assert [g["page"] for g in flags] == [47]  # 3 통과, 47 flag

    def test_unknown_page_allowed(self):
        assert cc.check_text("미상 (p.?)", 12, "f") == []

    def test_bound_none_skips(self):
        assert cc.check_text("아무 (p.999)", None, "f") == []

    def test_zero_page_flagged(self):
        flags = cc.check_text("이상 (p.0)", 12, "f")
        assert len(flags) == 1 and flags[0]["page"] == 0

    def test_spaced_format(self):
        flags = cc.check_text("띄움 (p. 30)", 12, "f")
        assert len(flags) == 1 and flags[0]["page"] == 30


class TestCheckComparison:
    def _subs(self):
        return [
            {"company": "A건설", "total_pages": 10},
            {"company": "B사", "total_pages": 20},
        ]

    def test_per_submission_bound(self):
        comparison = {"submissions": {
            "A건설": {"배치": {"strengths": ["우수 (p.15)"], "weaknesses": [], "notes": ""}},
            "B사":   {"배치": {"strengths": ["우수 (p.15)"], "weaknesses": [], "notes": ""}},
        }}
        flags = cc.check_comparison(comparison, self._subs())
        # p.15: A건설(10쪽)은 초과 flag, B사(20쪽)는 통과
        assert len(flags) == 1
        assert flags[0]["company"] == "A건설" and flags[0]["page"] == 15

    def test_concept_comparison_uses_union(self):
        comparison = {"submissions": {}, "concept_comparison": {"배치": "A는 (p.15), B는 (p.25)"}}
        flags = cc.check_comparison(comparison, self._subs())
        # union bound=20 → p.25만 flag
        assert [g["page"] for g in flags] == [25]

    def test_no_flags_when_clean(self):
        comparison = {"submissions": {
            "A건설": {"배치": {"strengths": ["좋음 (p.3)"], "weaknesses": [], "notes": ""}},
        }}
        assert cc.check_comparison(comparison, self._subs()) == []


class TestCheckDiagnosis:
    def test_axes_and_requirement_mapping(self):
        diagnosis = {
            "axes": {"공간": {"strengths": ["동선 (p.30)"], "weaknesses": ["약함 (p.4)"]}},
            "requirement_mapping": [{"requirement": "x", "evidence": "충족 (p.99)"}],
        }
        flags = cc.check_diagnosis(diagnosis, {"total_pages": 8})
        pages = sorted(g["page"] for g in flags)
        assert pages == [30, 99]  # p.4 통과


class TestCheckMyproject:
    def test_axes_evidence(self):
        deep = {
            "axes_evidence": {"컨셉": {"strengths": ["강함 (p.50)"], "evidence": "근거 (p.2)"}},
            "improvement_points": ["개선 (p.60)"],
        }
        flags = cc.check_myproject(deep, {"total_pages": 10})
        assert sorted(g["page"] for g in flags) == [50, 60]


class TestFlagsBandHtml:
    def test_empty_returns_blank(self):
        assert cc.flags_band_html([]) == ""
        assert cc.flags_band_html(None) == ""

    def test_renders_and_escapes(self):
        html = cc.flags_band_html([
            {"value": "p.47", "field": "submissions.<A>.배치", "page": 47,
             "bound": 12, "context": "남향 <배치>"},
        ])
        assert "p.47" in html and "문서 12쪽" in html
        assert "&lt;A&gt;" in html  # field escape
        assert "&lt;배치&gt;" in html  # context escape
        assert "<A>" not in html
