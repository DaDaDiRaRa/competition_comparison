"""수주 제안서 → `deck_render/1.0` 장표 매핑 회귀.

네트워크 0 · LLM 0. 터읽기 `render_slides.py` 의 **한 장 상한**(kpi 4·cards 4·rows 12)과
`RenderRequest` 계약(낱말 5개 · ASCII filename)을 우리 쪽에서 지키는지 본다 —
넘겨도 그쪽이 자르지만, 잘린 안은 회의에서 없는 것으로 읽힌다.
"""
import pytest

from services.proposal_deck import (
    CARDS_PER_SLIDE,
    MAX_CARDS,
    MAX_KPI,
    MAX_ROWS,
    SCHEMA_VERSION,
    build_deck,
    _ascii_filename,
)

KINDS = {"cover", "kpi", "cards", "table", "text"}


def _dir(name, i=0):
    return {
        "direction": f"{name} — 한 줄 설명",
        "narrative": "이 컨셉은 배점 무게중심에서 출발한다. " * 4,
        "addresses": "배치계획 40점에 건다",
        "scoring_play": "배치 10 + 조망 5",
        "tradeoffs": "연면적을 조금 포기한다",
        "site_rationale": "남측 20m 도로에 접한다",
        "basis": [f"p.{10 + i}", "배치계획"],
    }


@pytest.fixture
def proposal():
    return {
        "executive_summary": "발주처가 진짜 원하는 것은 열린 청사다 — 배점이 시민개방에 쏠려 있다.",
        "concept_hook": {
            "keyword": "열린마당",
            "tagline": "되살림 · 잇기 · 지속",
            "axes": [
                {"term": "되살림", "ko": "낡은 청사를 다시 쓴다", "basis": ["p.7"]},
                {"term": "잇기", "ko": "가로와 마당을 잇는다", "basis": ["배치계획"]},
            ],
        },
        "win_themes": [{"theme": "시민개방 저층부", "rationale": "배점 1순위", "basis": ["p.18"]}],
        "design_directions": [_dir(f"안{i}", i) for i in range(5)],
        "placement_strategy": {
            "synthesis": "남측 도로와 북측 일조가 겹쳐 이렇게 풀린다.",
            "zones": [
                {"program": "시민개방 저층부", "plan": "S", "level": "저층", "required": True,
                 "why": "지침서가 남측 배치를 명시", "basis": ["p.20"]},
                {"program": "업무동", "plan": "N", "level": "중층", "required": False,
                 "why": "정북 일조를 피한다", "basis": ["site_context.road_access"]},
            ],
        },
        "priorities": [{"rank": 1, "focus": "배치계획", "why": "배점 40", "scoring_weight": "40%"}],
        "risks": [
            {"risk": "실격 조건 미충족", "severity": "high", "mitigation": "착수 즉시 확인", "basis": "p.3"},
            {"risk": "공사비 초과", "severity": "low", "mitigation": "대안 검토", "basis": "p.30"},
        ],
        "kickoff_checklist": ["현장 답사", "법규 확인"],
        "open_questions": ["주차 대수 기준이 모호하다"],
        "scoring_focus": [
            {"category": "배치계획", "points": 40, "weight_pct": 40, "rank": 1},
            {"category": "설계의 창의성", "points": None, "shared_with": ["공간계획"], "rank": 2},
        ],
        "data_confidence": "medium",
        "caveats": ["실제 심사 결과는 보장하지 못한다"],
    }


@pytest.fixture
def feasibility():
    return {
        "sites": [{"site_area_sqm": 12345.6, "floor_area_ratio_pct": 460,
                   "building_coverage_pct": 60, "max_height_m": 40}],
        "construction_cost_100m_won": 1200,
        "design_cost_100m_won": 80,
        "construction_period_months": 30,
    }


# ── 계약 ────────────────────────────────────────────────────────────────────


def test_schema_and_only_five_words(proposal, feasibility):
    """낱말 다섯 개를 넘기지 않는다 — 늘리면 터읽기가 우리 도메인을 알기 시작한다."""
    deck = build_deck(proposal, "영등포구청", "공공", feasibility=feasibility)
    assert deck["schema_version"] == SCHEMA_VERSION
    assert deck["slides"], "장이 하나도 없다"
    assert {s["kind"] for s in deck["slides"]} <= KINDS
    assert all(s.get("title") for s in deck["slides"])


