import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Windows 콘솔/파이프(cp949)에서 유니코드 print(em-dash·한글 외 기호)가 startup 을
# 죽이지 않도록 표준 스트림을 UTF-8 로 강제. lifespan 의 경고 print 가
# UnicodeEncodeError 로 graceful degradation 을 무력화하고 앱 기동을 막던 회귀 방지.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from mcp_server.server import mcp as _mcp

from config import set_request_api_key
from routers import accumulate, diagnose, settings, patterns, upload, archive, brief
from services.archive_search import build_index as build_archive_index
from services.db_manager import init_db
from version import __version__


async def _bind_request_api_key(x_anthropic_api_key: str | None = Header(default=None)):
    """요청 헤더(X-Anthropic-Api-Key)의 사용자별 키를 요청 컨텍스트에 바인딩 (per-browser).

    모든 LLM 호출은 settings.api_key 를 읽고, 그 property 가 이 요청 컨텍스트 키를
    최우선 사용한다. 헤더가 없으면 빈 값 → 세션 메모리/환경변수로 폴백 (로컬 dev·tools).
    전역 의존성이라 모든 엔드포인트(SSE 스트리밍 포함)에 적용된다.
    """
    set_request_api_key(x_anthropic_api_key)


# --- MCP (/mcp) ---------------------------------------------------------------
# kunwon-ops docs/plan-mcp-gateway.md §9 의 검증된 패턴 그대로: lifespan 결합 ·
# Bearer 토큰 미들웨어 · Starlette Mount 대신 raw ASGI 프리픽스 래퍼.
_mcp_asgi_app = _mcp.streamable_http_app()

#: `/mcp` 전용 공유키. **없으면 항상 401**(fail closed) — 우리 DB 는 공모 자료라
#: 실수로 열리면 안 된다. 도구 자체는 읽기 전용·LLM 0 이라 과금 위험은 없다.
_MCP_SHARED_KEY = os.environ.get("COMPETITION_MCP_KEY")


class _McpAuthMiddleware:
    """Bearer 토큰이 COMPETITION_MCP_KEY 와 일치해야 통과."""

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        token = headers.get(b"authorization", b"").decode("latin-1")
        expected = f"Bearer {_MCP_SHARED_KEY}" if _MCP_SHARED_KEY else None
        # compare_digest — 비교 시간이 일치 길이에 따라 달라지지 않도록
        if not expected or not hmac.compare_digest(token, expected):
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
        await self._app(scope, receive, send)


class _McpMount:
    """`/mcp` 와 `/mcp/*` 를 FastMCP 로 보낸다.

    Starlette `Mount` 는 트레일링 슬래시 없는 `/mcp` 자체를 못 잡아 캐치올(정적 파일 `/`)로
    새는 문제가 있다(형제앱 arch-site-model 실측, plan-mcp-gateway §9). 그래서 라우팅
    이전 단계인 순수 ASGI 래퍼에서 프리픽스를 직접 잘라 우회한다.
    """

    def __init__(self, inner_app, mcp_app, prefix="/mcp"):
        self._app = inner_app
        self._mcp_app = mcp_app
        self._prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            if path == self._prefix or path.startswith(self._prefix + "/"):
                sub_scope = dict(scope)
                sub_scope["path"] = path[len(self._prefix):] or "/"
                await self._mcp_app(sub_scope, receive, send)
                return
        await self._app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        print(f"[WARNING] DB 초기화 실패 ({e}) — 설정 탭에서 DB 경로를 확인하세요.")
    try:
        n = build_archive_index()
        print(f"[INFO] 아카이브 인덱싱 완료 — {n}개 공모")
    except Exception as e:
        print(f"[WARNING] 아카이브 인덱싱 실패 ({e}) — /api/archive 검색 결과가 비어있을 수 있습니다.")
    if not _MCP_SHARED_KEY:
        print("[INFO] COMPETITION_MCP_KEY 미설정 — /mcp 는 항상 401 입니다(fail closed).")
    # MCP 세션 매니저를 앱 lifespan 에 결합 (§9)
    async with _mcp.session_manager.run():
        yield


app = FastAPI(
    title="Competition Analyzer API", version=__version__, lifespan=lifespan,
    dependencies=[Depends(_bind_request_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accumulate.router, prefix="/api/accumulate", tags=["accumulate"])
app.include_router(diagnose.router, prefix="/api/diagnose", tags=["diagnose"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(archive.router, prefix="/api/archive", tags=["archive"])
app.include_router(brief.router, prefix="/api/brief", tags=["brief"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/readme")
def readme():
    """사용자 매뉴얼: README.md(단일 소스)를 HTML로 런타임 렌더링해 서빙.

    별도 README.html 을 유지하지 않으므로 콘텐츠 드리프트가 없다. 경로는
    PyInstaller 번들 → Docker 이미지(/app/backend) → 로컬 dev(리포 루트) 순.
    """
    from services.readme_renderer import render_readme_html

    bundle = getattr(sys, "_MEIPASS", None)
    candidates = []
    if bundle:
        candidates.append(Path(bundle) / "README.md")
    candidates.extend([
        Path(__file__).parent / "README.md",        # Docker 이미지: /app/backend/README.md
        Path(__file__).parent.parent / "README.md",  # 로컬 dev: 리포 루트
    ])
    md_path = next((p for p in candidates if p.exists()), None)
    if md_path is None:
        raise HTTPException(404, "README.md not found")
    return HTMLResponse(render_readme_html(md_path.read_text(encoding="utf-8")))


@app.get("/api/version")
def version():
    return {"version": __version__}


# ---------------- 정적 프론트엔드 서빙 ----------------
def _resolve_frontend_dist() -> Path | None:
    """개발 모드 + PyInstaller 번들 모드 모두 대응."""
    import sys
    # PyInstaller --onedir/--onefile 번들: sys._MEIPASS에 리소스 추출됨
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidate = Path(bundle) / "frontend_dist"
        if candidate.exists():
            return candidate
    # 개발 모드
    dev = Path(__file__).parent.parent / "frontend" / "dist"
    if dev.exists():
        return dev
    return None


_FRONTEND_DIST = _resolve_frontend_dist()
if _FRONTEND_DIST is not None:
    # SPA: 정적 자산 서빙 + 그 외 경로는 index.html로 폴백
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def _root():
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def _spa_fallback(full_path: str):
        # API 경로는 위에서 매칭되므로 여기로 안 옴
        target = (_FRONTEND_DIST / full_path).resolve()
        # 경로 탐색 방지: dist 하위가 아니면 index.html로 폴백
        if target.is_file() and str(target).startswith(str(_FRONTEND_DIST.resolve())):
            return FileResponse(target)
        return FileResponse(_FRONTEND_DIST / "index.html")

# --- MCP 마운트 (맨 마지막) ----------------------------------------------------
# 정적 SPA 캐치올(`/{full_path:path}`)이 등록된 **뒤**에 감싼다. 이 래퍼가 라우팅보다
# 먼저 `/mcp` 를 가로채므로 캐치올로 새지 않는다. FastAPI 인스턴스(`_fastapi_app`)는
# lifespan 을 위해 그대로 두고, ASGI 진입점만 래퍼로 바꾼다.
_fastapi_app = app
app = _McpMount(_fastapi_app, _McpAuthMiddleware(_mcp_asgi_app))
