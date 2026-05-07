"""
accumulate.py — 데이터 축적 파이프라인 라우터

변경 이력:
  - extract_pdf(..., page_map=...)  : 분류 결과를 추출 단계에 전달
                                      → 타입별 최적 프롬프트 + AREA_TABLE 타일 분할 활성화
  - _timestamp                      : 모든 SSE 이벤트에 파이프라인 시작 시각 추가
                                      (CLAUDE.md 필수 규칙 — ProgressLog elapsed time 표시용)
"""

import json
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from config import settings, FACILITY_TYPES
from services.db_manager import (
    make_competition_id, save_project_meta, save_brief,
    save_submission, save_comparison, load_brief, load_project_meta,
    list_projects, list_submissions, save_report, get_report_path, load_pattern,
)
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_pdf, merge_extracted_data
from services.comparator import compare_submissions, diagnose_submission
from services.pattern_builder import build_pattern
from services.report_generator import generate_comparison_report
from services.utils import sse

router = APIRouter()


# ── 조회 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("/projects")
def get_projects(facility_type: str | None = None):
    return list_projects(facility_type)


@router.get("/projects/{facility_type}/{competition_id}")
def get_project(facility_type: str, competition_id: str):
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    return {
        "meta": meta,
        "brief": load_brief(facility_type, competition_id),
        "submissions": list_submissions(facility_type, competition_id),
    }


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
    return FileResponse(
        path, media_type="text/html",
        filename=f"{competition_id}_report.html",
    )


# ── 제안서 단건 추가 ──────────────────────────────────────────────────────────

