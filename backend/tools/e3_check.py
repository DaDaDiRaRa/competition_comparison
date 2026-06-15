"""
E-3 검증 — Tier 0 라우팅 확인 (API 호출 없음)
각 PDF 페이지의 임베딩 텍스트 길이를 측정해 어떤 tier로 라우팅될지 보고.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # noqa: E402
from services.utils import get_page_text  # noqa: E402
from services.data_extractor import OCR_MIN_CHARS, DIGITAL_TEXT_EXCLUDE_TYPES  # noqa: E402

PDFS = [
    Path(r"M:\06_설계사업6본부\설계사업6본부 4소\02 프로젝트\21046 하남 보바스병원 신축공사\사례조사- 착수계 샘플\설계공모 지침서_충북권 공공 어린이 재활의료센터.pdf"),
]

PREVIEW_PAGES = 8  # 페이지별 상세 미리보기 수


def check(pdf_path: Path) -> None:
    if not pdf_path.exists():
        print(f"\n[NOT FOUND] {pdf_path.name}\n")
        return

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    doc.close()

    tier0, short, empty = 0, 0, 0
    rows = []

    for i in range(total):
        raw = get_page_text(pdf_path, i)
        stripped = raw.strip()
        l = len(stripped)

        if l == 0:
            tier = "EMPTY -> Vision"
            empty += 1
        elif l < OCR_MIN_CHARS:
            tier = f"short({l}ch) -> Vision"
            short += 1
        else:
            tier = f"Tier0 OK  ({l}ch)"
            tier0 += 1

        if i < PREVIEW_PAGES:
            preview = stripped[:70].replace("\n", " ")
            rows.append(f"  p{i+1:02d}  {tier:<28s}  \"{preview}\"")

    label = pdf_path.name[:55].encode("ascii", "replace").decode()
    print(f"\n{'='*70}")
    print(f"PDF: {label}")
    print(f"total {total}p  |  Tier0 candidates: {tier0}p  |  short: {short}p  |  empty: {empty}p")
    pct = tier0 / total * 100 if total else 0
    print(f"Tier0 ratio: {pct:.0f}%")
    print(f"\nFirst {PREVIEW_PAGES} pages:")
    for r in rows:
        print(r.encode("ascii", "replace").decode())
    if total > PREVIEW_PAGES:
        print(f"  ... ({total - PREVIEW_PAGES}p omitted)")

    print(f"\n[NOTE] These types skip Tier0 -> tiled/vision:")
    print(f"  {sorted(DIGITAL_TEXT_EXCLUDE_TYPES)}")


if __name__ == "__main__":
    print(f"OCR_MIN_CHARS = {OCR_MIN_CHARS}")
    print(f"DIGITAL_TEXT_EXCLUDE_TYPES = {sorted(DIGITAL_TEXT_EXCLUDE_TYPES)}")
    for p in PDFS:
        check(p)
    print("\nDone.")
