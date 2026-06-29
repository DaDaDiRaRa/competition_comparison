"""
brief_proposal_report_generator.to_proposal_html 단위 테스트 — LLM / 네트워크 의존 없음.

대상: _proposal dict → 자체완결 HTML (Report Generation Rule: 렌더만).
검증: 핵심 섹션 렌더, 빈 입력 graceful, html.escape(XSS 방어), 결정론 배점 카드,
      리스크 severity 클래스, 사실/제안 디스클레이머.
"""
from services.brief_proposal_report_generator import to_proposal_html


_PROPOSAL = {
    "executive_summary": "배치계획에 무게중심이 있다. 동선 해법을 전면에 세우길 권장한다.",
    "data_confidence": "medium",
    "scoring_focus": [
        {"category": "배치계획", "points": 40, "weight_pct": 40.0, "rank": 1},
        {"category": "공간계획", "points": 30, "weight_pct": 30.0, "rank": 2},
        {"category": "정성평가", "points": None, "weight_pct": None, "rank": None},
    ],
    "win_themes": [
        {"theme": "감염동선 분리", "rationale": "배점 1순위",
         "scoring_link": "배치계획 40점", "basis": ["p.20", "배치계획"]},
    ],
    "design_directions": [
        {"direction": "코어 분리형 배치", "addresses": "동선 분리",
         "tradeoffs": "저층부 면적 손실", "basis": ["p.20"]},
    ],
    "priorities": [
        {"rank": 2, "focus": "B작업", "why": "두번째", "scoring_weight": "30%"},
        {"rank": 1, "focus": "A작업", "why": "첫번째", "scoring_weight": "40%"},
    ],
    "risks": [
        {"risk": "ZEB 미달 시 실격", "severity": "high", "mitigation": "에너지 컨설팅", "basis": "p.31"},
        {"risk": "주차 부족", "severity": "low", "mitigation": "지하 확장", "basis": "p.12"},
    ],
    "kickoff_checklist": ["부지 답사", "면적표 검증"],
    "open_questions": ["주차 기준 확인"],
    "caveats": ["실제 심사 결과는 보장할 수 없습니다."],
    "model_id": "claude-opus-4-8",
    "generated_at": "2026-06-25T10:00:00",
}


class TestToProposalHtml:

    def test_core_sections_render(self):
        h = to_proposal_html(_PROPOSAL, "영등포 신청사", "공공청사")
        for needle in ("수주 핵심 테마", "설계 접근 방향", "착수 우선순위",
                       "리스크 · 대응", "착수 체크리스트", "발주처 확인 필요",
                       "배점 무게중심", "감염동선 분리", "ZEB 미달 시 실격",
                       "영등포 신청사", "공공청사"):
            assert needle in h, needle

    def test_disclaimer_and_not_prediction(self):
        h = to_proposal_html(_PROPOSAL, "x", "y")
        # 사실/제안 구분 + 당락 예측 아님 고지가 항상 박혀 있어야 한다
        assert "수주 전략 가설" in h
        assert "당락 예측 아님" in h

    def test_priorities_sorted_by_rank(self):
        h = to_proposal_html(_PROPOSAL, "", "")
        # rank 1(A작업)이 rank 2(B작업)보다 먼저 나와야 한다
        assert h.index("A작업") < h.index("B작업")

    def test_risk_severity_class(self):
        h = to_proposal_html(_PROPOSAL, "", "")
        assert 'class="risk high"' in h
        assert 'class="risk low"' in h
        # high severity 가 low 보다 먼저 (정렬)
        assert h.index("ZEB 미달") < h.index("주차 부족")

    def test_scoring_cards_only_ranked(self):
        h = to_proposal_html(_PROPOSAL, "", "")
        assert "배치계획" in h and "공간계획" in h
        # 명시 배점 없는(rank None) 항목은 카드에서 제외
        assert "정성평가" not in h

    def test_empty_graceful(self):
        h = to_proposal_html({}, "", "")
        assert "<html" in h and "</html>" in h
        # 내용 없는 섹션은 생략되지만 디스클레이머·헤더는 유지
        assert "수주 전략 가설" in h

    def test_none_input_graceful(self):
        h = to_proposal_html(None, "", "")
        assert "<html" in h

    def test_html_escape_xss(self):
        evil = {"executive_summary": "<script>alert(1)</script>",
                "win_themes": [{"theme": "<img src=x onerror=y>", "basis": ["p.1"]}]}
        h = to_proposal_html(evil, "<b>name</b>", "")
        assert "<script>alert(1)</script>" not in h
        assert "&lt;script&gt;" in h
        assert "<img src=x" not in h


_SITE_CONTEXT = {
    "matched_address": "서울특별시 영등포구 당산동 123",
    "address_input": "당산동 123",
    "lat": 37.52, "lng": 126.90, "radius_m": 500,
    "analysis": {
        "orientation": "장변 남북, 남향 양호",
        "road_access": "남측 20m 도로 접면, 코너 필지",
        "surrounding_uses": "북측 주거, 남측 상업",
        "natural_assets": "동측 안양천 약 300m",
        "special_context": "고도지구 인접",
        "overall_summary": "남향·코너의 도심 부지로 가시성이 높다.",
        "confidence": "medium",
        "caveats": ["지적 경계는 위성으로 확정 불가"],
    },
}


class TestSiteContextSection:

    def test_renders_when_present(self):
        h = to_proposal_html(_PROPOSAL, "영등포", "공공청사",
                             site_context=_SITE_CONTEXT, site_image_b64="QUJD")
        assert "대지 · 맥락 분석" in h
        assert "남향·코너의 도심 부지로 가시성이 높다." in h   # overall_summary
        assert "남측 20m 도로 접면" in h                        # 필드
        assert 'data:image/jpeg;base64,QUJD' in h              # 위성 썸네일 임베드
        assert "서울특별시 영등포구 당산동 123" in h            # matched_address 캡션
        assert '<a href="#site">대지</a>' in h                  # nav 링크
        assert "현장 답사" in h                                 # 추론/확인필요 라벨

    def test_absent_by_default(self):
        h = to_proposal_html(_PROPOSAL, "x", "y")
        assert "대지 · 맥락 분석" not in h
        assert '<a href="#site">' not in h

    def test_summary_only_no_image(self):
        sc = {"analysis": {"overall_summary": "요약만 있음"}}
        h = to_proposal_html(_PROPOSAL, "x", "y", site_context=sc)
        assert "대지 · 맥락 분석" in h
        assert "요약만 있음" in h
        assert "data:image/jpeg" not in h

    def test_empty_analysis_skips_section(self):
        h = to_proposal_html(_PROPOSAL, "x", "y", site_context={"analysis": {}})
        assert "대지 · 맥락 분석" not in h

    def test_site_xss_escaped(self):
        sc = {"analysis": {"overall_summary": "<script>x</script>",
                           "orientation": "<b>향</b>"}}
        h = to_proposal_html(_PROPOSAL, "x", "y", site_context=sc)
        assert "<script>x</script>" not in h
        assert "&lt;script&gt;" in h
