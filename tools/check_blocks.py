"""DOCX 블록 구조 확인 — 요구사항 관련 블록 분석."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'backend')

from services.docx_loader import split_docx_to_blocks, get_block_source_text

DOCX = r'C:\Users\20260102\Documents\카카오톡 받은 파일\1. 대전인재개발원 도시개발사업 설계용역_제안요청서(수정).docx'
blocks = split_docx_to_blocks(DOCX)

print(f"총 블록 수: {len(blocks)}\n")
print(f"{'블록':>4}  {'헤더 (60자)':48}  {'단락수':>4}  {'표':>3}  {'source_len':>10}")
print("-" * 80)
for b in blocks:
    hdr = (b.get('header_text') or '')[:48]
    n_para = len(b.get('paragraphs') or [])
    has_table = bool(b.get('table_markdown'))
    src = get_block_source_text(b)
    print(f"{b['block_num']:>4}  {hdr:48}  {n_para:>4}  {'O' if has_table else '-':>3}  {len(src):>10}")

# 단락이 많고 표도 있는 블록 (요구사항 섹션 후보)
print("\n\n=== 단락 5개 이상이면서 source_len 1000 이상 블록 (요구사항 후보) ===\n")
for b in blocks:
    n_para = len(b.get('paragraphs') or [])
    src = get_block_source_text(b)
    if n_para >= 5 and len(src) >= 1000:
        hdr = b.get('header_text') or ''
        print(f"블록 {b['block_num']}: {hdr!r}")
        print(f"  단락수={n_para}, source_len={len(src)}, 표={'있음' if b.get('table_markdown') else '없음'}")
        # 단락 미리보기
        for p in (b.get('paragraphs') or [])[:5]:
            print(f"  | {p[:80]!r}")
        if n_para > 5:
            print(f"  | ... ({n_para-5}개 더)")
        print()
