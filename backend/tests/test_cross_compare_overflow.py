"""교차비교 토큰 오버플로우 가드 회귀 테스트 (MATURITY 로드맵 #5).

대규모 교차비교(제출물·축 多)에서 Pass 2(리빌)가 실패/부분응답/토큰상한 도달해도:
  - Pass 1(축별 등급·블라인드 순위)을 통째로 잃지 않는다 (비치명).
  - concept_comparison 은 전 축 키 보장 (부분 응답 방어).
  - 축약·실패 시 _coverage_note 로 사용자에게 고지 (silent truncation 금지).
LLM 은 call_messages monkeypatch (네트워크 0).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import axes_keys_for
import services.comparator as comp

FT = "public"
AXES = axes_keys_for(FT)


def _subs():
    return [
        {"company": "현대", "result": "win", "facility_type": FT, "total_pages": 10,
         "extracted_data": {}},
        {"company": "삼성", "result": "lose", "facility_type": FT, "total_pages": 10,
         "extracted_data": {}},
    ]


def _blind_json():
    # Pass 1 은 익명 라벨(A안/B안) 키로 반환
    cell = {"grade": "B", "grade_justification": "", "strengths": [],
            "weaknesses": [], "brief_compliance": "unclear", "notes": ""}
    return json.dumps({
        "submissions": {"A안": {ax: dict(cell) for ax in AXES},
                        "B안": {ax: dict(cell) for ax in AXES}},
        "blind_ranking": ["A안", "B안"],
    }, ensure_ascii=False)


def _patch(monkeypatch, second):
    """call_messages: 1st=blind(정상), 2nd=second(리빌 응답 or 예외 트리거 문자열)."""
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _blind_json() if calls["n"] == 1 else second
    monkeypatch.setattr(comp, "call_messages", fake)


class TestPass2FailureNonFatal:
    def test_blind_preserved_and_note_set(self, monkeypatch):
        # 리빌이 비-JSON → parse 실패 → 축소 진행
        _patch(monkeypatch, "이건 JSON 이 아니다")
        result = comp._run_compare_sync({}, _subs(), FT)
        # Pass 1 등급 살아있음
        assert set(result["submissions"].keys()) == {"현대", "삼성"}
        # 사후 분석은 비었지만 고지됨
        assert result.get("_coverage_note")
        assert result["key_differentiators"] == []
        # concept 은 전 축 키 보장, 값은 ""
        assert set(result["concept_comparison"].keys()) >= set(AXES)
        assert all(v == "" for v in result["concept_comparison"].values())


class TestConceptAllAxisFill:
    def test_partial_concept_filled(self, monkeypatch):
        # 리빌이 첫 축만 반환 → 나머지 축은 "" 로 채워짐
        reveal = json.dumps({
            "key_differentiators": ["차별 (p.3)"],
            "winner_strengths": [], "loser_weaknesses": [],
            "gap_notes": "정렬됨",
            "concept_comparison": {AXES[0]: "현대는 A안 (p.3)"},
        }, ensure_ascii=False)
        _patch(monkeypatch, reveal)
        result = comp._run_compare_sync({}, _subs(), FT)
        assert set(result["concept_comparison"].keys()) >= set(AXES)
        assert result["concept_comparison"][AXES[0]] == "현대는 A안 (p.3)"
        assert result["concept_comparison"][AXES[1]] == ""
        # 성공 케이스라 커버리지 고지 없음
        assert "_coverage_note" not in result


class TestCappedNote:
    def test_capped_sets_note(self, monkeypatch):
        # 출력 상한을 아주 작게 낮춰 capped 경로 강제 (리빌 자체는 정상)
        monkeypatch.setattr(comp, "_MODEL_OUTPUT_CAP", 100)
        reveal = json.dumps({
            "key_differentiators": [], "winner_strengths": [], "loser_weaknesses": [],
            "gap_notes": "", "concept_comparison": {ax: "" for ax in AXES},
        }, ensure_ascii=False)
        _patch(monkeypatch, reveal)
        result = comp._run_compare_sync({}, _subs(), FT)
        assert "축약" in result.get("_coverage_note", "")
