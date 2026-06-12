"""
accumulate.py — 데이터 축적 파이프라인 라우터

변경 이력:
  - extract_pdf(..., page_map=...)  : 분류 결과를 추출 단계에 전달
                                      → 타입별 최적 프롬프트 + AREA_TABLE 타일 분할 활성화
  - _timestamp                      : 모든 SSE 이벤트에 파이프라인 시작 시각 추가
                                      (CLAUDE.md 필수 규칙 — ProgressLog elapsed time 표시용)
"""

import json
import logging
import shutil
import tempfile
import time
import traceback

logger = logging.getLogger(__name__)

_MAX_PDF_BYTES = 200 * 1024 * 1024  # 200MB
_PDF_MAGIC = b"%PDF"


def _validate_pdf(data: bytes, name: str = "파일"):
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(400, f"{name}: 파일 크기가 50MB를 초과합니다 ({len(data) // 1024 // 1024}MB).")
    if not data.startswith(_PDF_MAGIC):
        raise HTTPException(400, f"{name}: PDF 형식이 아닙니다.")


async def _read_upload(file: "UploadFile | None") -> bytes | None:
    """UploadFile → bytes. None이면 None 반환."""
    if file is None:
        return None
    return await file.read()


async def _resolve_pdf(file: "UploadFile | None", file_ref: str | None) -> bytes | None:
    """UploadFile 또는 file_ref 중 하나를 bytes로 반환."""
    if file_ref:
        return resolve_file_ref(file_ref).read_bytes()
    return await _read_upload(file)


from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from routers.upload import resolve_file_ref

from config import settings, FACILITY_TYPES
from services.db_manager import (
    make_competition_id, save_project_meta, save_brief,
    save_submission, save_comparison, load_comparison, load_brief, load_project_meta,
    list_projects, list_submissions, load_submission, save_report, get_report_path, load_pattern,
    save_submission_report, get_submission_report_path,
    save_cross_compare_report, get_cross_compare_report_path, list_cross_compare_reports, _slugify,
    update_submission, has_comparison,
    save_myproject_deep, save_myproject_report, get_myproject_report_path,
    update_project_meta,
)
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_pdf, merge_extracted_data, extract_brief_requirements
from services.comparator import compare_submissions, diagnose_submission
from services.pattern_builder import build_pattern
from services.report_generator import generate_comparison_report
from services.submission_report_generator import generate_submission_report
from services.myproject_analyzer import deep_analyze
from services.myproject_report_generator import generate_myproject_report
from services.utils import sse, user_error_msg as _user_error_msg
from services.archive_search import rebuild_index as _rebuild_archive_index

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
    project_number: str = Form(...),
    client: str = Form(""),
    location: str = Form(""),
):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    cid = make_competition_id(project_number, competition_name)
    save_project_meta(cid, facility_type, competition_name, project_number, client, location)
    return {"ok": True, "competition_id": cid}


@router.get("/projects/{facility_type}/{competition_id}/report")
def get_report(facility_type: str, competition_id: str):
    path = get_report_path(facility_type, competition_id)
    if not path.exists():
        raise HTTPException(404, "Report not found")
    resp = FileResponse(path, media_type="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/projects/{facility_type}/{competition_id}/submissions/{company}/report")
def get_submission_report(facility_type: str, competition_id: str, company: str):
    path = get_submission_report_path(facility_type, competition_id, company)
    if path is None or not path.exists():
        raise HTTPException(404, "Submission report not found")
    resp = FileResponse(path, media_type="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/projects/{facility_type}/{competition_id}/submissions/{company}/deep-report")
def get_myproject_deep_report(facility_type: str, competition_id: str, company: str):
    """MyProjectMode 심층 분석 HTML 리포트 — submissions/{slug}_{result}_deep.html"""
    path = get_myproject_report_path(facility_type, competition_id, company)
    if path is None or not path.exists():
        raise HTTPException(404, "Deep report not found")
    resp = FileResponse(path, media_type="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/projects/{facility_type}/{competition_id}/submissions/{company}")
def get_submission(facility_type: str, competition_id: str, company: str):
    """단일 submission 전체 데이터 조회 — 편집 모달용."""
    sub = load_submission(facility_type, competition_id, company)
    if not sub:
        raise HTTPException(404, "Submission not found")
    return sub


