import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from config import settings, FACILITY_TYPES
from services.db_manager import load_pattern
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_pdf, merge_extracted_data
from services.comparator import diagnose_submission
from services.utils import sse

router = APIRouter()


@router.post("/run")
async def run_diagnosis(
    facility_type: str = Form(...),
    competition_name: str = Form(""),
    brief_pdf: bytes = File(...),
    submission_pdf: bytes = File(...),
):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    brief_bytes = brief_pdf
    submission_bytes = submission_pdf

    async def event_stream():
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_diag_"))
        try:
            yield sse({"type": "stage", "stage": "load_patterns", "msg": f"DB 패턴 로드: {facility_type}"})
            patterns = load_pattern(facility_type)
            yield sse({"type": "info", "patterns_available": bool(patterns),
                       "win_count": patterns.get("win_count", 0)})

            # --- BRIEF ---
            yield sse({"type": "stage", "stage": "brief", "msg": "지침서 분석 중"})
            brief_path = tmp_root / "brief.pdf"
            brief_path.write_bytes(brief_bytes)

            yield sse({"type": "progress", "step": "classify_brief", "page": 0, "total": 1})
            brief_cls = await classify_all_pages(brief_path)
            total_brief = len(brief_cls)

            for c in brief_cls:
                yield sse({"type": "progress", "step": "classify_brief",
                           "page": c["page"], "total": total_brief, "page_type": c["primary_type"]})

            yield sse({"type": "progress", "step": "extract_brief", "page": 0, "total": 1})
            brief_exts = await extract_pdf(brief_path)
            yield sse({"type": "progress", "step": "extract_brief", "page": 1, "total": 1})

            brief_data = merge_extracted_data(brief_cls, brief_exts)
            brief_data["page_map"] = brief_cls
            brief_data["total_pages"] = total_brief
            yield sse({"type": "done", "step": "brief", "total_pages": total_brief})

            # --- SUBMISSION ---
            yield sse({"type": "stage", "stage": "submission", "msg": "자사 제안서 분석 중"})
            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(submission_bytes)

            yield sse({"type": "progress", "step": "classify_sub", "page": 0, "total": 1})
            sub_cls = await classify_all_pages(sub_path)
            total_sub = len(sub_cls)

            for c in sub_cls:
                yield sse({"type": "progress", "step": "classify_sub",
                           "page": c["page"], "total": total_sub, "page_type": c["primary_type"]})

            yield sse({"type": "progress", "step": "extract_sub", "page": 0, "total": 1})
            sub_exts = await extract_pdf(sub_path)
            yield sse({"type": "progress", "step": "extract_sub", "page": 1, "total": 1})

            page_dist = {}
            for c in sub_cls:
                pt = c["primary_type"]
                page_dist[pt] = page_dist.get(pt, 0) + 1

            sub_data = merge_extracted_data(sub_cls, sub_exts)
            sub_data["page_map"] = sub_cls
            sub_data["total_pages"] = total_sub
            sub_data["page_distribution"] = page_dist
            yield sse({"type": "done", "step": "submission", "total_pages": total_sub,
                       "page_distribution": page_dist})

            # --- DIAGNOSIS ---
            yield sse({"type": "stage", "stage": "diagnose", "msg": "AI 진단 분석 중"})
            diagnosis = await diagnose_submission(
                facility_type=facility_type,
                winning_patterns=patterns,
                brief_data=brief_data,
                submission_data=sub_data,
            )
            diagnosis.update({
                "facility_type": facility_type,
                "competition_name": competition_name,
                "total_pages": total_sub,
                "page_distribution": page_dist,
                "brief_total_pages": total_brief,
                "page_map": sub_cls,
            })
            yield sse({"type": "complete", "result": diagnosis})

        except Exception as e:
            yield sse({"type": "error", "message": str(e), "detail": traceback.format_exc()})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
