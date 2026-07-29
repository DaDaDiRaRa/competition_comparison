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
import base64
import json
import logging
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from config import settings, FACILITY_TYPES, facility_label
from routers.upload import resolve_file_ref
from services.db_manager import _atomic_write, _sync_write, _sync_write_bytes, _slugify
from services.page_classifier import classify_all_pages_brief, classify_all_blocks_brief
from services.data_extractor import extract_pdf, extract_docx, extract_hwpx, merge_extracted_data, extract_brief_requirements
from services.docx_loader import split_docx_to_blocks
from services.hwpx_loader import split_hwpx_to_blocks
from services.brief_validator import validate_brief
from services.brief_checklist_exporter import to_markdown, to_xlsx, to_html
from services.brief_advisor import interpret_brief
from services.brief_proposal import propose_project
from services.brief_proposal_report_generator import to_proposal_html
from services.brief_playbook import build_playbook
from services.brief_playbook_report_generator import to_playbook_html
from services.reference_cases import collect_reference_context
from services.utils import sse, user_error_msg as _user_error_msg, pdf_page_count, normalize_design_guidelines_grouped, html_file_response

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


def _merge_multi_brief_data(data_list: list[dict]) -> dict:
    """여러 파일의 brief_data를 첫 번째 파일 우선(first_wins)으로 병합.

    - design_guidelines_grouped: 모든 파일 연결 후 재정규화 (cross-file dedup)
    - _quantitative: 필드별 first non-null wins
    - page_map / total_pages: 합산
    - 나머지: 첫 번째 파일 비어있는 경우만 뒤 파일 값 사용
    """
    if len(data_list) == 1:
        return data_list[0]

    base = {k: v for k, v in data_list[0].items() if k != "_by_type"}

    # design_guidelines_grouped 전파일 수집 (나중에 재정규화)
    all_grouped: list[dict] = list(base.get("design_guidelines_grouped") or [])

    for extra in data_list[1:]:
        all_grouped.extend(extra.get("design_guidelines_grouped") or [])

        for key, val in extra.items():
            if key in ("_by_type", "design_guidelines_grouped", "page_map",
                       "total_pages", "_quantitative"):
                continue
            base_val = base.get(key)
            empty = base_val is None or base_val == "" or base_val == {} or base_val == []
            if empty:
                base[key] = val

    # design_guidelines_grouped 재정규화 (cross-file 중복 제거)
    base["design_guidelines_grouped"] = normalize_design_guidelines_grouped(all_grouped) if all_grouped else []

    # _quantitative: 필드별 first non-null wins
    merged_quant: dict = {}
    for d in data_list:
        for k, v in (d.get("_quantitative") or {}).items():
            if v is not None and k not in merged_quant:
                merged_quant[k] = v
    base["_quantitative"] = merged_quant

    # page_map / total_pages 합산
    all_pages: list[dict] = []
    for d in data_list:
        all_pages.extend(d.get("page_map") or [])
    base["page_map"] = all_pages
    base["total_pages"] = len(all_pages)

    # 장르는 합쳐진 brief_evaluation 전체 신호로 재판별 (first-wins 로 첫 파일 값만
    # 쓰면 공고문·지침서 중 한쪽 축만 반영됨). 결정론·LLM 0, 실패해도 무중단.
    try:
        from services.brief_genre import detect_brief_genre
        base["_brief_genre"] = detect_brief_genre(base)
    except Exception:
        pass

    return base


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
                "has_proposal":       (briefs_dir / f"{p.stem}_proposal.html").exists(),
                "has_playbook":       (briefs_dir / f"{p.stem}_playbook.html").exists(),
                "has_site_context":   bool(meta.get("_site_context")),
                "brief_genre":        (meta.get("_brief_genre") or {}).get("genre", "unknown"),
                "validation_summary": (meta.get("validation") or {}).get("summary", {}),
            })
        except Exception:
            pass
    return items


