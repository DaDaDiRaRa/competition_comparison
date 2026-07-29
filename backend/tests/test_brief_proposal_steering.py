# -*- coding: utf-8 -*-
"""'변수' steering (대화형 컨셉 조종 v1) 회귀 테스트 — LLM/네트워크 0.

핵심 계약:
  1. steering 없으면 기존 경로와 프롬프트 블록이 동일 (블록 2개, 레거시 캐시 보호)
  2. steering 있으면 3번째 블록에 지시가 순서대로 포함되고 cache_control 없음
     (block1/2 캐시 prefix 유지 — 반복 루프 입력 캐시 히트)
  3. A층 불변: LLM 이 scoring_focus 를 조작해도 결정론 값으로 덮어씀 (steering 하에서도)
  4. _steering_applied 부착 (로그와 일치 보장용) — 렌더 HTML 에는 미노출
  5. 라우터: 빈 body 하위호환 / _steering_log 누적 / reset / LLM 실패 시 로그 미persist /
     상한 400 / list_briefs 노출
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import services.brief_proposal as bp
from config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# 서비스 계층 — _propose_sync 프롬프트 조립 + 결정론 덮어쓰기
# ═══════════════════════════════════════════════════════════════════════════════

_BRIEF = {
    "_brief_meta": {"brief_id": "b1", "brief_name": "테스트 청사"},
    "brief_evaluation": {
        "total_points": 100,
        "evaluation_categories": [
            {"name": "배치계획", "points": 60, "shared_with": [], "sub_items": []},
            {"name": "기술계획", "points": 40, "shared_with": [], "sub_items": []},
        ],
    },
}

# LLM 이 scoring_focus 를 조작해서 돌려주는 응답 (덮어쓰기 검증용)
_LLM_JSON = json.dumps({
    "executive_summary": "요약",
    "scoring_focus": [{"category": "조작된축", "points": 999}],
    "placement_strategy": {
        "zones": [
            {"program": "보건소", "plan": "S", "level": "저층", "required": True},
            {"program": "업무동", "plan": "N", "level": "상층", "required": False},
        ],
        "alternatives": [
            {"label": "A", "zones": [
                {"program": "보건소", "plan": "N", "level": "상층", "required": True},
                {"program": "업무동", "plan": "S", "level": "저층", "required": False},
            ]},
        ],
    },
    "caveats": ["실제 심사 결과 보장 못 함"],
}, ensure_ascii=False)


def _capture_call(captured):
    def fake_call_messages(**kwargs):
        captured.append(kwargs)
        return _LLM_JSON
    return fake_call_messages


class TestSteeringPrompt:

    def test_no_steering_two_blocks(self, monkeypatch):
        cap = []
        monkeypatch.setattr(bp, "call_messages", _capture_call(cap))
        bp._propose_sync(dict(_BRIEF), "public")
        content = cap[0]["messages"][0]["content"]
        assert len(content) == 2                       # 레거시와 동일
        assert all("cache_control" in b for b in content)

    def test_empty_steering_same_as_none(self, monkeypatch):
        cap = []
        monkeypatch.setattr(bp, "call_messages", _capture_call(cap))
        bp._propose_sync(dict(_BRIEF), "public", steering=[])
        bp._propose_sync(dict(_BRIEF), "public", steering=["  ", ""])  # 공백만 → 무시
        assert len(cap[0]["messages"][0]["content"]) == 2
        assert len(cap[1]["messages"][0]["content"]) == 2

    def test_steering_third_block_no_cache(self, monkeypatch):
        cap = []
        monkeypatch.setattr(bp, "call_messages", _capture_call(cap))
        bp._propose_sync(dict(_BRIEF), "public",
                         steering=["테마를 '흐름'으로", "공공성을 재난 거점으로 해석"])
        content = cap[0]["messages"][0]["content"]
        assert len(content) == 3
        block3 = content[2]["text"]
        assert "1. 테마를 '흐름'으로" in block3
        assert "2. 공공성을 재난 거점으로 해석" in block3
        assert "cache_control" not in content[2]        # block1/2 캐시 prefix 유지
        # 적용 규칙(A층 불변) 포함
        assert "required=true" in block3 or "사실이 이기고" in block3

    def test_block12_identical_with_and_without_steering(self, monkeypatch):
        cap = []
        monkeypatch.setattr(bp, "call_messages", _capture_call(cap))
        bp._propose_sync(dict(_BRIEF), "public")
        bp._propose_sync(dict(_BRIEF), "public", steering=["지시"])
        c0, c1 = cap[0]["messages"][0]["content"], cap[1]["messages"][0]["content"]
        assert c0[0] == c1[0] and c0[1] == c1[1]        # 캐시 히트 전제

    def test_scoring_focus_deterministic_under_steering(self, monkeypatch):
        monkeypatch.setattr(bp, "call_messages", _capture_call([]))
        r = bp._propose_sync(dict(_BRIEF), "public", steering=["아무 지시"])
        cats = [f["category"] for f in r["scoring_focus"]]
        assert "조작된축" not in cats                    # LLM 조작 무시
        assert "배치계획" in cats                        # 결정론 값
        r2 = bp._propose_sync(dict(_BRIEF), "public")   # steering 없어도 동일
        assert r["scoring_focus"] == r2["scoring_focus"]

    def test_lock_required_zone_under_steering(self, monkeypatch):
        monkeypatch.setattr(bp, "call_messages", _capture_call([]))
        r = bp._propose_sync(dict(_BRIEF), "public", steering=["보건소를 상층으로 옮겨줘"])
        alt = r["placement_strategy"]["alternatives"][0]["zones"]
        z = {x["program"]: (x["plan"], x["level"]) for x in alt}
        assert z["보건소"] == ("S", "저층")             # required 존은 권장안 기준 고정

    def test_steering_applied_attached(self, monkeypatch):
        monkeypatch.setattr(bp, "call_messages", _capture_call([]))
        r = bp._propose_sync(dict(_BRIEF), "public", steering=["지시1"])
        assert r["_steering_applied"] == ["지시1"]
        r2 = bp._propose_sync(dict(_BRIEF), "public")
        assert r2["_steering_applied"] == []


class TestSteeringNotRendered:

    def test_html_has_no_steering_text(self):
        from services.brief_proposal_report_generator import to_proposal_html
        proposal = {
            "executive_summary": "요약",
            "scoring_focus": [],
            "caveats": [],
            "_steering_applied": ["테마를흐름으로XYZ"],
        }
        html = to_proposal_html(proposal, "테스트 청사", "공공시설")
        assert "테마를흐름으로XYZ" not in html           # 내부 저장만 (사용자 결정)


# ═══════════════════════════════════════════════════════════════════════════════
# 라우터 계층 — _steering_log 누적/초기화/하위호환/상한
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    monkeypatch.setattr(settings, "_memory_api_key", "sk-test")
    (tmp_path / "_briefs").mkdir(parents=True, exist_ok=True)
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app), tmp_path


def _make_brief(db: Path, bid: str, extra: dict | None = None):
    data = {"_brief_meta": {"brief_id": bid, "facility_type": "public",
                            "brief_name": "테스트"}}
    data.update(extra or {})
    (db / "_briefs" / f"{bid}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _mock_propose(monkeypatch, calls):
    async def fake(brief_data, facility_type, steering=None):
        calls.append(list(steering or []))
        return {"executive_summary": "요약", "scoring_focus": [], "caveats": [],
                "data_confidence": "medium", "_steering_applied": list(steering or [])}
    import routers.brief as rb
    monkeypatch.setattr(rb, "propose_project", fake)


class TestProposeSteeringRouter:
    BID = "20260729_000000_public_테스트"

    def _log(self, db):
        d = json.loads((db / "_briefs" / f"{self.BID}.json").read_text(encoding="utf-8"))
        return [e["instruction"] for e in d.get("_steering_log", [])]

    def test_empty_body_backward_compat(self, client, monkeypatch):
        c, db = client
        _make_brief(db, self.BID)
        calls = []
        _mock_propose(monkeypatch, calls)
        r = c.post(f"/api/brief/{self.BID}/propose")     # body 없음 — 기존 호출
        assert r.status_code == 200
        assert r.json()["steering_count"] == 0
        assert calls[0] == []
        assert self._log(db) == []

    def test_steering_accumulates(self, client, monkeypatch):
        c, db = client
        _make_brief(db, self.BID)
        calls = []
        _mock_propose(monkeypatch, calls)
        c.post(f"/api/brief/{self.BID}/propose", json={"steering": "지시1"})
        r = c.post(f"/api/brief/{self.BID}/propose", json={"steering": "지시2"})
        assert r.json()["steering_count"] == 2
        assert r.json()["steering_log"] == ["지시1", "지시2"]
        assert calls[1] == ["지시1", "지시2"]            # 누적 전체가 LLM 에 전달
        assert self._log(db) == ["지시1", "지시2"]

    def test_reset_clears_and_regenerates(self, client, monkeypatch):
        c, db = client
        _make_brief(db, self.BID)
        calls = []
        _mock_propose(monkeypatch, calls)
        c.post(f"/api/brief/{self.BID}/propose", json={"steering": "지시1"})
        r = c.post(f"/api/brief/{self.BID}/propose", json={"reset_steering": True})
        assert r.status_code == 200
        assert r.json()["steering_count"] == 0
        assert calls[1] == []                            # clean 재생성
        assert self._log(db) == []

    def test_log_not_persisted_on_llm_failure(self, client, monkeypatch):
        c, db = client
        _make_brief(db, self.BID)

        async def boom(brief_data, facility_type, steering=None):
            raise RuntimeError("llm down")
        import routers.brief as rb
        monkeypatch.setattr(rb, "propose_project", boom)
        r = c.post(f"/api/brief/{self.BID}/propose", json={"steering": "지시1"})
        assert r.status_code == 500
        assert self._log(db) == []                       # 실패 시 로그 미persist

    def test_length_and_count_limits(self, client, monkeypatch):
        c, db = client
        log = [{"instruction": f"지시{i}", "generated_at": "t"} for i in range(20)]
        _make_brief(db, self.BID, {"_steering_log": log})
        calls = []
        _mock_propose(monkeypatch, calls)
        r = c.post(f"/api/brief/{self.BID}/propose", json={"steering": "x" * 501})
        assert r.status_code == 400                      # 지시당 500자
        r = c.post(f"/api/brief/{self.BID}/propose", json={"steering": "넘침"})
        assert r.status_code == 400                      # 누적 20개 상한
        r = c.post(f"/api/brief/{self.BID}/propose",
                   json={"steering": "다시", "reset_steering": True})
        assert r.status_code == 200                      # 초기화 동반이면 통과

    def test_list_briefs_exposes_log(self, client, monkeypatch):
        c, db = client
        _make_brief(db, self.BID,
                    {"_steering_log": [{"instruction": "지시A", "generated_at": "t"}]})
        r = c.get("/api/brief/list")
        assert r.status_code == 200
        item = next(x for x in r.json() if x["brief_id"] == self.BID)
        assert item["steering_log"] == ["지시A"]