@router.put("/projects/{facility_type}/{competition_id}/submissions/{company}")
async def edit_submission(
    facility_type: str,
    competition_id: str,
    company: str,
    body: dict,
):
    """
    편집된 submission 저장.
    body: { extracted_data, result, meta_overrides? }
    result 변경 시 파일명 변경 + 패턴 재구축.
    """
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    new_extracted = body.get("extracted_data")
    new_result = body.get("result", "lose")
    meta_overrides = body.get("meta_overrides")

    if new_extracted is None:
        raise HTTPException(400, "extracted_data 필드가 없습니다.")
    if not isinstance(new_extracted, dict):
        raise HTTPException(400, "extracted_data는 객체여야 합니다.")
    if new_result not in ("win", "lose", "contracted"):
        raise HTTPException(400, "result는 win / lose / contracted 중 하나여야 합니다.")

    # 사전 검증: 편집 대상 submission이 존재해야 함 (신규 생성은 다른 엔드포인트)
    existing = load_submission(facility_type, competition_id, company)
    if not existing:
        raise HTTPException(404, "편집할 제안서를 찾을 수 없습니다.")

    try:
        update_info = update_submission(
            facility_type, competition_id, company,
            new_result, new_extracted, meta_overrides,
        )
    except Exception as e:
        logger.error("edit_submission error: %s", traceback.format_exc())
        raise HTTPException(500, _user_error_msg(e))

    updated_sub = update_info["submission"]

    # 개별 리포트 재생성
    report_regenerated = False
    try:
        from services.submission_report_generator import generate_submission_report
        html = generate_submission_report(updated_sub)
        save_submission_report(facility_type, competition_id, company, html)
        report_regenerated = True
    except Exception as e:
        logger.error("Submission report regen failed: %s", e)

    # 패턴 재구축 조건:
    #  - 새 result가 win/contracted (당선 데이터 갱신)
    #  - result가 변경됨 (예: win → lose 시 기존 당선 데이터를 패턴에서 제거)
    pattern_rebuilt = False
    if new_result in ("win", "contracted") or update_info["result_changed"]:
        try:
            build_pattern(facility_type)
            pattern_rebuilt = True
        except Exception as e:
            logger.error("Pattern rebuild failed: %s", e)

    comparison_stale = has_comparison(facility_type, competition_id)

    return {
        "ok": True,
        "submission_saved": True,
        "report_regenerated": report_regenerated,
        "pattern_rebuilt": pattern_rebuilt,
        "comparison_stale": comparison_stale,
        "result_changed": update_info["result_changed"],
        "edited_at": updated_sub.get("_edited_at"),
    }


@router.get("/cross-compare/reports")
def list_cross_reports():
    return list_cross_compare_reports()


@router.get("/cross-compare/reports/{filename}")
def get_cross_compare_report(filename: str):
    path = get_cross_compare_report_path(filename)
    if path is None or not path.exists():
        raise HTTPException(404, "Cross-compare report not found")
    return FileResponse(path, media_type="text/html", filename=filename)


# ── 제안서 단건 추가 ──────────────────────────────────────────────────────────

