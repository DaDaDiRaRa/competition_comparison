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


_FEASIBILITY = {
    "sites": [{
        "site_area_sqm": 43000, "floor_area_ratio_pct": 250,
        "building_coverage_pct": 18, "max_height_m": 95,
    }],
    "construction_cost_100m_won": 1440, "design_cost_100m_won": 120,
    "construction_period_months": 32,
}


class TestPhase1Hero:

    def test_hero_renders_image_and_summary(self):
        h = to_proposal_html(_PROPOSAL, "영등포", "공공청사",
                             site_context=_SITE_CONTEXT, site_image_b64="QUJD")
        assert 'class="hero"' in h
        assert 'data:image/jpeg;base64,QUJD' in h
        assert "남향·코너의 도심 부지로 가시성이 높다." in h     # overall_summary in hero
        assert "VWorld 위성" in h

    def test_hero_compacts_site_section(self):
        # 히어로가 이미지를 보여주면 대지 섹션은 이미지를 중복하지 않는다(b64 1회만)
        h = to_proposal_html(_PROPOSAL, "x", "y",
                             site_context=_SITE_CONTEXT, site_image_b64="QUJD")
        assert h.count("data:image/jpeg;base64,QUJD") == 1
        # 필드는 여전히 대지 섹션에 나온다
        assert "남측 20m 도로 접면" in h

    def test_no_hero_without_image(self):
        h = to_proposal_html(_PROPOSAL, "x", "y", site_context=_SITE_CONTEXT)
        assert 'class="hero"' not in h


class TestPhase1FactsBand:

    def test_facts_band_renders_extracted_numbers(self):
        h = to_proposal_html(_PROPOSAL, "x", "y", feasibility=_FEASIBILITY)
        assert "사업 규모" in h
        assert "지침서 추출 사실" in h
        assert "43,000" in h and "부지면적" in h       # 천단위 콤마
        assert "250" in h and "용적률" in h
        assert "1,440" in h and "공사비" in h
        assert "32" in h and "공사기간" in h
        assert '<a href="#facts">규모</a>' in h         # nav 링크

    def test_facts_band_absent_when_no_data(self):
        h = to_proposal_html(_PROPOSAL, "x", "y")
        # "사업 규모"는 CSS 주석에도 있으니 렌더된 섹션/라벨로 판정
        assert 'id="facts"' not in h
        assert "지침서 추출 사실" not in h
        assert '<a href="#facts">' not in h

    def test_facts_band_skips_missing_fields(self):
        fe = {"sites": [{"site_area_sqm": 1000}]}  # 나머지 결측
        h = to_proposal_html(_PROPOSAL, "x", "y", feasibility=fe)
        assert "부지면적" in h
        assert "용적률" not in h   # 결측 필드는 칸 자체가 없음

    def test_multi_site_note(self):
        fe = {"sites": [{"site_area_sqm": 1000}, {"site_area_sqm": 2000}]}
        h = to_proposal_html(_PROPOSAL, "x", "y", feasibility=fe)
        assert "부지 2곳 중 대표" in h


_PROPOSAL_P2 = dict(
    _PROPOSAL,
    design_directions=[
        {"direction": "코어 분리형",
         "narrative": "동선을 두 코어로 나눠 감염·일반 흐름을 분리하는 안이다. 배치계획 배점이 1순위인 점에서 출발한다.",
         "addresses": "동선 분리",
         "scoring_play": "배치 10 + 조망 5", "tradeoffs": "면적 손실",
         "site_rationale": "북측 산 조망축이 있어 가능", "basis": ["p.20"]},
    ],
    program_directions=[
        {"claim": "저층부에 시민개방형 공유 프로그램 집중",
         "detail": "시민개방에 배점이 쏠리므로 저층부를 도시에 내준다. 로비·공유홀을 가로에 면하게 두어 접근성을 높인다.",
         "basis": ["배치계획", "p.20"]},
    ],
    massing_strategy=[
        {"claim": "남측 조망축으로 판상 펼치고 코어를 북측에",
         "detail": "북측 산 조망(위성 실측)을 거실축에 맞추는 판상 배치로, 일조와 조망 배점을 동시에 노린다.",
         "basis": ["site_context.natural_assets"]},
    ],
    phasing=[
        {"claim": "1단계 동선 골격 확정 후 입면 전개",
         "detail": "배치가 1순위 배점이라 동선·코어 골격을 먼저 확정하고, 그 위에 입면 차별화를 얹는 순서가 안전하다.",
         "basis": ["배치계획"]},
    ],
)


