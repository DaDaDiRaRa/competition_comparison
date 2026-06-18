"""
test_docx_extractor.py — DOCX 분할/추출 단위 테스트

대상:
  - services.docx_loader.split_docx_to_blocks()
  - services.data_extractor._extract_docx_eval_from_table()

LLM 호출 없음. 모든 시나리오는 python-docx로 인메모리 docx 생성.

실행:
  cd backend
  ./venv/Scripts/python.exe -m pytest ../tests/test_docx_extractor.py -v
"""

from __future__ import annotations

import io
import sys
import types
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt

# ── sys.path / heavy-dep 스텁 (LLM/httpx 미설치 환경 대비) ───────────────────
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_STUBBED = False
try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")
    _STUBBED = True

# data_extractor 가 import 시 config / llm_client / utils 를 끌어옴 — 가벼운 스텁.
if "config" not in sys.modules:
    class _S:
        model_id = "stub"
        model_id_classify = "stub"
        dpi_classify = 72
        dpi_extract = 120
        extraction_priority_limit = 2
    _cfg = types.ModuleType("config")
    _cfg.settings = _S()
    _cfg.axes_keys_for = lambda *a, **k: []
    # page_classifier 가 import 시 사용하는 타입 집합 — 실제 config 값과 동일하게 채움
    _cfg.PAGE_TYPES = {
        "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
        "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
        "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION", "HEALTH_CENTER",
        "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY", "UNIT_PLAN",
        "INCENTIVE_TABLE", "BRANDING", "BUSINESS_VIABILITY", "AREA_INCREASE",
        "VIEW_ANALYSIS", "COMMUNITY_PROGRAM", "COMPANY_PORTFOLIO",
        "CONSTRUCTION_PLAN", "UNIT_PLAN_PENTHOUSE",
    }
    _cfg.BRIEF_PAGE_TYPES = {
        "BRIEF_OVERVIEW", "BRIEF_PROJECT_INFO", "BRIEF_SITE", "BRIEF_PROGRAM",
        "BRIEF_DESIGN_MASSING", "BRIEF_DESIGN_FACADE", "BRIEF_DESIGN_SUSTAIN",
        "BRIEF_DESIGN_SPECIAL", "BRIEF_DESIGN_GUIDE", "BRIEF_TECHNICAL",
        "BRIEF_REGULATIONS", "BRIEF_EVALUATION", "BRIEF_SUBMISSION", "BRIEF_ADMIN",
    }
    sys.modules["config"] = _cfg

if "services.llm_client" not in sys.modules:
    _llm = types.ModuleType("services.llm_client")
    _llm.call_messages = lambda **k: "{}"
    sys.modules["services.llm_client"] = _llm

if "services.utils" not in sys.modules:
    _utils = types.ModuleType("services.utils")
    for n in ("get_page_text", "ocr_page", "parse_json_response",
             "rasterize_pdf", "rasterize_page_tiled", "safe_encode_image"):
        setattr(_utils, n, lambda *a, **k: None)
    # 공유 dict 헬퍼 — 실제 utils.py 와 동일 동작 (test 시 import 가능하도록)
    def _first(data, key):
        v = (data or {}).get(key) or {}
        if isinstance(v, list):
            v = v[0] if v else {}
        return v if isinstance(v, dict) else {}
    def _as_list(data, key):
        v = (data or {}).get(key) or []
        return v if isinstance(v, list) else ([v] if v else [])
    _utils._first = _first
    _utils._as_list = _as_list
    sys.modules["services.utils"] = _utils

from services.docx_loader import split_docx_to_blocks   # noqa: E402
from services.data_extractor import _extract_docx_eval_from_table  # noqa: E402


# ── 헬퍼: 인메모리 docx 생성 ───────────────────────────────────────────────────
def _doc_to_path(doc, tmp_path: Path, name: str = "test.docx") -> str:
    p = tmp_path / name
    doc.save(str(p))
    return str(p)


def _set_run_font(run, *, bold: bool = False, size_pt: float | None = None):
    if bold:
        run.bold = True
    if size_pt is not None:
        run.font.size = Pt(size_pt)


def _add_vmerge_to_cell(cell, val: str | None = "continue"):
    """셀에 w:vMerge 요소 추가. val='restart' 시 시작 셀, None 시 continue."""
    tcPr = cell._tc.get_or_add_tcPr()
    vmerge = OxmlElement("w:vMerge")
    if val == "restart":
        vmerge.set(qn("w:val"), "restart")
    tcPr.append(vmerge)


# ════════════════════════════════════════════════════════════════════════════
# split_docx_to_blocks
# ════════════════════════════════════════════════════════════════════════════

def test_empty_docx_returns_no_blocks(tmp_path):
    """빈 docx — 블록 0개 반환, 에러 없음."""
    doc = Document()
    path = _doc_to_path(doc, tmp_path, "empty.docx")
    blocks = split_docx_to_blocks(path)
    assert blocks == []


