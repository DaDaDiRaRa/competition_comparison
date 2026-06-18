import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'backend')

from services.docx_loader import split_docx_to_blocks
from services.data_extractor import _extract_docx_eval_from_table

DOCX = r'C:\Users\20260102\Documents\카카오톡 받은 파일\1. 대전인재개발원 도시개발사업 설계용역_제안요청서(수정).docx'
blocks = split_docx_to_blocks(DOCX)

eval_blocks = []
for b in blocks:
    hdr = b.get('header_text') or ''
    if b.get('table_markdown') and ('배점' in hdr or '심사' in hdr or '평가' in hdr):
        eval_blocks.append(b)

print(f'Total blocks: {len(blocks)}')
print(f'Eval candidate blocks: {len(eval_blocks)}')
for b in eval_blocks[:5]:
    print(f'\n  Block {b["block_num"]}: {b["header_text"]!r}')
    print(f'  merge_info count: {len(b.get("merge_info") or [])}')
    md = b["table_markdown"] or ""
    print(f'  table_markdown[:400]:')
    print(md[:400])
    print()
    result = _extract_docx_eval_from_table(b)
    cats = result.get('evaluation_categories', [])
    print(f'  --> categories ({len(cats)}):')
    for c in cats[:6]:
        print(f'      name={c.get("name")!r}  pts={c.get("points")}  subs={c.get("sub_items")}  shared={c.get("shared_with")}')
