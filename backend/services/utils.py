import io
import json
import threading
from pathlib import Path


# ── 래스터라이즈 ──────────────────────────────────────────────────────────────
# Claude Sonnet API는 이미지를 내부적으로 최장변 ~1568px로 리사이즈한다.
# 따라서 DPI를 올려봐야 Claude가 실제로 보는 해상도는 동일하다.
#   150 DPI → 2481x1755px → Claude 실효: 1568x1109px
#   200 DPI → 3308x2339px → Claude 실효: 1568x1108px  (파일만 3배 큼)
#
# 핵심 개선점:
#   1. JPEG → PNG : 손실 압축 제거. 소수점 숫자/작은 텍스트 오독 방지.
#   2. 타일 분할 : 정보 밀도가 높은 페이지(면적표 등)를 4분할해서 각각 전송.
#                  각 타일은 원본 대비 2배 실효 해상도로 Claude에게 보인다.

def rasterize_pdf(
    pdf_path: Path,
    dpi: int = 150,
    fmt: str = "png",
) -> list[tuple[bytes, int]]:
    """
    PDF를 이미지 리스트로 변환.

    Parameters
    ----------
    pdf_path : Path
        변환할 PDF 경로.
    dpi : int
        래스터라이즈 DPI. 분류용 72, 추출용 150 권장.
        (200 이상은 Claude API 리사이즈로 효과 없음 — 파일만 커짐)
    fmt : str
        "png" (기본, 무손실) 또는 "jpeg" (대역폭 절약 필요 시).

    Returns
    -------
    list of (image_bytes, page_number_1indexed)
    """
    import fitz  # pymupdf

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        doc = fitz.open(str(pdf_path), pdf_preserve_links=False)

    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pages = []

    for i, page in enumerate(doc):
        try:
            pix = page.get_pixmap(matrix=matrix)
            pages.append((pix.tobytes(fmt), i + 1))
        except Exception:
            # 변환 실패 시 빈 페이지 삽입
            w = int(595 * dpi / 72)
            h = int(842 * dpi / 72)
            blank = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), True)
            pages.append((blank.tobytes(fmt), i + 1))

    doc.close()
    return pages


def rasterize_page_tiled(
    pdf_path: Path,
    page_index: int,
    dpi: int = 150,
    fmt: str = "png",
    cols: int = 2,
    rows: int = 2,
) -> list[bytes]:
    """
    단일 페이지를 (cols × rows) 타일로 분할하여 반환.

    면적표(AREA_TABLE), 기술(TECHNICAL) 등 정보 밀도가 높은 페이지에 사용.
    각 타일은 Claude에게 전체 페이지 대비 (cols×rows)배 높은 실효 해상도로 보인다.
    예: 2×2 분할 → 타일 1개당 실효 해상도 약 2배 향상.

    Parameters
    ----------
    pdf_path : Path
    page_index : int   0-based 페이지 번호
    dpi : int
    fmt : str
    cols, rows : int   분할 열/행 수 (기본 2×2 = 4타일)

    Returns
    -------
    list of image_bytes, 좌→우, 위→아래 순서
    """
    import fitz

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        doc = fitz.open(str(pdf_path), pdf_preserve_links=False)

    page = doc[page_index]
    matrix = fitz.Matrix(dpi / 72, dpi / 72)

    # 페이지 좌표(point) 기준으로 분할 → page.get_pixmap(clip=...)에 직접 전달.
    # 픽셀 단위 Pixmap(source, IRect) 생성자는 일부 PyMuPDF 버전에서 시그니처
    # 매칭이 깨지므로 사용 금지.
    page_w = page.rect.width
    page_h = page.rect.height
    tile_w = page_w / cols
    tile_h = page_h / rows

    tiles = []
    for r in range(rows):
        for c in range(cols):
            x0 = c * tile_w
            y0 = r * tile_h
            x1 = page_w if c == cols - 1 else (c + 1) * tile_w
            y1 = page_h if r == rows - 1 else (r + 1) * tile_h
            clip = fitz.Rect(x0, y0, x1, y1)
            tile_pix = page.get_pixmap(matrix=matrix, clip=clip)
            tiles.append(tile_pix.tobytes(fmt))

    doc.close()
    return tiles


