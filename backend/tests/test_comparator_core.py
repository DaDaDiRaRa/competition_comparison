"""comparator 핵심 로직 회귀 테스트 (MATURITY 로드맵 #8 — 기존 미검증 코어).

내가 이번 작업에서 안 건드린 comparator 의 2-pass 흐름·순수 함수를 잠근다:
익명화/역익명화, gap_analysis 정렬 산출, compare/diagnose 정상경로 병합 + 인용검증 훅.
LLM 은 call_messages monkeypatch (네트워크 0).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import axes_keys_for
import services.comparator as comp

FT = "public"
AXES = axes_keys_for(FT)


class TestRevealPromptSharpening:
    """Layer 2 — 리빌 프롬프트 심화(대비·구체성·인과)가 되돌려지지 않게 잠금."""

    def _prompt(self):
        static, _ = comp._build_reveal_prompt_parts(
            [{"company": "A", "result": "win"}, {"company": "B", "result": "lose"}],
            {"submissions": {}}, FT)
        return static

    def test_no_unreplaced_placeholders(self):
        import re
        assert re.search(r"\{max_\w+\}|\{kd_chars\}|\{wl_chars\}|\{global_chars\}", self._prompt()) is None

    def test_contrast_and_specificity_rules(self):
        p = self._prompt()
        assert "SPECIFICITY RULE" in p            # 일반론 금지·구체 무브 인용
        assert "당락을 갈랐다" in p                 # 명시적 win↔lose 대비 포맷
        assert "Never invent" in p and "(p.N)" in p   # 환각·인용 가드 유지

    def test_sizes_tuned(self):
        p = self._prompt()
        assert "max_4" in p and "70 chars" in p    # key_differentiators 여유
        assert "45 chars" in p                     # winner/loser 간결·구체


# ── 순수 함수 ─────────────────────────────────────────────────────────────────

class TestAnonymize:
    def test_labels_and_result_removed(self):
        subs = [{"company": "현대", "result": "win", "x": 1},
                {"company": "삼성", "result": "lose", "x": 2}]
        anon, rev = comp._anonymize_submissions(subs)
        assert [s["company"] for s in anon] == ["A안", "B안"]
        assert all("result" not in s for s in anon)          # 블라인드 보장
        assert rev == {"A안": "현대", "B안": "삼성"}
        assert anon[0]["x"] == 1                               # 다른 필드 보존

    def test_deanonymize_restores_names(self):
        blind = {"submissions": {"A안": {"공간": {}}, "B안": {"공간": {}}},
                 "blind_ranking": ["B안", "A안"]}
        out = comp._deanonymize_blind_result(blind, {"A안": "현대", "B안": "삼성"})
        assert set(out["submissions"]) == {"현대", "삼성"}
        assert out["blind_ranking"] == ["삼성", "현대"]


class TestGapAnalysis:
    def test_high_when_top1_matches(self):
        g = comp._compute_gap_analysis(["현대", "삼성", "GS"], {"현대": "win"}, "")
        assert g["alignment"] == "high"
        assert g["top1_matches_winner"] is True

    def test_partial_when_winner_in_top_half_not_first(self):
        g = comp._compute_gap_analysis(["현대", "삼성", "GS", "롯데"],
                                       {"현대": "lose", "삼성": "win"}, "")
        assert g["alignment"] == "partial"

    def test_low_when_winner_at_bottom(self):
        g = comp._compute_gap_analysis(["현대", "삼성", "GS", "롯데"],
                                       {"롯데": "win"}, "")
        assert g["alignment"] == "low"

    def test_unknown_without_winners(self):
        g = comp._compute_gap_analysis(["현대", "삼성"], {"현대": "lose"}, "")
        assert g["alignment"] == "unknown"


# ── 2-pass 정상경로 ───────────────────────────────────────────────────────────

def _patch_two(monkeypatch, blind, reveal):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return blind if calls["n"] == 1 else reveal
    monkeypatch.setattr(comp, "call_messages", fake)


class TestCompareHappyPath:
    def test_full_merge_deanonymized(self, monkeypatch):
        cell = {"grade": "B", "grade_justification": "", "strengths": ["좋음 (p.3)"],
                "weaknesses": [], "brief_compliance": "yes", "notes": ""}
        blind = json.dumps({
            "submissions": {"A안": {ax: dict(cell) for ax in AXES},
                            "B안": {ax: dict(cell) for ax in AXES}},
            "blind_ranking": ["A안", "B안"],
        }, ensure_ascii=False)
        reveal = json.dumps({
            "key_differentiators": ["차별 (p.2)"], "winner_strengths": ["강점 (p.3)"],
            "loser_weaknesses": ["약점 (p.4)"], "gap_notes": "정렬됨",
            "concept_comparison": {AXES[0]: "현대는 배치 (p.2)"},
        }, ensure_ascii=False)
        _patch_two(monkeypatch, blind, reveal)

        subs = [{"company": "현대", "result": "win", "facility_type": FT,
                 "total_pages": 10, "extracted_data": {}},
                {"company": "삼성", "result": "lose", "facility_type": FT,
                 "total_pages": 10, "extracted_data": {}}]
        r = comp._run_compare_sync({}, subs, FT)

        assert set(r["submissions"]) == {"현대", "삼성"}          # 역익명화
        assert r["winner_strengths"] == ["강점 (p.3)"]
        assert r["gap_analysis"]["alignment"] == "high"           # 현대=top1=win
        assert set(r["concept_comparison"]) >= set(AXES)          # 전 축 키
        assert r["_citation_flags"] == []                         # p.2~4 ≤ 10, 위반 없음
        assert "_coverage_note" not in r                          # 소규모 → 고지 없음

    def test_citation_flag_on_bad_page(self, monkeypatch):
        cell = {"grade": "B", "strengths": ["환각 (p.99)"], "weaknesses": [],
                "brief_compliance": "unclear", "notes": ""}
        blind = json.dumps({"submissions": {"A안": {AXES[0]: dict(cell)}},
                            "blind_ranking": ["A안"]}, ensure_ascii=False)
        reveal = json.dumps({"concept_comparison": {}}, ensure_ascii=False)
        _patch_two(monkeypatch, blind, reveal)
        subs = [{"company": "현대", "result": "win", "facility_type": FT,
                 "total_pages": 12, "extracted_data": {}}]
        r = comp._run_compare_sync({}, subs, FT)
        # p.99 > 12쪽 → 인용검증이 flag
        assert any(f["page"] == 99 for f in r["_citation_flags"])


class TestDiagnoseHappyPath:
    def test_parse_and_citation_hook(self, monkeypatch):
        diag = json.dumps({
            "axes": {AXES[0]: {"grade": "B", "strengths": ["좋음 (p.5)"],
                               "weaknesses": ["약함 (p.99)"], "recommendations": []}},
            "overall_grade": "B", "strengths": [], "weaknesses": [], "recommendations": [],
        }, ensure_ascii=False)
        monkeypatch.setattr(comp, "call_messages", lambda *a, **k: diag)
        r = comp._run_diagnose_sync(FT, {}, {}, {"total_pages": 10, "concept": {"_page": 1}})
        assert r["overall_grade"] == "B"
        assert "_citation_flags" in r
        assert any(f["page"] == 99 for f in r["_citation_flags"])  # p.99 > 10
