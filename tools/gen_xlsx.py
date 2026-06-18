"""Block 31 추출 결과로 xlsx Sheet2 구조 직접 확인."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'backend')

import types
_cfg = types.ModuleType("config")
class _S:
    model_id = "stub"; model_id_classify = "stub"
    dpi_classify = 72; dpi_extract = 120; extraction_priority_limit = 2
_cfg.settings = _S()
_cfg.axes_keys_for = lambda *a, **k: []
_cfg.PAGE_TYPES = set()
_cfg.BRIEF_PAGE_TYPES = set()
sys.modules["config"] = _cfg

_llm = types.ModuleType("services.llm_client")
_llm.call_messages = lambda **k: "{}"
sys.modules["services.llm_client"] = _llm

_utils = types.ModuleType("services.utils")
for _n in ("get_page_text","ocr_page","parse_json_response",
           "rasterize_pdf","rasterize_page_tiled","safe_encode_image"):
    setattr(_utils, _n, lambda *a, **k: None)
def _first(data, key):
    v = (data or {}).get(key) or {}
    if isinstance(v, list): v = v[0] if v else {}
    return v if isinstance(v, dict) else {}
def _as_list(data, key):
    v = (data or {}).get(key) or []
    return v if isinstance(v, list) else ([v] if v else [])
_utils._first = _first; _utils._as_list = _as_list
sys.modules["services.utils"] = _utils

from services.docx_loader import split_docx_to_blocks
from services.data_extractor import _extract_docx_eval_from_table
from services.brief_checklist_exporter import to_xlsx

DOCX = r'C:\Users\20260102\Documents\카카오톡 받은 파일\1. 대전인재개발원 도시개발사업 설계용역_제안요청서(수정).docx'

blocks = split_docx_to_blocks(DOCX)
# Block 31: '3.4 평가방법 > 구분 · 평가사항 · 배점'
block31 = next(b for b in blocks if b["block_num"] == 31)
result = _extract_docx_eval_from_table(block31)
cats = result.get("evaluation_categories", [])
print(f"categories ({len(cats)}):")
for c in cats:
    print(f"  name={c.get('name')!r}  pts={c.get('points')}  subs={c.get('sub_items')}  shared={c.get('shared_with')}")

# brief_data 최소 구성
brief_data = {
    "brief_evaluation": [{
        "evaluation_categories": cats,
        "total_points":         result.get("total_points"),
        "eval_method":          result.get("eval_method"),
        "jury":                 result.get("jury"),
        "disqualify":           result.get("disqualify"),
        "points_sum_warning":   result.get("points_sum_warning", False),
    }]
}

xlsx_bytes = to_xlsx(brief_data, {})
out = r'C:\Users\20260102\Downloads\test_sheet2.xlsx'
with open(out, 'wb') as f:
    f.write(xlsx_bytes)
print(f"\nSaved: {out}")