@router.post("/projects/{facility_type}/{competition_id}/add-submission")
async def add_submission(
    facility_type: str,
    competition_id: str,
    company: str = Form(...),
    result: str = Form(...),  # "win" | "contracted" | "lose"
    submission_pdf: bytes = File(...),
):
    """기존 프로젝트에 제안서 1개 추가. 분류→추출→저장만. 비교분석 없음."""
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")

    async def event_stream():
        ts = int(time.time() * 1000)
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_addsub_"))
        try:
            yield sse({"type": "stage", "stage": "submission", "company": company,
                       "msg": f"제안서 처리: {company}", "_timestamp": ts})

            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(submission_pdf)

            sub_classifications = await classify_all_pages(sub_path)
            total_sub = len(sub_classifications)
            for cls in sub_classifications:
                yield sse({"type": "progress", "step": "classify_sub",
                           "company": company, "page": cls["page"], "total": total_sub,
                           "page_type": cls["primary_type"], "_timestamp": ts})

            yield sse({"type": "stage", "stage": "extract",
                       "msg": "제안서 데이터 추출 중", "_timestamp": ts})
            sub_extractions = await extract_pdf(sub_path, page_map=sub_classifications)

            page_dist: dict[str, int] = {}
            for cls in sub_classifications:
                pt = cls["primary_type"]
                page_dist[pt] = page_dist.get(pt, 0) + 1

            extracted = merge_extracted_data(sub_classifications, sub_extractions)
            extracted["page_distribution"] = page_dist
            extracted["total_pages"] = total_sub

            sub_doc = {
                "company": company,
                "result": result,
                "competition_id": competition_id,
                "facility_type": facility_type,
                "total_pages": total_sub,
                "page_map": sub_classifications,
                "page_distribution": page_dist,
                "extracted_data": extracted,
            }
            save_submission(facility_type, competition_id, company, result, sub_doc)
            yield sse({"type": "done", "step": "submission",
                       "company": company, "_timestamp": ts})

            yield sse({
                "type": "complete",
                "competition_id": competition_id,
                "facility_type": facility_type,
                "company": company,
                "result": result,
                "total_pages": total_sub,
                "page_distribution": page_dist,
                "_timestamp": ts,
            })
        except Exception as e:
            yield sse({"type": "error", "message": str(e),
                       "detail": traceback.format_exc(), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 비교분석 재실행 ────────────────────────────────────────────────────────────

@router.post("/projects/{facility_type}/{competition_id}/rerun-compare")
async def rerun_compare(facility_type: str, competition_id: str):
    """기존 저장된 데이터로 비교분석 + 리포트만 재실행. SSE 스트리밍."""
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    brief_data = load_brief(facility_type, competition_id) or {}
    submissions_data = list_submissions(facility_type, competition_id)
    if not submissions_data:
        raise HTTPException(400, "제안서 데이터 없음. 전체 분석을 먼저 실행하세요.")

    async def event_stream():
        # _timestamp: 파이프라인 시작 시각(ms). ProgressLog elapsed time 표시에 필수.
        ts = int(time.time() * 1000)

        try:
            yield sse({"type": "stage", "stage": "compare",
                       "msg": "비교분석 중", "_timestamp": ts})
            comparison = await compare_submissions(brief_data, submissions_data)
            comparison["competition_id"] = competition_id
            save_comparison(facility_type, competition_id, comparison)

            yield sse({"type": "stage", "stage": "pattern",
                       "msg": "당선 패턴 업데이트 중", "_timestamp": ts})
            build_pattern(facility_type)

            yield sse({"type": "stage", "stage": "report",
                       "msg": "HTML 비교 리포트 생성 중", "_timestamp": ts})
            report_subs = [
                {"company": s["company"], "result": s["result"],
                 "total_pages": s["total_pages"]}
                for s in submissions_data
            ]
            html = generate_comparison_report(meta, report_subs, comparison)
            save_report(facility_type, competition_id, html)
            yield sse({"type": "done", "step": "report", "_timestamp": ts})

            yield sse({
                "type": "complete",
                "competition_id": competition_id,
                "facility_type": facility_type,
                "report_available": True,
                "comparison": comparison,
                "_timestamp": ts,
                "submissions": [
                    {"company": s["company"], "result": s["result"],
                     "total_pages": s["total_pages"],
                     "page_distribution": s.get("page_distribution", {})}
                    for s in submissions_data
                ],
            })
        except Exception as e:
            yield sse({"type": "error", "message": str(e),
                       "detail": traceback.format_exc(), "_timestamp": ts})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 전체 파이프라인 ────────────────────────────────────────────────────────────

@router.post("/run")
async def run_pipeline(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    year: int = Form(...),
    client: str = Form(...),
    location: str = Form(...),
    brief_pdf: bytes | None = File(None),
    submissions_json: str = Form(...),
    submission_pdfs: list[bytes] = File(...),
):
    """
    submissions_json: JSON array of {company, result} matching submission_pdfs order.
    brief_pdf is optional — omit if no brief document available.
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
        # _timestamp: 파이프라인 시작 시각(ms). 이후 모든 SSE 이벤트에 포함.
        ts = int(time.time() * 1000)

        cid = make_competition_id(year, competition_name)
        save_project_meta(cid, facility_type, competition_name, year, client, location)
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_run_"))

        try:
            brief_data: dict = {}

            # ── BRIEF (분류 → 추출, 선택 사항) ──────────────────────────────
            if brief_bytes:
                yield sse({"type": "stage", "stage": "brief",
                           "msg": "지침서 PDF 처리 중", "_timestamp": ts})

                brief_path = tmp_root / "brief.pdf"
                brief_path.write_bytes(brief_bytes)

                # 1단계: 페이지 분류
                yield sse({"type": "progress", "step": "classify_brief",
                           "page": 0, "total": 1, "_timestamp": ts})
                brief_classifications = await classify_all_pages(brief_path)
                total_brief = len(brief_classifications)

                for cls in brief_classifications:
                    yield sse({"type": "progress", "step": "classify_brief",
                               "page": cls["page"], "total": total_brief,
                               "page_type": cls["primary_type"], "_timestamp": ts})

                # 2단계: 데이터 추출 — 분류 결과(page_map) 전달
                #   → AREA_TABLE·TECHNICAL 페이지는 자동으로 2×2 타일 분할 추출 적용
                yield sse({"type": "stage", "stage": "brief_extract",
                           "msg": "지침서 데이터 추출 중", "_timestamp": ts})
                brief_extractions = await extract_pdf(brief_path, page_map=brief_classifications, is_brief=True)
                yield sse({"type": "progress", "step": "extract_brief",
                           "page": 1, "total": 1, "_timestamp": ts})

                brief_data = merge_extracted_data(brief_classifications, brief_extractions)
                brief_data["page_map"] = brief_classifications
                brief_data["total_pages"] = total_brief
                save_brief(facility_type, cid, brief_data)
                yield sse({"type": "done", "step": "brief",
                           "total_pages": total_brief, "_timestamp": ts})

            # ── SUBMISSIONS ───────────────────────────────────────────────────
            processed_submissions = []

            for idx, (sub_bytes, meta) in enumerate(zip(sub_bytes_list, sub_meta)):
                company = meta.get("company", f"company_{idx + 1}")
                result = meta.get("result", "lose")

                yield sse({"type": "stage", "stage": "submission",
                           "company": company, "result": result,
                           "msg": f"제안서 처리: {company}", "_timestamp": ts})

                sub_dir = tmp_root / f"sub_{idx}"
                sub_dir.mkdir(exist_ok=True)
                sub_path = sub_dir / "submission.pdf"
                sub_path.write_bytes(sub_bytes)

                # 1단계: 페이지 분류
                yield sse({"type": "progress", "step": "classify_sub",
                           "company": company, "page": 0, "total": 1, "_timestamp": ts})
                sub_classifications = await classify_all_pages(sub_path)
                total_sub = len(sub_classifications)

                for cls in sub_classifications:
                    yield sse({"type": "progress", "step": "classify_sub",
                               "company": company,
                               "page": cls["page"], "total": total_sub,
                               "page_type": cls["primary_type"], "_timestamp": ts})

                # 2단계: 데이터 추출 — 분류 결과(page_map) 전달
                #   → AREA_TABLE·TECHNICAL 페이지는 타일 분할 추출 자동 적용
                yield sse({"type": "progress", "step": "extract_sub",
                           "company": company, "page": 0, "total": 1, "_timestamp": ts})
                sub_extractions = await extract_pdf(sub_path, page_map=sub_classifications)
                yield sse({"type": "progress", "step": "extract_sub",
                           "company": company, "page": 1, "total": 1, "_timestamp": ts})

                page_dist: dict[str, int] = {}
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
                yield sse({"type": "done", "step": "submission",
                           "company": company, "_timestamp": ts})

            # ── 비교분석 ──────────────────────────────────────────────────────
            yield sse({"type": "stage", "stage": "compare",
                       "msg": "비교분석 중", "_timestamp": ts})
            comparison = await compare_submissions(brief_data, processed_submissions)
            comparison["competition_id"] = cid
            save_comparison(facility_type, cid, comparison)

            # ── 패턴 업데이트 ─────────────────────────────────────────────────
            yield sse({"type": "stage", "stage": "pattern",
                       "msg": "당선 패턴 업데이트 중", "_timestamp": ts})
            build_pattern(facility_type)

            # ── HTML 리포트 생성 ──────────────────────────────────────────────
            yield sse({"type": "stage", "stage": "report",
                       "msg": "HTML 비교 리포트 생성 중", "_timestamp": ts})
            comp_meta = {
                "competition_name": competition_name,
                "facility_type": facility_type,
                "year": year,
                "client": client,
                "location": location,
            }
            report_subs = [
                {"company": s["company"], "result": s["result"],
                 "total_pages": s["total_pages"]}
                for s in processed_submissions
            ]
            html = generate_comparison_report(comp_meta, report_subs, comparison)
            save_report(facility_type, cid, html)
            yield sse({"type": "done", "step": "report", "_timestamp": ts})

            yield sse({
                "type": "complete",
                "competition_id": cid,
                "facility_type": facility_type,
                "report_available": True,
                "comparison": comparison,
                "_timestamp": ts,
                "submissions": [
                    {"company": s["company"], "result": s["result"],
                     "total_pages": s["total_pages"],
                     "page_distribution": s["page_distribution"]}
                    for s in processed_submissions
                ],
            })

        except Exception as e:
            yield sse({"type": "error", "message": str(e),
                       "detail": traceback.format_exc(), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 단독 등록 파이프라인 ────────────────────────────────────────────────────────

@router.post("/run-single")
async def run_single_pipeline(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    year: int = Form(...),
    client: str = Form(...),
    location: str = Form(...),
    company: str = Form(...),
    result: str = Form(...),  # "win" | "contracted" | "lose"
    brief_pdf: bytes | None = File(None),
    submission_pdf: bytes = File(...),
):
    """지침서(선택) + 제안서 1개. 비교 없이 DB 저장 → 패턴 갱신.
    낙선(lose)인 경우 기존 패턴 대비 원인 진단을 추가로 수행."""
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    async def event_stream():
        ts = int(time.time() * 1000)
        cid = make_competition_id(year, competition_name)
        save_project_meta(cid, facility_type, competition_name, year, client, location)
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_single_"))

        try:
            brief_data: dict = {}

            # ── BRIEF (선택 사항) ──────────────────────────────────────────────
            if brief_pdf:
                yield sse({"type": "stage", "stage": "brief",
                           "msg": "지침서 PDF 처리 중", "_timestamp": ts})
                brief_path = tmp_root / "brief.pdf"
                brief_path.write_bytes(brief_pdf)

                brief_classifications = await classify_all_pages(brief_path)
                total_brief = len(brief_classifications)
                for cls in brief_classifications:
                    yield sse({"type": "progress", "step": "classify_brief",
                               "page": cls["page"], "total": total_brief,
                               "page_type": cls["primary_type"], "_timestamp": ts})

                yield sse({"type": "stage", "stage": "brief_extract",
                           "msg": "지침서 데이터 추출 중", "_timestamp": ts})
                brief_extractions = await extract_pdf(brief_path, page_map=brief_classifications, is_brief=True)

                brief_data = merge_extracted_data(brief_classifications, brief_extractions)
                brief_data["page_map"] = brief_classifications
                brief_data["total_pages"] = total_brief
                save_brief(facility_type, cid, brief_data)
                yield sse({"type": "done", "step": "brief",
                           "total_pages": total_brief, "_timestamp": ts})

            # ── SUBMISSION ────────────────────────────────────────────────────
            yield sse({"type": "stage", "stage": "submission", "company": company,
                       "msg": f"제안서 처리: {company}", "_timestamp": ts})
            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(submission_pdf)

            sub_classifications = await classify_all_pages(sub_path)
            total_sub = len(sub_classifications)
            for cls in sub_classifications:
                yield sse({"type": "progress", "step": "classify_sub",
                           "page": cls["page"], "total": total_sub,
                           "page_type": cls["primary_type"], "_timestamp": ts})

            yield sse({"type": "stage", "stage": "extract",
                       "msg": "제안서 데이터 추출 중", "_timestamp": ts})
            sub_extractions = await extract_pdf(sub_path, page_map=sub_classifications)

            page_dist: dict[str, int] = {}
            for cls in sub_classifications:
                pt = cls["primary_type"]
                page_dist[pt] = page_dist.get(pt, 0) + 1

            extracted = merge_extracted_data(sub_classifications, sub_extractions)
            extracted["page_distribution"] = page_dist
            extracted["total_pages"] = total_sub

            sub_doc = {
                "company": company,
                "result": result,
                "competition_id": cid,
                "facility_type": facility_type,
                "total_pages": total_sub,
                "page_map": sub_classifications,
                "page_distribution": page_dist,
                "extracted_data": extracted,
            }
            save_submission(facility_type, cid, company, result, sub_doc)
            yield sse({"type": "done", "step": "submission",
                       "company": company, "_timestamp": ts})

            # ── 패턴 갱신 (당선/수의계약만) ───────────────────────────────────
            if result in ("win", "contracted"):
                yield sse({"type": "stage", "stage": "pattern",
                           "msg": "패턴 업데이트 중", "_timestamp": ts})
                build_pattern(facility_type)

            # ── 낙선 원인 진단 (패턴이 있을 때만) ─────────────────────────────
            diagnosis = None
            if result == "lose":
                patterns = load_pattern(facility_type)
                if patterns and patterns.get("win_count", 0) > 0:
                    yield sse({"type": "stage", "stage": "diagnose",
                               "msg": "낙선 원인 분석 중 (패턴 대비)", "_timestamp": ts})
                    diagnosis = await diagnose_submission(
                        facility_type=facility_type,
                        winning_patterns=patterns,
                        brief_data=brief_data,
                        submission_data=extracted,
                    )

            yield sse({
                "type": "complete",
                "competition_id": cid,
                "facility_type": facility_type,
                "report_available": False,
                "company": company,
                "result": result,
                "total_pages": total_sub,
                "page_distribution": page_dist,
                "diagnosis": diagnosis,
                "_timestamp": ts,
            })

        except Exception as e:
            yield sse({"type": "error", "message": str(e),
                       "detail": traceback.format_exc(), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")