from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from config import settings, FACILITY_TYPES
from services.db_manager import init_db

router = APIRouter()


class SettingsUpdateRequest(BaseModel):
    db_path: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    raster_dpi_classify: Optional[int] = None
    raster_dpi_extract: Optional[int] = None
    model_id: Optional[str] = None
    provider: Optional[str] = None  # "api" or "sdk"


@router.get("")
def get_settings():
    return settings.to_dict()


@router.put("")
def update_settings(req: SettingsUpdateRequest):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    settings.update(update)
    if "db_path" in update:
        init_db()
    return {"ok": True, "settings": settings.to_dict()}


@router.get("/facility-types")
def get_facility_types():
    return FACILITY_TYPES


@router.post("/init-db")
def initialize_db():
    init_db()
    return {"ok": True, "db_path": str(settings.db_path)}
