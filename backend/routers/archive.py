from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import FACILITY_TYPES
from services.archive_search import get_index
from services.db_manager import load_comparison, load_project_meta

router = APIRouter()


def _filter_cards(
    cards: list[dict],
    facility_type: str | None = None,
    result_filter: str = "all",
) -> list[dict]:
    out = cards
    if facility_type:
        out = [c for c in out if c.get("facility_type") == facility_type]
    if result_filter and result_filter != "all":
        winners_key = "actual_winners"
        if result_filter == "win":
            out = [c for c in out if c.get("gap_analysis", {}).get(winners_key)]
        elif result_filter == "lose":
            # 당선자 없는 (혹은 알 수 없는) 공모 = 진단/검토용 자료
            out = [c for c in out if not c.get("gap_analysis", {}).get(winners_key)]
    return out


@router.get("/list")
def list_archive(facility_type: str | None = None):
    if facility_type and facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    index = get_index()
    cards = list(index._cards.values())
    cards = _filter_cards(cards, facility_type=facility_type)
    return {"items": cards, "total": len(cards)}


class SearchBody(BaseModel):
    query: str = ""
    facility_type: str | None = None
    result_filter: str = "all"  # "win" | "lose" | "all"


@router.post("/search")
def search_archive(body: SearchBody):
    if body.facility_type and body.facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {body.facility_type}")
    if body.result_filter not in ("all", "win", "lose"):
        raise HTTPException(400, f"Unknown result_filter: {body.result_filter}")

    index = get_index()
    q = (body.query or "").strip()

    # 2글자 이하: 전체 목록과 동일하게 반환
    if len(q) <= 2:
        cards = list(index._cards.values())
        cards = _filter_cards(cards, body.facility_type, body.result_filter)
        return {"items": cards, "total": len(cards), "query_interpreted": ""}

    # 3글자 이상: 자연어 검색
    cards = index.search_natural(q, limit=50)
    cards = _filter_cards(cards, body.facility_type, body.result_filter)
    return {"items": cards, "total": len(cards), "query_interpreted": q}


@router.get("/{facility_type}/{competition_id}")
def get_comparison(facility_type: str, competition_id: str):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    comp = load_comparison(facility_type, competition_id)
    meta = load_project_meta(facility_type, competition_id) or {}
    if not comp and not meta:
        raise HTTPException(404, f"Project not found: {facility_type}/{competition_id}")
    # 비교 결과(있으면) + 메타 병합. 키 충돌 시 comparison이 우선이되 meta는 별도 키로 노출.
    return {**(comp or {}), "meta": meta}
