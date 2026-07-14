"""아카이브 BM25 관련도 랭킹 회귀 테스트 (MATURITY 로드맵 #6).

기존 FTS5 MATCH 는 ORDER BY 가 없어 무순 50건 컷(관련도 정렬 불가)이었다.
BM25 관련도순 + 컬럼 가중치(_BM25_WEIGHTS)로 best-first 정렬을 검증한다.
컬럼 순서: competition_id, facility_type, ranking, key_differentiators,
          winner_patterns, concept_keywords, gap_analysis_alignment, extra_meta
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.archive_search import ArchiveSearchIndex, _BM25_WEIGHTS


def _insert(idx, cid, cols):
    """cols = 7개 텍스트(facility_type..extra_meta). competition_id 는 cid."""
    idx._cards[cid] = {"competition_id": cid}
    idx.conn.execute(
        "INSERT INTO archive_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, *cols),
    )


class TestBm25Weights:
    def test_weight_count_matches_columns(self):
        # 8개 컬럼 → 8개 가중치 (개수 어긋나면 bm25 가 OperationalError)
        assert len([w for w in _BM25_WEIGHTS.split(",")]) == 8


class TestRelevanceOrdering:
    def test_facility_match_ranks_first(self):
        idx = ArchiveSearchIndex(base_path=Path("/nonexistent"))
        # c_strong: 시설유형 컬럼에 '의료시설동' → 가중 2.0 우대
        _insert(idx, "c_strong", ("의료시설동", "", "", "", "", "", ""))
        # c_weak: extra_meta 에만 언급 → 가중 1.0
        _insert(idx, "c_weak", ("주거시설", "", "", "", "", "", "의료시설동 살짝"))
        # 노이즈
        _insert(idx, "n1", ("교육시설", "", "", "", "", "", ""))
        idx.conn.commit()

        results = idx._ranked_match('"의료시설동"', 10)
        cids = [r["competition_id"] for r in results]
        assert "c_strong" in cids and "c_weak" in cids
        assert "n1" not in cids                    # 매칭만 반환
        assert cids.index("c_strong") < cids.index("c_weak")  # 강매칭 우선
        idx.close()

    def test_returns_ordered_not_empty(self):
        idx = ArchiveSearchIndex(base_path=Path("/nonexistent"))
        for i in range(5):
            _insert(idx, f"c{i}", (f"업무시설 프로젝트{i}", "", "", "", "", "", ""))
        idx.conn.commit()
        results = idx._ranked_match('"업무시설"', 3)
        assert len(results) == 3   # LIMIT 적용, 관련도순 (bm25 미에러)
        idx.close()

    def test_empty_query_paths(self):
        idx = ArchiveSearchIndex(base_path=Path("/nonexistent"))
        assert idx.search_keyword("") == []
        assert idx.search_keyword("   ") == []
        idx.close()
