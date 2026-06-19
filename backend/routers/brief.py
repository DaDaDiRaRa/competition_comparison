"""
routers/brief.py — 지침서 단독 분석 엔드포인트

POST /api/brief/analyze            : 지침서 PDF → 분류·추출·요구사항·검증 → 저장 (SSE)
GET  /api/brief/exports/{filename} : md / xlsx 다운로드
GET  /api/brief/list               : 저장된 지침서 목록 (최신순)

저장 위치: {db_path}/_briefs/{YYYYMMDD_HHMMSS}_{facility_type}_{slug}.{json|md|xlsx}
파일 쓰기: _atomic_write (JSON) / _sync_write (text) / _sync_write_bytes (binary)
기존 accumulate / diagnose 파이프라인은 건드리지 않음.
"""
import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from config import settings, FACILITY_TYPES
from routers.upload import resolve_file_ref
from services.db_manager import _atomic_write, _sync_write, _sync_write_bytes, _slugify
from services.page_classifier import classify_all_pages_brief, classify_all_blocks_brief
from services.data_extractor import extract_pdf, extract_docx, merge_extracted_data, extract_brief_requirements
from services.docx_loader import split_docx_to_blocks
from services.brief_validator import validate_brief
from services.brief_checklist_exporter import to_markdown, to_xlsx
from services.utils import sse, user_error_msg as _user_error_msg, pdf_page_count

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_PDF_BYTES  = 200 * 1024 * 1024  # 200 MB
_MAX_DOCX_BYTES = 50 * 1024 * 1024   # 50 MB
_PDF_MAGIC      = b"%PDF"
_DOCX_MAGIC     = b"PK\x03\x04"      # ZIP/OOXML header


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _validate_brief_file(data: bytes, filename: str, name: str = "파일") -> str:
    """확장자별 검증 후 형식 반환 ("pdf" | "docx")."""
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        if len(data) > _MAX_PDF_BYTES:
            raise HTTPException(
                400,
                f"{name}: 파일 크기가 {_MAX_PDF_BYTES // 1024 // 1024}MB를 초과합니다 "
                f"({len(data) // 1024 // 1024}MB).",
            )
        if not data.startswith(_PDF_MAGIC):
            raise HTTPException(400, f"{name}: PDF 형식이 아닙니다.")
        return "pdf"
    if ext == ".docx":
        if len(data) > _MAX_DOCX_BYTES:
            raise HTTPException(
                400,
                f"{name}: 파일 크기가 {_MAX_DOCX_BYTES // 1024 // 1024}MB를 초과합니다 "
                f"({len(data) // 1024 // 1024}MB).",
            )
        if not data.startswith(_DOCX_MAGIC):
            raise HTTPException(400, f"{name}: DOCX(ZIP) 형식이 아닙니다.")
        return "docx"
    raise HTTPException(400, "PDF 또는 DOCX 파일만 지원합니다.")


def _briefs_dir() -> Path:
    """호출 시점 db_path 기준 _briefs 디렉터리 반환 (설정 변경 대응)."""
    d = settings.db_path / "_briefs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 목록 조회 ─────────────────────────────────────────────────────────────────

@router.get("/list")
def list_briefs():
    """저장된 지침서 분석 목록 (최신순). 각 항목에 다운로드 파일 존재 여부 포함."""
    briefs_dir = settings.db_path / "_briefs"
    if not briefs_dir.exists():
        return []

    items = []
    for p in sorted(briefs_dir.glob("*.json"), reverse=True):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
            bm   = meta.get("_brief_meta") or {}
            items.append({
                "brief_id":           p.stem,
                "facility_type":      bm.get("facility_type", ""),
                "brief_name":         bm.get("brief_name", ""),
                "analyzed_at":        bm.get("analyzed_at", ""),
                "source_format":      bm.get("source_format", "pdf"),
                "total_pages":        meta.get("total_pages", 0),
                "has_md":             (briefs_dir / f"{p.stem}.md").exists(),
                "has_xlsx":           (briefs_dir / f"{p.stem}.xlsx").exists(),
                "validation_summary": (meta.get("validation") or {}).get("summary", {}),
            })
        except Exception:
            pass
    return items


# ── 파일 다운로드 ──────────────────────────────────────────────────────────────

