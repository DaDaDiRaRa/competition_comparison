"""
brief_advisor.py 결정론 백본 단위 테스트 (Unit 1) — LLM / 네트워크 의존 없음.

대상:
  - compute_scoring_focus    : 배점·비중·랭킹 + null/shared_with(병합셀) 시맨틱
  - extract_emphasis_signals : 강조어휘 문장 + 분류별 분량 (design_guidelines_grouped)

배점 null 시맨틱은 brief_validator._check_points_mismatch 와 일치해야 한다
(shared_with non-empty = 공유 점수, null + shared 없음 = 정성평가).
"""
import services.brief_advisor as ba
from services.brief_advisor import (
    compute_scoring_focus,
    extract_emphasis_signals,
    _select_eval_page,
)


# ═══════════════════════════════════════════════════════════════════════════════
# compute_scoring_focus
# ═══════════════════════════════════════════════════════════════════════════════

# 영등포 통합신청사 배점표 형태 (병합셀 + 정성평가 혼재)
_EVAL_YDP = {
    "brief_evaluation": {
        "total_points": 100,
        "evaluation_categories": [
            {"name": "과업의 목적", "points": 20, "shared_with": [], "sub_items": ["a", "b"]},
            {"name": "배치계획", "points": 40, "shared_with": ["공간계획"], "sub_items": ["a"]},
            {"name": "공간계획", "points": None, "shared_with": ["배치계획"], "sub_items": ["a", "b", "c"]},
            {"name": "기술계획", "points": 20, "shared_with": [], "sub_items": []},
            {"name": "설계의 적정성", "points": None, "shared_with": ["기술계획"], "sub_items": []},
            {"name": "경관 및 주변과의 조화", "points": 20, "shared_with": [], "sub_items": []},
            {"name": "창의성 및 공공성", "points": None, "shared_with": [], "sub_items": ["a"]},
        ],
    }
}


class TestComputeScoringFocus:

    def test_empty_when_no_evaluation(self):
        assert compute_scoring_focus({}) == []
        assert compute_scoring_focus({"brief_evaluation": []}) == []
        assert compute_scoring_focus({"brief_evaluation": {"evaluation_categories": []}}) == []

    def test_preserves_order_and_count(self):
        focus = compute_scoring_focus(_EVAL_YDP)
        assert [f["category"] for f in focus] == [
            "과업의 목적", "배치계획", "공간계획", "기술계획",
            "설계의 적정성", "경관 및 주변과의 조화", "창의성 및 공공성",
        ]

    def test_points_and_weight(self):
        focus = {f["category"]: f for f in compute_scoring_focus(_EVAL_YDP)}
        assert focus["배치계획"]["points"] == 40
        assert focus["배치계획"]["weight_pct"] == 40.0
        assert focus["과업의 목적"]["weight_pct"] == 20.0

    def test_top_rank_is_highest_points(self):
        focus = compute_scoring_focus(_EVAL_YDP)
        ranked = {f["category"]: f["rank"] for f in focus}
        # 배치계획(40) 이 1위
        assert ranked["배치계획"] == 1
        # 20점 항목 3개는 2~4위 (동점, 추출 순서 안정)
        assert ranked["과업의 목적"] == 2
        assert ranked["기술계획"] == 3
        assert ranked["경관 및 주변과의 조화"] == 4

    def test_shared_with_null_is_not_qualitative(self):
        """null 점수 + shared_with 있음 = 공유 점수(병합셀). 정성평가 아님, rank None."""
        focus = {f["category"]: f for f in compute_scoring_focus(_EVAL_YDP)}
        gp = focus["공간계획"]
        assert gp["points"] is None
        assert gp["shared_with"] == ["배치계획"]
        assert gp["is_qualitative"] is False
        assert gp["rank"] is None
        assert gp["weight_pct"] is None

    def test_null_without_shared_is_qualitative(self):
        """null 점수 + shared_with 없음 = 정성평가 항목."""
        focus = {f["category"]: f for f in compute_scoring_focus(_EVAL_YDP)}
        cv = focus["창의성 및 공공성"]
        assert cv["points"] is None
        assert cv["shared_with"] == []
        assert cv["is_qualitative"] is True
        assert cv["rank"] is None

    def test_sub_items_count(self):
        focus = {f["category"]: f for f in compute_scoring_focus(_EVAL_YDP)}
        assert focus["공간계획"]["sub_items_count"] == 3
        assert focus["기술계획"]["sub_items_count"] == 0

    def test_weight_denominator_falls_back_to_sum(self):
        """total_points 없으면 numeric 합을 분모로 사용."""
        data = {"brief_evaluation": {"evaluation_categories": [
            {"name": "A", "points": 30}, {"name": "B", "points": 10},
        ]}}
        focus = {f["category"]: f for f in compute_scoring_focus(data)}
        assert focus["A"]["weight_pct"] == 75.0   # 30 / 40
        assert focus["B"]["weight_pct"] == 25.0

    def test_selects_eval_page_with_most_points(self):
        """비연속 스태킹: numeric 배점이 가장 많은 페이지 선택 (_first 아님)."""
        data = {"brief_evaluation": [
            {"evaluation_categories": [{"name": "헤더만", "points": None}], "_page": 1},
            {"total_points": 100, "evaluation_categories": [
                {"name": "A", "points": 60}, {"name": "B", "points": 40},
            ], "_page": 9},
        ]}
        focus = compute_scoring_focus(data)
        assert [f["category"] for f in focus] == ["A", "B"]
        assert focus[0]["rank"] == 1

    def test_ignores_merged_pages(self):
        """_merged 스태킹 페이지는 선택 후보에서 제외."""
        data = {"brief_evaluation": [
            {"_merged": True, "evaluation_categories": [
                {"name": "X", "points": 50}, {"name": "Y", "points": 50}]},
            {"total_points": 100, "evaluation_categories": [{"name": "A", "points": 100}]},
        ]}
        focus = compute_scoring_focus(data)
        assert [f["category"] for f in focus] == ["A"]


