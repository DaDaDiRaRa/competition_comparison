"""tests/test_brief_genre.py — 지침서 장르 판별(brief_genre) 결정론 테스트.

LLM/네트워크 없음. 합성 fixture 로 competition/bid/unknown 3 케이스 + 마진·혼재 검증.
실데이터(대치미도=bid, 영등포/종로=competition, 하안주공=unknown)로 튜닝된 로직.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.brief_genre import detect_brief_genre, GENRE_LABEL


def _eval(*names):
    return {"brief_evaluation": {
        "evaluation_categories": [{"name": n, "points": 10} for n in names]
    }}


class TestGenreDetection:
    def test_bid_by_eval_axes(self):
        """사업수행능력·참여기술자·가격평가 축 → bid."""
        d = _eval("사업수행능력평가", "가격평가", "참여기술자(50)", "유사 용역 실적(40)", "신용도(10)")
        r = detect_brief_genre(d)
        assert r["genre"] == "bid"
        assert r["confidence"] == "high"
        assert r["bid_score"] > r["competition_score"]

    def test_competition_by_eval_axes(self):
        """배치·공간·기술계획·경관 축 → competition."""
        d = _eval("과업의 목적", "배치계획", "공간계획", "기술계획", "경관 및 주변과의 조화")
        r = detect_brief_genre(d)
        assert r["genre"] == "competition"
        assert r["confidence"] == "high"

    def test_unknown_when_no_signals(self):
        """평가축 없고 마커 없음 → unknown (억지 판정 금지)."""
        d = {"brief_overview": {"text": "본 지침서는 대상지 개요를 설명한다."}}
        r = detect_brief_genre(d)
        assert r["genre"] == "unknown"
        assert r["confidence"] == "low"

    def test_bid_text_markers_over_incidental_gongmo(self):
        """본문에 '공모'가 있어도 적격심사·낙찰·PQ 축이 강하면 bid (대치미도 패턴)."""
        d = _eval("사업수행능력평가", "참여기술자", "유사용역실적", "신용도")
        d["brief_admin"] = {"text": "재건축 정비사업 설계 공모 관련 적격심사 및 낙찰자 선정"}
        r = detect_brief_genre(d)
        assert r["genre"] == "bid"

    def test_signals_reported(self):
        d = _eval("참여기술자", "가격평가")
        r = detect_brief_genre(d)
        assert "참여기술자" in r["signals"]["bid_axis"]
        assert "가격평가" in r["signals"]["bid_axis"]

    def test_never_raises_on_garbage(self):
        for bad in [{}, {"brief_evaluation": "not a dict"}, {"brief_evaluation": [None, 3]},
                    {"_requirements": None}]:
            r = detect_brief_genre(bad)
            assert r["genre"] in ("competition", "bid", "unknown")

    def test_label_map_covers_all(self):
        for g in ("competition", "bid", "unknown"):
            assert g in GENRE_LABEL