# ── PaddleOCR ─────────────────────────────────────────────────────────────────
# 무료 로컬 OCR. PowerPoint→PDF 변환본(이미지 기반)처럼 임베디드 텍스트가 없는 PDF에서
# Claude API 없이 텍스트/숫자를 인식한다.
# 싱글턴 패턴: 첫 호출 시 모델 로드(~수 초), 이후 재사용.
# 스레드 안전: asyncio.to_thread()로 병렬 호출될 수 있으므로 lock 보호.

_paddle_ocr_lock = threading.Lock()
_paddle_ocr_instance = None


def _get_paddle_ocr():
    global _paddle_ocr_instance
    with _paddle_ocr_lock:
        if _paddle_ocr_instance is None:
            from paddleocr import PaddleOCR  # noqa: PLC0415
            _paddle_ocr_instance = PaddleOCR(
                use_angle_cls=True,
                lang="korean",
                show_log=False,
            )
    return _paddle_ocr_instance


def ocr_page(pdf_path: Path, page_index: int, dpi: int = 300) -> str:
    """
    PaddleOCR로 PDF 페이지에서 텍스트 추출. 무료·로컬 실행.

    - dpi=300 : 150 DPI 대비 2배 해상도 → 작은 숫자/한글 인식률 향상.
    - 신뢰도 0.5 미만 라인은 제외.
    - PaddleOCR 미설치 또는 오류 시 빈 문자열 반환 (vision fallback 유도).
    """
    import io

    try:
        import numpy as np
        from PIL import Image as PILImage
    except ImportError:
        return ""

    try:
        ocr = _get_paddle_ocr()
    except Exception:
        return ""

    try:
        import fitz  # pymupdf

        doc = fitz.open(str(pdf_path))
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        img_bytes = pix.tobytes("png")
        doc.close()
    except Exception:
        return ""

    try:
        img_array = np.array(PILImage.open(io.BytesIO(img_bytes)).convert("RGB"))
        result = ocr.ocr(img_array, cls=True)
    except Exception:
        return ""

    if not result or not result[0]:
        return ""

    lines = []
    for line in result[0]:
        if line and len(line) >= 2:
            text_conf = line[1]
            if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                text, conf = text_conf[0], text_conf[1]
                if conf >= 0.5:
                    lines.append(str(text))

    return "\n".join(lines)


def has_embedded_text(pdf_path: Path, page_index: int, min_chars: int = 50) -> bool:
    """
    페이지에 임베딩된 텍스트가 있는지 확인.
    PPT→PDF 변환본(플래튼)은 False 반환.
    True인 경우 get_text()로 직접 추출 가능.
    """
    import fitz

    try:
        doc = fitz.open(str(pdf_path))
        text = doc[page_index].get_text("text")
        doc.close()
        return len(text.strip()) >= min_chars
    except Exception:
        return False


