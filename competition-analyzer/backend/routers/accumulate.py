import json
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from config import settings, FACILITY_TYPES
from services.db_manager import (
    make_competition_id, save_project_meta, save_brief,
    save_submission, save_comparison, load_brief, load_project_meta,
    list_projects, list_submissions, save_report, get_report_path,
)
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_pdf, merge_extracted_data
from services.comparator import compare_submissions
from services.pattern_builder import build_pattern
from services.report_generator import generate_comparison_report
from services.utils import sse

router = APIRouter()


@router.get("/projects")
def get_projects(facility_type: str | None = None):
    return list_projects(facility_type)


@router.get("/projects/{facility_type}/{competition_id}")
def get_project(facility_type: str, competition_id: str):
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    return {"meta": meta, "brief": load_brief(facility_type, competition_id),
            "submissions": list_submissions(facility_type, competition_id)}


@router.post("/project")
async def create_project(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    year: int = Form(...),
    client: str = Form(...),
    location: str = Form(...),
):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    cid = make_competition_id(year, competition_name)
    save_project_meta(cid, facility_type, competition_name, year, client, location)
    return {"ok": True, "competition_id": cid}


@router.get("/projects/{facility_type}/{competition_id}/report")
def get_report(facility_type: str, competition_id: str):
    path = get_report_path(facility_type, competition_id)
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(path, media_type="text/html",
                        filename=f"{competition_id}_report.html")


@router.post("/run")
async def run_pipeline(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    year: int = Form(...),
    client: str = Form(...),
    location: str = Form(...),
    brief_pdf: bytes = File(...),
    submissions_json: str = Form(...),
    submission_pdfs: list[bytes] = File(...),
):
    """
    submissions_json: JSON array of {company, result} matching submission_pdfs order.
    Streams SSE progress events.
    """
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    try:
        sub_meta = json.loads(submissions_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "submissions_json must be valid JSON array")
    if len(sub_meta) != len(submission_pdfs):
        raise HTTPException(400, "submissions_json length must match submission_pdfs count")

    brief_bytes = brief_pdf
    sub_bytes_list = list(submission_pdfs)

    async def event_stream():
        cid = make_competition_id(year, competition_name)
        save_project_meta(cid, facility_type, competition_name, year, client, location)
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_run_"))
        try:
            # --- BRIEF (classify + extract) ---
            yield sse({"type": "stage", "stage": "brief", "msg": "지침서 PDF 처리 중"})
            brief_path = tmp_root / "brief.pdf"
            brief_path.write_bytes(brief_bytes)

            yield sse({"type": "progress", "step": "classify_brief", "page": 0, "total": 1})
            brief_classifications = await classify_all_pages(brief_path)
            total_brief = len(brief_classifications)

            for cls in brief_classifications:
                yield sse({"type": "progress", "step": "classify_brief",
                           "page": cls["page"], "total": total_brief,
                           "page_type": cls["primary_type"]})

            yield sse({"type": "stage", "stage": "brief_extract", "msg": "지침서 데이터 추출 중"})
            brief_extractions = await extract_pdf(brief_path)
            yield sse({"type": "progress", "step": "extract_brief", "page": 1, "total": 1})

            brief_data = merge_extracted_data(brief_classifications, brief_extractions)
            brief_data["page_map"] = brief_classifications
            brief_data["total_pages"] = total_brief
            save_brief(facility_type, cid, brief_data)
            yield sse({"type": "done", "step": "brief", "total_pages": total_brief})

            # --- SUBMISSIONS ---
            processed_submissions = []
            for idx, (sub_bytes, meta) in enumerate(zip(sub_bytes_list, sub_meta)):
                company = meta.get("company", f"company_{idx+1}")
                result = meta.get("result", "lose")
                yield sse({"type": "stage", "stage": "submission",
                           "company": company, "result": result,
                           "msg": f"제안서 처리: {company}"})

                sub_dir = tmp_root / f"sub_{idx}"
                sub_dir.mkdir(exist_ok=True)
                sub_path = sub_dir / "submission.pdf"
                sub_path.write_bytes(sub_bytes)

                yield sse({"type": "progress", "step": "classify_sub",
                           "company": company, "page": 0, "total": 1})
                sub_classifications = await classify_all_pages(sub_path)
                total_sub = len(sub_classifications)

                for cls in sub_classifications:
                    yield sse({"type": "progress", "step": "classify_sub",
                               "company": company, "page": cls["page"], "total": total_sub,
                               "page_type": cls["primary_type"]})

                yield sse({"type": "progress", "step": "extract_sub",
                           "company": company, "page": 0, "total": 1})
                sub_extractions = await extract_pdf(sub_path)
                yield sse({"type": "progress", "step": "extract_sub",
                           "company": company, "page": 1, "total": 1})

                page_dist = {}
                for cls in sub_classifications:
                    pt = cls["primary_type"]
                    page_dist[pt] = page_dist.get(pt, 0) + 1

                sub_doc = {
                    "company": company,
                    "result": result,
                    "competition_id": cid,
                    "facility_type": facility_type,
                    "total_pages": total_sub,
                    "page_map": sub_classifications,
                    "page_distribution": page_dist,
                    "extracted_data": merge_extracted_data(sub_classifications, sub_extractions),
                }
                save_submission(facility_type, cid, company, result, sub_doc)
                processed_submissions.append(sub_doc)
                yield sse({"type": "done", "step": "submission", "company": company})

            # --- NODE 3: COMPARISON ---
            yield sse({"type": "stage", "stage": "compare", "msg": "비교분석 중"})
            comparison = await compare_submissions(brief_data, processed_submissions)
            comparison["competition_id"] = cid
            save_comparison(facility_type, cid, comparison)

            # --- REBUILD PATTERN ---
            yield sse({"type": "stage", "stage": "pattern", "msg": "당선 패턴 업데이트 중"})
            build_pattern(facility_type)

            # --- HTML REPORT ---
            yield sse({"type": "stage", "stage": "report", "msg": "HTML 비교 리포트 생성 중"})
            meta = {"competition_name": competition_name, "facility_type": facility_type,
                    "year": year, "client": client, "location": location}
            report_subs = [
                {"company": s["company"], "result": s["result"],
                 "total_pages": s["total_pages"]}
                for s in processed_submissions
            ]
            html = generate_comparison_report(meta, report_subs, comparison)
            save_report(facility_type, cid, html)
            yield sse({"type": "done", "step": "report"})

            yield sse({"type": "complete", "competition_id": cid,
                       "facility_type": facility_type,
                       "report_available": True,
                       "comparison": comparison,
                       "submissions": [
                           {"company": s["company"], "result": s["result"],
                            "total_pages": s["total_pages"],
                            "page_distribution": s["page_distribution"]}
                           for s in processed_submissions
                       ]})
        except Exception as e:
            yield sse({"type": "error", "message": str(e), "detail": traceback.format_exc()})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