def test_tables_only_three_blocks(tmp_path):
    """표만 있는 docx (표 3개) — 블록 3개, 각각 table_markdown 보유."""
    doc = Document()
    for i in range(3):
        tbl = doc.add_table(rows=2, cols=2)
        tbl.rows[0].cells[0].text = f"H1_{i}"
        tbl.rows[0].cells[1].text = f"H2_{i}"
        tbl.rows[1].cells[0].text = f"V1_{i}"
        tbl.rows[1].cells[1].text = f"V2_{i}"
    path = _doc_to_path(doc, tmp_path, "tables_only.docx")
    blocks = split_docx_to_blocks(path)
    assert len(blocks) == 3
    for i, b in enumerate(blocks):
        assert b["table_markdown"] is not None
        assert f"H1_{i}" in b["table_markdown"]
        assert f"V2_{i}" in b["table_markdown"]


def test_text_only_paragraphs_populated(tmp_path):
    """텍스트만 — 블록 분할되며 paragraphs 채워짐."""
    doc = Document()
    doc.add_heading("1. 사업개요", level=1)
    doc.add_paragraph("본 사업은 ABC 도시개발사업이다.")
    doc.add_paragraph("발주처는 XYZ 회사이다.")
    doc.add_heading("2. 입찰 절차", level=1)
    doc.add_paragraph("입찰은 공개입찰 방식이다.")
    path = _doc_to_path(doc, tmp_path, "text_only.docx")
    blocks = split_docx_to_blocks(path)

    # 최소 2개 헤딩 → 2개 이상 블록
    assert len(blocks) >= 2
    # 모든 블록의 paragraphs 채워졌는지
    total_paras = sum(len(b["paragraphs"]) for b in blocks)
    assert total_paras >= 3
    # 표 없음
    assert all(b["table_markdown"] is None for b in blocks)


def test_kt_case_no_heading_styles(tmp_path):
    """Heading 스타일 없이 폰트 휴리스틱(R2)으로 분할."""
    doc = Document()
    # 큰 글씨 단락 — 헤더 후보
    p1 = doc.add_paragraph()
    r1 = p1.add_run("제1장 사업개요")
    _set_run_font(r1, size_pt=18.0)
    doc.add_paragraph("이것은 본문 단락 1.")
    doc.add_paragraph("이것은 본문 단락 2.")
    # 새 헤더
    p2 = doc.add_paragraph()
    r2 = p2.add_run("제2장 입찰 절차")
    _set_run_font(r2, size_pt=18.0)
    doc.add_paragraph("입찰 본문 1.")

    path = _doc_to_path(doc, tmp_path, "kt_case.docx")
    blocks = split_docx_to_blocks(path)
    # 폰트 휴리스틱이 정상 작동하면 최소 2개 블록
    assert len(blocks) >= 2
    headers = [b["header_text"] for b in blocks]
    assert any("제1장 사업개요" in h for h in headers)
    assert any("제2장 입찰 절차" in h for h in headers)


def test_vmerge_cells_marked_in_table_markdown(tmp_path):
    """vMerge 병합 셀 — markdown에서 병합행은 빈 칸, merge_info 기록."""
    doc = Document()
    tbl = doc.add_table(rows=3, cols=2)
    tbl.rows[0].cells[0].text = "GROUP"
    tbl.rows[0].cells[1].text = "Detail A"
    # row 1: col 0 = continue, col 1 = "Detail B"
    _add_vmerge_to_cell(tbl.rows[0].cells[0], val="restart")
    _add_vmerge_to_cell(tbl.rows[1].cells[0], val=None)
    tbl.rows[1].cells[1].text = "Detail B"
    # row 2: col 0 = continue, col 1 = "Detail C"
    _add_vmerge_to_cell(tbl.rows[2].cells[0], val=None)
    tbl.rows[2].cells[1].text = "Detail C"

    path = _doc_to_path(doc, tmp_path, "vmerge.docx")
    blocks = split_docx_to_blocks(path)
    assert len(blocks) == 1
    blk = blocks[0]
    md = blk["table_markdown"]
    assert md is not None

    lines = md.split("\n")
    # 헤더 + 구분선 + 본문 2행 = 4줄 (3행 표지만 헤더 1행 포함이므로 본문 2행)
    # 본문 1행 (원본 row 1): col 0 가 vMerge continue → 빈 칸
    assert "|  |" in lines[2] or lines[2].startswith("| |")  # col 0 빈 칸
    # merge_info에 GROUP 행이 3행 merge로 기록되어야 함
    assert len(blk["merge_info"]) >= 1
    assert any(m["value"] == "GROUP" and m["merged_rows"] == 3 for m in blk["merge_info"])


def test_toc_pattern_compressed(tmp_path):
    """F1: TOC 패턴(\t숫자) 단락들은 "(목차)" 블록으로 압축."""
    doc = Document()
    # 비-TOC 헤더
    p1 = doc.add_paragraph()
    r1 = p1.add_run("제 안 요 청 서")
    _set_run_font(r1, size_pt=20.0)
    # TOC 항목 5개
    for i in range(5):
        doc.add_paragraph(f"제{i+1}장 사업개요\t{i+1}")
    # 다음 일반 본문
    doc.add_paragraph("본문 시작입니다.")

    path = _doc_to_path(doc, tmp_path, "toc.docx")
    blocks = split_docx_to_blocks(path)
    # 목차 블록 존재
    toc_headers = [b for b in blocks if "(목차)" in b["header_text"]]
    assert len(toc_headers) == 1
    # 5개 TOC 단락이 단일 블록의 paragraphs로 모임
    assert len(toc_headers[0]["paragraphs"]) == 5


