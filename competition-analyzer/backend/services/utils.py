import base64
import json
from pathlib import Path


def rasterize_pdf(pdf_path: Path, dpi: int = 150) -> list[tuple[bytes, int]]:
    """PDF를 JPEG 이미지 리스트로 변환. (jpeg_bytes, page_number_1indexed) 반환"""
    import fitz  # pymupdf

    # PDF 손상 시 복구 옵션으로 재시도
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        doc = fitz.open(str(pdf_path), pdf_preserve_links=False)

    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pages = []
    for i, page in enumerate(doc):
        try:
            pix = page.get_pixmap(matrix=matrix)
            pages.append((pix.tobytes("jpeg"), i + 1))
        except Exception:
            # 페이지 변환 실패 시 흰 페이지 추가
            blank_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, int(595*dpi/72), int(842*dpi/72)), True)
            blank_pix.set_colorspace(fitz.csRGB)
            pages.append((blank_pix.tobytes("jpeg"), i + 1))

    doc.close()
    return pages


def parse_json_response(text: str) -> dict:
    text = text.strip()
    for delim in ("```json", "```"):
        if delim in text:
            text = text.split(delim)[1].split("```")[0].strip()
            break
    return json.loads(text)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