class TestPhase2Interpretation:

    def test_direction_card_has_new_fields(self):
        h = to_proposal_html(_PROPOSAL_P2, "x", "y")
        assert "득점" in h and "배치 10 + 조망 5" in h
        assert "이 부지라서" in h and "북측 산 조망축이 있어 가능" in h

    def test_interp_sections_render_with_badge_and_anchor(self):
        h = to_proposal_html(_PROPOSAL_P2, "x", "y")
        assert "프로그램 방향" in h and "매스 전략" in h and "단계 접근" in h
        assert "저층부에 시민개방형 공유 프로그램 집중" in h
        assert h.count("AI 해석") >= 4   # 범례 + directions + 3 interp 섹션
        # 각 해석 항목은 근거 앵커를 단다
        assert "site_context.natural_assets" in h

    def test_interp_detail_and_direction_narrative_render(self):
        # '읽을 만한 깊이' 보강 — claim 제목 + detail 본문, 방향 narrative 단락
        h = to_proposal_html(_PROPOSAL_P2, "x", "y")
        assert 'class="id"' in h
        assert "로비·공유홀을 가로에 면하게 두어" in h          # program detail
        assert 'class="dir-card-narr"' in h
        assert "감염·일반 흐름을 분리하는 안이다" in h          # direction narrative

    def test_legend_renders_when_interp_present(self):
        h = to_proposal_html(_PROPOSAL_P2, "x", "y")
        assert 'class="legend"' in h
        assert "확인된" in h and "추론한" in h
        assert '<a href="#program">프로그램</a>' in h

    def test_legend_absent_when_no_directions_or_interp(self):
        bare = {"executive_summary": "요약만", "caveats": ["x"]}
        h = to_proposal_html(bare, "x", "y")
        assert 'class="legend"' not in h
        assert '<a href="#program">' not in h

    def test_interp_skips_items_without_claim_or_basis(self):
        p = dict(_PROPOSAL, program_directions=[{"basis": ["p.1"]}, {"claim": ""}])
        h = to_proposal_html(p, "x", "y")
        assert 'id="program"' not in h   # 유효 항목 0 → 섹션 생략

    def test_interp_xss_escaped(self):
        p = dict(_PROPOSAL, massing_strategy=[{"claim": "<script>x</script>", "basis": ["p.1"]}])
        h = to_proposal_html(p, "x", "y")
        assert "<script>x</script>" not in h
        assert "&lt;script&gt;" in h


# 권장 종합안·결정 요약용 — 5안(>=2) + 배점 랭킹
_PROPOSAL_REC = dict(
    _PROPOSAL,
    scoring_focus=[
        {"category": "배치계획", "points": 40, "weight_pct": 40.0, "rank": 1},
        {"category": "경관", "points": 20, "weight_pct": 20.0, "rank": 2},
        {"category": "기술", "points": 20, "weight_pct": 20.0, "rank": 3},
    ],
    design_directions=[
        {"direction": "저층 개방형 — 저층부 개방", "addresses": "경관 20점", "scoring_play": "경관 20",
         "tradeoffs": "효율 저하", "basis": ["p.1"]},
        {"direction": "동선 분리형 — 코어 분리", "addresses": "배치계획 40점 동선", "scoring_play": "배치계획 40",
         "tradeoffs": "공용면적 증가", "basis": ["p.2"]},
        {"direction": "사생활 배려형 — 북측 저층화", "addresses": "경관", "scoring_play": "경관",
         "tradeoffs": "볼륨이 줄어 유효면적 감소", "basis": ["p.3"]},
    ],
)


class TestDecisionCockpit:
    def test_cockpit_renders(self):
        h = to_proposal_html(_PROPOSAL, "영등포", "공공청사")
        assert 'class="cockpit"' in h
        assert "결정 요약" in h and "DECISION BRIEF" in h
        assert "발주 의도" in h and "최대 리스크" in h

    def test_cockpit_absent_when_too_thin(self):
        h = to_proposal_html({"executive_summary": "요약만"}, "x", "y")
        assert 'class="cockpit"' not in h   # 셀 3개 미만이면 생략


class TestRecommendedSynthesis:
    def test_recommendation_renders_backbone_and_grafts(self):
        h = to_proposal_html(_PROPOSAL_REC, "영등포", "공공청사")
        assert 'class="rec"' in h
        assert "권장 종합안" in h
        assert "동선 분리형" in h            # 배치계획 40점 겨냥 → 뼈대
        assert "접목" in h

    def test_volume_reducer_is_conditional_not_graft(self):
        h = to_proposal_html(_PROPOSAL_REC, "x", "y")
        # 사생활 배려형(볼륨 축소)은 조건부로 — 접목 칩이 아님
        i_cond = h.find("조건부 옵션")
        assert i_cond >= 0 and "사생활 배려형" in h[i_cond:i_cond + 200]

    def test_no_recommendation_with_single_direction(self):
        h = to_proposal_html(_PROPOSAL, "x", "y")   # design_directions 1개
        assert 'class="rec"' not in h

    def test_no_recommendation_for_bid_na(self):
        p = dict(_PROPOSAL_REC, design_directions=[{"direction": "해당 없음 — 설계자 선정 입찰"}])
        h = to_proposal_html(p, "x", "y")
        assert 'class="rec"' not in h


