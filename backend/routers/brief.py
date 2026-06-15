"""
routers/brief.py — 지침서 단독 분석 엔드포인트

POST /api/brief/analyze            : 지침서 PDF → 분류·추출·요구사항·검증 → 저장 (SSE)
GET  /api/brief/exports/{filename} : md / xlsx 다운로드
GET  /api/brief/list               : 저장된 지침서 목록 (최신순)

저장 위치: {db_path}/_briefs/{YYYYMMDD_HHMMSS}_{facility_type}_{slug}.{json|md|xlsx}
파일 쓰기: _atomic_write (JSON) / _sync_write (text) / _sync_write_bytes (binary)
기존 accumulate / diagnose 파이프라인은 건드리지 않음.
"""
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
from services.db_manager import _atomic_write, _sync_write, _slugify
from services.page_classifier import classify_all_pages_brief
from services.data_extractor import extract_pdf, merge_extracted_data, extract_brief_requirements
from services.brief_validator import validate_brief
from services.brief_checklist_exporter import to_markdown, to_xlsx
from services.utils import sse, user_error_msg as _user_error_msg

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_PDF_BYTES = 200 * 1024 * 1024  # 200 MB
_PDF_MAGIC     = b"%PDF"


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _validate_pdf(data: bytes, name: str = "파일") -> None:
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(
            400,
            f"{name}: 파일 크기가 {_MAX_PDF_BYTES // 1024 // 1024}MB를 초과합니다 "
            f"({len(data) // 1024 // 1024}MB).",
        )
    if not data.startswith(_PDF_MAGIC):
        raise HTTPException(400, f"{name}: PDF 형식이 아닙니다.")


def _briefs_dir() -> Path:
    """호출 시점 db_path 기준 _briefs 디렉터리 반환 (설정 변경 대응)."""
    d = settings.db_path / "_briefs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sync_write_bytes(path: Path, data: bytes) -> None:
    """바이너리 파일 쓰기 + fsync — GCSFUSE write-back 캐시 플러시 보장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


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

    # PDF bytes 해소 — 청크 업로드(file_ref) 우선, 없으면 multipart
    if brief_pdf_ref:
        pdf_bytes = resolve_file_ref(brief_pdf_ref).read_bytes()
    elif brief_pdf:
        pdf_bytes = await brief_pdf.read()
    else:
        raise HTTPException(400, "brief_pdf 또는 brief_pdf_ref 중 하나가 필요합니다.")

    _validate_pdf(pdf_bytes, "지침서 PDF")

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

            # ── 1. 페이지 분류 ─────────────────────────────────────────────
            yield sse({
                "type": "stage", "stage": "classify_brief",
                "msg": "지침서 페이지 분류 중", "_timestamp": ts,
            })
            pdf_path = tmp_dir / "brief.pdf"
            pdf_path.write_bytes(pdf_bytes)

            yield sse({
                "type": "progress", "step": "classify_brief",
                "page": 0, "total": 1, "_timestamp": ts,
            })
            classifications = await classify_all_pages_brief(pdf_path)
            total_pages     = len(classifications)

            for cls in classifications:
                yield sse({
                    "type": "progress", "step": "classify_brief",
                    "page": cls["page"], "total": total_pages,
                    "page_type": cls["primary_type"], "_timestamp": ts,
                })
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
                "_timestamp": ts,
            })

            # ── 5. 저장 — JSON · MD · xlsx ──────────────────────────────────
            yield sse({
                "type": "stage", "stage": "save",
                "msg": "결과 저장 중 (JSON · MD · xlsx)", "_timestamp": ts,
            })
            briefs_dir = _briefs_dir()

            # 목록 API 파싱용 메타 — _brief.json 내부에 포함
            brief_data["_brief_meta"] = {
                "brief_id":      brief_id,
                "facility_type": facility_type,
                "brief_name":    brief_name.strip() or "",
                "analyzed_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            json_path  = briefs_dir / f"{brief_id}.json"
            md_path    = briefs_dir / f"{brief_id}.md"
            xlsx_path  = briefs_dir / f"{brief_id}.xlsx"

            _atomic_write(json_path, brief_data)
            _sync_write(md_path, to_markdown(brief_data, validation))
            _sync_write_bytes(xlsx_path, to_xlsx(brief_data, validation))

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
                "_timestamp":         ts,
            })

        except Exception as e:
            logger.error("brief/analyze error: %s", traceback.format_exc())
            yield sse({"type": "error", "message": _user_error_msg(e), "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
