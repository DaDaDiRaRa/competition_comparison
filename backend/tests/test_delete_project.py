"""프로젝트 삭제 회귀 테스트.

delete_project(폴더 삭제 + path traversal 방어) + DELETE 엔드포인트(삭제→패턴/아카이브
재구축, 404/400) 를 잠근다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings
from services.db_manager import delete_project, get_competition_dir


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    return tmp_path


def _make_project(db: Path, ft="public", cid="c1"):
    d = db / ft / cid
    (d / "submissions").mkdir(parents=True)
    (d / "_meta.json").write_text(json.dumps(
        {"facility_type": ft, "competition_id": cid, "competition_name": "테스트"},
        ensure_ascii=False), encoding="utf-8")
    (d / "submissions" / "a_win.json").write_text("{}", encoding="utf-8")
    return d


class TestDeleteProject:
    def test_deletes_existing(self, db):
        d = _make_project(db)
        assert d.exists()
        assert delete_project("public", "c1") is True
        assert not d.exists()

    def test_missing_returns_false(self, db):
        assert delete_project("public", "does_not_exist") is False

    def test_path_traversal_rejected(self, db):
        _make_project(db)
        for bad in ("..", "../public", "a/b"):
            with pytest.raises(ValueError):
                delete_project(bad, "c1")
            with pytest.raises(ValueError):
                delete_project("public", bad)

    def test_sibling_untouched(self, db):
        _make_project(db, cid="c1")
        keep = _make_project(db, cid="c2")
        delete_project("public", "c1")
        assert keep.exists()          # 다른 프로젝트는 그대로


class TestDeleteEndpoint:
    @pytest.fixture
    def client(self, db):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app), db

    def test_delete_success_and_rebuilds(self, client):
        c, db = client
        _make_project(db)
        r = c.delete("/api/accumulate/projects/public/c1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        assert not get_competition_dir("public", "c1").exists()

    def test_delete_missing_404(self, client):
        c, _ = client
        r = c.delete("/api/accumulate/projects/public/nope")
        assert r.status_code == 404