_BID_STRUCT = {
    "top_layer": {
        "basis_dimension": "연면적",
        "axes": [
            {"name": "사업수행능력평가", "role": "pq",
             "bands": [{"label": "8만㎡미만", "min_sqm": None, "max_sqm": 80000, "weight_pct": 20.0},
                       {"label": "24만㎡이상", "min_sqm": 240000, "max_sqm": None, "weight_pct": 40.0}]},
            {"name": "가격평가", "role": "price", "weight_range": [60.0, 80.0], "bands": []},
        ],
        "applicable": {"note": "연면적 미확보 — 적용 밴드 판정 보류", "weights": {}},
    },
    "pq_detail": {"total_points": 100, "categories": []},
}


class TestBidStructureSection:
    def test_renders_when_bid(self):
        h = to_proposal_html(_PROPOSAL, "대치미도", "재건축", bid_structure=_BID_STRUCT)
        assert 'id="bidstruct"' in h
        assert "2층 배점 구조" in h
        assert "사업수행능력평가" in h and "가격평가" in h
        assert "20" in h and "40" in h              # 정확 밴드
        assert "60~80%" in h                          # 범위 폴백

    def test_absent_for_competition(self):
        h = to_proposal_html(_PROPOSAL, "영등포", "공공청사")   # bid_structure 미전달
        assert 'id="bidstruct"' not in h


class TestLawDiagnosisPanel:
    """_site_context.law_diagnosis → '법적 골격(건축법 진단)' 패널. e2e 실동작으로 확정:
    모드 A(용량)는 실형상이 없어 north_setback_m 이 대개 null → shadow_min_setback_m /
    shadow_setback_rule / shadow_applies 로 정북 일조를 노출해야 한다(영등포·하안주공 실측 회귀).
    """

    def _sc(self, **hs):
        base = {"north_setback_m": None, "shadow_applies": False, "shadow_setback_rule": None,
                "shadow_min_setback_m": None, "road_height_limit_m": None, "parcel_north_depth_m": None}
        base.update(hs)
        return {"law_diagnosis": [{
            "site_id": "부지1", "address": "테스트", "signal": "RED", "overall_score": 2.0,
            "envelope": {"bcr_limit_pct": 60.0, "far_limit_pct": 400.0},
            "height_solar": base, "reviews_required": [], "has_required_review": False,
            "low_confidence": True, "source_notes": {}, "limit_mismatch": [],
        }]}

    def test_panel_renders_envelope_and_tag(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(road_height_limit_m=50.0))
        assert "법적 골격" in h and "건축법 진단" in h
        assert "건폐/용적 한도" in h and "건폐 60%" in h and "용적 400%" in h

    def test_road_height_limit_shown(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(road_height_limit_m=50.0))
        assert "가로구역 최고높이" in h and "50m" in h

    def test_mode_a_solar_uses_shadow_min_not_north(self):
        # north_setback_m=null 이지만 shadow_min_setback_m=65 → 정북 정보가 누락되면 안 됨(핵심 회귀)
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(
            shadow_applies=True, shadow_min_setback_m=65.0, shadow_setback_rule="높이/2 후퇴"))
        assert "정북 일조" in h and "필요이격 65m" in h and "높이/2 후퇴" in h

    def test_solar_actual_setback_preferred_when_present(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(north_setback_m=3.5))
        assert "실이격 3.5m" in h

    def test_solar_row_absent_when_no_shadow(self):
        # 준공업 등 정북 미적용: shadow_applies=False·전부 null → 정북 행 자체가 없어야
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(road_height_limit_m=50.0))
        assert "정북 일조" not in h

    def test_limit_mismatch_and_low_conf_warnings(self):
        sc = self._sc(road_height_limit_m=50.0)
        sc["law_diagnosis"][0]["limit_mismatch"] = [{"field": "용적률", "brief_pct": 460, "diagnose_limit_pct": 400.0}]
        h = to_proposal_html({"executive_summary": "x"}, site_context=sc)
        assert "brief 수치 재확인" in h and "용적률" in h
        assert "신뢰도 낮음" in h

    def test_absent_when_no_law_diagnosis(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context={"analysis": {"overall_summary": "요약"}})
        assert "법적 골격" not in h

    def test_escapes_law_data(self):
        sc = self._sc(shadow_applies=True, shadow_min_setback_m=1.0, shadow_setback_rule="<script>x</script>")
        h = to_proposal_html({"executive_summary": "x"}, site_context=sc)
        assert "<script>x</script>" not in h


