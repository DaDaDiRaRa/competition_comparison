"""비교 리포트 대시보드 강점/약점 가독성 회귀 테스트.

파스텔-온-파스텔 저대비 알약 + 중복 회색 줄(#999) 문제를 의미색 알약(강점=초록/약점=빨강)
단일 표기로 고친 것을 잠근다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import axes_for
from services.report_generator import generate_comparison_report, _strip_grade_tail

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

    def test_strength_text_html_escaped(self):
        # LLM 강점/약점/notes 의 '<'·'>' 가 escape 되어 카드 마크업이 안 깨짐
        cell = {"grade": "B", "strengths": ["전면폭 <3m 우려 (p.3)"],
                "weaknesses": [], "brief_compliance": "partial", "notes": "용적률 > 400%"}
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "A", "result": "win", "total_pages": 10, "extracted_data": {}},
                {"company": "B", "result": "lose", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"A": {AX: dict(cell)}, "B": {AX: dict(cell)}},
                "concept_comparison": {}, "winner_strengths": [], "loser_weaknesses": [],
                "gap_analysis": {}}
        html = generate_comparison_report(meta, subs, comp)
        assert "전면폭 &lt;3m" in html and "&gt; 400%" in html
        assert "전면폭 <3m" not in html   # raw 없음

    def test_dashboard_verdict_headline(self):
        # 대시보드 카드: notes → 판정 헤드라인(db-card-verdict), 꼬리 "B 수준" 절삭 + (p.N) 보존
        cell = {"grade": "B", "strengths": ["좋음 (p.3)"], "weaknesses": [],
                "brief_compliance": "partial",
                "notes": "역상 전략 독창적이나 집중도 분산되어 B 수준 (p.7)"}
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "건원", "result": "win", "total_pages": 10, "extracted_data": {}},
                {"company": "B", "result": "lose", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"건원": {AX: dict(cell)}, "B": {AX: dict(cell)}},
                "concept_comparison": {}, "winner_strengths": [], "loser_weaknesses": [],
                "gap_analysis": {}}
        html = generate_comparison_report(meta, subs, comp)
        assert 'class="db-card-verdict"' in html
        verdict = html.split('class="db-card-verdict"')[1].split("</div>")[0]
        assert "집중도 분산" in verdict and "B 수준" not in verdict and "(p.7)" in verdict

    def test_winner_box_strengths_only(self):
        # 당선작 강점 분석: 강점만(대표 강점 헤드라인 + 나머지 불릿), balanced notes·약점 제거
        cell = {"grade": "A", "strengths": ["역상 포디움 랜드마크 (p.8)", "UAM 미래 프로그램 (p.17)"],
                "weaknesses": ["약점제거 (p.9)"],
                "notes": "컨셉 명확하나 집중도분산 미흡 (p.7)", "brief_compliance": "partial"}
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "건원", "result": "win", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"건원": {AX: dict(cell)}}, "concept_comparison": {},
                "key_differentiators": [], "winner_strengths": [], "loser_weaknesses": [],
                "gap_analysis": {}}
        html = generate_comparison_report(meta, subs, comp)
        wb = html.split("★ 건원")[1].split("db-wrap")[0]   # 당선박스 ~ 대시보드 직전
        assert "w-axis-lead" in wb and "역상 포디움" in wb and "UAM 미래" in wb  # 강점만
        assert "집중도분산" not in wb and "약점제거" not in wb                   # 부정·약점 없음
        assert "w-axis-verdict" not in wb                                       # 옛 balanced 판정 없음

    def test_keydiff_structured_card(self):
        # 핵심 차별화: 축 헤더 + 본문(당선/낙선 색강조) + 💡 인과 하이라이트로 구조화
        from services.report_generator import _render_keydiff_card
        c = _render_keydiff_card(
            "concept_clarity: 당선작은 명확(p.7), 낙선작은 산만(p.3) — 컨셉 완성도가 갈랐다",
            {"concept_clarity": "컨셉·아이덴티티"})
        assert "kd-axis" in c and "컨셉·아이덴티티" in c
        assert "var(--tag-strength)\">당선작" in c and "var(--tag-weakness)\">낙선작" in c
        assert "kd-insight" in c and "컨셉 완성도가 갈랐다" in c
        # 폴백: 축·인과 구분자 없으면 본문만
        assert "kd-insight" not in _render_keydiff_card("그냥 한 문장", {})

    def test_summary_top_block(self):
        # 핵심 요약(핵심 차별화 + 당선요인↔낙선함정 + 정합성 노트)이 대시보드 아코디언보다 위
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "건원", "result": "win", "total_pages": 10, "extracted_data": {}},
                {"company": "B사", "result": "lose", "total_pages": 10, "extracted_data": {}}]
        cell = {"grade": "B", "strengths": ["좋음 (p.3)"], "weaknesses": ["약함 (p.5)"],
                "brief_compliance": "partial", "notes": "컨셉 명확 (p.7)"}
        comp = {"submissions": {"건원": {AX: dict(cell)}, "B사": {AX: dict(cell)}},
                "concept_comparison": {},
                "key_differentiators": ["당선작은 컨셉 명확성에서 앞섰다 (p.7)"],
                "winner_strengths": ["배치 우수 (p.3)"], "loser_weaknesses": ["동선 미흡 (p.5)"],
                "gap_analysis": {"blind_top1": "건원", "actual_winners": ["건원"],
                                 "top1_matches_winner": True}}
        html = generate_comparison_report(meta, subs, comp)
        # key_differentiators 렌더(그동안 버려지던 신호)
        assert "keydiff-item" in html and "컨셉 명확성에서 앞섰다" in html
        # 당선요인 ↔ 낙선함정 2열
        assert "당선 요인" in html and "낙선 함정" in html
        # 정합성 노트
        assert "설계 품질이" in html
        # 순서: 핵심 요약 < 당선작 강점 분석 < 대시보드(설계 축별 비교 분석)
        assert 0 < html.find("핵심 요약") < html.find("당선작 강점 분석") < html.find("설계 축별 비교 분석")

    def test_gap_note_diverged(self):
        # 블라인드 1위 ≠ 실제 당선 → 설계 외 요인 경고
        meta = {"competition_name": "t", "facility_type": "public"}
        subs = [{"company": "A", "result": "win", "total_pages": 10, "extracted_data": {}}]
        comp = {"submissions": {"A": {}}, "concept_comparison": {},
                "key_differentiators": ["차별 (p.3)"], "winner_strengths": [], "loser_weaknesses": [],
                "gap_analysis": {"blind_top1": "B", "actual_winners": ["A"],
                                 "top1_matches_winner": False}}
        html = generate_comparison_report(meta, subs, comp)
        assert "설계 외 요인" in html

    def test_strip_grade_tail(self):
        assert _strip_grade_tail("집중도 분산되어 B 수준 (p.7)") == "집중도 분산 (p.7)"
        assert _strip_grade_tail("MEP 정량 미흡으로 B 수준 (p.43)") == "MEP 정량 미흡 (p.43)"
        # 문장 중간의 '수준'은 절삭 안 함 (꼬리 아닐 때 보수적)
        assert _strip_grade_tail("15.5% 미달로 D 수준, BF 미명시 (p.16)").endswith("BF 미명시 (p.16)")
        # 판정 없으면 원문 유지
        assert _strip_grade_tail("일반 문장 (p.5)") == "일반 문장 (p.5)"

    def test_grid_guarantees_min_card_width(self):
        # 밀도 개선: 회사 수만큼 균등분할(repeat(N,1fr)) → 최소폭 260px 보장 + 가로스크롤
        html = _html()
        assert "minmax(260px,1fr)" in html
        assert "grid-template-columns:repeat(2,1fr)" not in html  # 옛 균등분할 아님