@router.post("/projects/{facility_type}/{competition_id}/add-submission")
async def add_submission(
    facility_type: str,
    competition_id: str,
    company: str = Form(...),
    result: str = Form(...),  # "win" | "contracted" | "lose"
    submission_pdf: UploadFile | None = File(None),
    submission_pdf_ref: str | None = Form(None),  # chunked upload file_ref
):
    """기존 프로젝트에 제안서 1개 추가. 분류→추출→저장만. 비교분석 없음."""
    if not settings.has_api_key():
        raise HTTPException(401, "API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.")
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    sub_bytes = await _resolve_pdf(submission_pdf, submission_pdf_ref)
    if not sub_bytes:
        raise HTTPException(400, "submission_pdf 또는 submission_pdf_ref 중 하나가 필요합니다.")
    _validate_pdf(sub_bytes, "제안서 PDF")

    async def event_stream():
        ts = int(time.time() * 1000)
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_addsub_"))
        try:
            yield sse({"type": "stage", "stage": "submission", "company": company,
                       "msg": f"제안서 처리: {company}", "_timestamp": ts})

            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(sub_bytes)

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

            sub_report_html = generate_submission_report(sub_doc)
            save_submission_report(facility_type, competition_id, company, sub_report_html)

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
            logger.error("Pipeline error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})
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
            comparison = await compare_submissions(brief_data, submissions_data, facility_type)
            comparison["competition_id"] = competition_id
            save_comparison(facility_type, competition_id, comparison)

            yield sse({"type": "stage", "stage": "pattern",
                       "msg": "당선 패턴 업데이트 중", "_timestamp": ts})
            build_pattern(facility_type)

            yield sse({"type": "stage", "stage": "report",
                       "msg": "HTML 리포트 생성 중", "_timestamp": ts})
            report_subs = [
                {"company": s["company"], "result": s["result"],
                 "total_pages": s["total_pages"]}
                for s in submissions_data
            ]
            html = generate_comparison_report(meta, report_subs, comparison)
            save_report(facility_type, competition_id, html)

            for s in submissions_data:
                sub_report_html = generate_submission_report(s)
                save_submission_report(facility_type, competition_id, s["company"], sub_report_html)

            yield sse({"type": "done", "step": "report", "_timestamp": ts})

            try: _rebuild_archive_index()
            except Exception as e: logger.warning("archive 인덱스 갱신 실패: %s", e)

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
            logger.error("Pipeline error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 리포트만 재렌더링 (LLM 호출 X, 토큰 0) ─────────────────────────────────────

@router.post("/projects/{facility_type}/{competition_id}/rerender-report")
async def rerender_report(facility_type: str, competition_id: str):
    """기존 _comparison.json + submissions/*.json 으로 HTML 리포트만 재생성.
    LLM 호출 없음 — 토큰 비용 0. 디자인 변경/템플릿 업데이트 후 일괄 재반영용.
    """
    meta = load_project_meta(facility_type, competition_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    comparison = load_comparison(facility_type, competition_id)
    if not comparison:
        raise HTTPException(400, "비교 분석 데이터(_comparison.json) 없음. 먼저 비교분석을 실행하세요.")
    submissions_data = list_submissions(facility_type, competition_id)
    if not submissions_data:
        raise HTTPException(400, "제안서 데이터 없음.")

    report_subs = [
        {"company": s["company"], "result": s["result"],
         "total_pages": s["total_pages"],
         "extracted_data": s.get("extracted_data", {})}
        for s in submissions_data
    ]
    html = generate_comparison_report(meta, report_subs, comparison)
    save_report(facility_type, competition_id, html)

    sub_count = 0
    for s in submissions_data:
        sub_html = generate_submission_report(s)
        if save_submission_report(facility_type, competition_id, s["company"], sub_html):
            sub_count += 1

    return {
        "ok": True,
        "facility_type": facility_type,
        "competition_id": competition_id,
        "report_regenerated": True,
        "submission_reports_regenerated": sub_count,
    }


# ── 전체 파이프라인 ────────────────────────────────────────────────────────────

@router.post("/run")
async def run_pipeline(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    project_number: str = Form(...),
    client: str = Form(""),
    location: str = Form(""),
    brief_pdf: UploadFile | None = File(None),
    brief_pdf_ref: str | None = Form(None),
    submissions_json: str = Form(...),
    submission_pdfs: list[UploadFile] | None = File(None),
    submission_pdf_refs: str | None = Form(None),  # JSON array of file_refs
):
    """
    submissions_json: JSON array of {company, result} matching submission_pdfs order.
    brief_pdf / brief_pdf_ref: 지침서 PDF (선택). 둘 중 하나.
    submission_pdfs / submission_pdf_refs: 제안서 PDFs. 둘 중 하나.
    Streams SSE progress events.
    """
    if not settings.has_api_key():
        raise HTTPException(401, "API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.")
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    try:
        sub_meta = json.loads(submissions_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "submissions_json must be valid JSON array")

    if submission_pdf_refs:
        try:
            refs = json.loads(submission_pdf_refs)
        except json.JSONDecodeError:
            raise HTTPException(400, "submission_pdf_refs must be valid JSON array")
        sub_bytes_list = [resolve_file_ref(r).read_bytes() for r in refs]
    elif submission_pdfs:
        sub_bytes_list = [await f.read() for f in submission_pdfs]
    else:
        raise HTTPException(400, "submission_pdfs 또는 submission_pdf_refs 중 하나가 필요합니다.")

    if len(sub_meta) != len(sub_bytes_list):
        raise HTTPException(400, "submissions_json length must match submission_pdfs count")

    brief_bytes = await _resolve_pdf(brief_pdf, brief_pdf_ref)

    if brief_bytes:
        _validate_pdf(brief_bytes, "지침서 PDF")
    for i, sb in enumerate(sub_bytes_list):
        _validate_pdf(sb, f"제안서 PDF [{i+1}]")

    async def event_stream():
        # _timestamp: 파이프라인 시작 시각(ms). 이후 모든 SSE 이벤트에 포함.
        ts = int(time.time() * 1000)

        cid = make_competition_id(project_number, competition_name)
        save_project_meta(cid, facility_type, competition_name, project_number, client, location)
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

                yield sse({"type": "stage", "stage": "brief_reqs",
                           "msg": "지침서 요구사항 분석 중", "_timestamp": ts})
                brief_data["_requirements"] = await extract_brief_requirements(brief_data, facility_type)

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
                sub_report_html = generate_submission_report(sub_doc)
                save_submission_report(facility_type, cid, company, sub_report_html)
                processed_submissions.append(sub_doc)
                yield sse({"type": "done", "step": "submission",
                           "company": company, "_timestamp": ts})

            yield sse({
                "type": "complete",
                "competition_id": cid,
                "facility_type": facility_type,
                "report_available": False,
                "_timestamp": ts,
                "submissions": [
                    {"company": s["company"], "result": s["result"],
                     "total_pages": s["total_pages"],
                     "page_distribution": s["page_distribution"]}
                    for s in processed_submissions
                ],
            })

        except Exception as e:
            logger.error("Pipeline error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 단독 등록 파이프라인 ────────────────────────────────────────────────────────

@router.post("/run-single")
async def run_single_pipeline(
    competition_name: str = Form(...),
    facility_type: str = Form(...),
    project_number: str = Form(...),
    client: str = Form(""),
    location: str = Form(""),
    company: str = Form(...),
    result: str = Form(...),  # "win" | "contracted" | "lose"
    # ── MyProjectMode 상세 메타 (선택) ──────────────────────────────────────
    procurement_type: str = Form(""),  # 경쟁공모/수의계약/지명공모/턴키/민간발주/기타
    project_phase: str = Form(""),     # 기획/계획/기본설계/실시설계/CM
    role: str = Form(""),              # 주관사/컨소시엄/협력사
    partners: str = Form(""),          # 컨소시엄 파트너 (자유 텍스트)
    tags: str = Form(""),              # 콤마/공백 구분 자유 키워드
    memo: str = Form(""),              # 자유 텍스트 (자연어 검색 핵심 소스)
    gross_floor_area: str = Form(""),  # 연면적 (자유 텍스트 — 단위 포함 가능)
    floors: str = Form(""),            # 층수
    units: str = Form(""),             # 세대수
    brief_pdf: UploadFile | None = File(None),
    brief_pdf_ref: str | None = Form(None),
    submission_pdf: UploadFile | None = File(None),
    submission_pdf_ref: str | None = Form(None),
):
    """지침서(선택) + 제안서 1개. 비교 없이 DB 저장 → 패턴 갱신.
    낙선(lose)인 경우 기존 패턴 대비 원인 진단을 추가로 수행.
    선택 메타(procurement_type 등)는 _meta.json에 저장되어 아카이브 검색에 활용."""
    if not settings.has_api_key():
        raise HTTPException(401, "API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.")
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")
    sub_bytes = await _resolve_pdf(submission_pdf, submission_pdf_ref)
    if not sub_bytes:
        raise HTTPException(400, "submission_pdf 또는 submission_pdf_ref 중 하나가 필요합니다.")
    _validate_pdf(sub_bytes, "제안서 PDF")
    brief_bytes_single = await _resolve_pdf(brief_pdf, brief_pdf_ref)
    if brief_bytes_single:
        _validate_pdf(brief_bytes_single, "지침서 PDF")

    async def event_stream():
        ts = int(time.time() * 1000)
        cid = make_competition_id(project_number, competition_name)
        # 태그는 콤마/공백 구분 → 리스트로 정규화
        tag_list = [t.strip() for t in (tags or "").replace(",", " ").split() if t.strip()]
        extra_meta = {
            "procurement_type": procurement_type.strip(),
            "project_phase": project_phase.strip(),
            "role": role.strip(),
            "partners": partners.strip(),
            "tags": tag_list,
            "memo": memo.strip(),
            "gross_floor_area": gross_floor_area.strip(),
            "floors": floors.strip(),
            "units": units.strip(),
        }
        save_project_meta(
            cid, facility_type, competition_name, project_number, client, location,
            extra=extra_meta,
        )
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_single_"))

        try:
            brief_data: dict = {}

            # ── BRIEF (선택 사항) ──────────────────────────────────────────────
            if brief_bytes_single:
                yield sse({"type": "stage", "stage": "brief",
                           "msg": "지침서 PDF 처리 중", "_timestamp": ts})
                brief_path = tmp_root / "brief.pdf"
                brief_path.write_bytes(brief_bytes_single)

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

                yield sse({"type": "stage", "stage": "brief_reqs",
                           "msg": "지침서 요구사항 분석 중", "_timestamp": ts})
                brief_data["_requirements"] = await extract_brief_requirements(brief_data, facility_type)

                save_brief(facility_type, cid, brief_data)
                yield sse({"type": "done", "step": "brief",
                           "total_pages": total_brief, "_timestamp": ts})

            # ── SUBMISSION ────────────────────────────────────────────────────
            yield sse({"type": "stage", "stage": "submission", "company": company,
                       "msg": f"제안서 처리: {company}", "_timestamp": ts})
            sub_path = tmp_root / "submission.pdf"
            sub_path.write_bytes(sub_bytes)

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
            sub_report_html = generate_submission_report(sub_doc)
            save_submission_report(facility_type, cid, company, sub_report_html)
            yield sse({"type": "done", "step": "submission",
                       "company": company, "_timestamp": ts})

            # ── 심층 분석 (MyProjectMode 단일 제출물 전용) ────────────────────
            # 토큰 예산이 여유로워 평가축 deep evidence + 컨셉 narrative + 검색
            # 키워드를 풍부하게 추출 → 아카이브 자연어 검색 품질 강화.
            yield sse({"type": "stage", "stage": "deep_analyze",
                       "msg": "심층 분석 중 (평가축 deep evidence + 컨셉 narrative + 검색 키워드)",
                       "_timestamp": ts})
            try:
                deep = await deep_analyze(
                    facility_type=facility_type,
                    extracted_data=extracted,
                    brief_data=brief_data,
                    meta_extra=extra_meta,
                    company=company,
                    result=result,
                )
                deep_doc = {
                    "competition_id": cid,
                    "facility_type": facility_type,
                    "company": company,
                    "result": result,
                    "deep": deep,
                }
                save_myproject_deep(facility_type, cid, company, deep_doc)

                # AI가 추출한 auto_meta를 _meta.json에 머지 (사용자가 명시한 값 우선).
                # tags는 list, summary는 _meta.json의 memo 필드로 매핑하여 ArchiveDetail에 자연 노출.
                auto_meta = deep.get("auto_meta") or {}
                if isinstance(auto_meta, dict):
                    auto_extras = {
                        "procurement_type": auto_meta.get("procurement_type") or "",
                        "project_phase":    auto_meta.get("project_phase") or "",
                        "role":             auto_meta.get("role") or "",
                        "partners":         auto_meta.get("partners") or "",
                        "gross_floor_area": auto_meta.get("gross_floor_area") or "",
                        "floors":           auto_meta.get("floors") or "",
                        "units":            auto_meta.get("units") or "",
                        "tags":             auto_meta.get("tags") or [],
                        # AI summary는 사용자 메모가 비어있을 때만 memo 필드로 채움
                        "memo":             auto_meta.get("summary") or "",
                    }
                    update_project_meta(facility_type, cid, auto_extras)

                # HTML 리포트 — LLM 호출 없음, _deep.json + meta 렌더링만
                project_meta = load_project_meta(facility_type, cid) or {}
                # competition_name 보존을 위해 meta에 직접 주입
                project_meta.setdefault("competition_name", competition_name)
                deep_report_html = generate_myproject_report(
                    deep=deep, sub_doc=sub_doc, meta=project_meta,
                )
                save_myproject_report(facility_type, cid, company, deep_report_html)
                yield sse({"type": "done", "step": "deep_analyze",
                           "company": company,
                           "keywords_count": len(deep.get("search_keywords") or []),
                           "_timestamp": ts})
            except Exception as e:
                # 심층 분석 실패는 전체 파이프라인 실패로 처리하지 않음
                logger.warning("심층 분석 실패: %s", e)
                yield sse({"type": "warn", "stage": "deep_analyze",
                           "msg": f"심층 분석을 건너뛰었습니다: {_user_error_msg(e)}",
                           "_timestamp": ts})

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

            # 아카이브 인덱스 갱신 — 새 _meta.json/_comparison.json이 즉시 검색에 잡히도록.
            try: _rebuild_archive_index()
            except Exception as e: logger.warning("archive 인덱스 갱신 실패: %s", e)

            # 심층 리포트 존재 여부 — 프론트가 "심층 리포트 열기" 버튼 노출에 사용
            deep_report_available = get_myproject_report_path(facility_type, cid, company) is not None

            yield sse({
                "type": "complete",
                "competition_id": cid,
                "facility_type": facility_type,
                "report_available": False,
                "deep_report_available": deep_report_available,
                "company": company,
                "result": result,
                "total_pages": total_sub,
                "page_distribution": page_dist,
                "diagnosis": diagnosis,
                "_timestamp": ts,
            })

        except Exception as e:
            logger.error("Pipeline error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ── 교차 비교 ──────────────────────────────────────────────────────────────────

@router.post("/cross-compare")
async def cross_compare(
    items_json: str = Form(...),  # [{facility_type, competition_id, company}]
):
    """여러 프로젝트에서 선택한 제안서들을 교차 비교분석."""
    try:
        items = json.loads(items_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "items_json must be valid JSON array")

    async def event_stream():
        ts = int(time.time() * 1000)
        try:
            yield sse({"type": "stage", "stage": "load",
                       "msg": "제안서 데이터 로딩 중", "_timestamp": ts})

            submissions = []
            brief_data = {}
            file_parts = []  # 파일명 구성용: [(proj_label, company), ...]
            for item in items:
                ft = item["facility_type"]
                cid = item["competition_id"]
                company = item["company"]
                if not brief_data:
                    brief_data = load_brief(ft, cid) or {}
                sub = load_submission(ft, cid, company)
                if not sub:
                    continue

                meta = load_project_meta(ft, cid) or {}
                proj_label = meta.get("competition_name") or cid

                # 같은 회사명이 다른 프로젝트에서 중복으로 들어오면 프로젝트명을
                # 붙여서 유니크 라벨 생성 (comparator가 company 키로 dedup하는 문제 회피)
                duplicate = any(
                    it["company"] == company and it["competition_id"] != cid
                    for it in items
                )
                if duplicate:
                    sub = {**sub, "company": f"{company} ({proj_label})"}

                submissions.append(sub)
                file_parts.append((proj_label, company))

            if len(submissions) < 2:
                yield sse({"type": "error",
                           "message": "비교할 제안서를 2개 이상 선택해주세요.", "_timestamp": ts})
                return

            yield sse({"type": "stage", "stage": "compare",
                       "msg": f"{len(submissions)}개 제안서 비교분석 중 (시간이 걸릴 수 있습니다)", "_timestamp": ts})
            comparison = await compare_submissions(brief_data, submissions)

            # ── 리포트 생성 + 저장 ─────────────────────────────────────
            stamp = time.strftime("%Y%m%d_%H%M%S")
            label_segments = [_slugify(f"{p}_{c}") for p, c in file_parts]
            joined = "_vs_".join(label_segments) or "cross_compare"
            # Windows 파일명 길이 제한 회피 (전체 260자)
            if len(joined) > 180:
                joined = joined[:180]
            filename = f"{stamp}_{joined}.html"

            synthetic_meta = {
                "competition_name": f"교차비교 — {' vs '.join(c for _, c in file_parts)}",
                "facility_type": submissions[0].get("facility_type", ""),
                "year": "",
                "client": "",
                "location": "",
            }
            html = generate_comparison_report(synthetic_meta, submissions, comparison)
            save_cross_compare_report(filename, html)

            yield sse({
                "type": "complete",
                "comparison": comparison,
                "report_filename": filename,
                "_timestamp": ts,
            })

        except Exception as e:
            logger.error("Pipeline error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
