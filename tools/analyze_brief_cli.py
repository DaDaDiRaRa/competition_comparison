"""
analyze_brief_cli.py — 지침서 PDF 단독 분석 CLI (HTTP/SSE 없이 파이프라인 직접 호출)

routers/brief.py::analyze_brief 의 핵심 로직을 그대로 재현하여 _brief.json/md/xlsx 저장.
P0-3 / P1-3 / P2-3 검증 및 V-10e (그룹 병렬 로그) 캡처용.

사용:
    $env:ANTHROPIC_API_KEY = (Get-Content C:\\Temp\\anthropic_key.txt -Raw).Trim()
    $env:PYTHONUTF8 = "1"
    backend\\venv\\Scripts\\python.exe tools\\analyze_brief_cli.py "<PDF경로>" <facility_type> <label> 2>stderr.log
"""
import asyncio
import logging
import sys
import time
from pathlib import Path

# backend 를 import 경로에 추가
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from config import settings, FACILITY_TYPES  # noqa: E402
from services.page_classifier import classify_all_pages_brief  # noqa: E402
from services.data_extractor import (  # noqa: E402
    extract_pdf, merge_extracted_data, extract_brief_requirements,
)
from services.brief_validator import validate_brief  # noqa: E402
from services.brief_checklist_exporter import to_markdown, to_xlsx  # noqa: E402
from services.db_manager import _atomic_write, _sync_write, _sync_write_bytes, _slugify  # noqa: E402

# INFO 로그 → stderr (V10E_TRACE 포함)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("analyze_brief_cli")


async def analyze(pdf_path: Path, facility_type: str, label: str) -> str:
    if not settings.has_api_key():
        raise SystemExit("ERROR: API 키 없음 (ANTHROPIC_API_KEY env 확인)")
    if facility_type not in FACILITY_TYPES:
        raise SystemExit(f"ERROR: unknown facility_type {facility_type}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    slug = _slugify(label.strip()) if label.strip() else ""
    brief_id = (f"{stamp}_{facility_type}_{slug}" if slug else f"{stamp}_{facility_type}")[:120]

    log.info("=== classify start: %s ===", pdf_path.name)
    t0 = time.monotonic()
    classifications = await classify_all_pages_brief(pdf_path)
    log.info("=== classify done: %d pages in %.1fs ===", len(classifications), time.monotonic() - t0)

    log.info("=== extract start ===")
    t1 = time.monotonic()
    extractions = await extract_pdf(pdf_path, page_map=classifications, is_brief=True)
    log.info("=== extract done in %.1fs ===", time.monotonic() - t1)

    brief_data = merge_extracted_data(classifications, extractions)
    brief_data["page_map"] = classifications
    brief_data["total_pages"] = len(classifications)

    log.info("=== requirements start ===")
    brief_data["_requirements"] = await extract_brief_requirements(brief_data, facility_type)

    brief_data["_brief_meta"] = {
        "brief_id": brief_id,
        "facility_type": facility_type,
        "brief_name": label.strip() or "",
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_format": "pdf",
    }
    log.info("=== validate start ===")
    brief_data.update(validate_brief(brief_data, brief_data["_requirements"]))
    validation = brief_data.get("validation") or {}

    briefs_dir = settings.db_path / "_briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(briefs_dir / f"{brief_id}.json", brief_data)
    _sync_write(briefs_dir / f"{brief_id}.md", to_markdown(brief_data, validation))
    _sync_write_bytes(briefs_dir / f"{brief_id}.xlsx", to_xlsx(brief_data, validation))

    summary = (validation.get("summary") or {})
    log.info("=== SAVED brief_id=%s flags=%s ===", brief_id, summary)
    return brief_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: analyze_brief_cli.py <pdf_path> <facility_type> [label]")
    pdf = Path(sys.argv[1])
    ft = sys.argv[2]
    lbl = sys.argv[3] if len(sys.argv) > 3 else ""
    if not pdf.exists():
        raise SystemExit(f"ERROR: PDF not found: {pdf}")
    bid = asyncio.run(analyze(pdf, ft, lbl))
    print(f"BRIEF_ID={bid}")
