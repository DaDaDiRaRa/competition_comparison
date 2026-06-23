from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings, FACILITY_TYPES, PAGE_TYPES_META, COMPARISON_AXES_BY_GROUP
from services.db_manager import init_db

router = APIRouter()


class SettingsUpdateRequest(BaseModel):
    raster_dpi_classify: Optional[int] = None
    raster_dpi_extract: Optional[int] = None
    model_id: Optional[str] = None
    model_id_classify: Optional[str] = None


class DbPathRequest(BaseModel):
    db_path: str


@router.get("")
def get_settings():
    return settings.to_dict()


@router.put("")
def update_settings(req: SettingsUpdateRequest):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    settings.update(update)
    return {"ok": True, "settings": settings.to_dict()}


@router.post("/db-path")
def set_db_path(req: DbPathRequest):
    path_str = req.db_path.strip()
    if not path_str:
        raise HTTPException(status_code=400, detail="DB 경로를 입력하세요.")
    try:
        from pathlib import Path
        path = Path(path_str)
        settings.set_db_path(str(path))
        init_db()
        return {"ok": True, "db_path": str(settings.db_path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"경로 설정 실패: {e}")


@router.get("/facility-types")
def get_facility_types():
    return {k: v["label_ko"] for k, v in FACILITY_TYPES.items()}


@router.get("/meta")
def get_meta():
    return {
        "facility_types": [
            {"key": k, "label_ko": v["label_ko"], "group": v["group"]}
            for k, v in FACILITY_TYPES.items()
        ],
        "page_types": PAGE_TYPES_META,
        "axes_by_group": {
            group: {
                k: {"label_ko": v["label_ko"], "icon": v.get("icon", "•")}
                for k, v in axes.items()
            }
            for group, axes in COMPARISON_AXES_BY_GROUP.items()
        },
    }


@router.post("/init-db")
def initialize_db():
    init_db()
    return {"ok": True, "db_path": str(settings.db_path)}
