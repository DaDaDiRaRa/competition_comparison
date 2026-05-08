import json
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from config import settings, FACILITY_TYPES
from services.db_manager import load_pattern, load_submission
from services.page_classifier import classify_all_pages
from services.data_extractor import extract_pdf, merge_extracted_data
from services.comparator import diagnose_submission
from services.pattern_builder import build_pattern_from_submissions
from services.utils import sse

router = APIRouter()


@router.post("/run")
async def run_diagnosis(
    facility_type: str = Form(...),
    competition_name: str = Form(""),
    submission_pdf: bytes = File(...),
    brief_pdf: bytes | None = File(None),
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

            # --- BRIEF (선택 사항) ---
            brief_data: dict = {}
            total_brief = 0
            if brief_bytes:
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
                brief_exts = await extract_pdf(brief_path, page_map=brief_cls, is_brief=True)
                yield sse({"type": "progress", "step": "extract_brief", "page": 1, "total": 1})

                brief_data = merge_extracted_data(brief_cls, brief_exts)
                brief_data["page_map"] = brief_cls
                brief_data["total_pages"] = total_brief
                yield sse({"type": "done", "step": "brief", "total_pages": total_brief})
            else:
                yield sse({"type": "info", "msg": "지침서 미제출 — 패턴 기반 진단만 수행"})

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
            sub_exts = await extract_pdf(sub_path, page_map=sub_cls)
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


# ── 특정 공모 선택 진단 (사용자가 참조할 프로젝트를 직접 고름) ──────────────────

@router.post("/run-vs-projects")
async def run_diagnosis_vs_projects(
    facility_type: str = Form(...),
    competition_name: str = Form(""),
    reference_items_json: str = Form(...),  # [{facility_type, competition_id, company}]
    submission_pdf: bytes = File(...),
    brief_pdf: bytes | None = File(None),
):
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    try:
        ref_items = json.loads(reference_items_json)
    except Exception:
        raise HTTPException(400, "Invalid reference_items_json")
    if not ref_items:
        raise HTTPException(400, "참조할 공모를 1개 이상 선택해주세요.")

    brief_bytes = brief_pdf
    submission_bytes = submission_pdf

    async def event_stream():
        tmp_root = Path(tempfile.mkdtemp(prefix="comp_diag_"))
        try:
            # --- 참조 제출물 로드 + 패턴 생성 ---
            yield sse({"type": "stage", "stage": "load_refs",
                       "msg": f"참조 공모 {len(ref_items)}개 로드 중"})
            ref_subs = []
            for it in ref_items:
                sub = load_submission(it["facility_type"], it["competition_id"], it["company"])
                if sub:
                    ref_subs.append(sub)
            if not ref_subs:
                yield sse({"type": "error", "message": "선택한 공모를 불러올 수 없습니다."})
                return
            patterns = build_pattern_from_submissions(facility_type, ref_subs)
            yield sse({"type": "info", "patterns_available": True,
                       "win_count": patterns.get("win_count", 0),
                       "msg": f"선택 공모 {len(ref_subs)}개로 패턴 구성"})

            # --- BRIEF (선택) ---
            brief_data: dict = {}
            total_brief = 0
            if brief_bytes:
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
                brief_exts = await extract_pdf(brief_path, page_map=brief_cls, is_brief=True)
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
            sub_exts = await extract_pdf(sub_path, page_map=sub_cls)
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
            yield sse({"type": "stage", "stage": "diagnose",
                       "msg": f"AI 진단 분석 중 (참조: {len(ref_subs)}개 공모)"})
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
                "reference_count": len(ref_subs),
                "reference_items": [
                    {"competition_id": it["competition_id"], "company": it["company"]}
                    for it in ref_items
                ],
            })
            yield sse({"type": "complete", "result": diagnosis})

        except Exception as e:
            yield sse({"type": "error", "message": str(e), "detail": traceback.format_exc()})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
