"""myproject_analyzer.deep_analyze end-to-end 회귀 (MATURITY 로드맵 #8 — 기존 미검증 코어).

LLM 응답 파싱 + setdefault 폴백 + 인용검증 훅 배선 + 실패 graceful 을 잠근다.
call_messages monkeypatch (네트워크 0).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import services.myproject_analyzer as mp

FT = "public"


def _run(**kw):
    defaults = dict(facility_type=FT, extracted_data={"total_pages": 10, "c": {"_page": 1}},
                    brief_data=None, meta_extra={}, company="현대", result="win")
    defaults.update(kw)
    return asyncio.run(mp.deep_analyze(**defaults))


class TestDeepAnalyzeHappyPath:
    def test_parse_and_defaults(self, monkeypatch):
        out = json.dumps({
            "concept_narrative": "컨셉 서술",
            "axes_evidence": {"공간": {"grade": "A", "strengths": ["동선 (p.3)"],
                                       "weaknesses": []}},
        }, ensure_ascii=False)
        monkeypatch.setattr(mp, "call_messages", lambda *a, **k: out)
        r = _run()
        assert r["concept_narrative"] == "컨셉 서술"
        # 누락 필드 폴백
        for k in ("key_differentiators", "improvement_points", "search_keywords", "auto_meta"):
            assert k in r
        assert r["rubric_version"]
        assert "_citation_flags" in r

    def test_citation_flag_on_bad_page(self, monkeypatch):
        out = json.dumps({
            "axes_evidence": {"공간": {"grade": "A", "strengths": ["환각 (p.99)"]}},
        }, ensure_ascii=False)
        monkeypatch.setattr(mp, "call_messages", lambda *a, **k: out)
        r = _run(extracted_data={"total_pages": 12, "c": {"_page": 1}})
        assert any(f["page"] == 99 for f in r["_citation_flags"])

    def test_llm_failure_graceful(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("LLM down")
        monkeypatch.setattr(mp, "call_messages", boom)
        r = _run()
        # 실패해도 스키마 유지 + _error
        assert r["axes_evidence"] == {} and "_error" in r
        assert r["rubric_version"]
