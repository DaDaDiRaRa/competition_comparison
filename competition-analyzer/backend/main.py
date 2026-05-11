from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routers import accumulate, diagnose, settings, patterns
from services.db_manager import init_db
from version import __version__

app = FastAPI(title="Competition Analyzer API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accumulate.router, prefix="/api/accumulate", tags=["accumulate"])
app.include_router(diagnose.router, prefix="/api/diagnose", tags=["diagnose"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    return {"version": __version__}


# ---------------- 정적 프론트엔드 서빙 ----------------
def _resolve_frontend_dist() -> Path | None:
    """개발 모드에서 frontend/dist 위치 탐색."""
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
        target = _FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_FRONTEND_DIST / "index.html")
