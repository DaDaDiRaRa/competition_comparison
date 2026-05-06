import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from config import settings, FACILITY_TYPES
from services.db_manager import load_pattern
from services.pdf_rasterizer import rasterize_pdf
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_page, merge_extracted_data
from services.comparator import diagnose_submission
from services.utils import sse

router = APIRouter()


@router.post("/run")
async def run_diagnosis(
    facility_type: str = Form(...),
    competition_name: str = Form(""),
    brief_pdf: UploadFile = File(...),
    submission_pdf: UploadFile = File(...),
):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

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
            brief_path.write_bytes(await brief_pdf.read())

            brief_imgs, _ = rasterize_pdf(brief_path, settings.dpi_classify, tmp_root / "brief_cls")
            total_brief = len(brief_imgs)
            brief_cls = await classify_all_pages(brief_imgs)
            for c in brief_cls:
                yield sse({"type": "progress", "step": "classify_brief",
                           "page": c["page"], "total": total_brief, "page_type": c["primary_type"]})

            brief_exts = []
            for i, (img, c) in enumerate(zip(brief_imgs, brief_cls)):
                ext = await extract_page(img, c["primary_type"])
                brief_exts.append(ext)
                yield sse({"type": "progress", "step": "extract_brief", "page": i + 1, "total": total_brief})

            brief_data = merge_extracted_data(brief_cls, brief_exts)
            brief_data["page_map"] = brief_cls
            brief_data["total_pages"] = total_brief
            yield sse({"type": "done", "step": "brief", "total_pages": total_brief})

            # --- SUBMISSION ---
            yield sse({"type": "stage", "stage": "submission", "msg": "자사 제안서 분석 중"})
            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(await submission_pdf.read())

            # Classify at low DPI (parallel)
            cls_imgs, _ = rasterize_pdf(sub_path, settings.dpi_classify, tmp_root / "sub_cls")
            total_sub = len(cls_imgs)
            sub_cls = await classify_all_pages(cls_imgs)
            for c in sub_cls:
                yield sse({"type": "progress", "step": "classify_sub",
                           "page": c["page"], "total": total_sub, "page_type": c["primary_type"]})

            # Extract at high DPI
            ext_imgs, _ = rasterize_pdf(sub_path, settings.dpi_extract, tmp_root / "sub_ext")
            sub_exts = []
            for i, (img, c) in enumerate(zip(ext_imgs, sub_cls)):
                ext = await extract_page(img, c["primary_type"])
                sub_exts.append(ext)
                yield sse({"type": "progress", "step": "extract_sub", "page": i + 1, "total": total_sub})

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
            yield sse({"type": "error", "message": str(e)})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
