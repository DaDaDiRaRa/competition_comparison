"""fitz.get_text() 실제 유니코드 내용 확인 — 터미널 인코딩과 무관하게 파일로 저장"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.utils import get_page_text

PDFS = [
    Path(r"M:\06_설계사업6본부\설계사업6본부 4소\02 프로젝트\21046 하남 보바스병원 신축공사\사례조사- 착수계 샘플\설계공모 지침서_충북권 공공 어린이 재활의료센터.pdf"),
]

OUT = Path(__file__).parent / "e3_text_sample.txt"
lines = []

for pdf in PDFS:
    if not pdf.exists():
        lines.append(f"[NOT FOUND] {pdf.name}\n")
        continue
    lines.append(f"\n{'='*60}")
    lines.append(f"PDF: {pdf.name}")
    lines.append(f"{'='*60}")
    for i in range(12):
        t = get_page_text(pdf, i)
        stripped = t.strip()
        lines.append(f"\n--- p{i+1} ({len(stripped)}자) ---")
        lines.append(stripped[:500] if stripped else "(비어있음)")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"저장 완료: {OUT}")