def test_force_cut_at_30_paragraphs(tmp_path):
    """F3: 단락 30개 초과 시 강제 컷, "(계속)" suffix."""
    doc = Document()
    p1 = doc.add_paragraph()
    r1 = p1.add_run("긴 섹션")
    _set_run_font(r1, size_pt=20.0)
    # 35개 일반 단락
    for i in range(35):
        doc.add_paragraph(f"본문 단락 {i+1}.")

    path = _doc_to_path(doc, tmp_path, "force_cut.docx")
    blocks = split_docx_to_blocks(path)
    # "(계속)" 표시된 블록 존재
    continues = [b for b in blocks if "(계속)" in b["header_text"]]
    assert len(continues) >= 1, f"force-cut 트리거 안 됨 — blocks={[b['header_text'] for b in blocks]}"


# ════════════════════════════════════════════════════════════════════════════
# _extract_docx_eval_from_table
# ════════════════════════════════════════════════════════════════════════════

def _make_eval_block(table_md: str, merge_info: list[dict]) -> dict:
    return {
        "block_num": 1,
        "header_text": "심사기준",
        "paragraphs": [],
        "table_markdown": table_md,
        "merge_info": merge_info,
    }


def test_eval_normal_scoring_table():
    """정상 배점표 — total_points=100, categories 올바름."""
    md = "\n".join([
        "| 구분 | 평가사항 | 배점 |",
        "| --- | --- | --- |",
        "| 배치계획 | 적정성 | 30 |",
        "| 디자인 | 창의성 | 40 |",
        "| 친환경 | 인증 | 30 |",
    ])
    block = _make_eval_block(md, merge_info=[])
    result = _extract_docx_eval_from_table(block)
    assert result["total_points"] == 100
    cats = result["evaluation_categories"]
    assert len(cats) == 3
    names = [c["name"] for c in cats]
    assert "배치계획" in names
    assert "디자인" in names
    assert "친환경" in names
    pts = [c["points"] for c in cats]
    assert sorted(pts) == [30, 30, 40]


def test_eval_shared_with_merged_points_cell():
    """병합 셀 (배치+공간이 40 공유) — shared_with 배열 생성.

    원본 표:
      | 구분  | 평가사항 | 배점 |
      | 배치  | x       | 40   |  ← 배점 셀이 다음 행과 vMerge
      | 공간  | y       |      |  ← 배점 셀 continuation
      | 기술  | z       | 60   |

    merge_info: points_col(2) row=1 rows=2 value=40
                (markdown header가 lines[0], 구분선 lines[1], body 는 lines[2~])
    """
    md = "\n".join([
        "| 구분 | 평가사항 | 배점 |",
        "| --- | --- | --- |",
        "| 배치 | x | 40 |",
        "| 공간 | y |  |",
        "| 기술 | z | 60 |",
    ])
    # merge_info row 는 원본 table.rows 인덱스 (헤더 포함).
    # body[0]=원본 row1, body[1]=원본 row2.
    # 배점 병합은 원본 row 1~2 → row=1 merged_rows=2.
    merge_info = [{"row": 1, "col": 2, "merged_rows": 2, "value": "40"}]
    block = _make_eval_block(md, merge_info=merge_info)
    result = _extract_docx_eval_from_table(block)

    cats = result["evaluation_categories"]
    # 배치+공간 그룹 + 기술 = 2개
    assert len(cats) == 2
    grouped = [c for c in cats if c["shared_with"]]
    assert len(grouped) == 1
    assert grouped[0]["name"] == "배치"
    assert "공간" in grouped[0]["shared_with"]
    assert grouped[0]["points"] == 40
    # 단일 행 카테고리
    single = [c for c in cats if not c["shared_with"]]
    assert len(single) == 1
    assert single[0]["name"] == "기술"
    assert single[0]["points"] == 60
    # total_points = 40 + 60 = 100
    assert result["total_points"] == 100


def test_eval_subtotal_rows_excluded():
    """소계/합계 행 — 자동 제외, 카테고리에서 누락."""
    md = "\n".join([
        "| 구분 | 평가사항 | 배점 |",
        "| --- | --- | --- |",
        "| 배치 | x | 30 |",
        "| 디자인 | y | 40 |",
        "| 기술 | z | 30 |",
        "| 소계 |  | 70 |",
        "| 가격 | a | 30 |",
        "| 총계 |  | 100 |",
    ])
    block = _make_eval_block(md, merge_info=[])
    result = _extract_docx_eval_from_table(block)
    # 소계/총계 제외 → 4개 카테고리만
    cats = result["evaluation_categories"]
    names = [c["name"] for c in cats]
    assert "소계" not in names
    assert "총계" not in names
    assert "배치" in names and "디자인" in names and "기술" in names and "가격" in names
    # 총계 행이 100이면 그대로 total_points로 사용
    assert result["total_points"] == 100


def test_eval_no_points_column_returns_empty():
    """배점 컬럼 없는 표 — 빈 categories, 에러 없음."""
    md = "\n".join([
        "| 항목 | 설명 |",
        "| --- | --- |",
        "| 사업명 | 대전 ABC |",
        "| 위치 | 대전광역시 |",
    ])
    block = _make_eval_block(md, merge_info=[])
    result = _extract_docx_eval_from_table(block)
    assert result["evaluation_categories"] == []
    assert result["total_points"] is None