def test_per_slide_caps_are_respected(proposal, feasibility):
    """한 장 상한 — 넘기면 터읽기가 자르고 그 안은 회의에서 없는 것이 된다."""
    deck = build_deck(proposal, "영등포구청", "공공", feasibility=feasibility)
    for s in deck["slides"]:
        assert len(s.get("kpis", [])) <= MAX_KPI
        assert len(s.get("cards", [])) <= MAX_CARDS
        assert len(s.get("rows", [])) <= MAX_ROWS
        if s.get("ratios"):
            assert len(s["ratios"]) == len(s["headers"]), "열 수와 다르면 터읽기가 ratios 를 버린다"


def test_five_directions_are_all_shown(proposal, feasibility):
    """5안이 카드 상한(4)에 걸려 조용히 사라지지 않는다."""
    deck = build_deck(proposal, "영등포구청", "공공", feasibility=feasibility)
    cards = [c["head"] for s in deck["slides"] if s["kind"] == "cards" and "설계" in s["title"]
             for c in s["cards"]]
    assert len(cards) == 5
    assert len(set(cards)) == 5
    n_slides = sum(1 for s in deck["slides"] if s["kind"] == "cards" and "설계" in s["title"])
    assert n_slides == (5 + CARDS_PER_SLIDE - 1) // CARDS_PER_SLIDE


def test_cards_body_is_a_string(proposal, feasibility):
    """터읽기 `_s(one,"body")` 는 str 만 받는다 — 리스트를 주면 "['a','b']" 가 찍힌다."""
    deck = build_deck(proposal, "영등포구청", "공공", feasibility=feasibility)
    for s in deck["slides"]:
        for c in s.get("cards", []):
            assert isinstance(c.get("body", ""), str)
            assert isinstance(c.get("head", ""), str)


def test_sources_carry_basis(proposal, feasibility):
    """PPTX 엔 data-ev 를 못 단다 — 근거는 sources 로 따라가야 한다."""
    deck = build_deck(proposal, "영등포구청", "공공", feasibility=feasibility)
    allsrc = [x for s in deck["slides"] for x in s.get("sources", [])]
    assert "p.20" in allsrc, "배치 근거가 캡션까지 안 갔다"
    assert "p.3" in allsrc, "risks[].basis 는 문자열인데 놓쳤다"


def test_facts_come_from_feasibility_only(proposal, feasibility):
    kpis = [k for s in build_deck(proposal, "X", "공공", feasibility=feasibility)["slides"]
            if s["kind"] == "kpi" for k in s["kpis"]]
    vals = " ".join(k["value"] for k in kpis)
    assert "12,346" in vals
    assert "460%" in vals


def test_cost_facts_are_not_dropped_by_the_kpi_cap(proposal, feasibility):
    """부지 제원 4개 + 사업비 3개 = 7개. 한 장에 몰면 사업비가 통째로 잘린다."""
    slides = build_deck(proposal, "X", "공공", feasibility=feasibility)["slides"]
    labels = [k["label"] for s in slides if s["kind"] == "kpi" for k in s["kpis"]]
    assert {"부지면적", "용적률", "건폐율", "최고높이"} <= set(labels)
    assert {"공사비", "설계비", "공사기간"} <= set(labels), "사업비가 상한에 걸려 사라졌다"
    assert sum(1 for s in slides if s["kind"] == "kpi") == 2


def test_required_and_proposed_zones_are_separated(proposal):
    deck = build_deck(proposal, "X", "공공")
    tbl = next(s for s in deck["slides"] if s["kind"] == "table" and s["title"] == "배치 전략")
    marks = [r[2] for r in tbl["rows"]]
    assert marks == ["필수", "제안"]


# ── 없는 장은 없다고 말한다 ─────────────────────────────────────────────────


def test_missing_is_named_not_silent(proposal):
    """feasibility 를 안 주면 '사업 규모' 가 빠지고 **왜** 빠졌는지 적힌다."""
    deck = build_deck(proposal, "X", "공공")           # feasibility 없음
    assert not any(s["kind"] == "kpi" for s in deck["slides"])
    assert any("사업 규모" in m for m in deck["missing"])


def test_missing_travels_inside_the_deck(proposal):
    """헤더가 아니라 마지막 장에 실린다 — 파일만 들고 가는 사람에게 보여야 한다."""
    deck = build_deck(proposal, "X", "공공")
    last = deck["slides"][-1]
    assert last["kind"] == "text" and last["title"] == "못 담은 것"
    assert last["body"]


