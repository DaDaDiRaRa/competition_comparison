from fastapi import APIRouter, HTTPException

from config import FACILITY_TYPES
from services.db_manager import load_pattern, all_patterns
from services.pattern_builder import build_pattern

router = APIRouter()


@router.get("")
def list_patterns():
    return all_patterns()


@router.get("/{facility_type}")
def get_pattern(facility_type: str):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    pattern = load_pattern(facility_type)
    if not pattern:
        return {"facility_type": facility_type, "win_count": 0, "patterns": {}}
    return pattern


@router.post("/rebuild/{facility_type}")
def rebuild_pattern(facility_type: str):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    pattern = build_pattern(facility_type)
    return {"ok": True, "pattern": pattern}


@router.post("/rebuild-all")
def rebuild_all_patterns():
    results = {}
    for ft in FACILITY_TYPES:
        results[ft] = build_pattern(ft)
    return {"ok": True, "results": results}