# ════════════════════════════════════════════════════════════════════════════
# unit_program[] merge + exporter rendering
# ════════════════════════════════════════════════════════════════════════════

def test_merge_unit_program_across_pages():
    """_merge_brief_project_info_pages — unit_program[] 항목들이 페이지 간 합쳐짐."""
    from services.data_extractor import _merge_brief_project_info_pages
    page_a = {
        "competition_name": "공모A", "sites": [
            {"site_id": "단일부지", "site_area_sqm": 100, "facilities": ["주거"]}
        ],
        "construction_cost_100m_won": None, "design_cost_100m_won": None,
        "construction_period_months": None, "budget_notes": [], "special_conditions": [],
        "unit_program": [
            {"block": "1,2BL", "tenure": "분양", "type_label": "84형",
             "area_text": "전용 85㎡", "ratio_text": "80%", "note": "조정가능"}
        ],
        "_page": 3,
    }
    page_b = {
        "competition_name": "공모A", "sites": [
            {"site_id": "단일부지", "floor_area_sqm": 500, "facilities": ["근린생활"]}
        ],
        "construction_cost_100m_won": None, "design_cost_100m_won": None,
        "construction_period_months": None, "budget_notes": [], "special_conditions": [],
        "unit_program": [
            # 동일 entry — 중복 제거 대상
            {"block": "1,2BL", "tenure": "분양", "type_label": "84형",
             "area_text": "전용 85㎡", "ratio_text": "80%", "note": "조정가능"},
            {"block": "3BL", "tenure": "임대", "type_label": "59형",
             "area_text": "전용 59㎡", "ratio_text": "20%", "note": "조정가능"},
            {"block": "근린생활시설", "tenure": "", "type_label": "",
             "area_text": "적정 규모", "ratio_text": "", "note": "전체 3% 이내"},
        ],
        "_page": 23,
    }
    merged = _merge_brief_project_info_pages([page_a, page_b])
    ups = merged.get("unit_program") or []
    # 중복 1개 제거 → 3개
    assert len(ups) == 3
    blocks = [u.get("block") for u in ups]
    assert "1,2BL" in blocks and "3BL" in blocks and "근린생활시설" in blocks


def test_exporter_renders_unit_program_in_xlsx(tmp_path):
    """to_xlsx — unit_program 행이 시트 1 에 나타남."""
    from services.brief_checklist_exporter import to_xlsx
    from openpyxl import load_workbook

    brief_data = {
        "_brief_meta": {"facility_type": "residential", "source_format": "docx",
                        "brief_id": "test", "brief_name": "테스트"},
        "brief_project_info": {
            "competition_name": "공모X",
            "sites": [{"site_id": "단일부지", "site_area_sqm": 1000,
                       "address": "서울시", "zoning": "주거"}],
            "construction_cost_100m_won": None, "design_cost_100m_won": None,
            "construction_period_months": None,
            "budget_notes": [], "special_conditions": [],
            "unit_program": [
                {"block": "1,2BL", "tenure": "분양", "type_label": "84형",
                 "area_text": "전용 85㎡", "ratio_text": "80%", "note": "조정가능"},
                {"block": "3BL", "tenure": "임대", "type_label": "59형",
                 "area_text": "전용 59㎡", "ratio_text": "20%", "note": ""},
                {"block": "공공기여시설", "tenure": "", "type_label": "",
                 "area_text": "4,800평", "ratio_text": "", "note": "용적률 400% 이내"},
            ],
        },
        "_quantitative": {},
    }
    xlsx_bytes = to_xlsx(brief_data, validation={"summary": {"high": 0, "medium": 0, "low": 0},
                                                 "flags": []})
    out = tmp_path / "out.xlsx"
    out.write_bytes(xlsx_bytes)

    wb = load_workbook(str(out))
    ws = wb["1.면적·프로그램"]
    # 셀 텍스트 합치기 — unit_program 컨텐츠가 있는지
    all_text = "\n".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    )
    assert "단위세대·시설별 분배" in all_text
    assert "1,2BL(분양)" in all_text
    assert "3BL(임대)" in all_text
    assert "공공기여시설" in all_text
    assert "84형" in all_text
    assert "4,800평" in all_text
    assert "용적률 400% 이내" in all_text


def test_exporter_renders_unit_program_in_md():
    """to_markdown — unit_program 행이 마크다운에 나타남."""
    from services.brief_checklist_exporter import to_markdown
    brief_data = {
        "_brief_meta": {"facility_type": "residential", "source_format": "docx",
                        "brief_id": "test", "brief_name": ""},
        "brief_project_info": {
            "competition_name": "공모X",
            "sites": [{"site_id": "단일부지"}],
            "construction_cost_100m_won": None, "design_cost_100m_won": None,
            "construction_period_months": None,
            "budget_notes": [], "special_conditions": [],
            "unit_program": [
                {"block": "1,2BL", "tenure": "분양", "type_label": "84형",
                 "area_text": "전용 85㎡", "ratio_text": "80%", "note": "조정가능"},
            ],
        },
        "_quantitative": {},
    }
    md = to_markdown(brief_data, validation={"summary": {"high": 0, "medium": 0, "low": 0},
                                             "flags": []})
    assert "단위세대·시설별 분배" in md
    assert "1,2BL(분양)" in md
    assert "84형" in md
    assert "전용 85㎡" in md
    assert "80%" in md