@router.delete("/{brief_id}")
def delete_brief(brief_id: str):
    """지침서 분석 1건의 모든 파생 파일 삭제 (json·md·xlsx·html·proposal·playbook·site).

    path traversal 방지 — brief_id 에 경로 구분자가 있으면 거부. `{brief_id}.*` 와
    `{brief_id}_*` 만 지워 다른 지침서(더 긴 slug)를 건드리지 않는다(구분자 경계).
    """
    safe_id = Path(brief_id).name
    # 경로 구분자 + glob 메타문자(* ? [ ]) 거부 — Path().name 은 슬래시만 막고 glob 은 못 막는다.
    # (막지 않으면 DELETE /brief/* 가 glob("*.*") 로 확장돼 전 지침서를 삭제 — 정상 brief_id 엔 무해)
    if safe_id != brief_id or not safe_id or any(c in safe_id for c in "*?[]"):
        raise HTTPException(400, "잘못된 brief_id 입니다.")

    briefs_dir = settings.db_path / "_briefs"
    if not briefs_dir.exists():
        raise HTTPException(404, "지침서를 찾을 수 없습니다.")

    # `{id}.ext`(원본·파생) + `{id}_suffix`(proposal/playbook/site) — 구분자로 경계 고정.
    targets = list(briefs_dir.glob(f"{safe_id}.*")) + list(briefs_dir.glob(f"{safe_id}_*"))
    targets = [p for p in targets if p.is_file()]
    if not targets:
        raise HTTPException(404, "지침서를 찾을 수 없습니다.")

    removed = 0
    for p in targets:
        try:
            p.unlink()
            removed += 1
        except Exception as e:
            logger.warning("지침서 파일 삭제 실패 %s: %s", p.name, e)

    return {"deleted": True, "brief_id": safe_id, "files_removed": removed}


# ── 파일 다운로드 ──────────────────────────────────────────────────────────────

