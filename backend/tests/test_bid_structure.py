"""tests/test_bid_structure.py — 입찰 2층 배점 구조 파싱(bid_structure) 테스트.

LLM 0. 대치미도 입찰지침서 실구조(연면적 밴드 20/30/40% + PQ 100점표) 재현.
정직성: 밴드 기준(연면적) 값 미확보 시 적용 밴드를 단정하지 않고 note.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.bid_structure import build_bid_structure, _parse_bands, _parse_bands_from_method


def _bid(genre="bid", crit=None, reqs=None, quant=None, sites=None):
    d = {
        "_brief_genre": {"genre": genre},
        "_requirements": {
            "evaluation_criteria": crit or [],
            "requirements": reqs or [],
        },
        "brief_evaluation": {
            "total_points": 100,
            "evaluation_categories": [
                {"name": "참여기술자(50)", "points": 50},
                {"name": "유사용역실적(40)", "points": 40},
                {"name": "신용도(10)", "points": 10},
            ],
        },
    }
    if quant:
        d["_quantitative"] = quant
    if sites:
        d["feasibility_export"] = {"sites": sites}
    return d


_CRIT = [
    {"item": "사업수행능력평가 (8만㎡ 미만: 20%, 8만~24만㎡: 30%, 24만㎡ 이상: 40%)", "points": None},
    {"item": "가격평가 (8만㎡ 미만: 80%, 8만~24만㎡: 70%, 24만㎡ 이상: 60%)", "points": None},
]
_REQS = [{"axis": "business_viability", "description": "가격평가 비중: 연면적 규모에 따라 60~80% 차등 적용"}]


class TestParseBands:
    def test_three_bands(self):
        bands = _parse_bands("사업수행능력평가 (8만㎡ 미만: 20%, 8만~24만㎡: 30%, 24만㎡ 이상: 40%)")
        assert len(bands) == 3
        assert bands[0] == {"label": "8만㎡ 미만: 20%", "min_sqm": None, "max_sqm": 80000, "weight_pct": 20.0}
        assert bands[1]["min_sqm"] == 80000 and bands[1]["max_sqm"] == 240000
        assert bands[2]["min_sqm"] == 240000 and bands[2]["max_sqm"] is None


# 대치미도 p22.evaluation_method 실문구 (run 간 안정적 소스)
_METHOD = ("전체연면적 규모에 따라 사업수행능력평가와 가격평가의 비중이 달라짐: "
           "8만㎡미만(사업수행능력평가 20%, 가격평가 80%), "
           "8만㎡이상~24만㎡미만(사업수행능력평가 30%, 가격평가 70%), "
           "24만㎡이상(사업수행능력평가 40%, 가격평가 60%)")


class TestParseBandsFromMethod:
    def test_per_axis_bands(self):
        r = _parse_bands_from_method(_METHOD)
        assert [b["weight_pct"] for b in r["사업수행능력평가"]] == [20.0, 30.0, 40.0]
        assert [b["weight_pct"] for b in r["가격평가"]] == [80.0, 70.0, 60.0]
        # 구간 경계
        assert r["사업수행능력평가"][0]["max_sqm"] == 80000
        assert r["사업수행능력평가"][1]["min_sqm"] == 80000 and r["사업수행능력평가"][1]["max_sqm"] == 240000
        assert r["사업수행능력평가"][2]["min_sqm"] == 240000

    def test_empty_on_no_bands(self):
        assert _parse_bands_from_method("사업수행능력과 가격을 종합 평가한다.") == {}


class TestMultiTableMerge:
    def _two_page_be(self):
        """상위층(p22, method 밴드) + PQ상세(p24, 100점표) 2페이지."""
        return [
            {"_page": 22, "total_points": 100, "evaluation_method": _METHOD,
             "evaluation_categories": [
                 {"name": "사업수행능력평가", "points": None},
                 {"name": "가격평가", "points": None}]},
            {"_page": 24, "total_points": 100, "evaluation_categories": [
                 {"name": "참여기술자(50)", "points": 50},
                 {"name": "유사용역실적(40)", "points": 40},
                 {"name": "신용도(10)", "points": 10}]},
        ]

    def test_top_from_method_pq_from_detail_page(self):
        """상위 밴드는 p22 method 에서, PQ상세는 p24 에서 — 각 층을 올바른 표에서."""
        d = {"_brief_genre": {"genre": "bid"}, "_requirements": {},
             "brief_evaluation": self._two_page_be()}
        bs = build_bid_structure(d)
        axes = {a["role"]: a for a in bs["top_layer"]["axes"]}
        assert [b["weight_pct"] for b in axes["pq"]["bands"]] == [20.0, 30.0, 40.0]
        assert [b["weight_pct"] for b in axes["price"]["bands"]] == [80.0, 70.0, 60.0]
        assert bs["top_layer"]["basis_dimension"] == "연면적"
        pq = {c["name"]: c["points"] for c in bs["pq_detail"]["categories"]}
        assert pq == {"참여기술자(50)": 50, "유사용역실적(40)": 40, "신용도(10)": 10}

    def test_method_beats_missing_criteria(self):
        """evaluation_criteria 가 밴드를 떨궈도 method 로 정확 밴드 복원 (run B 회귀)."""
        d = {"_brief_genre": {"genre": "bid"},
             "_requirements": {"evaluation_criteria": [{"item": "사업수행능력평가 합계", "points": 100}]},
             "brief_evaluation": self._two_page_be()}
        bs = build_bid_structure(d)
        pq_axis = next(a for a in bs["top_layer"]["axes"] if a["role"] == "pq")
        assert [b["weight_pct"] for b in pq_axis["bands"]] == [20.0, 30.0, 40.0]


class TestBuildBidStructure:
    def test_none_when_not_bid(self):
        assert build_bid_structure(_bid(genre="competition", crit=_CRIT)) is None

    def test_structure_from_pq_table_only(self):
        """상위 밴드 신호가 없어도 PQ 100점표만으로 구조 노출 (하위 breakdown 가치)."""
        bs = build_bid_structure(_bid(crit=[{"item": "가격평가", "points": None}]))
        assert bs is not None
        assert bs["pq_detail"]["total_points"] == 100
        assert bs["top_layer"]["axes"] == []

    def test_range_fallback_when_no_exact_bands(self):
        """정확 밴드 없이 requirements 범위('60~80% 차등')만 있으면 weight_range 로 폴백."""
        bs = build_bid_structure(_bid(
            crit=[{"item": "사업수행능력평가 합계", "points": 100}],
            reqs=[{"axis": "business_viability",
                   "description": "가격평가 비중: 연면적 규모에 따라 60~80% 차등 적용"}],
        ))
        price = next(a for a in bs["top_layer"]["axes"] if a["role"] == "price")
        assert price["weight_range"] == [60.0, 80.0]
        assert not any(b.get("min_sqm") or b.get("max_sqm") for b in price.get("bands", []))
        assert bs["top_layer"]["basis_dimension"] == "연면적"

    def test_top_layer_axes_and_thresholds(self):
        bs = build_bid_structure(_bid(crit=_CRIT, reqs=_REQS))
        tl = bs["top_layer"]
        assert tl["basis_dimension"] == "연면적"
        assert tl["thresholds_sqm"] == [80000, 240000]
        names = {a["name"]: a for a in tl["axes"]}
        assert names["사업수행능력평가"]["role"] == "pq"
        assert names["가격평가"]["role"] == "price"
        assert [b["weight_pct"] for b in names["사업수행능력평가"]["bands"]] == [20.0, 30.0, 40.0]

    def test_pq_detail_aggregated(self):
        bs = build_bid_structure(_bid(crit=_CRIT))
        pq = bs["pq_detail"]
        assert pq["total_points"] == 100
        assert {c["name"]: c["points"] for c in pq["categories"]} == {
            "참여기술자(50)": 50, "유사용역실적(40)": 40, "신용도(10)": 10,
        }

    def test_applicable_held_when_basis_value_missing(self):
        """연면적 미확보 → 적용 밴드 단정 금지 (대치미도)."""
        bs = build_bid_structure(_bid(crit=_CRIT, reqs=_REQS))
        app = bs["top_layer"]["applicable"]
        assert app["basis_value_sqm"] is None
        assert app["weights"] == {}
        assert "연면적" in app["note"] and "확인" in app["note"]

    def test_applicable_computed_when_floor_area_known(self):
        """연면적 알면 적용 밴드·유효 가중치 계산."""
        bs = build_bid_structure(_bid(crit=_CRIT, reqs=_REQS,
                                      quant={"total_floor_area_sqm": 300000}))  # 24만 이상
        app = bs["top_layer"]["applicable"]
        assert app["basis_value_sqm"] == 300000
        assert app["weights"]["사업수행능력평가"] == 40.0
        assert app["weights"]["가격평가"] == 60.0

    def test_does_not_guess_from_site_area_when_basis_is_floor_area(self):
        """기준이 연면적인데 대지면적만 있으면 사용 안 함 (21만㎡ 대지 ≠ 연면적)."""
        bs = build_bid_structure(_bid(crit=_CRIT, reqs=_REQS,
                                      sites=[{"site_area_sqm": 210193.8}]))
        assert bs["top_layer"]["applicable"]["basis_value_sqm"] is None

    def test_never_raises(self):
        for bad in [{}, {"_brief_genre": {"genre": "bid"}},
                    {"_brief_genre": {"genre": "bid"}, "_requirements": "x"}]:
            build_bid_structure(bad)  # None 또는 dict, 예외 없어야