# ════════════════════════════════════════════════════════════════════════════
# Adjustment B — _merge_brief_project_info_pages: empty-site skip
# ════════════════════════════════════════════════════════════════════════════

def _make_pi_page(site_id: str, *, page: int, **site_overrides) -> dict:
    """공통 BRIEF_PROJECT_INFO 페이지 payload — site 1개만 포함."""
    site = {
        "site_id": site_id, "address": "", "zoning": "", "scope": "",
        "facilities": [], "site_area_sqm": None, "floor_area_sqm": None,
        "building_coverage_pct": None, "floor_area_ratio_pct": None,
        "max_height_m": None, "open_space_sqm": None, "open_space_notes": "",
    }
    site.update(site_overrides)
    return {
        "competition_name": "X", "organizer": None, "competition_type": None,
        "construction_cost_100m_won": None, "design_cost_100m_won": None,
        "construction_period_months": None,
        "budget_notes": [], "special_conditions": [], "unit_program": [],
        "sites": [site], "_page": page,
    }


def test_merge_drops_empty_orphan_site_when_other_has_data():
    """B: 한 페이지가 비어있는 site_id 만 보고 → 다른 페이지에 실값 있으면 빈 site 제거."""
    from services.data_extractor import _merge_brief_project_info_pages
    page_a = _make_pi_page("단일부지", page=3,
                            site_area_sqm=104223, address="대전")
    page_b = _make_pi_page("공동주택 1BL", page=40)  # 모든 필드 빈 양식 페이지
    merged = _merge_brief_project_info_pages([page_a, page_b])
    sites = merged["sites"]
    assert len(sites) == 1
    assert sites[0]["site_id"] == "단일부지"
    assert sites[0]["site_area_sqm"] == 104223


def test_merge_keeps_single_empty_site():
    """B: site 가 1개뿐인 경우는 비어있어도 유지 (사용자에게 '부지가 있긴 함' 정보)."""
    from services.data_extractor import _merge_brief_project_info_pages
    page = _make_pi_page("단일부지", page=3)   # 모든 필드 비어있음
    merged = _merge_brief_project_info_pages([page])
    sites = merged["sites"]
    assert len(sites) == 1
    assert sites[0]["site_id"] == "단일부지"


def test_merge_keeps_all_when_all_have_data():
    """B: 다중 부지 모두 실값 보유 → 모두 유지 (정상 다중 부지 케이스 회귀 방지)."""
    from services.data_extractor import _merge_brief_project_info_pages
    page = {
        "competition_name": "X", "organizer": None, "competition_type": None,
        "construction_cost_100m_won": None, "design_cost_100m_won": None,
        "construction_period_months": None,
        "budget_notes": [], "special_conditions": [], "unit_program": [],
        "sites": [
            {"site_id": "부지1", "site_area_sqm": 100, "address": "주소1",
             "zoning": "", "scope": "", "facilities": [],
             "floor_area_sqm": None, "building_coverage_pct": None,
             "floor_area_ratio_pct": None, "max_height_m": None,
             "open_space_sqm": None, "open_space_notes": ""},
            {"site_id": "부지2", "site_area_sqm": 200, "address": "주소2",
             "zoning": "", "scope": "", "facilities": [],
             "floor_area_sqm": None, "building_coverage_pct": None,
             "floor_area_ratio_pct": None, "max_height_m": None,
             "open_space_sqm": None, "open_space_notes": ""},
        ],
        "_page": 3,
    }
    merged = _merge_brief_project_info_pages([page])
    assert {s["site_id"] for s in merged["sites"]} == {"부지1", "부지2"}


# ════════════════════════════════════════════════════════════════════════════
# Adjustment A — page_classifier: 양식/별첨 헤더 강등
# ════════════════════════════════════════════════════════════════════════════

def test_form_header_downgrades_brief_project_info():
    """A: [서식N] / [양식N] / 별첨 / 부록 헤더 + BRIEF_PROJECT_INFO → BRIEF_SUBMISSION 강등."""
    from services.page_classifier import _normalise_brief_result
    for hdr in ("[서식3] 건축개요 및 시설별 면적표",
                "[서식 4] 단위세대 면적표",
                "[양식 1] 견적서",
                "별첨 #2 용역범위 구분표",
                "부록 A",
                "Appendix B"):
        result = _normalise_brief_result({
            "type": "BRIEF_PROJECT_INFO", "confidence": 0.85,
            "has_table": True, "has_text": True,
            "page_header_text": hdr,
        })
        assert result["primary_type"] == "BRIEF_SUBMISSION", \
            f"헤더 '{hdr}' 강등 실패 (got {result['primary_type']})"


def test_normal_project_info_header_unaffected():
    """A: 일반 사업개요 헤더는 강등 영향 없음 (PDF/영등포 회귀 방지)."""
    from services.page_classifier import _normalise_brief_result
    for hdr in ("1.2 사업개요",
                "제3장 제안서 작성지침 > 3.1 계획 개요",
                "사업 개요"):
        result = _normalise_brief_result({
            "type": "BRIEF_PROJECT_INFO", "confidence": 0.90,
            "has_table": True, "has_text": True,
            "page_header_text": hdr,
        })
        assert result["primary_type"] == "BRIEF_PROJECT_INFO", \
            f"헤더 '{hdr}' 가 잘못 강등됨"