def test_no_missing_slide_when_nothing_is_missing(proposal, feasibility):
    deck = build_deck(proposal, "X", "공공", feasibility=feasibility)
    if not deck["missing"]:
        assert deck["slides"][-1]["title"] != "못 담은 것"


# ── 입찰(bid) — 장르가 다르면 다른 장이 선다 ────────────────────────────────


def test_bid_replaces_five_directions():
    """입찰은 5안이 없다. '해당 없음' 자리표시를 컨셉으로 그리지 않는다."""
    bid_proposal = {
        "executive_summary": "사업수행능력이 승부처다.",
        "design_directions": [{"direction": "해당 없음(입찰)"}],
        "scoring_focus": [{"category": "참여기술자", "points": 50, "rank": 1}],
        "risks": [{"risk": "실적 부족", "severity": "high", "mitigation": "컨소시엄"}],
        "priorities": [{"rank": 1, "focus": "실적 정리", "why": "배점 40"}],
        "caveats": ["보장 없음"],
    }
    bs = {"top_layer": {
        "basis_dimension": "연면적",
        "axes": [
            {"name": "사업수행능력", "role": "pq",
             "bands": [{"label": "8만㎡ 미만", "weight_pct": 20},
                       {"label": "24만㎡ 이상", "weight_pct": 40}]},
            {"name": "가격", "role": "price", "weight_range": [60, 80]},
        ],
        "applicable": {"note": "연면적 미추출 — 적용 밴드 확인 필요"},
    }}
    deck = build_deck(bid_proposal, "대치미도", "재정비", bid_structure=bs)
    titles = [s["title"] for s in deck["slides"]]
    assert "배점 구조" in titles
    assert "설계 접근 방향" not in titles
    assert any("설계 접근 5안" in m for m in deck["missing"])
    bid_tbl = next(s for s in deck["slides"] if s["title"] == "배점 구조")
    assert "확인 필요" in bid_tbl["caption"], "정직성 — 밴드 단정 금지 고지가 사라졌다"


# ── 파일명 · 방어 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expect", [
    ("ydp_deck.pptx", "ydp_deck.pptx"),
    ("plain", "plain.pptx"),
    ("", "proposal_deck.pptx"),
    # 한글은 잘려 나가고 남은 조각만 쓴다. 사용자에게 보이는 한글 이름은
    # 우리 응답 헤더(RFC 6266)가 들고 가므로 이 값은 형제앱 내부용일 뿐이다.
    ("영등포구청_신청사_deck.pptx", "deck.pptx"),
    ("한글만_있는_이름.pptx", "proposal_deck.pptx"),          # 알아볼 글자가 0이면 기본값
    ("대치미도_2026_deck.pptx", "2026_deck.pptx"),
    ('bad"name/deck.pptx', "badnamedeck.pptx"),
])
def test_filename_is_ascii(raw, expect):
    """터읽기가 헤더에 그대로 박는다 — 한글이면 그쪽이 latin-1 로 500 을 낸다."""
    out = _ascii_filename(raw)
    out.encode("ascii")                       # 여기서 터지면 계약 위반
    assert out == expect


def test_deck_filename_is_ascii_even_for_korean_brief(proposal):
    deck = build_deck(proposal, "영등포구청 신청사", "공공", filename="영등포_deck.pptx")
    deck["filename"].encode("ascii")


def test_empty_proposal_is_refused():
    with pytest.raises(ValueError):
        build_deck({}, "X", "공공")


def test_thin_proposal_still_builds():
    """제안서가 얇아도 표지는 나온다 — 빈 파일을 주는 것보다 낫다."""
    deck = build_deck({"executive_summary": "짧다"}, "X", "공공")
    assert deck["slides"][0]["kind"] == "cover"
    assert deck["missing"]


def test_cockpit_matches_html_deck(proposal, feasibility):
    """결정 요약은 HTML 덱과 **같은 판단**이어야 한다 (단일 소스)."""
    from services.brief_proposal_report_generator import cockpit_cells
    deck = build_deck(proposal, "X", "공공", feasibility=feasibility)
    tbl = [s for s in deck["slides"] if s["title"] == "결정 요약"]
    cells = cockpit_cells(proposal)
    if len(cells) >= 3:
        assert tbl, "HTML 은 cockpit 을 그리는데 PPTX 엔 없다"
        assert len(tbl[0]["rows"]) == len(cells)
