"""`POST /api/brief/{id}/deck` 라우터 회귀 — 네트워크 0 (터읽기 호출은 monkeypatch).

두 가지를 잠근다:
  ① **헤더 latin-1 함정** — brief_id 는 한글을 보존한다(`_slugify`). PPTX 첨부 이름을
     그대로 헤더에 넣으면 ASGI 인코딩에서 500 (`test_brief_export_serving.py` 와 같은 병).
  ② **경계** — 우리가 터읽기에 넘기는 `filename` 은 ASCII 여야 한다. 그쪽 `/deck/render`
     는 받은 값을 그대로 `Content-Disposition` 에 박으므로 한글을 보내면 그 앱이 500 을 낸다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings

PPTX_MAGIC = b"PK\x03\x04"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    (tmp_path / "_briefs").mkdir(parents=True, exist_ok=True)
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app), tmp_path


@pytest.fixture
def sent(monkeypatch):
    """터읽기 대신 payload 를 붙잡아 두고 가짜 PPTX 를 돌려준다."""
    box = {}

    async def fake_render(payload, timeout=60.0):
        box["payload"] = payload
        return PPTX_MAGIC + b"fake-pptx-body"

    import services.teoilgi_client as tc
    monkeypatch.setattr(tc, "render_deck", fake_render)
    return box


def _brief(db: Path, brief_id: str, *, proposal=True):
    data = {
        "_brief_meta": {"facility_type": "public", "brief_name": "영등포구청 신청사"},
        "feasibility_export": {"sites": [{"site_area_sqm": 12345.0}]},
    }
    if proposal:
        data["_proposal"] = {
            "executive_summary": "발주처가 원하는 것은 열린 청사다.",
            "scoring_focus": [{"category": "배치계획", "points": 40, "weight_pct": 40, "rank": 1}],
            "risks": [{"risk": "실격", "severity": "high", "mitigation": "확인", "basis": "p.3"}],
            "priorities": [{"rank": 1, "focus": "배치", "why": "배점 40"}],
            "caveats": ["보장 없음"],
        }
    (db / "_briefs" / f"{brief_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestDeckRoute:
    def test_korean_brief_id_returns_pptx(self, client, sent):
        c, db = client
        bid = "20260827_public_영등포구청사"
        _brief(db, bid)
        r = c.post(f"/api/brief/{bid}/deck")
        assert r.status_code == 200, r.text
        assert r.content.startswith(PPTX_MAGIC)
        assert r.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.presentationml")

    def test_content_disposition_is_latin1_safe(self, client, sent):
        """헤더가 latin-1 로 인코딩돼야 500 이 안 난다."""
        c, db = client
        bid = "20260827_public_한글지침서"
        _brief(db, bid)
        r = c.post(f"/api/brief/{bid}/deck")
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        cd.encode("latin-1")                       # 여기서 터지면 실서버는 500
        assert "filename*=UTF-8''" in cd           # 한글 이름은 RFC 6266 로 살아 있다

    def test_filename_sent_to_sibling_is_ascii(self, client, sent):
        """터읽기가 헤더에 그대로 박는다 — 한글을 보내면 **그쪽이** 500 을 낸다."""
        c, db = client
        _brief(db, "20260827_public_한글지침서")
        c.post("/api/brief/20260827_public_한글지침서/deck")
        sent["payload"]["filename"].encode("ascii")
        assert sent["payload"]["filename"].endswith(".pptx")

    def test_payload_is_the_contract(self, client, sent):
        c, db = client
        _brief(db, "b1")
        c.post("/api/brief/b1/deck")
        p = sent["payload"]
        assert p["schema_version"] == "deck_render/1.0"
        assert {s["kind"] for s in p["slides"]} <= {"cover", "kpi", "cards", "table", "text"}

    def test_headers_report_slides_and_missing(self, client, sent):
        c, db = client
        _brief(db, "b1")
        r = c.post("/api/brief/b1/deck")
        assert int(r.headers["X-Deck-Slides"]) == len(sent["payload"]["slides"])
        assert int(r.headers["X-Deck-Missing"]) == len(sent["payload"]["missing"])

    def test_missing_proposal_is_400_not_500(self, client, sent):
        c, db = client
        _brief(db, "b1", proposal=False)
        r = c.post("/api/brief/b1/deck")
        assert r.status_code == 400
        assert "제안서" in r.json()["detail"]

    def test_unknown_brief_is_404(self, client, sent):
        c, _ = client
        assert c.post("/api/brief/nope/deck").status_code == 404

    def test_path_traversal_is_refused(self, client, sent):
        c, db = client
        _brief(db, "b1")
        # 경로 조작은 라우터가 거부하거나 라우팅이 안 맞아야 한다 — 절대 200 이 아니다.
        assert c.post("/api/brief/..%2F..%2Fetc/deck").status_code != 200

    def test_sibling_failure_is_502_with_reason(self, client, monkeypatch):
        """형제앱이 죽으면 이유를 들고 502 — 조용한 빈 파일보다 낫다."""
        c, db = client
        _brief(db, "b1")

        async def boom(payload, timeout=60.0):
            raise RuntimeError("터읽기 장표 서버에 연결하지 못했습니다: ConnectError")

        import services.teoilgi_client as tc
        monkeypatch.setattr(tc, "render_deck", boom)
        r = c.post("/api/brief/b1/deck")
        assert r.status_code == 502
        assert "터읽기" in r.json()["detail"]