@router.get("/exports/{filename}")
def download_export(filename: str):
    """저장된 md / xlsx 다운로드. path traversal 방지."""
    # Path().name 으로 디렉터리 구분자 제거 — 결과가 원본과 다르면 비정상 경로
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(400, "잘못된 파일명입니다.")

    ext = Path(safe_name).suffix.lower()
    if ext not in (".md", ".xlsx"):
        raise HTTPException(400, "md 또는 xlsx 파일만 다운로드 가능합니다.")

    path = settings.db_path / "_briefs" / safe_name
    if not path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")

    media_type = {
        ".md":   "text/markdown; charset=utf-8",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[ext]
    resp = FileResponse(path, media_type=media_type, filename=safe_name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 분석 엔드포인트 (SSE) ─────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_brief(
    facility_type: str = Form(...),
    brief_name: str = Form(""),
    brief_pdf: UploadFile | None = File(None),
    brief_pdf_ref: str | None = Form(None),
):
    """
    지침서 PDF 단독 분석 + 체크리스트 내보내기.

    facility_type : FACILITY_TYPES 키 — axes rubric 결정
    brief_name    : 파일명 라벨 (비어있으면 datetime 만 사용)
    brief_pdf     : multipart 직접 업로드
    brief_pdf_ref : /api/upload 청크 업로드 file_ref

    SSE 스테이지:
      classify_brief → extract_brief → brief_reqs → validate → save → complete
    """
    if not settings.has_api_key():
        raise HTTPException(
            401,
            "API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.",
        )
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    # 파일 bytes 해소 — 청크 업로드(file_ref) 우선, 없으면 multipart
    upload_filename: str = ""
    if brief_pdf_ref:
        ref_path = resolve_file_ref(brief_pdf_ref)
        file_bytes = ref_path.read_bytes()
        upload_filename = ref_path.name
    elif brief_pdf:
        file_bytes = await brief_pdf.read()
        upload_filename = brief_pdf.filename or ""
    else:
        raise HTTPException(400, "brief_pdf 또는 brief_pdf_ref 중 하나가 필요합니다.")

    source_format = _validate_brief_file(file_bytes, upload_filename, "지침서 파일")

    async def event_stream():
        # _timestamp: 파이프라인 시작 시각(ms). 모든 SSE 이벤트에 포함 (ProgressLog 필수).
        ts      = int(time.time() * 1000)
        tmp_dir = Path(tempfile.mkdtemp(prefix="comp_brief_"))

        try:
            # ── 파일명 스템 생성 ───────────────────────────────────────────
            stamp    = time.strftime("%Y%m%d_%H%M%S")
            slug     = _slugify(brief_name.strip()) if brief_name.strip() else ""
            brief_id = f"{stamp}_{facility_type}_{slug}" if slug else f"{stamp}_{facility_type}"
            brief_id = brief_id[:120]   # Windows 경로 길이 여유 확보

            # ── 1. 분류 ─────────────────────────────────────────────────────
            classify_msg = "지침서 블록 분류 중" if source_format == "docx" else "지침서 페이지 분류 중"
            yield sse({
                "type": "stage", "stage": "classify_brief",
                "msg": classify_msg, "_timestamp": ts,
            })

            if source_format == "docx":
                docx_path = tmp_dir / "brief.docx"
                docx_path.write_bytes(file_bytes)

                yield sse({
                    "type": "progress", "step": "classify_brief",
                    "page": 0, "total": 1, "_timestamp": ts,
                })
                try:
                    blocks = await asyncio.to_thread(split_docx_to_blocks, str(docx_path))
                except Exception as e:
                    logger.error("DOCX 파싱 실패: %s", traceback.format_exc())
                    raise RuntimeError(f"DOCX 파싱 오류. PDF로 변환 후 재시도 권장: {type(e).__name__}: {e}") from e
                classifications = await classify_all_blocks_brief(blocks)
            else:
                pdf_path = tmp_dir / "brief.pdf"
                pdf_path.write_bytes(file_bytes)

                # rasterize 없이 즉시 총 페이지 수 파악 → 진행 바에 total 표시
                total_pages_hint = pdf_page_count(pdf_path)
                yield sse({
                    "type": "progress", "step": "classify_brief",
                    "page": 0, "total": total_pages_hint, "_timestamp": ts,
                })

                # 배치 완료마다 큐로 진행률 수신
                progress_q: asyncio.Queue = asyncio.Queue()
                classify_task = asyncio.ensure_future(
                    classify_all_pages_brief(pdf_path, progress_q)
                )
                while True:
                    done_count = await progress_q.get()
                    if done_count is None:
                        break
                    yield sse({
                        "type": "progress", "step": "classify_brief",
                        "page": done_count, "total": total_pages_hint, "_timestamp": ts,
                    })
                classifications = await classify_task

            total_pages = len(classifications)
            yield sse({
                "type": "done", "step": "classify_brief",
                "total_pages": total_pages, "_timestamp": ts,
            })

            # ── 2. 데이터 추출 ─────────────────────────────────────────────
            yield sse({
                "type": "stage", "stage": "extract_brief",
                "msg": "지침서 데이터 추출 중", "_timestamp": ts,
            })
            yield sse({
                "type": "progress", "step": "extract_brief",
                "page": 0, "total": 1, "_timestamp": ts,
            })
            if source_format == "docx":
                extractions = await extract_docx(
                    str(docx_path), page_map=classifications, is_brief=True,
                )
            else:
                extractions = await extract_pdf(
                    pdf_path, page_map=classifications, is_brief=True,
                )
            brief_data                = merge_extracted_data(classifications, extractions)
            brief_data["page_map"]    = classifications
            brief_data["total_pages"] = total_pages

            yield sse({
                "type": "progress", "step": "extract_brief",
                "page": 1, "total": 1, "_timestamp": ts,
            })
            yield sse({"type": "done", "step": "extract_brief", "_timestamp": ts})

            # ── 3. 요구사항 분석 ────────────────────────────────────────────
            yield sse({
                "type": "stage", "stage": "brief_reqs",
                "msg": "지침서 요구사항 분석 중", "_timestamp": ts,
            })
            brief_data["_requirements"] = await extract_brief_requirements(
                brief_data, facility_type,
            )
            yield sse({"type": "done", "step": "brief_reqs", "_timestamp": ts})

            # ── 4. 검증 (결정론적, LLM 없음) ───────────────────────────────
            # validate_brief()가 facility_type을 사용하므로 _brief_meta를 먼저 설정
            brief_data["_brief_meta"] = {
                "brief_id":      brief_id,
                "facility_type": facility_type,
                "brief_name":    brief_name.strip() or "",
                "analyzed_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source_format": source_format,
            }
            yield sse({
                "type": "stage", "stage": "validate",
                "msg": "지침서 검증 중", "_timestamp": ts,
            })
            brief_data.update(validate_brief(brief_data, brief_data["_requirements"]))
            validation   = brief_data.get("validation") or {}
            flag_summary = validation.get("summary") or {}
            yield sse({
                "type": "done", "step": "validate",
                "flags": {
                    "high":   flag_summary.get("high", 0),
                    "medium": flag_summary.get("medium", 0),
                    "low":    flag_summary.get("low", 0),
                },
                "flag_list": validation.get("flags") or [],
                "_timestamp": ts,
            })

            # ── 5. 저장 — JSON · MD · xlsx ──────────────────────────────────
            yield sse({
                "type": "stage", "stage": "save",
                "msg": "결과 저장 중 (JSON · MD · xlsx)", "_timestamp": ts,
            })
            briefs_dir = _briefs_dir()

            json_path  = briefs_dir / f"{brief_id}.json"
            md_path    = briefs_dir / f"{brief_id}.md"
            xlsx_path  = briefs_dir / f"{brief_id}.xlsx"

            try:
                _atomic_write(json_path, brief_data)
            except Exception as je:
                logger.error("brief save JSON error: %s", traceback.format_exc())
                raise RuntimeError(f"JSON 저장 실패: {type(je).__name__}: {je}") from je

            try:
                _sync_write(md_path, to_markdown(brief_data, validation))
            except Exception as me:
                logger.error("brief save MD error: %s", traceback.format_exc())
                raise RuntimeError(f"MD 저장 실패: {type(me).__name__}: {me}") from me

            try:
                _sync_write_bytes(xlsx_path, to_xlsx(brief_data, validation))
            except Exception as xe:
                logger.error("brief save XLSX error: %s", traceback.format_exc())
                raise RuntimeError(f"XLSX 저장 실패: {type(xe).__name__}: {xe}") from xe

            yield sse({"type": "done", "step": "save", "_timestamp": ts})

            # ── 완료 ───────────────────────────────────────────────────────
            yield sse({
                "type": "complete",
                "brief_id":           brief_id,
                "facility_type":      facility_type,
                "total_pages":        total_pages,
                "md_filename":        f"{brief_id}.md",
                "xlsx_filename":      f"{brief_id}.xlsx",
                "validation_summary": flag_summary,
                "source_format":      source_format,
                "_timestamp":         ts,
            })

        except Exception as e:
            logger.error("brief/analyze error: %s", traceback.format_exc())
            user_msg = str(e) if str(e) else type(e).__name__
            yield sse({"type": "error", "message": user_msg, "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
