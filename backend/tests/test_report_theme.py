"""리포트 공유 디자인 토큰 회귀 테스트 (디자인 통일 Level 1).

모든 자체완결 리포트 HTML 이 report_theme.THEME_VARS(건원 RED + 명조/Montserrat)를
단일 소스로 주입하고, 오프브랜드 색(네이비/청록/골드 툴바·보라 헤더)이 남지 않음을 잠근다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.report_theme import THEME_VARS, ACCENT, SANS, SERIF

import services.report_generator as compare_rg
import services.diagnosis_report_generator as diag_rg
import services.myproject_report_generator as mp_rg
import services.submission_report_generator as sub_rg
import services.brief_playbook_report_generator as pb_rg
import services.brief_checklist_exporter as ck_ex
import services.brief_proposal_report_generator as pr_rg


# (모듈, CSS 속성명) — 모든 자체완결 리포트
_TARGETS = [
    (compare_rg, "_CSS"),
    (diag_rg, "_CSS"),
    (mp_rg, "_CSS"),
    (sub_rg, "_CSS"),
    (pb_rg, "_CSS"),
    (ck_ex, "_HTML_CSS"),
    (pr_rg, "_PROPOSAL_CSS"),
]

# 정리 대상 오프브랜드 색 (다크 툴바·비-RED 액센트)
_OFFBRAND = ["#1a2138", "#d4af37", "#1e3a8a", "#7c3aed"]


class TestTheme:
    def test_tokens_present(self):
        assert ACCENT == "#e60012"
        assert "--accent:#e60012" in THEME_VARS
        assert "Montserrat" in SANS and "Noto Serif KR" in SERIF
        assert "--serif:" in THEME_VARS and "--sans:" in THEME_VARS


class TestAllReportsInjectTheme:
    def test_theme_injected(self):
        for mod, attr in _TARGETS:
            css = getattr(mod, attr)
            assert "--accent:#e60012" in css, f"{mod.__name__} missing accent token"
            assert "--sans:" in css, f"{mod.__name__} missing sans token"

    def test_no_leftover_marker(self):
        for mod, attr in _TARGETS:
            assert "/*__THEME__*/" not in getattr(mod, attr), f"{mod.__name__} marker not replaced"


class TestNoOffbrandColors:
    def test_offbrand_removed_from_css(self):
        for mod, attr in _TARGETS:
            css = getattr(mod, attr)
            for hexv in _OFFBRAND:
                assert hexv not in css, f"{mod.__name__} still has off-brand {hexv}"

    def test_compare_toolbar_uses_accent(self):
        # 비교 리포트 다크/골드 툴바가 흰 배경 + 건원 RED 로 정정됐는지 (렌더 확인)
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "A", "result": "win", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"A": {}}, "concept_comparison": {},
                "winner_strengths": ["s (p.3)"], "loser_weaknesses": [], "gap_analysis": {}}
        html = compare_rg.generate_comparison_report(meta, subs, comp)
        assert "#1a2138" not in html and "#d4af37" not in html
        assert "--accent:#e60012" in html
