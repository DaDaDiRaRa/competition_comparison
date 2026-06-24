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
from services.data_extractor import extract_pdf, extract_docx, extract_hwpx, merge_extracted_data, extract_brief_requirements
from services.docx_loader import split_docx_to_blocks
from services.hwpx_loader import split_hwpx_to_blocks
from services.brief_validator import validate_brief
from services.brief_checklist_exporter import to_markdown, to_xlsx, to_html
from services.brief_advisor import interpret_brief
from services.utils import sse, user_error_msg as _user_error_msg, pdf_page_count

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_PDF_BYTES  = 200 * 1024 * 1024  # 200 MB
_MAX_DOCX_BYTES = 50 * 1024 * 1024   # 50 MB (DOCX / HWP / HWPX 공통)
_PDF_MAGIC      = b"%PDF"
_DOCX_MAGIC     = b"PK\x03\x04"          # ZIP/OOXML header
_HWPX_MAGIC     = b"PK\x03\x04"          # HWPX = ZIP 컨테이너 (DOCX 와 동일 시그니처)
_HWP_MAGIC      = b"\xd0\xcf\x11\xe0"    # HWP 5.x = OLE2 compound 컨테이너


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _validate_brief_file(data: bytes, filename: str, name: str = "파일") -> str:
    """확장자별 검증 후 형식 반환 ("pdf" | "docx" | "hwp" | "hwpx")."""
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
    if ext == ".hwpx":
        if len(data) > _MAX_DOCX_BYTES:
            raise HTTPException(
                400,
                f"{name}: 파일 크기가 {_MAX_DOCX_BYTES // 1024 // 1024}MB를 초과합니다 "
                f"({len(data) // 1024 // 1024}MB).",
            )
        if not data.startswith(_HWPX_MAGIC):
            raise HTTPException(400, f"{name}: HWPX(ZIP) 형식이 아닙니다.")
        return "hwpx"
    if ext == ".hwp":
        if len(data) > _MAX_DOCX_BYTES:
            raise HTTPException(
                400,
                f"{name}: 파일 크기가 {_MAX_DOCX_BYTES // 1024 // 1024}MB를 초과합니다 "
                f"({len(data) // 1024 // 1024}MB).",
            )
        if not data.startswith(_HWP_MAGIC):
            raise HTTPException(400, f"{name}: HWP(OLE2) 형식이 아닙니다.")
        return "hwp"
    raise HTTPException(400, "PDF, DOCX, HWP, HWPX 파일만 지원합니다.")


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
                "has_html":           (briefs_dir / f"{p.stem}.html").exists(),
                "has_insight":        bool(meta.get("_insight")),
                "validation_summary": (meta.get("validation") or {}).get("summary", {}),
            })
        except Exception:
            pass
    return items


# ── 파일 다운로드 ──────────────────────────────────────────────────────────────

