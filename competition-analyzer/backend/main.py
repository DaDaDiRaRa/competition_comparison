from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import accumulate, diagnose, settings, patterns
from services.db_manager import init_db

app = FastAPI(title="Competition Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
