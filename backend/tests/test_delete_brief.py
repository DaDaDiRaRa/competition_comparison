"""지침서 분석 삭제 회귀 테스트.

DELETE /brief/{brief_id} 가 파생 파일 전부(json·md·xlsx·html·proposal·playbook·site)를
지우되, 다른 지침서(더 긴 slug — 구분자 경계)는 건드리지 않고 path traversal 을 막는지 잠근다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    (tmp_path / "_briefs").mkdir(parents=True, exist_ok=True)
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app), tmp_path


def _make_brief(db: Path, bid: str, exts=(".json", ".md", ".xlsx", ".html"),
                suffixes=("_proposal.html", "_playbook.html", "_site.jpg")):
    d = db / "_briefs"
    for e in exts:
        (d / f"{bid}{e}").write_text("x", encoding="utf-8")
    for sfx in suffixes:
        (d / f"{bid}{sfx}").write_text("x", encoding="utf-8")


class TestDeleteBrief:
    def test_removes_all_derived_files(self, client):
        c, db = client
        bid = "20260714_120000_public_종로청사"
        _make_brief(db, bid)
        r = c.delete(f"/api/brief/{bid}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        assert list((db / "_briefs").glob(f"{bid}*")) == []   # 전부 삭제

    def test_sibling_longer_slug_untouched(self, client):
        c, db = client
        _make_brief(db, "20260714_120000_public_a")
        _make_brief(db, "20260714_120000_public_ab")   # 더 긴 slug — 건드리면 안 됨
        c.delete("/api/brief/20260714_120000_public_a")
        # ab 는 그대로 (구분자 경계로 {id}. / {id}_ 만 매칭)
        assert (db / "_briefs" / "20260714_120000_public_ab.json").exists()

    def test_missing_404(self, client):
        c, _ = client
        r = c.delete("/api/brief/does_not_exist")
        assert r.status_code == 404

    def test_path_traversal_blocked(self, client):
        c, db = client
        _make_brief(db, "x")
        outside = db / "victim.txt"
        outside.write_text("keep", encoding="utf-8")
        # 슬래시가 든 id 는 라우팅/핸들러에서 거부(405/404/400) — 어느 쪽이든 삭제 안 됨
        r = c.delete("/api/brief/..%2F..%2Fvictim.txt")
        assert r.status_code in (400, 404, 405)
        assert outside.exists()                       # DB 밖 파일 무손상
        assert (db / "_briefs" / "x.json").exists()   # 무관 지침서 무손상