class TestPlacementMultiSite:
    """다부지 placement 는 부지별로 다이어그램·카드를 분리한다(방위 뭉갬 방지). 단부지는 종전대로."""

    def _zone(self, program, plan, level="저층", site=None, required=False):
        z = {"program": program, "plan": plan, "level": level, "required": required,
             "why": "근거", "draws_on": ["대지:접도", "배점:배치40"]}
        if site:
            z["site"] = site
        return z

    def test_multisite_splits_per_site(self):
        ps = {"synthesis": "두 부지 성격이 다르다", "section_note": "단면 원리",
              "zones": [
                  self._zone("민원실(부지1)", "S", site="부지1", required=True),
                  self._zone("업무동(부지1)", "C", "상층", site="부지1"),
                  self._zone("보건소(부지2)", "S", site="부지2", required=True),
                  self._zone("커뮤니티(부지2)", "N", "중층", site="부지2"),
              ]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert 'class="place-site"' in h
        assert h.count('class="place-site-hd"') == 2          # 부지별 헤더 2개
        assert "부지1" in h and "부지2" in h
        assert h.count('class="place-dias"') == 2             # 다이어그램 쌍도 2세트
        # 번호는 전체 통합(1..4)
        for n in ("1", "2", "3", "4"):
            assert f'>{n}</text>' in h or f'>{n}</span>' in h

    def test_singlesite_no_split(self):
        ps = {"zones": [self._zone("민원실", "S"), self._zone("업무동", "C", "상층")]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert 'class="place-site"' not in h                  # 분리 없음
        assert h.count('class="place-dias"') == 1             # 다이어그램 쌍 1세트
        assert 'class="place-zones"' in h

    def test_single_labeled_site_not_split(self):
        # 부지 라벨이 하나뿐이면(다 같은 site) 분리하지 않음
        ps = {"zones": [self._zone("a", "S", site="부지1"), self._zone("b", "C", site="부지1")]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert 'class="place-site"' not in h

    def test_site_label_escaped(self):
        ps = {"zones": [self._zone("a", "S", site="<b>부지1</b>"),
                        self._zone("b", "C", site="부지2")]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert "<b>부지1</b>" not in h


class TestLawRefsFootnote:
    """Phase 3 — 관련 법조문 각주. graph 원문 있으면 접기, 없으면 law.go.kr 링크만(인용 가드)."""

    def _sc(self, with_texts):
        diag = {
            "site_id": "부지1", "address": "영등포",
            "envelope": {"bcr_limit_pct": 60.0, "far_limit_pct": 400.0},
            "height_solar": {"north_setback_m": None, "shadow_applies": True,
                             "shadow_setback_rule": "h/2", "shadow_min_setback_m": 65.0,
                             "road_height_limit_m": None, "parcel_north_depth_m": None},
            "reviews_required": [{"name": "건축위원회 심의"}], "has_required_review": True,
            "low_confidence": False, "source_notes": {}, "limit_mismatch": [],
            "law_refs": [{"name": "건축법 제61조 (일조)", "url": "https://law/61"},
                         {"name": "건축법 제55조 (건폐율)", "url": "https://law/55"}],
        }
        sc = {"law_diagnosis": [diag]}
        if with_texts:
            sc["law_texts"] = {"건축법 제61조 (일조)": {"content": "① 전용주거지역과 일반주거지역...",
                                                     "source_url": "https://law/61"}}
        return sc

    def test_footnote_with_graph_content(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(True))
        assert "관련 법조문" in h
        assert '<details class="law-ref">' in h and "전용주거지역과 일반주거지역" in h   # 원문 접기
        assert 'law-ref-lnk' in h and "건축법 제55조 (건폐율)" in h                      # 원문 없는 건 링크만
        assert 'href="https://law/61"' in h and 'target="_blank"' in h

    def test_footnote_links_only_without_texts(self):
        h = to_proposal_html({"executive_summary": "x"}, site_context=self._sc(False))
        assert "관련 법조문" in h and "건축법 제61조 (일조)" in h
        assert "<details" not in h        # law_texts 없으면 원문 각주 없이 링크만

    def test_law_data_escaped(self):
        sc = self._sc(True)
        sc["law_texts"]["건축법 제61조 (일조)"]["content"] = "<script>x</script>"
        h = to_proposal_html({"executive_summary": "x"}, site_context=sc)
        assert "<script>x</script>" not in h