class TestSelectEvalPage:

    def test_dict_form(self):
        be = {"evaluation_categories": [{"name": "A", "points": 10}]}
        assert _select_eval_page({"brief_evaluation": be}) is be

    def test_missing_returns_empty(self):
        assert _select_eval_page({}) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# extract_emphasis_signals
# ═══════════════════════════════════════════════════════════════════════════════

# 종로구청 형태: flat items + 중첩 items_by_sub 혼재, '특히' 강조어휘 포함
_GUIDELINES = {
    "design_guidelines_grouped": [
        {
            "category": "동선계획",
            "section_path": "5. 계획의 기본방향",
            "items": [],
            "items_by_sub": [
                {"sub_path": "5-1 배치 및 동선계획", "items": [
                    {"label": "■", "text": "기관별 동선을 분리하되 유연한 배치계획을 수립한다."},
                    {"label": "■", "text": "특히 보건소의 감염관련 동선은 다른 동선과 분리한다."},
                ]},
            ],
        },
        {
            "category": "일반사항",
            "section_path": "기본 설계지침",
            "items": [
                {"label": "■", "text": "역사공간과 조화되는 청사"},
                {"label": "•", "text": "반드시 서울미래유산의 역사성을 보존한다."},
            ],
            "items_by_sub": [],
        },
    ]
}


class TestExtractEmphasisSignals:

    def test_empty_when_no_guidelines(self):
        out = extract_emphasis_signals({})
        assert out == {"emphasis_phrases": [], "category_weights": []}

    def test_emphasis_phrases_detected(self):
        out = extract_emphasis_signals(_GUIDELINES)
        markers = {p["marker"] for p in out["emphasis_phrases"]}
        assert "특히" in markers
        assert "반드시" in markers
        # 강조어휘 없는 문장은 미포함
        texts = [p["text"] for p in out["emphasis_phrases"]]
        assert "역사공간과 조화되는 청사" not in texts

    def test_emphasis_phrase_carries_section_and_category(self):
        out = extract_emphasis_signals(_GUIDELINES)
        special = next(p for p in out["emphasis_phrases"] if p["marker"] == "특히")
        assert special["category"] == "동선계획"
        assert special["section"] == "5-1 배치 및 동선계획"

    def test_category_weights_count_and_sort(self):
        out = extract_emphasis_signals(_GUIDELINES)
        cw = {c["category"]: c for c in out["category_weights"]}
        # 동선계획 2항목, 일반사항 2항목
        assert cw["동선계획"]["item_count"] == 2
        assert cw["일반사항"]["item_count"] == 2
        # 분량 내림차순 정렬 (동점은 안정)
        counts = [c["item_count"] for c in out["category_weights"]]
        assert counts == sorted(counts, reverse=True)

    def test_category_weights_track_sections(self):
        out = extract_emphasis_signals(_GUIDELINES)
        cw = {c["category"]: c for c in out["category_weights"]}
        assert "5-1 배치 및 동선계획" in cw["동선계획"]["sections"]

    def test_handles_string_items(self):
        """items 가 {label,text} 아닌 순수 문자열이어도 처리."""
        data = {"design_guidelines_grouped": [
            {"category": "A", "section_path": "S", "items": ["반드시 지킬 것", "평범한 항목"]},
        ]}
        out = extract_emphasis_signals(data)
        assert out["category_weights"][0]["item_count"] == 2
        assert len(out["emphasis_phrases"]) == 1

    def test_dedups_identical_emphasis_phrases(self):
        """정규화 데이터가 같은 강조문장을 여러 그룹에 담아도 강조문장은 1회만 (종로 케이스)."""
        dup = "특히 소방 동선과 보행 동선이 겹치지 않도록 한다."
        data = {"design_guidelines_grouped": [
            {"category": "동선계획", "section_path": "5-1", "items": [{"text": dup}]},
            {"category": "보안", "section_path": "5-5", "items": [{"text": dup}]},
        ]}
        out = extract_emphasis_signals(data)
        assert len(out["emphasis_phrases"]) == 1
        # 분량 집계(category_weights)는 중복 차단 없이 양쪽 다 카운트 (실제 분량 반영)
        total_items = sum(c["item_count"] for c in out["category_weights"])
        assert total_items == 2


