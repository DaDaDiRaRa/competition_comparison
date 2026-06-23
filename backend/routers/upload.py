"""
upload.py — 대용량 PDF 청크 업로드 라우터

Cloud Run은 HTTP 요청을 32MB로 제한한다. 이 라우터는:
  1. /start  — 업로드 세션을 생성하고 upload_id를 반환
  2. /chunk/{upload_id} — 청크를 /tmp에 저장
  3. /finish/{upload_id} — 청크를 하나의 파일로 조립, file_ref 반환
  4. /cleanup/{upload_id} — 파이프라인 완료 후 임시 파일 삭제

파이프라인 엔드포인트는 file_ref를 받아 /tmp에서 직접 읽는다.
"""

import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

logger = logging.getLogger(__name__)
router = APIRouter()

_TMP = Path("/tmp/cc_uploads")
_MAX_CHUNK = 25 * 1024 * 1024   # 25MB (Cloud Run 32MB 한도 이내)
_MAX_TOTAL = 600 * 1024 * 1024  # 총 600MB 상한 (제출물 여러 개 합산)

# 허용 문서 컨테이너 시그니처. 청크 업로드는 제안서(PDF)뿐 아니라 지침서
# (DOCX/HWPX=ZIP, HWP=OLE2) 도 경유하므로 PDF 전용으로 막으면 25MB 초과
# 비-PDF 지침서 업로드가 깨진다. 정밀 타입 검증은 각 파이프라인(brief/_validate_brief_file 등)
# 에서 다시 수행하므로 여기서는 알려진 컨테이너인지만 coarse 하게 게이트한다.
_ALLOWED_MAGIC = (
    b"%PDF",          # PDF
    b"PK\x03\x04",    # ZIP/OOXML (DOCX·HWPX)
    b"\xd0\xcf\x11\xe0",  # OLE2 compound (HWP 5.x)
)


@router.post("/start")
async def start_upload():
    upload_id = str(uuid.uuid4())
    (_TMP / upload_id).mkdir(parents=True, exist_ok=True)
    return {"upload_id": upload_id}


@router.post("/chunk/{upload_id}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    session_dir = _TMP / upload_id
    if not session_dir.exists():
        raise HTTPException(404, "업로드 세션을 찾을 수 없습니다.")

    data = await chunk.read()
    if len(data) > _MAX_CHUNK:
        raise HTTPException(400, f"청크가 너무 큽니다 ({len(data)//1024//1024}MB > 25MB 한도).")

    # 누적 크기 검사
    existing = sum(f.stat().st_size for f in session_dir.glob("chunk_*"))
    if existing + len(data) > _MAX_TOTAL:
        raise HTTPException(400, f"파일 크기 합계가 {_MAX_TOTAL // 1024 // 1024}MB를 초과합니다.")

    (session_dir / f"chunk_{chunk_index:05d}").write_bytes(data)
    return {"ok": True, "chunk_index": chunk_index, "bytes": len(data)}


@router.post("/finish/{upload_id}")
async def finish_upload(upload_id: str, total_chunks: int = Form(...), filename: str = Form("file.pdf")):
    session_dir = _TMP / upload_id
    if not session_dir.exists():
        raise HTTPException(404, "업로드 세션을 찾을 수 없습니다.")

    out = session_dir / filename
    with out.open("wb") as f:
        for i in range(total_chunks):
            chunk_path = session_dir / f"chunk_{i:05d}"
            if not chunk_path.exists():
                raise HTTPException(400, f"청크 {i}가 누락됐습니다.")
            f.write(chunk_path.read_bytes())
            chunk_path.unlink()

    # 문서 컨테이너 매직 바이트 검사 (PDF / DOCX·HWPX=ZIP / HWP=OLE2)
    with out.open("rb") as f:
        magic = f.read(4)
    if not any(magic.startswith(sig) for sig in _ALLOWED_MAGIC):
        out.unlink()
        raise HTTPException(400, f"{filename}: 지원하지 않는 파일 형식입니다 (PDF/DOCX/HWP/HWPX).")

    file_ref = f"{upload_id}/{filename}"
    total_size = out.stat().st_size
    logger.info("Upload finished: %s (%d bytes)", file_ref, total_size)
    return {"file_ref": file_ref, "filename": filename, "size": total_size}


@router.delete("/cleanup/{upload_id}")
async def cleanup_upload(upload_id: str):
    session_dir = _TMP / upload_id
    if session_dir.exists():
        import shutil
        shutil.rmtree(session_dir, ignore_errors=True)
    return {"ok": True}


def resolve_file_ref(file_ref: str) -> Path:
    """file_ref → /tmp/cc_uploads/{upload_id}/{filename} 경로 반환. 경로 탐색 방지."""
    resolved = (_TMP / file_ref).resolve()
    if not str(resolved).startswith(str(_TMP.resolve())):
        raise HTTPException(400, "잘못된 file_ref입니다.")
    if not resolved.exists():
        raise HTTPException(400, f"업로드된 파일을 찾을 수 없습니다: {file_ref}")
    return resolved
