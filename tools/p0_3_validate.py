"""
P0-3 validation: run brief analysis pipeline on actual PDFs and verify
BRIEF_PROJECT_INFO classification + xlsx Sheet 1 "사업 개요" section.

Run from repo root:
    python tools/p0_3_validate.py
"""

import sys, os, json, io, tempfile, pathlib

# Add backend to path
BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

# Minimal config to avoid app_settings.json dependency
os.environ.setdefault("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))

PDFS = {
    "jongno_main": r"M:\103_건원 NEW 프론티어 프로그램\2020년\D2_사내 디자인 공모전\02_종로구청 설계공모 지침서_KOR.pdf",
    "jongno_sub":  r"M:\103_건원 NEW 프론티어 프로그램\2020년\D2_사내 디자인 공모전\03_종로구청 시설별 세부지침서_KOR.pdf",
    "yeongdp":     r"D:\BACK DATA\competition_comparison\설계공모 수정지침서(영등포구 통합 신청사 국제설계공모)_25.07.18..pdf",
}

FACILITY_TYPE = "public"  # 공공시설 — general group

# ──────────────────────────────────────────────────────────────────────────────

def classify_brief(pdf_path: str, label: str):
    """Classify all pages in a brief PDF and return page_map."""
    import asyncio
    from services.page_classifier import classify_all_pages_brief
    from config import settings

    print(f"\n{'='*70}")
    print(f"[CLASSIFY] {label}")
    print(f"  PDF: {pdf_path}")

    api_key = settings.api_key
    if not api_key:
        print("  !! No API key — skipping classification (LLM call required)")
        return None

    # classify_all_pages_brief returns list[dict]: [{page: int, type: str, ...}, ...]
    results = asyncio.run(classify_all_pages_brief(pdf_path))
    page_map = results  # extract_pdf expects list[dict] as-is
    print(f"  Total pages classified: {len(page_map)}")

    bpi_pages = [item["page"] for item in page_map if item.get("primary_type") == "BRIEF_PROJECT_INFO"]
    print(f"  BRIEF_PROJECT_INFO pages: {bpi_pages if bpi_pages else '(none)'}")

    # Print full distribution
    from collections import Counter
    dist = Counter(item.get("primary_type") for item in page_map)
    for ptype, cnt in sorted(dist.items()):
        marker = " <-- NEW" if ptype == "BRIEF_PROJECT_INFO" else ""
        print(f"    {ptype}: {cnt}{marker}")

    return page_map


def extract_brief(pdf_path: str, page_map: list, label: str):
    """Extract brief data and return brief_data dict."""
    import asyncio
    from services.data_extractor import extract_pdf, merge_extracted_data

    print(f"\n[EXTRACT] {label}")

    raw = asyncio.run(extract_pdf(pdf_path, page_map, is_brief=True))
    brief_data = merge_extracted_data(page_map, raw)

    bpi = brief_data.get("brief_project_info")
    if bpi:
        if isinstance(bpi, list):
            bpi = bpi[0] if bpi else {}
        sites = bpi.get("sites", [])
        print(f"  brief_project_info found: {len(sites)} site(s)")
        for i, s in enumerate(sites):
            print(f"    site[{i}]")
            print(f"      id       = {s.get('site_id')}")
            print(f"      address  = {s.get('address')}")
            print(f"      zoning   = {s.get('zoning')}")
            print(f"      scope    = {s.get('scope')}")
            print(f"      facilities = {s.get('facilities')}")
            print(f"      site_area_sqm      = {s.get('site_area_sqm')}")
            print(f"      floor_area_sqm     = {s.get('floor_area_sqm')}")
            print(f"      building_coverage_pct = {s.get('building_coverage_pct')}")
            print(f"      floor_area_ratio_pct  = {s.get('floor_area_ratio_pct')}")
            print(f"      max_height_m       = {s.get('max_height_m')}")
            print(f"      open_space_sqm     = {s.get('open_space_sqm')}")
        cost = bpi.get("construction_cost_100m_won")
        design_cost = bpi.get("design_cost_100m_won")
        period = bpi.get("construction_period_months")
        print(f"  construction_cost={cost} 억원  design_cost={design_cost} 억원  period={period} 개월")
        print(f"  budget_notes={bpi.get('budget_notes')}")
        print(f"  special_conditions={bpi.get('special_conditions')}")
    else:
        print("  brief_project_info: (not extracted)")

    return brief_data


def export_xlsx(brief_data: dict, label: str):
    """Generate xlsx and check Sheet 1 for 사업 개요 section."""
    from services.brief_checklist_exporter import to_xlsx

    print(f"\n[XLSX] {label}")

    # Use empty validation dict (no flags)
    validation = {"flags": [], "summary": {"high": 0, "medium": 0, "low": 0}, "checked_rules": []}
    raw_bytes = to_xlsx(brief_data, validation)

    # Save to temp file and inspect with openpyxl
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes))
    ws1 = wb.worksheets[0]

    print(f"  Sheet 1 name: {ws1.title}")
    print(f"  Rows: {ws1.max_row}  Cols: {ws1.max_column}")

    # Find 사업 개요 header
    found_bpi = False
    found_area_limit = False
    row_labels = []
    for row in ws1.iter_rows(min_row=1, values_only=True):
        cell0 = str(row[0] or "")
        if "사업 개요" in cell0:
            found_bpi = True
            print(f"  ✓ '사업 개요' section header found")
        if "전체 규모 한도" in cell0:
            found_area_limit = True
            print(f"  ✓ '전체 규모 한도' section found (still present)")
        if cell0.strip():
            row_labels.append(cell0.strip())

    if not found_bpi:
        print("  ✗ '사업 개요' section NOT found in Sheet 1")
    if not found_area_limit:
        print("  ✗ '전체 규모 한도' section NOT found — may have been removed unintentionally")

    print(f"\n  Sheet 1 non-empty cell[0] labels (first 30):")
    for lbl in row_labels[:30]:
        print(f"    {lbl}")

    # Save for manual inspection
    out_path = pathlib.Path(tempfile.gettempdir()) / f"p03_{label}.xlsx"
    out_path.write_bytes(raw_bytes)
    print(f"\n  Saved to: {out_path}")
    return out_path


