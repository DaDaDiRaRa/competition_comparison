"""tests/test_brief_playbook.py — 경험 기반 처방(brief_playbook) 테스트.

두 층:
  - brief_playbook: 무료 게이트(과거 데이터 없으면 LLM 미호출) + 결정론 덮어쓰기.
    LLM 은 monkeypatch 로 대체 — 네트워크/과금 없음.
  - brief_playbook_report_generator: 순수 렌더(LLM 0) — 섹션·배지·escape·빈 케이스.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings
from services.db_manager import save_project_meta, save_submission
import services.brief_playbook as bp
from services.brief_playbook import build_playbook, _data_basis, _empty_playbook
from services.brief_playbook_report_generator import to_playbook_html


FT = "test_facility"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    return tmp_path


def _win_submission(company, cid, strategy):
    return {
        "company": company, "result": "win", "competition_id": cid,
        "extracted_data": {"concept": [{
            "concept_name_ko": f"{company} 컨셉", "main_strategy": strategy,
            "sub_strategies": ["a", "b"],
        }]},
    }


def _seed_winner(db, cid="c1", company="A사", strategy="저층 개방형"):
    save_project_meta(cid, FT, "과거공모", "", "", "", merge=True)
    save_submission(FT, cid, company, "win", _win_submission(company, cid, strategy))


_BRIEF = {"_brief_meta": {"brief_id": "b1"}, "brief_evaluation": {
    "total_points": 100,
    "evaluation_categories": [
        {"name": "시민개방", "points": 40, "shared_with": [], "sub_items": ["a"]},
        {"name": "기술계획", "points": 30, "shared_with": [], "sub_items": []},
    ],
}}


# ── 무료 게이트 ──────────────────────────────────────────────────────────────

class TestFreeGate:
    def test_no_data_returns_sentinel_without_llm(self, db, monkeypatch):
        """과거 데이터 없으면 call_messages 를 호출하지 않고 sentinel 반환."""
        def _boom(*a, **k):
            raise AssertionError("과거 데이터 없는데 LLM 을 호출했다 (게이트 실패)")
        monkeypatch.setattr(bp, "call_messages", _boom)

        import asyncio
        result = asyncio.run(build_playbook(_BRIEF, FT))
        assert result["has_accumulated_data"] is False
        assert result["applications"] == []
        assert result["data_confidence"] == "none"
        assert result["caveats"], "안내 caveat 이 있어야 함"

    def test_has_data_calls_llm_and_overrides(self, db, monkeypatch):
        """과거 데이터 있으면 LLM 호출 + 결정론 값으로 덮어씀."""
        _seed_winner(db)

        llm_out = {
            "summary": "과거엔 개방성이 갈랐다.",
            "winning_lessons": [{"lesson": "저층 개방", "evidence": "당선작 공통",
                                 "source": "과거공모", "confidence": "strong"}],
            "losing_pitfalls": [],
            "applications": [{"guidance": "저층부를 개방하라", "rooted_in": "저층 개방",
                              "brief_anchor": "시민개방 배점 1순위", "basis": ["시민개방"],
                              "confidence": "strong"}],
            "watch_axes": [],
            # LLM 이 조작하려 시도하는 값들 — 결정론으로 덮어써져야 함
            "has_accumulated_data": False,
            "data_basis": {"win_n": 999},
            "data_confidence": "high",
            "caveats": ["실제 심사 결과는 보장 못 함"],
        }
        captured = {}
        def _fake(*a, **k):
            captured["called"] = True
            return json.dumps(llm_out, ensure_ascii=False)
        monkeypatch.setattr(bp, "call_messages", _fake)

        import asyncio
        result = asyncio.run(build_playbook(_BRIEF, FT))
        assert captured.get("called"), "LLM 이 호출됐어야 함"
        assert result["has_accumulated_data"] is True          # 덮어씀
        # LLM 의 win_n=999 는 무시되고 결정론 값으로 덮어써짐 (패턴 미빌드라 집계 0).
        assert result["data_basis"]["win_n"] == 0
        assert result["data_basis"]["case_count"] == 1         # 당선 발췌 1건 (연료 존재)
        assert result["scoring_focus"], "결정론 scoring_focus 부착"
        assert result["brief_id"] == "b1"
        assert result["_reference_cases"], "근거 사례 원본 보존"
        assert result["applications"][0]["basis"] == ["시민개방"]


# ── 결정론 헬퍼 ──────────────────────────────────────────────────────────────

class TestDataBasis:
    def test_counts_from_reference_ctx(self):
        ctx = {
            "pattern_summary": {"win_n": 3, "lose_n": 5},
            "case_excerpts": [{}, {}],
            "concept_comparison_excerpts": [{}],
        }
        db = _data_basis(ctx)
        assert db == {"win_n": 3, "lose_n": 5, "case_count": 2, "comparison_count": 1}

    def test_empty_ctx_all_zero(self):
        assert _data_basis({}) == {"win_n": 0, "lose_n": 0, "case_count": 0, "comparison_count": 0}


# ── 렌더러 ───────────────────────────────────────────────────────────────────

class TestRenderer:
    def test_empty_playbook_shows_guidance(self):
        pb = _empty_playbook(FT, "b1")
        html = to_playbook_html(pb, "테스트지침서", "테스트시설")
        assert "축적된 과거 데이터가 없습니다" in html
        assert "<!doctype html>" in html.lower()
        # 빈 케이스엔 처방 섹션이 없어야 함
        assert "이 지침서 적용" not in html

    def test_populated_playbook_renders_sections(self):
        pb = {
            "has_accumulated_data": True,
            "generated_at": "2026-07-12T10:00:00", "model_id": "claude-opus-4-8",
            "data_confidence": "medium",
            "data_basis": {"win_n": 3, "lose_n": 4, "case_count": 2, "comparison_count": 1},
            "summary": "과거엔 개방성이 당락을 갈랐다.",
            "winning_lessons": [{"lesson": "저층 개방형 채택", "evidence": "당선작 공통",
                                 "source": "과거공모A", "confidence": "strong"}],
            "losing_pitfalls": [{"pitfall": "폐쇄적 매스", "evidence": "낙선 공통",
                                 "source": "낙선 4건 집계", "confidence": "tentative"}],
            "applications": [{"guidance": "저층부를 시민에게 개방하라",
                              "rooted_in": "저층 개방형 채택", "brief_anchor": "시민개방 배점 1순위",
                              "basis": ["시민개방", "p.12"], "confidence": "strong"}],
            "watch_axes": [{"axis": "공공성", "why": "당락을 가름", "source": "과거공모A"}],
            "caveats": ["다른 공모의 경험을 적용한 가설이며 실제 심사 결과는 보장 못 함"],
        }
        html = to_playbook_html(pb, "OO청사 설계공모", "업무시설")
        assert "과거 당선 교훈" in html
        assert "과거 낙선 함정" in html
        assert "이 지침서 적용" in html
        assert "당락을 가른 축" in html
        assert "해석" in html                          # applications 배지 ('해석')
        assert "저층부를 시민에게 개방하라" in html
        assert "과거공모A" in html                       # source 칩
        assert "시민개방" in html                        # basis 칩
        assert "3" in html and "4" in html              # data_basis 밴드

    def test_escapes_html(self):
        pb = {
            "has_accumulated_data": True, "data_basis": {"win_n": 1},
            "summary": "", "winning_lessons": [], "losing_pitfalls": [],
            "applications": [{"guidance": "<script>alert(1)</script>", "rooted_in": "x",
                              "brief_anchor": "y", "basis": [], "confidence": ""}],
            "watch_axes": [], "caveats": [],
        }
        html = to_playbook_html(pb)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
