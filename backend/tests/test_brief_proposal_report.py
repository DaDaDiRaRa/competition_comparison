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
        assert h.count('class="ai-badge"') >= 4   # 범례 + directions + 3 interp 섹션 ('제안' 배지)
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


class TestSitePlan:
    """권장안 = 대지 배치도(위에서 본 평면, 방위별 별개 동). 채움=지침서 필수 / 점선=제안, LLM 0 SVG."""

    def _z(self, program, plan="S", level="저층", required=False):
        return {"program": program, "plan": plan, "level": level, "required": required, "why": "근거"}

    def test_site_plan_present_full_width(self):
        ps = {"zones": [self._z("주민센터", "S", "저층", True), self._z("주차", "C", "지하", True)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert 'aria-label="대지 배치도"' in h
        assert 'grid-column:1/-1' in h                              # 전체폭 히어로
        assert '라벨=방위(평면 위치)' in h                          # 캡션: 위치=방위(층 아님)
        assert '층 구성(상/중/저)은 아래 존 목록 참조' in h          # 층은 평면에 표기 안 함
        assert '주민센터' in h and '>지하<' in h                     # 이름 블록 + 지하 띠

    def test_separate_orientations_both_placed(self):
        # 방위가 다르면 별개 위치 = 별개 동 (한 건물로 뭉치지 않음)
        ps = {"zones": [self._z("보건소", "S", "저층", True),
                        self._z("업무동", "N", "상층", False)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert '보건소' in h and '업무동' in h
        assert 'stroke-dasharray' in h                              # 제안(업무동) 점선

    def test_renders_without_required_zone(self):
        ps = {"zones": [self._z("a", "S", "저층", False), self._z("b", "N", "상층", False)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert 'aria-label="대지 배치도"' in h

    def test_site_plan_escapes_program_name(self):
        ps = {"zones": [self._z("<b>x</b>", "S", "저층", True), self._z("y", "N", "상층", True)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        sec = h.split('aria-label="대지 배치도"')[1][:1500]
        assert '&lt;b&gt;x&lt;/b&gt;' in h and '<b>x</b>' not in sec

    def test_multisite_site_plan_per_site(self):
        ps = {"zones": [
            {"program": "민원실", "plan": "S", "level": "저층", "required": True, "site": "부지1"},
            {"program": "보건소", "plan": "S", "level": "저층", "required": True, "site": "부지2"},
        ]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert h.count('aria-label="대지 배치도"') == 2   # 부지별 1개씩

    def test_satellite_overlay_when_image_present(self):
        # 단부지 + 위성 이미지 → 실측 위성 위 오버레이 (흰 박스 아님)
        ps = {"zones": [self._z("보건소", "S", "저층", True), self._z("업무동", "N", "상층", False)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps}, site_image_b64="QUJD")
        assert '<image href="data:image/jpeg;base64,QUJD"' in h    # 실측 위성 배경
        assert '실측 위성 + 지적도 위 배치' in h                    # 정직 캡션
        assert 'aria-label="대지 배치도"' in h

    def test_white_box_fallback_without_image(self):
        ps = {"zones": [self._z("보건소", "S", "저층", True), self._z("업무동", "N", "상층", False)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert '<image href="data:image' not in h                  # 이미지 없으면 흰 박스
        assert 'aria-label="대지 배치도"' in h

    def test_real_parcel_boundary_drawn(self):
        # 위성 + 실측 필지 폴리곤 → 실제 대지경계선(건원 RED) 렌더
        ps = {"zones": [self._z("보건소", "S", "저층", True), self._z("업무동", "N", "상층", False)]}
        sc = {"parcel_norm": [[[0.42, 0.40], [0.58, 0.40], [0.58, 0.60], [0.42, 0.60], [0.42, 0.40]]]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps},
                             site_context=sc, site_image_b64="QUJD")
        assert '<polygon' in h and '#e60012' in h                  # 필지 경계선
        assert '실측 대지경계' in h                                 # 칩
        assert '빨간선=실측 대지경계' in h                          # 캡션

    def test_no_polygon_without_parcel(self):
        ps = {"zones": [self._z("보건소", "S", "저층", True), self._z("업무동", "N", "상층", False)]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps},
                             site_context={}, site_image_b64="QUJD")
        assert '<polygon' not in h and '<image href' in h          # 폴리곤 없음, 위성은 유지


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


class TestConceptCover:
    """concept_hook → 덱 오프닝 컨셉 표지. AI 제안 시안(사실 아님) + 근거 앵커 + graceful."""

    _HOOK = {
        "executive_summary": "s",
        "concept_hook": {
            "keyword": "TRANSIT",
            "tagline": "되살림 · 잇기 · 지속",
            "axes": [
                {"term": "되살림", "ko": "쇠퇴 역세권 재생", "en": "Urban Regeneration",
                 "basis": ["배점: 도시맥락 25%", "p.12"]},
                {"term": "잇기", "ko": "기술과 사람 연결", "en": "Smart City", "basis": ["강조: 스마트"]},
                {"term": "지속", "ko": "환경·구조 지속가능", "en": "", "basis": ["p.30"]},
            ],
        },
    }

    def test_cover_renders(self):
        h = to_proposal_html(self._HOOK, "테스트")
        assert "cc-cover" in h and "TRANSIT" in h
        assert "되살림" in h and "쇠퇴 역세권 재생" in h and "Urban Regeneration" in h
        assert "근거 배점: 도시맥락 25% · p.12" in h   # 축별 근거 앵커

    def test_cover_labeled_ai_proposal(self):
        # 사실 아님 — AI 제안 시안 명시 + 배지 (앱의 2층 분리 원칙)
        h = to_proposal_html(self._HOOK, "x")
        assert "컨셉 시안" in h and "ai-badge" in h
        assert "설계팀이 갈아끼우는 출발점" in h

    def test_cover_at_deck_top(self):
        # 표지는 덱 오프닝 — disclaimer/cockpit 본문보다 앞 (body 마커 기준)
        h = to_proposal_html(self._HOOK, "x")
        assert h.find('<section class="cc-cover">') < h.find("<div class='disclaimer'>")

    def test_tagline_autobuild(self):
        # tagline 없으면 axes.term 이어붙임
        p = {"concept_hook": {"keyword": "WEAVE", "axes": [{"term": "A"}, {"term": "B"}]}}
        h = to_proposal_html(p, "x")
        assert "A · B" in h

    def test_graceful_without_hook(self):
        # concept_hook 없거나 keyword 비면 표지 skip (LLM 이 근거 못 달아 생략한 경우).
        # '.cc-cover' CSS 는 늘 있으니 body 의 <section> 마커로 판정.
        M = '<section class="cc-cover">'
        assert M not in to_proposal_html({"executive_summary": "s"}, "x")
        assert M not in to_proposal_html({"concept_hook": {"keyword": ""}}, "x")
        assert M not in to_proposal_html({"concept_hook": "not-a-dict"}, "x")

    def test_cover_xss_escaped(self):
        p = {"concept_hook": {"keyword": "<script>a</script>",
                              "axes": [{"term": "<b>x", "ko": "<i>y", "basis": ["<u>z"]}]}}
        h = to_proposal_html(p, "x")
        assert "<script>a</script>" not in h and "&lt;script&gt;a&lt;/script&gt;" in h
        assert "<b>x" not in h and "&lt;b&gt;x" in h


class TestZoningAlternatives:
    """조닝 ALT — 사실-락(브랜드 로직) + 3안 렌더(설계안별 조직 스택)."""
    from services.brief_proposal import _lock_placement_alternatives as _lock

    def _ps(self):
        return {"placement_strategy": {
            "zones": [
                {"program": "보건소", "plan": "S", "level": "저층", "required": True, "why": "1층 필수"},
                {"program": "업무동", "plan": "N", "level": "중층", "required": False},
            ],
            "alternatives": [
                {"label": "A", "based_on": "조망 우선", "premise": "상층 조망",
                 "zones": [
                     {"program": "보건소", "plan": "N", "level": "상층", "required": True},  # 사실 위반 시도
                     {"program": "라운지", "plan": "C", "level": "상층", "required": False},
                 ]},
                {"label": "B", "based_on": "가로 활성", "premise": "저층 개방",
                 "zones": [{"program": "카페", "plan": "S", "level": "저층", "required": False}]},  # 보건소 누락
            ]}}

    def test_lock_forces_required_zone_position(self):
        r = self._ps()
        TestZoningAlternatives._lock(r)
        a0 = {z["program"]: (z["plan"], z["level"]) for z in r["placement_strategy"]["alternatives"][0]["zones"]}
        assert a0["보건소"] == ("S", "저층")          # 권장안 위치로 덮어씀
        assert a0["라운지"] == ("C", "상층")          # aura(추론)는 유지

    def test_lock_backfills_missing_required_zone(self):
        r = self._ps()
        TestZoningAlternatives._lock(r)
        a1 = {z["program"]: (z["plan"], z["level"]) for z in r["placement_strategy"]["alternatives"][1]["zones"]}
        assert a1.get("보건소") == ("S", "저층")       # 빠졌던 명시 존 보강

    def test_lock_caps_at_two(self):
        r = {"placement_strategy": {"zones": [], "alternatives": [
            {"label": str(i), "zones": [{"program": f"p{i}", "plan": "C", "level": "저층", "required": False}]}
            for i in range(5)]}}
        TestZoningAlternatives._lock(r)
        assert len(r["placement_strategy"]["alternatives"]) == 2

    def test_lock_noop_without_alternatives(self):
        r = {"placement_strategy": {"zones": [{"program": "x", "plan": "S", "level": "저층", "required": True}]}}
        TestZoningAlternatives._lock(r)          # alternatives 없음 → 예외 없이 no-op
        assert "alternatives" not in r["placement_strategy"] or not r["placement_strategy"]["alternatives"]

    def test_renders_two_alt_siteplans_plus_primary(self):
        r = self._ps()
        TestZoningAlternatives._lock(r)
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": r["placement_strategy"]})
        assert "프로그램 조닝 대안" in h
        # 권장안 히어로(1) + 대안 2 = 대지 배치도 3개 (ALT 도 동일 표현)
        assert h.count('aria-label="대지 배치도"') == 3
        assert "grid-column:1/-1" in h
        assert "지침서 필수 배치는 두 안 모두 동일" in h

    def test_single_alternative_not_rendered(self):
        # 대안 1개뿐이면 ALT 행 생략 → 권장안 대지 배치도만
        ps = {"zones": [{"program": "a", "plan": "S", "level": "저층", "required": True}],
              "alternatives": [{"label": "A", "zones": [{"program": "a", "plan": "S", "level": "저층", "required": True}]}]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert "프로그램 조닝 대안" not in h
        assert 'aria-label="대지 배치도"' in h                      # 권장안 대지 배치도는 남음

    def test_alt_program_name_escaped(self):
        ps = {"zones": [{"program": "코어", "plan": "C", "level": "중층", "required": True}],
              "alternatives": [
                  {"label": "A", "zones": [{"program": "<b>x</b>", "plan": "S", "level": "저층", "required": False}]},
                  {"label": "B", "zones": [{"program": "y", "plan": "N", "level": "상층", "required": False}]}]}
        h = to_proposal_html({"executive_summary": "x", "placement_strategy": ps})
        assert "<b>x</b>" not in h and "&lt;b&gt;x&lt;/b&gt;" in h


class TestOneDocSections:
    """'한 문서화'(2026-07-29) — 면적 스택·지침서 강조요소를 제안서 덱에 이식 (LLM 0)."""

    _EMPH = [
        {"topic": "감염 동선 분리", "signal_strength": "strong",
         "signals": ["본문 3회 반복", "1층 필수 명시"], "basis": ["p.18", "보건시설"]},
        {"topic": "공공 개방", "signal_strength": "weak", "signals": [], "basis": []},
    ]

    def test_program_stack_section_rendered(self):
        h = to_proposal_html({"executive_summary": "x"},
                             program_stack_html='<svg data-stack="1"></svg>')
        assert "프로그램 면적 구성" in h
        assert 'data-stack="1"' in h
        assert '<a href="#areas">면적</a>' in h                    # nav 링크

    def test_program_stack_graceful_skip(self):
        h = to_proposal_html({"executive_summary": "x"})
        assert "프로그램 면적 구성" not in h
        assert '<a href="#areas">' not in h

    def test_emphases_rendered_with_basis(self):
        h = to_proposal_html({"executive_summary": "x"}, key_emphases=self._EMPH)
        assert "지침서가 강조하는 요소" in h
        assert "감염 동선 분리" in h and "강한 신호" in h
        assert "본문 3회 반복" in h and "p.18" in h                # 근거 인용 유지
        assert '<a href="#emphasis">강조</a>' in h

    def test_emphases_graceful_skip(self):
        assert "지침서가 강조하는 요소" not in to_proposal_html({"executive_summary": "x"})
        assert "지침서가 강조하는 요소" not in to_proposal_html(
            {"executive_summary": "x"}, key_emphases=[{"topic": ""}])

    def test_emphases_escaped(self):
        h = to_proposal_html({"executive_summary": "x"},
                             key_emphases=[{"topic": "<img src=x>", "signals": ["<b>s</b>"]}])
        assert "<img src=x>" not in h and "&lt;img src=x&gt;" in h
        assert "<b>s</b>" not in h

    def test_massing_section_rendered(self):
        h = to_proposal_html({"executive_summary": "x"},
                             massing_html='<svg data-massing="1"></svg>')
        assert "개념 매스" in h
        assert 'data-massing="1"' in h
        assert '<a href="#massing">매스</a>' in h                   # nav 링크

    def test_massing_graceful_skip(self):
        h = to_proposal_html({"executive_summary": "x"})
        assert "개념 매스" not in h
        assert '<a href="#massing">' not in h

    def test_program_stack_helper_single_source(self):
        # 체크리스트 공용 헬퍼 — 면적 데이터 있으면 SVG, 없으면 "" (graceful)
        from services.brief_checklist_exporter import program_stack_html
        assert program_stack_html({}) == ""
        brief = {"brief_program": [{"area_table": [
            {"group_name": "구청", "total_area_sqm": 36019.0},
            {"group_name": "보건소", "total_area_sqm": 8594.0}]}]}
        out = program_stack_html(brief)
        assert "면적 프로그램 비례 다이어그램" in out
        assert "구청" in out and "보건소" in out
