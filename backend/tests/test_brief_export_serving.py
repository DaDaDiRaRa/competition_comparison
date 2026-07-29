"""지침서 export 서빙 회귀 테스트 — 한글 파일명 HTML 인라인 500 버그.

_slugify 가 한글(가-힣)을 보존하므로 brief_id·파일명에 한글이 들어간다. HTML 인라인
서빙이 Content-Disposition 헤더에 한글을 그대로 넣으면 ASGI 헤더 latin-1 인코딩에서
UnicodeEncodeError → 500. RFC 6266(ascii fallback + filename*=UTF-8'') 로 고친 것을 잠근다.
(버킷 직접 접근은 되는데 '리포트 열기/제안서 열기'만 500 나던 증상.)
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


def _write(db: Path, name: str, body: str = "<html>본문</html>"):
    (db / "_briefs" / name).write_text(body, encoding="utf-8")


class TestKoreanFilenameHtmlServing:
    def test_korean_html_report_serves_200(self, client):
        c, db = client
        fn = "20260714_public_종로구청사.html"
        _write(db, fn)
        r = c.get(f"/api/brief/exports/{fn}")
        assert r.status_code == 200
        assert "본문" in r.text

    def test_content_disposition_is_latin1_safe(self, client):
        # ASGI 는 헤더를 latin-1 로 인코딩 — 이 인코딩이 통과해야 500 이 안 난다.
        c, db = client
        fn = "20260714_public_한글제안서_proposal.html"
        _write(db, fn)
        r = c.get(f"/api/brief/exports/{fn}")
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        cd.encode("latin-1")  # UnicodeEncodeError 나면 실패
        assert cd.startswith("inline;")
        assert "filename*=UTF-8''" in cd  # RFC 6266 확장 파라미터 존재

    def test_ascii_html_still_works(self, client):
        c, db = client
        fn = "20260714_public.html"
        _write(db, fn)
        r = c.get(f"/api/brief/exports/{fn}")
        assert r.status_code == 200

    def test_missing_file_404_not_500(self, client):
        c, _ = client
        r = c.get("/api/brief/exports/없는파일_proposal.html")
        assert r.status_code == 404

    def test_download_flag_serves_attachment(self, client):
        # ?download=1 이면 인라인이 아니라 첨부(다운로드)로 내려와야 한다. 한글 파일명도 latin-1 안전.
        c, db = client
        fn = "20260714_public_한글제안서_proposal.html"
        _write(db, fn)
        r = c.get(f"/api/brief/exports/{fn}?download=1")
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        cd.encode("latin-1")  # UnicodeEncodeError 나면 실패
        assert cd.startswith("attachment;")
        assert "filename*=UTF-8''" in cd

    def test_default_is_inline(self, client):
        c, db = client
        fn = "20260714_public.html"
        _write(db, fn)
        r = c.get(f"/api/brief/exports/{fn}")
        assert r.headers["content-disposition"].startswith("inline;")
