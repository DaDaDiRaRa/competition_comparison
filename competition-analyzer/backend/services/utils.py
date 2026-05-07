import json
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
    full_pix = page.get_pixmap(matrix=matrix)

    w, h = full_pix.width, full_pix.height
    tile_w = w // cols
    tile_h = h // rows

    tiles = []
    for r in range(rows):
        for c in range(cols):
            x0 = c * tile_w
            y0 = r * tile_h
            x1 = x0 + tile_w if c < cols - 1 else w
            y1 = y0 + tile_h if r < rows - 1 else h
            clip = fitz.IRect(x0, y0, x1, y1)
            tile_pix = fitz.Pixmap(full_pix, clip)
            tiles.append(tile_pix.tobytes(fmt))

    doc.close()
    return tiles


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


# ── JSON 파싱 ─────────────────────────────────────────────────────────────────
def parse_json_response(text: str) -> dict:
    """Claude 응답에서 JSON 추출. ```json 펜스 자동 제거."""
    text = text.strip()
    for delim in ("```json", "```"):
        if delim in text:
            text = text.split(delim)[1].split("```")[0].strip()
            break
    return json.loads(text)


# ── SSE ───────────────────────────────────────────────────────────────────────
def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"