# ── 사용자 오류 메시지 ────────────────────────────────────────────────────────
def user_error_msg(e: Exception) -> str:
    """예외를 사용자가 이해할 수 있는 한국어 메시지로 변환."""
    msg = str(e)
    ml = msg.lower()

    # API / 인증
    if "illegal header" in ml or "localprotocol" in ml:
        return "API 키 형식이 잘못됐습니다. 설정 탭에서 API 키를 다시 입력해주세요 (따옴표·공백 없이 sk-ant-... 형식으로)."
    if "401" in msg or "api_key" in ml or "authentication" in ml or "invalid x-api-key" in ml:
        return "API 키가 올바르지 않습니다. 설정 탭에서 API 키를 다시 확인해주세요."
    if "api 키가 설정되지 않" in msg:
        return "API 키가 입력되지 않았습니다. 설정 탭에서 API 키를 입력해주세요."

    # 서버/네트워크
    if "502" in msg or "bad gateway" in ml:
        return "AI 서버에 일시적으로 접속할 수 없습니다. 잠시 후 다시 시도해주세요."
    if "503" in msg or "service unavailable" in ml:
        return "AI 서버가 점검 중입니다. 잠시 후 다시 시도해주세요."
    if "429" in msg or "rate limit" in ml or "too many requests" in ml:
        return "요청이 너무 많습니다. 잠시 기다렸다가 다시 시도해주세요."
    if "timeout" in ml or "timed out" in ml:
        return "처리 시간이 초과됐습니다. PDF 페이지 수가 많으면 나눠서 업로드해보세요."
    if "connection" in ml and ("refused" in ml or "reset" in ml or "error" in ml):
        return "서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도해주세요."

    # 파일 / PDF
    if "pdf" in ml or "fitz" in ml or "rasterize" in ml:
        return "PDF 파일을 읽는 중 오류가 발생했습니다. 파일이 손상되지 않았는지 확인해주세요."
    if "not found" in ml or "no such file" in ml:
        return "파일을 찾을 수 없습니다. 업로드가 완료됐는지 확인해주세요."
    if "파일 크기" in msg or "too large" in ml:
        return "파일 크기가 허용 한도를 초과했습니다. 더 작은 파일로 나눠서 업로드해주세요."

    # AI 응답 파싱
    if "json 파싱 실패" in ml or "json parseerror" in ml or "jsondecode" in ml:
        return "AI 응답을 해석하는 중 오류가 발생했습니다. 다시 시도하면 대부분 해결됩니다."
    if "블라인드 채점" in msg or "리빌 분석" in msg or "진단 json" in msg:
        return "AI가 분석 결과를 올바른 형식으로 반환하지 않았습니다. 다시 시도해주세요."

    # 메모리
    if "memory" in ml or "memoryerror" in ml:
        return "메모리가 부족합니다. PDF 파일 크기를 줄이거나 다른 파일을 닫고 다시 시도해주세요."

    # 기타 ValueError (우리가 직접 raise한 것 — 이미 한국어일 가능성 높음)
    if isinstance(e, ValueError) and any(c > '' for c in msg[:30]):
        return msg  # 이미 한국어 메시지면 그대로 반환

    # 최후 fallback — 기술적 코드 노출 없이
    return "예상치 못한 오류가 발생했습니다. 문제가 반복되면 화면을 새로고침하거나 관리자에게 문의해주세요."


# ── JSON 파싱 ─────────────────────────────────────────────────────────────────
def parse_json_response(text: str) -> dict:
    """Claude 응답에서 JSON 추출.

    복구 전략 (순서대로 시도):
    1. ```json / ``` 펜스 제거 후 직접 파싱
    2. 산문에 묻힌 JSON 블록 추출 (첫 { ~ 마지막 }, 또는 첫 [ ~ 마지막 ])
    3. trailing comma 제거 후 재파싱
    """
    import re as _re

    text = text.strip()

    # 1. 코드 펜스 제거
    for delim in ("```json", "```"):
        if delim in text:
            text = text.split(delim)[1].split("```")[0].strip()
            break

    # 2. 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. 산문에 묻힌 JSON 블록 추출 + trailing comma 복구
    for open_ch, close_ch in (('{', '}'), ('[', ']')):
        si = text.find(open_ch)
        ei = text.rfind(close_ch)
        if si != -1 and ei > si:
            candidate = text[si:ei + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                fixed = _re.sub(r',(\s*[}\]])', r'\1', candidate)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

    raise json.JSONDecodeError(
        f"JSON 파싱 실패 (복구 불가). 원문 앞 300자: {text[:300]}", text, 0
    )


# ── 이미지 크기 안전 인코딩 ───────────────────────────────────────────────────
def safe_encode_image(img_bytes: bytes, fmt: str = "png", max_bytes: int = 4_500_000) -> tuple[bytes, str]:
    """5MB 한도(여유 500KB)를 넘으면 자동으로 JPEG q=85 → q=70 → 다운스케일 폴백."""
    if len(img_bytes) <= max_bytes:
        return img_bytes, fmt

    import fitz

    pix = fitz.Pixmap(io.BytesIO(img_bytes))

    jpeg_bytes = pix.tobytes("jpeg", jpg_quality=85)
    if len(jpeg_bytes) <= max_bytes:
        return jpeg_bytes, "jpeg"

    jpeg_bytes = pix.tobytes("jpeg", jpg_quality=70)
    if len(jpeg_bytes) <= max_bytes:
        return jpeg_bytes, "jpeg"

    # 3차 폴백: 50% 다운스케일 후 JPEG
    scaled = fitz.Pixmap(pix)
    scaled.shrink(2)
    return scaled.tobytes("jpeg", jpg_quality=80), "jpeg"


# ── SSE ───────────────────────────────────────────────────────────────────────
def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"