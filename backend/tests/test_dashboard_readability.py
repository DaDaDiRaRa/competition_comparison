"""비교 리포트 대시보드 강점/약점 가독성 회귀 테스트.

파스텔-온-파스텔 저대비 알약 + 중복 회색 줄(#999) 문제를 의미색 알약(강점=초록/약점=빨강)
단일 표기로 고친 것을 잠근다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import axes_for
from services.report_generator import generate_comparison_report

AX = list(axes_for("public").keys())[0]


def _html():
    cell = {"grade": "B", "strengths": ["메타포 명확 (p.3)", "공식 분리 (p.5)"],
            "weaknesses": ["연결 약함 (p.7)"], "brief_compliance": "partial", "notes": "n"}
    meta = {"competition_name": "t", "facility_type": "public"}
    subs = [{"company": "A", "result": "win", "total_pages": 10, "extracted_data": {}},
            {"company": "B", "result": "lose", "total_pages": 10, "extracted_data": {}}]
    comp = {"submissions": {"A": {AX: dict(cell)}, "B": {AX: dict(cell)}},
            "concept_comparison": {}, "winner_strengths": [], "loser_weaknesses": [],
            "gap_analysis": {}}
    return generate_comparison_report(meta, subs, comp)


class TestDashboardReadability:
    def test_semantic_pills_present(self):
        html = _html()
        assert "db-tag-str" in html and "db-tag-weak" in html   # 의미색 알약

    def test_no_low_contrast_gray_dup(self):
        # 중복 회색 줄(#999 텍스트) 제거됨
        assert "#999" not in _html()

    def test_pills_use_token_colors(self):
        # 의미색은 :root 토큰(진초록/진빨강) — 파스텔 회사색 인라인 배경 아님
        html = _html()
        assert "--tag-strength-bg" in html and "--tag-weakness-bg" in html
        assert 'db-card-tag" style="background:' not in html   # 회사색 인라인 제거

    def test_content_preserved(self):
        html = _html()
        assert "메타포 명확" in html and "연결 약함" in html

    def test_grid_guarantees_min_card_width(self):
        # 밀도 개선: 회사 수만큼 균등분할(repeat(N,1fr)) → 최소폭 260px 보장 + 가로스크롤
        html = _html()
        assert "minmax(260px,1fr)" in html
        assert "grid-template-columns:repeat(2,1fr)" not in html  # 옛 균등분할 아님