# ═══════════════════════════════════════════════════════════════════════════════
# interpret_brief (Unit 2) — LLM 호출은 monkeypatch, API 미사용
# ═══════════════════════════════════════════════════════════════════════════════

_FAKE_INSIGHT = (
    '{"synthesis_summary":"요약","key_emphases":[{"topic":"동선","signal_strength":"strong",'
    '"signals":["s"],"basis":["배치계획"],"note":"n"}],"must_not_miss":[],'
    '"hidden_constraints":[],"reading_guide":[],"data_confidence":"high","caveats":[],'
    '"scoring_focus":[{"category":"LLM이 멋대로 바꾼 값","points":999}]}'
)


class TestBuildAdvisorPayload:

    def test_payload_shape(self):
        data = {
            **_EVAL_YDP, **_GUIDELINES,
            "validation": {"flags": [
                {"severity": "high", "message": "배점 합계 불일치", "location": "x"},
            ]},
        }
        p = ba._build_advisor_payload(data, "public")
        assert p["facility_type"] == "public"
        assert any(f["category"] == "배치계획" for f in p["scoring_focus"])
        assert "emphasis_phrases" in p["emphasis_signals"]
        # evaluation_detail 은 sub_items 텍스트 근거 포함
        cats = p["evaluation_detail"]["categories"]
        assert any(c["sub_items"] for c in cats)
        assert p["validation_flags"][0]["severity"] == "high"

    def test_payload_handles_minimal_data(self):
        """brief_program/project_info 없어도 graceful (sites/special 빈 리스트)."""
        p = ba._build_advisor_payload(_EVAL_YDP, "public")
        assert p["sites"] == []
        assert p["special_conditions"] == []
        assert p["validation_flags"] == []


class TestInterpretSync:

    def test_overrides_scoring_focus_deterministically(self, monkeypatch):
        """LLM 이 보낸 가짜 scoring_focus(999점)는 결정론 값으로 덮여야 한다 (환각 차단)."""
        monkeypatch.setattr(ba, "call_messages", lambda **kw: _FAKE_INSIGHT)
        result = ba._interpret_sync(_EVAL_YDP, "public")
        cats = {f["category"]: f for f in result["scoring_focus"]}
        assert cats["배치계획"]["points"] == 40
        assert "LLM이 멋대로 바꾼 값" not in cats

    def test_stamps_metadata(self, monkeypatch):
        monkeypatch.setattr(ba, "call_messages", lambda **kw: _FAKE_INSIGHT)
        result = ba._interpret_sync(_EVAL_YDP, "public")
        assert result["schema_version"] == 1
        assert result["facility_type"] == "public"
        assert result["model_id"]   # settings.model_id 스탬프
        # LLM 서사 필드는 보존
        assert result["synthesis_summary"] == "요약"
        assert result["key_emphases"][0]["topic"] == "동선"

    def test_raises_on_non_json(self, monkeypatch):
        monkeypatch.setattr(ba, "call_messages", lambda **kw: "이건 JSON 이 아님")
        try:
            ba._interpret_sync(_EVAL_YDP, "public")
            assert False, "should have raised"
        except ValueError as e:
            assert "파싱 실패" in str(e)