def test_form_header_on_other_types_unaffected():
    """A: 양식 헤더라도 BRIEF_PROJECT_INFO 가 아니면 강등 대상 아님."""
    from services.page_classifier import _normalise_brief_result
    result = _normalise_brief_result({
        "type": "BRIEF_SUBMISSION", "confidence": 0.9,
        "has_table": True, "has_text": True,
        "page_header_text": "[서식3] 건축개요 및 시설별 면적표",
    })
    assert result["primary_type"] == "BRIEF_SUBMISSION"


# ════════════════════════════════════════════════════════════════════════════
# Adjustment C — _extract_docx_unit_program_from_table
# ════════════════════════════════════════════════════════════════════════════

def _make_unit_block(table_md: str) -> dict:
    return {
        "block_num": 1, "header_text": "3.1 계획 개요",
        "paragraphs": [], "table_markdown": table_md, "merge_info": [],
    }


def test_unit_program_extracts_all_distribution_rows():
    """C: KT 케이스 — 1,2BL 분양 + 3BL 임대 + 시설 행 모두 추출."""
    from services.data_extractor import _extract_docx_unit_program_from_table
    md = "\n".join([
        "| 구 분 | 평형 | 면적 | 비율 | 비 고 |",
        "| --- | --- | --- | --- | --- |",
        "| 1,2BL (분양) | 84형 | 전용 85㎡ 내외 | 80% 내외 | 비율조정 가능 |",
        "| 1,2BL (분양) | 59~110형 | 전용 59~110㎡ 내외 | 20% 내외 | 비율조정 가능 |",
        "| 3BL (임대) | 59형 | 전용 59㎡ 내외 | 20% 내외 | 비율조정 가능 |",
        "| 3BL (임대) | 84형 | 전용 85㎡ 내외 | 80% 내외 | 비율조정 가능 |",
        "| 근린생활시설 |  | 적정 규모 제안 |  | 전체 연면적의 3% 이내 |",
        "| 공공기여시설 |  | 4,800평 |  | 용적률 400% 이내 |",
    ])
    rows = _extract_docx_unit_program_from_table(_make_unit_block(md))
    blocks_set = {r["block"] for r in rows}
    # 4개 카테고리 모두 등장
    assert "1,2BL" in blocks_set
    assert "3BL" in blocks_set
    assert any("근린생활시설" in b for b in blocks_set)
    assert any("공공기여시설" in b for b in blocks_set)
    # 분양/임대 tenure 식별
    tenures = {r["tenure"] for r in rows}
    assert "분양" in tenures and "임대" in tenures
    # type_label
    types = {r["type_label"] for r in rows if r["type_label"]}
    assert "84형" in types and "59형" in types and "59~110형" in types
    # 전체 행 수: 1,2BL 2종 + 3BL 2종 + 근린 + 공공 = 6
    assert len(rows) == 6


def test_unit_program_skips_scoring_table():
    """C: 배점표는 분배표가 아니므로 빈 결과 (영등포 회귀 방지)."""
    from services.data_extractor import _extract_docx_unit_program_from_table
    md = "\n".join([
        "| 구분 | 평가사항 | 배점 |",
        "| --- | --- | --- |",
        "| 디자인 | x | 30 |",
        "| 친환경 | y | 40 |",
    ])
    rows = _extract_docx_unit_program_from_table(_make_unit_block(md))
    assert rows == []


def test_unit_program_skips_empty_template_table():
    """C: 빈 양식 면적표 ([서식4] 단위세대 면적표 같은 케이스) — area/ratio 빈 행 차단.

    Adjustment A 가 [서식N] 헤더를 BRIEF_SUBMISSION 으로 강등하므로 실제 파이프라인에선
    이 함수 호출 안 됨. 그래도 C 단독 호출 시 false positive 차단해야 회귀 안전.
    """
    from services.data_extractor import _extract_docx_unit_program_from_table
    md = "\n".join([
        "| 구 분 | 유 형 | 세대수 | 전용 면적 | 비고 |",
        "| --- | --- | --- | --- | --- |",
        "| 공동 주택 (1BL) | 00 ty (평형) |  |  |  |",
        "| 공동 주택 (1BL) | 00 ty (평형) |  |  |  |",
        "| 공동 주택 (2BL) | 00 ty (평형) |  |  |  |",
    ])
    rows = _extract_docx_unit_program_from_table(_make_unit_block(md))
    assert rows == []


def test_unit_program_skips_simple_metadata_table():
    """C: 사업명/위치 같은 메타데이터 표는 빈 결과 (Block #3 사업개요 표 회귀 방지)."""
    from services.data_extractor import _extract_docx_unit_program_from_table
    md = "\n".join([
        "| 사 업 명 | 사 업 명 | 대전인재개발원 도시개발사업 설계용역 |",
        "| --- | --- | --- |",
        "| 대지위치 | 대지위치 | 대전광역시 서구 |",
        "| 시설 개요 | 대지면적 | 104,223㎡ |",
    ])
    rows = _extract_docx_unit_program_from_table(_make_unit_block(md))
    # 시설개요/대지위치 등은 block 패턴에 안 맞으므로 빈 결과
    assert rows == []