@router.get("/exports/{filename}")
def download_export(filename: str):
    """저장된 md / xlsx / html 다운로드. path traversal 방지.

    html 은 브라우저 인라인 표시 (보기용), md/xlsx 는 attachment (다운로드).
    """
    # Path().name 으로 디렉터리 구분자 제거 — 결과가 원본과 다르면 비정상 경로
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(400, "잘못된 파일명입니다.")

    ext = Path(safe_name).suffix.lower()
    if ext not in (".md", ".xlsx", ".html"):
        raise HTTPException(400, "md / xlsx / html 파일만 다운로드 가능합니다.")

    path = settings.db_path / "_briefs" / safe_name
    if not path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")

    media_type = {
        ".md":   "text/markdown; charset=utf-8",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".html": "text/html; charset=utf-8",
    }[ext]
    if ext == ".html":
        # 인라인 표시 — filename 지정 시 attachment 가 되므로 생략하고 헤더 직접 설정
        resp = FileResponse(path, media_type=media_type)
        resp.headers["Content-Disposition"] = f'inline; filename="{safe_name}"'
    else:
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
    include_insight: bool = Form(True),
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
            classify_msg = "지침서 블록 분류 중" if source_format in ("docx", "hwp", "hwpx") else "지침서 페이지 분류 중"
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
            elif source_format in ("hwp", "hwpx"):
                hwpx_path = tmp_dir / f"brief.{source_format}"
                hwpx_path.write_bytes(file_bytes)

                yield sse({
                    "type": "progress", "step": "classify_brief",
                    "page": 0, "total": 1, "_timestamp": ts,
                })
                try:
                    blocks = await asyncio.to_thread(split_hwpx_to_blocks, str(hwpx_path))
                except Exception as e:
                    logger.error("HWP/HWPX 파싱 실패: %s", traceback.format_exc())
                    raise RuntimeError(f"HWP/HWPX 파싱 오류. PDF로 변환 후 재시도 권장: {type(e).__name__}: {e}") from e
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
            elif source_format in ("hwp", "hwpx"):
                extractions = await extract_hwpx(
                    str(hwpx_path), page_map=classifications, is_brief=True,
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

            # ── 4.5 AI 종합 해설 (옵션, LLM 1콜) ─────────────────────────────
            # 한 방 통합: 추출 직후 같은 run 에서 해설까지. 실패해도 추출 결과는 살림.
            brief_data["_insight"] = None
            if include_insight and settings.has_api_key():
                yield sse({
                    "type": "stage", "stage": "insight",
                    "msg": "AI 종합 해설 생성 중", "_timestamp": ts,
                })
                try:
                    brief_data["_insight"] = await interpret_brief(brief_data, facility_type)
                    yield sse({
                        "type": "done", "step": "insight",
                        "data_confidence": (brief_data["_insight"] or {}).get("data_confidence"),
                        "_timestamp": ts,
                    })
                except Exception as ie:
                    logger.error("brief insight error: %s", traceback.format_exc())
                    # 해설 실패는 비치명적 — 경고만 보내고 추출 산출물은 그대로 저장
                    yield sse({
                        "type": "insight_error",
                        "message": _user_error_msg(ie), "_timestamp": ts,
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
            html_path  = briefs_dir / f"{brief_id}.html"

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
                _sync_write(html_path, to_html(brief_data, validation))
            except Exception as he:
                logger.error("brief save HTML error: %s", traceback.format_exc())
                raise RuntimeError(f"HTML 저장 실패: {type(he).__name__}: {he}") from he

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
                "html_filename":      f"{brief_id}.html",
                "validation_summary": flag_summary,
                "source_format":      source_format,
                "has_insight":        bool(brief_data.get("_insight")),
                "_timestamp":         ts,
            })

        except Exception as e:
            logger.error("brief/analyze error: %s", traceback.format_exc())
            user_msg = str(e) if str(e) else type(e).__name__
            yield sse({"type": "error", "message": user_msg, "_timestamp": ts})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── AI 종합 해설 재생성 (옵션, 추출 재처리 없음) ──────────────────────────────

@router.post("/{brief_id}/interpret")
async def reinterpret_brief(brief_id: str):
    """저장된 지침서의 AI 종합 해설만 재생성 (LLM 1콜, PDF 재처리 없음).

    용도: 분석 시 해설을 껐다가 나중에 켜기 / 프롬프트 개선 후 기존 분석에 재적용.
    _brief.json 의 `_insight` 갱신 + HTML·xlsx·md 재렌더 (셋 다 AI 종합 해설 포함).
    """
    if not settings.has_api_key():
        raise HTTPException(401, "API 키가 설정되지 않았습니다. 설정 탭에서 입력해주세요.")

    safe_id = Path(brief_id).name
    if safe_id != brief_id:
        raise HTTPException(400, "잘못된 brief_id 입니다.")

    briefs_dir = settings.db_path / "_briefs"
    json_path  = briefs_dir / f"{safe_id}.json"
    if not json_path.exists():
        raise HTTPException(404, "지침서 분석을 찾을 수 없습니다.")

    try:
        brief_data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"지침서 JSON 로드 실패: {type(e).__name__}")

    facility_type = (brief_data.get("_brief_meta") or {}).get("facility_type", "")
    try:
        brief_data["_insight"] = await interpret_brief(brief_data, facility_type)
    except Exception as e:
        logger.error("reinterpret error: %s", traceback.format_exc())
        raise HTTPException(500, f"종합 해설 생성 실패: {_user_error_msg(e)}")

    validation = brief_data.get("validation") or {}
    try:
        _atomic_write(json_path, brief_data)
        _sync_write(briefs_dir / f"{safe_id}.html", to_html(brief_data, validation))
        _sync_write(briefs_dir / f"{safe_id}.md", to_markdown(brief_data, validation))
        _sync_write_bytes(briefs_dir / f"{safe_id}.xlsx", to_xlsx(brief_data, validation))
    except Exception as e:
        logger.error("reinterpret save error: %s", traceback.format_exc())
        raise HTTPException(500, f"저장 실패: {type(e).__name__}")

    ins = brief_data.get("_insight") or {}
    return {
        "brief_id":        safe_id,
        "has_insight":     bool(brief_data.get("_insight")),
        "data_confidence": ins.get("data_confidence"),
        "html_filename":   f"{safe_id}.html",
    }
