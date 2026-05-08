from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings, FACILITY_TYPES
from services.db_manager import init_db

router = APIRouter()


class SettingsUpdateRequest(BaseModel):
    raster_dpi_classify: Optional[int] = None
    raster_dpi_extract: Optional[int] = None
    model_id: Optional[str] = None
    model_id_classify: Optional[int] = None


class ApiKeyRequest(BaseModel):
    api_key: str


@router.get("")
def get_settings():
    return settings.to_dict()


@router.put("")
def update_settings(req: SettingsUpdateRequest):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    settings.update(update)
    return {"ok": True, "settings": settings.to_dict()}


@router.get("/api-key-status")
def api_key_status():
    """API 키 설정 여부만 반환 (키 자체는 절대 노출하지 않음)."""
    return {"has_key": settings.has_api_key()}


@router.post("/api-key")
def set_api_key(req: ApiKeyRequest):
    """API 키를 세션 메모리에 저장. 디스크에 쓰지 않음 (앱 종료 시 소멸)."""
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API 키가 비어 있습니다.")
    settings.set_api_key(key)
    return {"ok": True, "has_key": True}


@router.delete("/api-key")
def clear_api_key():
    settings.clear_api_key()
    return {"ok": True, "has_key": False}


@router.get("/facility-types")
def get_facility_types():
    return FACILITY_TYPES


@router.post("/init-db")
def initialize_db():
    init_db()
    return {"ok": True, "db_path": str(settings.db_path)}
