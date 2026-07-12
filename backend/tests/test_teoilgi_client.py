"""터읽기(arch-site-context) 연동 클라이언트 테스트 — 네트워크 없이 결정적.

시설유형→용도 매핑, /board 호출 graceful(실패·비200→None), 다이제스트가 실측만 담고
터읽기 ②AI판단·notes 는 제외하는지(경계) 검증.
"""

import asyncio
import json

import services.teoilgi_client as tc
from config import FACILITY_TYPES
from services.brief_proposal import _measured_digest


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        if self._exc:
            raise self._exc
        return self._resp


def test_use_type_mapping_all_valid():
    for ft in FACILITY_TYPES:
        assert tc.use_type_for(ft) in {"주거", "상업", "의료"}
    assert tc.use_type_for("medical") == "의료"
    assert tc.use_type_for("commercial") == "상업"
    assert tc.use_type_for("residential") == "주거"
    assert tc.use_type_for("__unknown__") == "주거"  # 안전 기본


def test_fetch_success(monkeypatch):
    payload = {"schema_version": "board_brief/1.0",
               "design_drivers": [{"rank": 1, "name": "방재·침수 대비"}]}
    monkeypatch.setattr(tc.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp=_Resp(200, payload)))
    out = asyncio.run(tc.fetch_board_context("서울 영등포구 여의대로 24", use_type="주거"))
    assert out and out["schema_version"] == "board_brief/1.0"


def test_fetch_graceful_on_exception(monkeypatch):
    monkeypatch.setattr(tc.httpx, "AsyncClient", lambda *a, **k: _FakeClient(exc=RuntimeError("down")))
    assert asyncio.run(tc.fetch_board_context("x")) is None


def test_fetch_graceful_on_non_200(monkeypatch):
    monkeypatch.setattr(tc.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp=_Resp(503, {})))
    assert asyncio.run(tc.fetch_board_context("x")) is None


def test_digest_keeps_measured_excludes_ai_judgment():
    d = _measured_digest({
        "region": "영등포구",
        "design_drivers": [{"rank": 1, "name": "방재·침수 대비", "response": "방수판", "strength": 5.0, "evidence": []}],
        "key_facts": [{"item": "1인가구비율", "index": 125, "index_band": "상회", "proximity": "시군구"}],
        "synthesis": {"judgment": "AI 의견 — 새면 안 됨"},  # ②는 경계상 제외돼야
        "notes": ["원시 노트"],
    })
    assert d["design_drivers"][0]["name"] == "방재·침수 대비"
    assert d["key_facts"][0]["index"] == 125
    assert "synthesis" not in d   # ②AI판단 미유출
    assert "notes" not in d       # 원시 노트 제외


def test_digest_none_on_non_dict():
    assert _measured_digest(None) is None
    assert _measured_digest("x") is None