def test_unit_program_merge_dedupes_by_block_and_type_label():
    """C: LLM + 표 머지 — (block, type_label) 동일한 entry 중복 제거."""
    from services.data_extractor import _merge_unit_program_rows
    llm = [{"block": "1,2BL", "tenure": "분양", "type_label": "84형",
            "area_text": "85㎡", "ratio_text": "80%", "note": "조정"}]
    table = [
        {"block": "1,2BL", "tenure": "분양", "type_label": "84형",
         "area_text": "85㎡", "ratio_text": "80%", "note": "조정"},   # dup → skip
        {"block": "3BL", "tenure": "임대", "type_label": "59형",
         "area_text": "59㎡", "ratio_text": "20%", "note": ""},        # new
    ]
    merged = _merge_unit_program_rows(llm, table)
    assert len(merged) == 2
    keys = {(r["block"], r["type_label"]) for r in merged}
    assert keys == {("1,2BL", "84형"), ("3BL", "59형")}


# ════════════════════════════════════════════════════════════════════════════
# design_guidelines_grouped[] — 스키마 보존 + merge + exporter 렌더링
# ════════════════════════════════════════════════════════════════════════════

def test_docx_loader_emits_label_pattern_hint(tmp_path):
    """docx_loader: 가)/나)/다) 또는 1)/2) 글머리가 있으면 source text 에 힌트 출력."""
    from services.docx_loader import split_docx_to_blocks, get_block_source_text
    doc = Document()
    p1 = doc.add_paragraph()
    r1 = p1.add_run("3.2.3 계획지침")
    _set_run_font(r1, size_pt=18.0)
    doc.add_paragraph("1) 토지이용 및 배치계획")
    doc.add_paragraph("가) 대지 주변의 토지이용을 고려한다.")
    doc.add_paragraph("나) 교통편의 시설과의 연계성을 고려한다.")
    doc.add_paragraph("2) 단지계획")
    doc.add_paragraph("가) 인공구조물은 최소화한다.")

    path = _doc_to_path(doc, tmp_path, "labels.docx")
    blocks = split_docx_to_blocks(path)
    assert blocks
    src = get_block_source_text(blocks[0])
    # 힌트 라인이 포함되어야 함
    assert "[LABEL_PATTERNS_DETECTED]" in src
    # 1) 와 가) 둘 다 감지돼야 함
    hint_line = next(l for l in src.split("\n") if l.startswith("[LABEL_PATTERNS_DETECTED]"))
    assert "1)" in hint_line and "가)" in hint_line


def test_merge_aggregates_design_guidelines_grouped():
    """merge_extracted_data: 여러 BRIEF_DESIGN_* / BRIEF_PROGRAM 페이지의 grouped[] 단일 리스트로 집계."""
    from services.data_extractor import merge_extracted_data
    classifications = [
        {"page": 1, "primary_type": "BRIEF_DESIGN_MASSING"},
        {"page": 2, "primary_type": "BRIEF_DESIGN_FACADE"},
        {"page": 3, "primary_type": "BRIEF_PROGRAM"},
    ]
    extractions = [
        {"page": 1, "type": "BRIEF_DESIGN_MASSING", "data": {
            "design_guidelines_grouped": [
                {"facility_scope": "전체", "space_scope": "전체", "category": "배치계획",
                 "section_path": "3.2.3 > 1) 토지이용", "items": [
                     {"label": "가)", "text": "대지 주변 ..."},
                     {"label": "나)", "text": "교통편의 ..."},
                 ]}
            ]}},
        {"page": 2, "type": "BRIEF_DESIGN_FACADE", "data": {
            "design_guidelines_grouped": [
                {"facility_scope": "전체", "space_scope": "전체", "category": "입면·재료",
                 "section_path": "3.2.3 > 5) 입면", "items": [
                     {"label": "가)", "text": "지역의 랜드마크 ..."},
                 ]}
            ]}},
        {"page": 3, "type": "BRIEF_PROGRAM", "data": {
            "design_guidelines_grouped": [
                {"facility_scope": "구청", "space_scope": "간부공간", "category": "공간구성",
                 "section_path": "II.3 > ① 구청 > 간부공간", "items": [
                     {"label": "-", "text": "직무공간의 배치를 고려 ..."},
                 ]}
            ]}},
    ]
    merged = merge_extracted_data(classifications, extractions)
    grouped = merged.get("design_guidelines_grouped") or []
    assert len(grouped) == 3
    scopes = {(g["facility_scope"], g["category"]) for g in grouped}
    assert ("전체", "배치계획") in scopes
    assert ("전체", "입면·재료") in scopes
    assert ("구청", "공간구성") in scopes