def check_page_map_from_saved_json(label: str, json_path: str):
    """If we have a saved _brief.json, check it directly without running LLM."""
    p = pathlib.Path(json_path)
    if not p.exists():
        return None
    print(f"\n[JSON] Loading saved brief JSON for {label}: {json_path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data


def run_xlsx_only(label: str, brief_data: dict):
    """Skip classify/extract — just test xlsx generation from a dict."""
    return export_xlsx(brief_data, label)


# ──────────────────────────────────────────────────────────────────────────────

def main():
    from config import settings, BRIEF_PAGE_TYPES, BRIEF_PAGE_TYPES_META

    print("\n" + "="*70)
    print("P0-3 VALIDATION - BRIEF_PROJECT_INFO pipeline test")
    print("="*70)

    # Sanity check config
    assert "BRIEF_PROJECT_INFO" in BRIEF_PAGE_TYPES, "BRIEF_PROJECT_INFO missing from BRIEF_PAGE_TYPES!"
    assert BRIEF_PAGE_TYPES_META.get("BRIEF_PROJECT_INFO") == "사업개요", "Meta mismatch!"
    print("\n[CONFIG] BRIEF_PROJECT_INFO registered OK")
    print(f"  Index in list: {BRIEF_PAGE_TYPES.index('BRIEF_PROJECT_INFO')}")
    print(f"  Meta label: {BRIEF_PAGE_TYPES_META['BRIEF_PROJECT_INFO']}")

    # Check API key
    api_key = settings.api_key
    if not api_key:
        print("\n!! ANTHROPIC_API_KEY not set. Classification/extraction steps require LLM.")
        print("   Set env var and re-run, or provide saved _brief.json paths.")
        print("\n[XLSX-ONLY] Testing xlsx export with synthetic brief_data...")
        _test_xlsx_synthetic()
        return

    for label, pdf_path in PDFS.items():
        if not pathlib.Path(pdf_path).exists():
            print(f"\n[SKIP] {label} — file not found: {pdf_path}")
            continue

        page_map = classify_brief(pdf_path, label)
        if page_map is None:
            continue

        brief_data = extract_brief(pdf_path, page_map, label)
        export_xlsx(brief_data, label)

    print("\n" + "="*70)
    print("P0-3 DONE")
    print("="*70)


def _test_xlsx_synthetic():
    """Test xlsx export with hand-crafted brief_data containing BRIEF_PROJECT_INFO."""
    # Single-site synthetic data
    brief_single = {
        "brief_project_info": {
            "competition_name": "종로구청 설계공모",
            "organizer": "종로구",
            "competition_type": "설계공모",
            "sites": [
                {
                    "site_id": "단일부지",
                    "address": "서울특별시 종로구 종로1·2·3·4가동",
                    "zoning": "제2종 일반주거지역",
                    "scope": "신축",
                    "facilities": ["구청 청사", "주민 편의시설"],
                    "site_area_sqm": 5200.0,
                    "floor_area_sqm": 18500.0,
                    "building_coverage_pct": 60.0,
                    "floor_area_ratio_pct": 350.0,
                    "max_height_m": 45.0,
                    "open_space_sqm": 800.0,
                    "open_space_notes": "공개공지 법정 기준 이상",
                }
            ],
            "construction_cost_100m_won": 320.0,
            "design_cost_100m_won": 12.5,
            "construction_period_months": 30,
            "budget_notes": ["VAT 별도", "공사비 산정 기준: 2024년 단가"],
            "special_conditions": ["면적 허용 오차 ±5%"],
        }
    }

    # Multi-site synthetic data
    brief_multi = {
        "brief_project_info": {
            "competition_name": "영등포구 통합 신청사 국제설계공모",
            "organizer": "영등포구",
            "competition_type": "국제설계공모",
            "sites": [
                {
                    "site_id": "부지1",
                    "address": "서울특별시 영등포구 영등포동 A",
                    "zoning": "일반상업지역",
                    "scope": "신축",
                    "facilities": ["구청 본관"],
                    "site_area_sqm": 8400.0,
                    "floor_area_sqm": None,
                    "building_coverage_pct": 50.0,
                    "floor_area_ratio_pct": 800.0,
                    "max_height_m": 90.0,
                    "open_space_sqm": 1200.0,
                    "open_space_notes": "",
                },
                {
                    "site_id": "부지2",
                    "address": "서울특별시 영등포구 영등포동 B",
                    "zoning": "준주거지역",
                    "scope": "신축",
                    "facilities": ["주민 편의시설", "주차장"],
                    "site_area_sqm": 3100.0,
                    "floor_area_sqm": 9300.0,
                    "building_coverage_pct": 60.0,
                    "floor_area_ratio_pct": 300.0,
                    "max_height_m": 35.0,
                    "open_space_sqm": None,
                    "open_space_notes": "",
                },
            ],
            "construction_cost_100m_won": 980.0,
            "design_cost_100m_won": None,
            "construction_period_months": 48,
            "budget_notes": [],
            "special_conditions": ["각 부지 별도 발주", "면적 허용 오차 ±3%"],
        }
    }

    print("\n  --- Synthetic single-site xlsx ---")
    out1 = export_xlsx(brief_single, "synthetic_single")

    print("\n  --- Synthetic multi-site xlsx ---")
    out2 = export_xlsx(brief_multi, "synthetic_multi")

    print(f"\n  Open these files to verify Sheet 1 '사업 개요' section:")
    print(f"    {out1}")
    print(f"    {out2}")


if __name__ == "__main__":
    main()
