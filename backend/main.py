import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    bundle = getattr(sys, "_MEIPASS", None)
    candidates = []
    if bundle:
        candidates.append(Path(bundle) / "README.html")
    candidates.extend([
        Path(__file__).parent.parent.parent / "README.html",
        Path(__file__).parent.parent.parent / "docs" / "README.html",
    ])
    for p in candidates:
        if p.exists():
            return FileResponse(p, media_type="text/html")
    raise HTTPException(404, "README.html not found")


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