@router.get("/exports/{filename}")
def download_export(filename: str, download: bool = Query(False)):
    """저장된 md / xlsx / html 다운로드. path traversal 방지.

    html 은 기본 브라우저 인라인 표시 (보기용). `?download=1` 이면 첨부 다운로드.
    md/xlsx 는 항상 attachment (다운로드).
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
        # 인라인 표시(기본) 또는 첨부 다운로드(?download=1). 한글 파일명 RFC 6266 처리는 헬퍼가 담당.
        return html_file_response(path, download=download, filename=safe_name)
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
    brief_pdf_refs: str | None = Form(None),   # JSON 배열 — 복수 파일 청크 업로드용
    include_insight: bool = Form(True),
    include_proposal: bool = Form(True),       # 기본 ON — 분석 한 방에 수주 제안서까지(대지·법 융합; 끄면 비용·지연 절감)
    site_address: str = Form(""),              # 선택 — 지침서에서 주소를 못 읽거나 틀릴 때 직접 고정(비우면 추출값)
):
    """
    지침서 분석 + 체크리스트 내보내기. 단일 파일 또는 복수 파일(혼합 포맷 가능) 지원.

    facility_type  : FACILITY_TYPES 키
    brief_name     : 파일명 라벨
    brief_pdf      : multipart 직접 업로드 (단일, 소파일용)
    brief_pdf_ref  : 청크 업로드 file_ref (단일)
    brief_pdf_refs : JSON 배열 ["ref1","ref2",...] (복수 파일, /api/upload 경유)

    SSE 스테이지:
      classify_brief → extract_brief (파일마다) → brief_reqs → validate → save → complete
    첫 번째 파일 우선 충돌 처리. design_guidelines_grouped 는 모든 파일 합산.
    """
    if not settings.has_api_key():
        raise HTTPException(
            401,
            "API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.",
        )
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {facility_type}")

    # 파일 목록 해소 — [(bytes, filename), ...]
    file_items: list[tuple[bytes, str]] = []
    if brief_pdf_refs:
        # 복수 파일: JSON 배열 of refs
        try:
            refs = json.loads(brief_pdf_refs)
        except Exception:
            raise HTTPException(400, "brief_pdf_refs가 유효한 JSON 배열이 아닙니다.")
        if not isinstance(refs, list) or not refs:
            raise HTTPException(400, "brief_pdf_refs 배열이 비어있습니다.")
        for ref in refs:
            ref_path = resolve_file_ref(ref)
            file_items.append((ref_path.read_bytes(), ref_path.name))
    elif brief_pdf_ref:
        ref_path = resolve_file_ref(brief_pdf_ref)
        file_items.append((ref_path.read_bytes(), ref_path.name))
    elif brief_pdf:
        file_items.append((await brief_pdf.read(), brief_pdf.filename or ""))
    else:
        raise HTTPException(400, "brief_pdf 또는 brief_pdf_ref(s) 중 하나가 필요합니다.")

    # 각 파일 형식 사전 검증 (event_stream 진입 전)
    validated_formats: list[str] = []
    for i, (fb, fn) in enumerate(file_items):
        validated_formats.append(
            _validate_brief_file(fb, fn, f"파일 {i + 1}")
        )

    async def event_stream():
        # _timestamp: 파이프라인 시작 시각(ms). 모든 SSE 이벤트에 포함 (ProgressLog 필수).
        ts      = int(time.time() * 1000)
        tmp_dir = Path(tempfile.mkdtemp(prefix="comp_brief_"))
        n_files = len(file_items)

        try:
            # ── 파일명 스템 생성 ───────────────────────────────────────────
            stamp    = time.strftime("%Y%m%d_%H%M%S")
            slug     = _slugify(brief_name.strip()) if brief_name.strip() else ""
            brief_id = f"{stamp}_{facility_type}_{slug}" if slug else f"{stamp}_{facility_type}"
            brief_id = brief_id[:120]   # Windows 경로 길이 여유 확보

            # ── 1+2. 파일별 분류 · 추출 루프 ────────────────────────────────
            all_brief_data: list[dict] = []
            source_files_meta: list[dict] = []

            for fi, (file_bytes, upload_filename) in enumerate(file_items):
                source_format = validated_formats[fi]
                file_label    = f"[{fi + 1}/{n_files}] " if n_files > 1 else ""

                # ── 1. 분류 ────────────────────────────────────────────────
                classify_msg = (
                    f"{file_label}지침서 블록 분류 중"
                    if source_format in ("docx", "hwp", "hwpx")
                    else f"{file_label}지침서 페이지 분류 중"
                )
                yield sse({
                    "type": "stage", "stage": "classify_brief",
                    "msg": classify_msg, "_timestamp": ts,
                })

                if source_format == "docx":
                    docx_path = tmp_dir / f"brief_{fi}.docx"
                    docx_path.write_bytes(file_bytes)
                    yield sse({
                        "type": "progress", "step": "classify_brief",
                        "page": 0, "total": 1, "_timestamp": ts,
                    })
                    try:
                        blocks = await asyncio.to_thread(split_docx_to_blocks, str(docx_path))
                    except Exception as e:
                        logger.error("DOCX 파싱 실패: %s", traceback.format_exc())
                        raise RuntimeError(
                            f"DOCX 파싱 오류 ({upload_filename}). PDF로 변환 후 재시도 권장: "
                            f"{type(e).__name__}: {e}"
                        ) from e
                    classifications = await classify_all_blocks_brief(blocks)

                elif source_format in ("hwp", "hwpx"):
                    hwpx_path = tmp_dir / f"brief_{fi}.{source_format}"
                    hwpx_path.write_bytes(file_bytes)
                    yield sse({
                        "type": "progress", "step": "classify_brief",
                        "page": 0, "total": 1, "_timestamp": ts,
                    })
                    try:
                        blocks = await asyncio.to_thread(split_hwpx_to_blocks, str(hwpx_path))
                    except Exception as e:
                        logger.error("HWP/HWPX 파싱 실패: %s", traceback.format_exc())
                        raise RuntimeError(
                            f"HWP/HWPX 파싱 오류 ({upload_filename}). PDF로 변환 후 재시도 권장: "
                            f"{type(e).__name__}: {e}"
                        ) from e
                    classifications = await classify_all_blocks_brief(blocks)

                else:  # pdf
                    pdf_path = tmp_dir / f"brief_{fi}.pdf"
                    pdf_path.write_bytes(file_bytes)
                    total_pages_hint = pdf_page_count(pdf_path)
                    yield sse({
                        "type": "progress", "step": "classify_brief",
                        "page": 0, "total": total_pages_hint, "_timestamp": ts,
                    })
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

                total_pages_i = len(classifications)
                yield sse({
                    "type": "done", "step": "classify_brief",
                    "total_pages": total_pages_i, "_timestamp": ts,
                })

                # ── 2. 데이터 추출 ─────────────────────────────────────────
                yield sse({
                    "type": "stage", "stage": "extract_brief",
                    "msg": f"{file_label}지침서 데이터 추출 중", "_timestamp": ts,
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

                partial_data              = merge_extracted_data(classifications, extractions)
                partial_data["page_map"]  = classifications
                partial_data["total_pages"] = total_pages_i
                all_brief_data.append(partial_data)
                source_files_meta.append({
                    "filename":      upload_filename,
                    "source_format": source_format,
                    "total_pages":   total_pages_i,
                })

                yield sse({
                    "type": "progress", "step": "extract_brief",
                    "page": 1, "total": 1, "_timestamp": ts,
                })
                yield sse({"type": "done", "step": "extract_brief", "_timestamp": ts})

            # ── 파일 합산 ──────────────────────────────────────────────────
            brief_data   = _merge_multi_brief_data(all_brief_data)
            total_pages  = brief_data.get("total_pages", 0)
            # source_format: 단일 포맷이면 그대로, 혼합이면 "multi"
            fmt_set      = {m["source_format"] for m in source_files_meta}
            source_format = next(iter(fmt_set)) if len(fmt_set) == 1 else "multi"

            # ── 3. 요구사항 분석 ────────────────────────────────────────────
            yield sse({
                "type": "stage", "stage": "brief_reqs",
                "msg": "지침서 요구사항 분석 중", "_timestamp": ts,
            })
            brief_data["_requirements"] = await extract_brief_requirements(
                brief_data, facility_type,
            )
            yield sse({"type": "done", "step": "brief_reqs", "_timestamp": ts})

            # 입찰(bid) 2층 배점 구조 — genre=="bid" 일 때만. requirements(상위 연면적 밴드)
            # + brief_evaluation(하위 PQ 100점표) 재배치. 결정론·LLM 0, 실패해도 무중단.
            try:
                from services.bid_structure import build_bid_structure
                bs = build_bid_structure(brief_data)
                if bs:
                    brief_data["_bid_structure"] = bs
            except Exception:
                logger.warning("_bid_structure 생성 실패 (무시)", exc_info=True)

            # ── 4. 검증 (결정론적, LLM 없음) ───────────────────────────────
            brief_data["_brief_meta"] = {
                "brief_id":      brief_id,
                "facility_type": facility_type,
                "brief_name":    brief_name.strip() or "",
                "analyzed_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source_format": source_format,
                "source_files":  source_files_meta,  # 복수 파일 상세
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
            briefs_dir = _briefs_dir()   # 이후 단계(대지분석·저장) 공유
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
                    yield sse({
                        "type": "insight_error",
                        "message": _user_error_msg(ie), "_timestamp": ts,
                    })

            # ── 4.7 대지·맥락 분석 (VWorld vision + 터읽기 실측, 자동) ──────
            #   (a) vision = 형상·접도·조망 등 위성/지적도 시각 판독 (기존, VWorld 키 있을 때)
            #   (b) measured = 터읽기 실측(인구지수·수급진단·재해·설계드라이버) — 형제앱, 키 무관·graceful
            brief_data["_site_context"] = None
            fe_sites = (brief_data.get("feasibility_export") or {}).get("sites") or []
            # 사용자 확정 주소(선택) — 지침서 추출을 신뢰 못 할 때 고정. 첫 부지 주소를 대체(envelope
            #   유지 → law 작동), 부지 테이블 없으면(청사류) 주소만 합성 부지(vision+measured, law skip).
            _addr_override = (site_address or "").strip()
            if _addr_override:
                if fe_sites:
                    fe_sites = [dict(fe_sites[0], address=_addr_override), *fe_sites[1:]]
                else:
                    fe_sites = [{"site_id": "부지1", "address": _addr_override}]
            addressed = [s for s in fe_sites if s.get("address")]
            if addressed:
                sc: dict = {}

                # 부지별 vision(VWorld) + measured(터읽기) — 다부지 비대칭 해소: 전 부지 각각(병렬).
                #   첫 부지 이미지만 히어로로 저장({brief_id}_site.jpg). vision 은 VWorld 키 있을 때만.
                #   sc 대표값(analysis·measured·matched_address…)=첫 부지(단일부지·기존 소비자 호환),
                #   sc["sites"]=전 부지 [{site_id, address, analysis, measured}].
                async def _analyze_site(idx: int, s: dict) -> dict:
                    addr = s.get("address")
                    out: dict = {"site_id": s.get("site_id"), "address": addr}
                    if settings.has_vworld_key():
                        try:
                            from services.vworld_analyzer import run_site_analysis
                            r = await run_site_analysis(
                                address=addr,
                                vworld_key=settings.vworld_api_key,
                                vworld_domain=settings.vworld_domain,
                                save_image_path=(briefs_dir / f"{brief_id}_site.jpg") if idx == 0 else None,
                            )
                            out["_vision"] = {k: v for k, v in r.items() if k != "image_jpeg_b64"}
                            out["analysis"] = r.get("analysis")
                        except Exception as se:
                            logger.warning("대지 vision 분석 실패 (비치명, %s): %s", addr, se)
                    try:
                        from services.teoilgi_client import fetch_board_context, use_type_for
                        m = await fetch_board_context(addr, use_type=use_type_for(facility_type))
                        if m:
                            out["measured"] = m
                    except Exception as me:
                        logger.warning("터읽기 실측 실패 (비치명, %s): %s", addr, me)
                    return out

                yield sse({
                    "type": "stage", "stage": "site_analysis",
                    "msg": f"대지·맥락 분석 중 ({len(addressed)}개 부지)", "_timestamp": ts,
                })
                _sr = await asyncio.gather(
                    *[_analyze_site(i, s) for i, s in enumerate(addressed)],
                    return_exceptions=True,
                )
                site_results = [r for r in _sr if isinstance(r, dict)]
                if site_results:
                    first = site_results[0]
                    sc.update(first.get("_vision") or {})   # 첫 부지 대표: matched_address·lat·lng·radius_m·analysis
                    if first.get("measured"):
                        sc["measured"] = first["measured"]
                    sc["sites"] = [{"site_id": r.get("site_id"), "address": r.get("address"),
                                    "analysis": r.get("analysis"), "measured": r.get("measured")}
                                   for r in site_results]
                yield sse({"type": "done", "step": "site_analysis", "_timestamp": ts})

                # 건축법 진단 되받기 (arch-law-diagnose) — 배치의 '법적 골격'.
                #   feasibility_export 허용 한도로 최대 매스 역산 → 진단 → 정북 일조사선·가로구역
                #   높이·건폐/용적 한도·심의여부. ARCH_LAW_API_URL 설정 시에만(게이트), 부지별 병렬,
                #   실패/필수값 결측 부지는 조용히 skip. brief 에 없는 매스 골격을 채운다.
                try:
                    from services import arch_law_client as alc
                    reqs = [(s, alc.to_request(s)) for s in fe_sites]
                    diag_targets = [(s, rq) for s, rq in reqs if rq]
                    if alc.is_enabled() and diag_targets:
                        yield sse({
                            "type": "stage", "stage": "law_diagnosis",
                            "msg": f"건축법 진단 중 ({len(diag_targets)}개 부지)", "_timestamp": ts,
                        })
                        diags = await asyncio.gather(
                            *[alc.diagnose(rq) for _, rq in diag_targets],
                            return_exceptions=True,
                        )
                        law_out: list[dict] = []
                        for (s, _rq), diag in zip(diag_targets, diags):
                            if isinstance(diag, Exception) or not diag:
                                continue
                            dig = alc.digest_diagnosis(diag, site=s)
                            if dig:
                                dig["site_id"] = s.get("site_id")
                                dig["address"] = s.get("address")
                                law_out.append(dig)
                        if law_out:
                            sc["law_diagnosis"] = law_out
                            # Phase 3: 배치 관련 조문 원문 각주 (arch-law-graph) — 전 부지 refs 배치
                            #   조회 1콜. graph 죽어도 골격 유지(graceful). found=false 는 제외(링크만).
                            try:
                                _ref_names = [ref.get("name") for d in law_out
                                              for ref in (d.get("law_refs") or []) if ref.get("name")]
                                if _ref_names:
                                    _texts = await alc.fetch_law_texts(_ref_names)
                                    if _texts:
                                        sc["law_texts"] = _texts
                            except Exception as ge:
                                logger.warning("법조문 원문 조회 실패 (비치명): %s", ge)
                            yield sse({"type": "done", "step": "law_diagnosis", "_timestamp": ts})
                        else:
                            yield sse({
                                "type": "law_diagnosis_error",
                                "message": "건축법 진단 미확보 (응답 없음) — 배점·envelope 근거로만 배치 진행",
                                "_timestamp": ts,
                            })
                except Exception as le:
                    logger.warning("건축법 진단 되받기 실패 (비치명): %s", le)

                brief_data["_site_context"] = sc or None

            # ── 4.8 수주 제안서 (옵션, LLM 1콜) — 추출+대지+법을 한 방에 종합 해석 ──
            #   include_proposal 시 propose_project 가 _insight(4.5)+_site_context(4.7: vision·
            #   measured·law_diagnosis)+배점을 종합해 placement·법적 골격까지 산출. 수집된 신호가
            #   버튼 없이 바로 소비됨. 실패해도 비치명(추출·해설·site_context 산출물 유지).
            if include_proposal and settings.has_api_key():
                yield sse({
                    "type": "stage", "stage": "proposal",
                    "msg": "수주 제안서 생성 중 (대지·법 융합, LLM)", "_timestamp": ts,
                })
                try:
                    proposal = await propose_project(brief_data, facility_type)
                    proposal["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    brief_data["_proposal"] = proposal   # 5단계 json 저장이 함께 씀
                    _sync_write(
                        briefs_dir / f"{brief_id}_proposal.html",
                        _render_proposal_html(brief_data, brief_id, briefs_dir,
                                              facility_type, brief_name or brief_id),
                    )
                    yield sse({
                        "type": "done", "step": "proposal",
                        "data_confidence": proposal.get("data_confidence"), "_timestamp": ts,
                    })
                except Exception as pe:
                    logger.error("brief proposal error: %s", traceback.format_exc())
                    yield sse({
                        "type": "proposal_error",
                        "message": _user_error_msg(pe), "_timestamp": ts,
                    })

            # ── 5. 저장 — JSON · MD · xlsx · html ──────────────────────────
            yield sse({
                "type": "stage", "stage": "save",
                "msg": "결과 저장 중 (JSON · MD · xlsx)", "_timestamp": ts,
            })

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
                "has_proposal":       bool(brief_data.get("_proposal")),
                "proposal_filename":  f"{brief_id}_proposal.html" if brief_data.get("_proposal") else None,
                "has_site_context":   bool(brief_data.get("_site_context")),
                "site_context":       brief_data.get("_site_context"),
                "brief_genre":        (brief_data.get("_brief_genre") or {}).get("genre", "unknown"),
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


# ── 프로젝트 수주 제안서 생성 (수주 전략 처방, 추출 재처리 없음) ──────────────

def _render_proposal_html(brief_data: dict, safe_id: str, briefs_dir: Path,
                          facility_type: str, brief_name: str) -> str:
    """_proposal → 자체완결 제안서 HTML (대지 위성 썸네일 base64 임베드). /propose·/analyze 공용.

    site_context·feasibility·bid_structure 를 함께 넘겨 법적 골격·대지·2층 배점 섹션까지 렌더.
    """
    site_context = brief_data.get("_site_context")
    site_image_b64 = ""
    if site_context:
        site_img_path = briefs_dir / f"{safe_id}_site.jpg"
        if site_img_path.exists():
            try:
                site_image_b64 = base64.standard_b64encode(site_img_path.read_bytes()).decode()
            except Exception:
                site_image_b64 = ""
    return to_proposal_html(
        brief_data["_proposal"], brief_name, facility_label(facility_type),
        site_context=site_context, site_image_b64=site_image_b64,
        feasibility=brief_data.get("feasibility_export"),
        bid_structure=brief_data.get("_bid_structure"),
    )


@router.post("/{brief_id}/propose")
async def propose_brief(brief_id: str):
    """저장된 지침서로 '프로젝트 수주 제안서'를 생성 (LLM 1콜, PDF 재처리 없음).

    AI 종합 해설(_insight)이 '사실 triage(해설가)'라면 제안서(_proposal)는
    '수주 전략(전략가)' — 같은 결정론 백본 위에서 핵심 테마·접근 방향·우선순위·
    리스크·착수 체크리스트를 제안한다. 사실 주장엔 근거 인용 유지, 당락 예측 아님.

    _brief.json 의 `_proposal` 갱신 + 별도 `{brief_id}_proposal.html` 렌더.
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

    bm            = brief_data.get("_brief_meta") or {}
    facility_type = bm.get("facility_type", "")
    brief_name    = bm.get("brief_name", "") or safe_id

    try:
        proposal = await propose_project(brief_data, facility_type)
    except Exception as e:
        logger.error("propose error: %s", traceback.format_exc())
        raise HTTPException(500, f"수주 제안서 생성 실패: {_user_error_msg(e)}")

    proposal["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    brief_data["_proposal"] = proposal
    proposal_filename = f"{safe_id}_proposal.html"

    try:
        _atomic_write(json_path, brief_data)
        _sync_write(
            briefs_dir / proposal_filename,
            _render_proposal_html(brief_data, safe_id, briefs_dir, facility_type, brief_name),
        )
    except Exception as e:
        logger.error("propose save error: %s", traceback.format_exc())
        raise HTTPException(500, f"저장 실패: {type(e).__name__}")

    return {
        "brief_id":          safe_id,
        "has_proposal":      True,
        "data_confidence":   proposal.get("data_confidence"),
        "proposal_filename": proposal_filename,
    }


# ── 경험 기반 처방 생성 (과거 축적 데이터 → 이 지침서 적용, 추출 재처리 없음) ──

@router.post("/{brief_id}/playbook")
async def build_brief_playbook(brief_id: str):
    """저장된 지침서로 '경험 기반 처방'을 생성 (최대 LLM 1콜, PDF 재처리 없음).

    같은 시설유형의 과거 당선·낙선 축적 데이터(reference_cases)를 읽어, 이 지침서에
    어떻게 적용할지 처방한다. interpret(해설가)·propose(전략가)와 별개인 세 번째 산출물.

    과거 데이터가 없으면 LLM 호출 없이 `has_playbook=False` 를 반환한다 (무료 게이트).
    있으면 `_brief.json` 의 `_playbook` 갱신 + 별도 `{brief_id}_playbook.html` 렌더.
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

    bm            = brief_data.get("_brief_meta") or {}
    facility_type = bm.get("facility_type", "")
    brief_name    = bm.get("brief_name", "") or safe_id

    # 무료 게이트 — 과거 축적 데이터 없으면 LLM 호출 전에 중단 (API 안 쓰는 단계 우선).
    if not collect_reference_context(facility_type):
        return {
            "brief_id":     safe_id,
            "has_playbook": False,
            "reason": (
                "이 시설유형에 축적된 과거 당선·낙선 데이터가 없어 경험 기반 처방을 만들 수 "
                "없습니다. '경쟁 공모 등록' 탭에서 같은 시설유형의 과거 공모(당락 라벨 포함)를 "
                "등록하고 비교분석을 실행해 데이터를 쌓으면 사용할 수 있습니다."
            ),
        }

    try:
        playbook = await build_playbook(brief_data, facility_type)
    except Exception as e:
        logger.error("playbook error: %s", traceback.format_exc())
        raise HTTPException(500, f"경험 기반 처방 생성 실패: {_user_error_msg(e)}")

    # build_playbook 내부 게이트가 sentinel 을 반환한 경우 (경합/캐시 등) — 저장 안 함.
    if not playbook.get("has_accumulated_data", False):
        return {
            "brief_id":     safe_id,
            "has_playbook": False,
            "reason":       (playbook.get("caveats") or ["축적된 과거 데이터가 없습니다."])[0],
        }

    playbook["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    brief_data["_playbook"] = playbook
    playbook_filename = f"{safe_id}_playbook.html"

    try:
        _atomic_write(json_path, brief_data)
        _sync_write(
            briefs_dir / playbook_filename,
            to_playbook_html(playbook, brief_name, facility_label(facility_type)),
        )
    except Exception as e:
        logger.error("playbook save error: %s", traceback.format_exc())
        raise HTTPException(500, f"저장 실패: {type(e).__name__}")

    return {
        "brief_id":          safe_id,
        "has_playbook":      True,
        "data_confidence":   playbook.get("data_confidence"),
        "playbook_filename": playbook_filename,
    }


# ── 대지·맥락 분석 (VWorld + Claude vision) ──────────────────────────────────

class SiteAnalyzeRequest(BaseModel):
    address: str                   # 분석할 주소 (지번 또는 도로명)
    radius_m: int = 500            # 분석 반경 (m)


@router.post("/{brief_id}/site-analyze")
async def analyze_site(brief_id: str, req: SiteAnalyzeRequest):
    """VWorld 위성+지적도 이미지 취득 → Claude vision 대지·맥락 분석.

    - VWorld API 키: settings.vworld_api_key (설정 탭에서 저장)
    - Anthropic API 키: X-Anthropic-Api-Key 헤더 (기존 경로)
    - 결과: _site_context 로 _brief.json 갱신 + {brief_id}_site.jpg 저장
    """
    if not settings.has_vworld_key():
        raise HTTPException(400, "VWorld API 키가 설정되지 않았습니다. 설정 탭에서 입력해주세요.")
    if not settings.has_api_key():
        raise HTTPException(401, "Anthropic API 키가 설정되지 않았습니다.")

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

    address = req.address.strip()
    if not address:
        raise HTTPException(400, "주소가 비어있습니다.")

    from services.vworld_analyzer import run_site_analysis
    image_filename = f"{safe_id}_site.jpg"
    image_path = briefs_dir / image_filename

    try:
        result = await run_site_analysis(
            address=address,
            vworld_key=settings.vworld_api_key,
            vworld_domain=settings.vworld_domain,
            radius_m=req.radius_m,
            save_image_path=image_path,
        )
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("site-analyze error: %s", traceback.format_exc())
        raise HTTPException(500, f"대지 분석 실패: {type(e).__name__}: {e}")

    # _site_context 저장 (_brief.json 갱신)
    site_ctx = {
        "address_input":   result["address_input"],
        "matched_address": result["matched_address"],
        "lat":             result["lat"],
        "lng":             result["lng"],
        "radius_m":        result["radius_m"],
        "image_filename":  image_filename,
        "analyzed_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        "analysis":        result["analysis"],
        "has_cadastral":   result.get("has_cadastral", False),
        "parcel_norm":     result.get("parcel_norm"),   # 실측 필지 경계(이미지 정규화 링) 또는 None
    }
    brief_data["_site_context"] = site_ctx
    try:
        _atomic_write(json_path, brief_data)
    except Exception as e:
        logger.error("site-analyze save error: %s", traceback.format_exc())
        raise HTTPException(500, f"저장 실패: {type(e).__name__}")

    return {
        "brief_id":        safe_id,
        "has_site_context": True,
        "matched_address": result["matched_address"],
        "lat":             result["lat"],
        "lng":             result["lng"],
        "image_filename":  image_filename,
        "analysis":        result["analysis"],
        "has_cadastral":   result.get("has_cadastral", False),
        "image_jpeg_b64":  result.get("image_jpeg_b64", ""),
    }


@router.get("/{brief_id}/site-image")
def get_site_image(brief_id: str):
    """저장된 대지 분석 위성 이미지 반환 (JPEG)."""
    safe_id = Path(brief_id).name
    if safe_id != brief_id:
        raise HTTPException(400, "잘못된 brief_id 입니다.")
    image_path = settings.db_path / "_briefs" / f"{safe_id}_site.jpg"
    if not image_path.exists():
        raise HTTPException(404, "대지 이미지가 없습니다. 대지 분석을 먼저 실행해주세요.")
    return FileResponse(image_path, media_type="image/jpeg")


@router.get("/{brief_id}/site-context")
def get_site_context(brief_id: str):
    """저장된 _site_context 반환 (이력 카드 표시용)."""
    safe_id = Path(brief_id).name
    if safe_id != brief_id:
        raise HTTPException(400, "잘못된 brief_id 입니다.")
    json_path = settings.db_path / "_briefs" / f"{safe_id}.json"
    if not json_path.exists():
        raise HTTPException(404, "지침서를 찾을 수 없습니다.")
    try:
        brief_data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"JSON 로드 실패: {type(e).__name__}")
    sc = brief_data.get("_site_context")
    if not sc:
        raise HTTPException(404, "대지 분석 결과가 없습니다.")
    return sc
