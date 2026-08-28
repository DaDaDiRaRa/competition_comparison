"""앱이 **뜨는지** — import 와 라우트 등록을 명시적으로 못박는다.

계기(2026-08-28): 형제앱 arch-law-diagnose 가 **테스트 340건 전부 초록인데 앱이 아예
안 뜨는** 상태를 라이브 e2e 에서야 발견했다. `main` 을 import 하는 테스트가 하나도
없었기 때문이다. 원인은 의존성 충돌이었다 — `fastapi==0.115.5`(starlette<0.42) 와
`mcp>=1.2` 가 한 venv 에 있는데 최신 `mcp` 가 `sse-starlette>=1.6.1` → `starlette>=0.49.1`
을 끌고 와 import 가 죽었다.

우리는 지금 `mcp` 를 안 쓰고 `pip check` 도 깨끗하다. 그래도 이 파일을 두는 이유:

  · 지금의 boot 보장이 **우연**이다 — `main` 을 import 하는 테스트가 6개 있지만
    전부 다른 것을 보러 온 김에 import 할 뿐이라, 그것들이 지워지면 보장도 같이 사라진다.
  · **C-1(MCP provider 전환)이 로드맵에 있다.** 그때 `mcp` 를 넣으면 저쪽이 밟은
    그 함정이 그대로 우리 것이 된다. `kunwon-ops/docs/plan-mcp-gateway.md §9` 도
    「백엔드 venv 에 mcp 를 넣으면 starlette 가 올라가 fastapi 핀이 깨지므로
    **서비스 분리 필수**」라고 적어 뒀다 — 그 실패가 여기서 먼저 보여야 한다.

느리지도 않다(import 한 번). 라우트까지 보는 이유는, import 는 되는데 라우터 등록이
누락되는 일이 실제로 있었기 때문이다(2026-08-27 `/deck` 배선 누락 — 모듈 테스트는
전부 통과했고 e2e 에서야 잡혔다).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_main_imports():
    """의존성 충돌·문법 오류로 앱이 죽으면 여기서 먼저 터진다."""
    from main import app
    assert app is not None


@pytest.mark.parametrize("path,method", [
    ("/api/brief/analyze", "POST"),
    ("/api/brief/list", "GET"),
    ("/api/brief/{brief_id}/propose", "POST"),
    ("/api/brief/{brief_id}/deck", "POST"),        # 2026-08-27 배선이 통째로 누락됐던 자리
    ("/api/brief/{brief_id}/playbook", "POST"),
    ("/api/accumulate/run", "POST"),
    ("/api/diagnose/run", "POST"),
    ("/api/settings/meta", "GET"),
    ("/api/upload/start", "POST"),
    ("/api/upload/chunk/{upload_id}", "POST"),
])
def test_core_routes_are_registered(path, method):
    """import 는 되는데 라우터 등록만 빠지는 일이 실제로 있었다."""
    # ⚠ `main.app` 은 **MCP 래퍼**(`_McpMount`)라 `.routes` 가 없다 — 라우트는 그 안의
    #   FastAPI 인스턴스가 들고 있다. uvicorn 진입점은 래퍼가 맞다(`/mcp` 가로채기).
    from main import _fastapi_app
    routes = {(r.path, m) for r in _fastapi_app.routes
              for m in getattr(r, "methods", ()) or ()}
    assert (path, method) in routes, f"{method} {path} 가 등록돼 있지 않다"


def test_no_broken_dependencies():
    """`pip check` 상당 — 설치된 패키지들의 요구사항이 서로 맞는가.

    C-1(MCP provider)에서 `mcp` 를 같은 venv 에 넣었다. arch-law-diagnose 는 이걸로 앱이
    안 떴지만(`fastapi==0.115.5` → `starlette<0.42`) 우리 fastapi 는 0.136 대라
    `sse-starlette` 가 요구하는 `starlette>=0.49` 를 이미 만족한다. **이 테스트가 그
    조건을 계속 지킨다** — fastapi 를 내려 핀하거나 mcp 를 올리면 여기서 먼저 터진다.
    """
    from importlib.metadata import distributions

    from packaging.requirements import Requirement
    from packaging.version import InvalidVersion, Version

    installed = {}
    for d in distributions():
        name = (d.metadata["Name"] or "").lower().replace("_", "-")
        if name:
            installed[name] = d.version

    broken = []
    for d in distributions():
        owner = d.metadata["Name"] or "?"
        for raw in (d.requires or []):
            try:
                req = Requirement(raw)
            except Exception:                      # noqa: BLE001 — 파싱 불가는 판단 보류
                continue
            if req.marker is not None and not req.marker.evaluate():
                continue                            # extra/환경 조건부 의존은 제외
            have = installed.get(req.name.lower().replace("_", "-"))
            if have is None or not req.specifier:
                continue                            # 미설치 optional 은 pip check 도 안 잡는다
            try:
                if not req.specifier.contains(Version(have), prereleases=True):
                    broken.append(f"{owner} 는 {raw} 를 요구하는데 설치된 것은 {have}")
            except InvalidVersion:
                continue
    assert not broken, "의존성 충돌:\n  " + "\n  ".join(broken)


# ── MCP 표면 (C-1) ──────────────────────────────────────────────────────────


def test_mcp_is_mounted_ahead_of_the_spa_catchall():
    """Starlette Mount 는 트레일링 슬래시 없는 `/mcp` 를 캐치올(정적 `/`)로 흘린다
    (형제앱 실측). 라우팅 이전 단계의 ASGI 래퍼여야 한다."""
    import main
    assert type(main.app).__name__ == "_McpMount"
    assert main._fastapi_app is not main.app


@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/anything"])
def test_mcp_requires_auth(path, monkeypatch):
    """키가 없으면 **항상 401**(fail closed) — 우리 DB 는 공모 자료다."""
    from fastapi.testclient import TestClient

    import main
    monkeypatch.setattr(main, "_MCP_SHARED_KEY", None)
    app = main._McpMount(main._fastapi_app, main._McpAuthMiddleware(main._mcp_asgi_app))
    r = TestClient(app).post(path, json={})
    assert r.status_code == 401, f"{path} 가 인증 없이 통과했다"


def test_wrong_token_is_rejected(monkeypatch):
    from fastapi.testclient import TestClient

    import main
    monkeypatch.setattr(main, "_MCP_SHARED_KEY", "right-key")
    app = main._McpMount(main._fastapi_app, main._McpAuthMiddleware(main._mcp_asgi_app))
    c = TestClient(app)
    assert c.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/mcp", json={}, headers={"Authorization": "right-key"}).status_code == 401


def test_rest_api_still_works_through_the_wrapper():
    """회귀 — `/mcp` 가로채기가 나머지 REST 를 막으면 안 된다."""
    from fastapi.testclient import TestClient

    from main import app
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


def test_mcp_tools_are_read_only():
    """쓰기 도구를 열면 안 된다 — 분석·제안서 생성은 과금·장시간 작업이라 REST 전용."""
    import asyncio

    from mcp_server.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"search_competitions", "list_briefs", "get_brief", "get_facility_pattern"}


# ── MCP 도구 동작 (읽기 전용 · 네트워크 0) ──────────────────────────────────


@pytest.fixture
def mcp_db(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    (tmp_path / "_briefs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _tool_json(raw):
    import json
    return json.loads(raw)


def test_get_brief_returns_summary_not_the_whole_file(mcp_db):
    """`_brief.json` 은 1MB 가 넘는다 — 통째로 올리면 컨텍스트가 손해다."""
    import json

    from mcp_server.server import get_brief
    (mcp_db / "_briefs" / "b1.json").write_text(json.dumps({
        "_brief_meta": {"facility_type": "public", "brief_name": "테스트 청사"},
        "_quantitative": {"site_area_sqm": 10438.0},
        "feasibility_export": {"schema_version": 2, "sites": [{"site_id": "부지1"}]},
        "brief_program": [{"huge": "x" * 5000}],          # 요약에 안 실려야 한다
        "_contradictions": [{"label": "총 대지면적", "spread_ratio": 5.38, "sources": []}],
    }, ensure_ascii=False), encoding="utf-8")
    out = _tool_json(get_brief("b1"))
    assert out["brief_name"] == "테스트 청사"
    assert out["_contradictions"], "경고는 있으면 실어야 한다"
    assert "brief_program" not in out, "본문 블록이 요약에 샜다"


def test_get_brief_rejects_path_traversal(mcp_db):
    from mcp_server.server import get_brief
    assert _tool_json(get_brief("../../etc/passwd"))["error"] == "BAD_ID"
    assert _tool_json(get_brief("nope"))["error"] == "NOT_FOUND"


def test_clean_brief_has_no_empty_warning_keys(mcp_db):
    """빈 키가 늘면 읽는 쪽이 신호를 놓친다 — 경고는 있을 때만."""
    import json

    from mcp_server.server import get_brief
    (mcp_db / "_briefs" / "b2.json").write_text(
        json.dumps({"_brief_meta": {"facility_type": "public"}}), encoding="utf-8")
    out = _tool_json(get_brief("b2"))
    assert "_contradictions" not in out and "_merge_conflicts" not in out


def test_unknown_facility_type_lists_the_valid_ones(mcp_db):
    from mcp_server.server import get_facility_pattern
    out = _tool_json(get_facility_pattern("존재하지않는유형"))
    assert out["error"] == "UNKNOWN_TYPE" and "public" in out["message"]


def test_empty_inputs_are_honest_errors(mcp_db):
    from mcp_server.server import get_facility_pattern, search_competitions
    assert _tool_json(search_competitions(""))["error"] == "EMPTY_QUERY"
    assert _tool_json(get_facility_pattern("  "))["error"] == "EMPTY_TYPE"


def test_limits_are_clamped(mcp_db):
    """MCP 응답은 컨텍스트에 그대로 실린다 — 크게 열면 손해다."""
    from mcp_server.server import MAX_LIMIT, _clamp
    assert _clamp(9999, 10) == MAX_LIMIT
    assert _clamp(0, 10) == 1
    assert _clamp("x", 10) == 10 and _clamp(None, 10) == 10