def test_merge_dedupes_grouped_by_section_path():
    """같은 section_path + 같은 첫 항목 텍스트면 중복 제거."""
    from services.data_extractor import merge_extracted_data
    classifications = [
        {"page": 1, "primary_type": "BRIEF_DESIGN_GUIDE"},
        {"page": 2, "primary_type": "BRIEF_DESIGN_GUIDE"},
    ]
    same_group = {"facility_scope": "전체", "space_scope": "전체", "category": "배치계획",
                  "section_path": "3.2.3 > 1) 토지이용",
                  "items": [{"label": "가)", "text": "대지 주변의 토지이용 ..."}]}
    extractions = [
        {"page": 1, "type": "BRIEF_DESIGN_GUIDE", "data": {"design_guidelines_grouped": [same_group]}},
        {"page": 2, "type": "BRIEF_DESIGN_GUIDE", "data": {"design_guidelines_grouped": [same_group]}},
    ]
    merged = merge_extracted_data(classifications, extractions)
    assert len(merged.get("design_guidelines_grouped") or []) == 1


def test_exporter_renders_facility_specific_and_common_sections(tmp_path):
    """to_xlsx + to_markdown: 시설별 + 공통 grouped 섹션 모두 렌더링."""
    from services.brief_checklist_exporter import to_xlsx, to_markdown
    from openpyxl import load_workbook

    brief_data = {
        "_brief_meta": {"facility_type": "public", "source_format": "pdf",
                        "brief_id": "test", "brief_name": ""},
        "brief_project_info": {"competition_name": "X", "sites": [{"site_id": "단일부지"}],
                               "construction_cost_100m_won": None, "design_cost_100m_won": None,
                               "construction_period_months": None,
                               "budget_notes": [], "special_conditions": [], "unit_program": []},
        "_quantitative": {},
        "design_guidelines_grouped": [
            {"facility_scope": "구청", "space_scope": "간부공간", "category": "공간구성",
             "section_path": "II.3 > ① 구청 > 간부공간",
             "items": [{"label": "-", "text": "직무공간 배치 고려"}]},
            {"facility_scope": "구의회", "space_scope": "전체", "category": "공간구성",
             "section_path": "II.3 > ② 구의회",
             "items": [{"label": "-", "text": "본회의장 동선 고려"}]},
            {"facility_scope": "전체", "space_scope": "전체", "category": "배치계획",
             "section_path": "II.4 > 1) 배치",
             "items": [{"label": "가)", "text": "남향 우선 배치"}]},
        ],
    }
    # xlsx
    xlsx_bytes = to_xlsx(brief_data, {"summary": {"high": 0, "medium": 0, "low": 0}, "flags": []})
    out = tmp_path / "out.xlsx"
    out.write_bytes(xlsx_bytes)
    wb = load_workbook(str(out))
    ws = wb["3.요구사항"]
    all_text = "\n".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1) for c in range(1, ws.max_column + 1)
    )
    assert "시설별 설계지침" in all_text
    assert "공통 설계지침" in all_text
    assert "[구청]" in all_text and "[구의회]" in all_text
    assert "남향 우선 배치" in all_text
    assert "직무공간 배치 고려" in all_text

    # markdown
    md = to_markdown(brief_data, {"summary": {"high": 0, "medium": 0, "low": 0}, "flags": []})
    assert "### 시설별 설계지침" in md
    assert "### 공통 설계지침" in md
    assert "[구청]" in md
    assert "남향 우선 배치" in md


def test_exporter_skips_grouped_section_when_empty(tmp_path):
    """grouped 가 비어있으면 새 섹션은 렌더링 안 됨 (회귀 방지)."""
    from services.brief_checklist_exporter import to_xlsx
    from openpyxl import load_workbook

    brief_data = {
        "_brief_meta": {"facility_type": "residential", "source_format": "pdf",
                        "brief_id": "test", "brief_name": ""},
        "brief_project_info": {"competition_name": "X", "sites": [{"site_id": "단일부지"}],
                               "construction_cost_100m_won": None, "design_cost_100m_won": None,
                               "construction_period_months": None,
                               "budget_notes": [], "special_conditions": [], "unit_program": []},
        "_quantitative": {},
        # design_guidelines_grouped 없음 (구 데이터 시뮬레이션)
    }
    xlsx_bytes = to_xlsx(brief_data, {"summary": {"high": 0, "medium": 0, "low": 0}, "flags": []})
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["3.요구사항"]
    all_text = "\n".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1) for c in range(1, ws.max_column + 1)
    )
    assert "시설별 설계지침" not in all_text
    assert "공통 설계지침" not in all_text


def test_exporter_skips_unit_program_when_absent():
    """unit_program 비어있을 때 — 시트에 해당 섹션이 나타나지 않음 (회귀 방지)."""
    from services.brief_checklist_exporter import to_xlsx
    from openpyxl import load_workbook

    brief_data = {
        "_brief_meta": {"facility_type": "residential", "source_format": "pdf",
                        "brief_id": "test", "brief_name": ""},
        "brief_project_info": {
            "competition_name": "공모Y",
            "sites": [{"site_id": "단일부지"}],
            "construction_cost_100m_won": None, "design_cost_100m_won": None,
            "construction_period_months": None,
            "budget_notes": [], "special_conditions": [],
            # unit_program 자체 없음 (구 데이터 시뮬레이션)
        },
        "_quantitative": {},
    }
    xlsx_bytes = to_xlsx(brief_data, validation={"summary": {"high": 0, "medium": 0, "low": 0},
                                                 "flags": []})
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["1.면적·프로그램"]
    all_text = "\n".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    )
    assert "단위세대·시설별 분배" not in all_text
