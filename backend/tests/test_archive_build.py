"""아카이브 인덱싱 end-to-end 회귀 테스트 (MATURITY 로드맵 #8 — 기존 미검증 코어).

디스크 fixture(_meta.json/_comparison.json)로 ArchiveSearchIndex.build() → 검색까지
실제 경로를 잠근다. LLM 자연어 변환은 monkeypatch (네트워크 0), 폴백 경로도 검증.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import services.archive_search as arch
from services.archive_search import ArchiveSearchIndex


def _make_comp(base: Path, ft: str, cid: str, name: str,
               winner_strengths: list, key_diff: list):
    d = base / ft / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "_meta.json").write_text(json.dumps({
        "facility_type": ft, "competition_id": cid, "competition_name": name,
    }, ensure_ascii=False), encoding="utf-8")
    (d / "_comparison.json").write_text(json.dumps({
        "winner_strengths": winner_strengths, "key_differentiators": key_diff,
        "ranking": ["현대건설"], "gap_analysis": {"alignment": "high"},
    }, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def index(tmp_path):
    _make_comp(tmp_path, "medical", "c_med", "종합병원 공모",
               ["환자 동선 최적화 배치", "자연채광 병동"], ["동선 효율"])
    _make_comp(tmp_path, "public", "c_pub", "구청사 공모",
               ["시민 개방형 로비", "친환경 인증"], ["개방성"])
    idx = ArchiveSearchIndex(base_path=tmp_path)
    idx.build()
    yield idx
    idx.close()


class TestBuild:
    def test_counts_all(self, index):
        assert len(index.all_cards()) == 2

    def test_cards_have_meta(self, index):
        cids = {c["competition_id"] for c in index.all_cards()}
        assert cids == {"c_med", "c_pub"}


class TestSearch:
    def test_keyword_finds_by_winner_strength(self, index):
        # '자연채광' 은 medical 공모의 winner_strength → 그 공모만
        results = index.search_keyword("자연채광")
        assert [c["competition_id"] for c in results] == ["c_med"]

    def test_keyword_by_facility_synonym(self, index):
        # facility 컬럼은 동의어 확장 인덱싱 → '의료시설' 로 medical 매칭
        results = index.search_keyword("의료시설")
        assert any(c["competition_id"] == "c_med" for c in results)

    def test_natural_falls_back_to_keyword_on_llm_fail(self, index, monkeypatch):
        # LLM 변환 실패 → search_keyword 폴백 (결과 유지)
        def boom(*a, **k):
            raise RuntimeError("LLM down")
        monkeypatch.setattr(arch, "call_messages", boom)
        results = index.search_natural("친환경 인증")
        assert any(c["competition_id"] == "c_pub" for c in results)

    def test_natural_uses_extracted_keywords(self, index, monkeypatch):
        monkeypatch.setattr(arch, "call_messages",
                            lambda *a, **k: '{"keywords": ["환자 동선"]}')
        results = index.search_natural("병원 동선 좋은 사례")
        assert any(c["competition_id"] == "c_med" for c in results)
