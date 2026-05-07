import asyncio
import base64
from pathlib import Path

from config import settings, PAGE_TYPES
from services.llm_client import call_messages
from services.utils import parse_json_response, rasterize_pdf

BATCH_SIZE = 10  # 한 번에 처리할 최대 페이지 수

SYSTEM_PROMPT = (
    "You are an architectural document page classifier. "
    "You analyze pages from Korean architectural design competition reports "
    "(설계공모 설계설명서). Respond ONLY in the specified JSON format. "
    "Do NOT add explanations or natural language."
)

CLASSIFY_PROMPT = """\
TASK: Classify each provided page image in order.

RULES:
- For each image, select exactly ONE primary type from the list below
- If a page contains multiple types, pick the DOMINANT one
- Confidence: 0.0-1.0
- Return exactly one JSON object per image, in the same order as provided

PAGE_TYPES:
- COVER: 표지, registration code, competition title only
- TOC_HERO: table of contents + main hero rendering
- SITE_CONTEXT: aerial/map view, urban analysis, site boundary, historical context
- CONCEPT: design concept diagrams, massing strategy, keyword text blocks
- SPECIAL_SPACE: detailed program/space planning, user scenarios
- RENDERING_EXT: exterior perspective rendering (full or half page)
- RENDERING_INT: interior perspective rendering
- SITE_PLAN: top-down site layout with buildings, roads, north arrow
- LANDSCAPE: planting plan, green areas, outdoor design
- FLOOR_PLAN: architectural floor plan with room labels, grid lines
- SECTION: vertical section/cut drawing with floor levels
- ELEVATION: facade front view drawing
- CIRCULATION: movement/flow diagrams with arrows
- HEALTH_CENTER: 보건소 related content (plans, concepts, sections)
- TECHNICAL: structural/MEP/fire/environmental engineering
- AREA_TABLE: area breakdown tables, cost estimates, data tables
- SUSTAINABILITY: green/ESG/energy/environmental strategies

RESPOND JSON ONLY as an array, one object per image:
[
  {"page":1,"type":"PAGE_TYPE","confidence":0.0,"sub_elements":["list","of","visible","elements"],"has_text":true,"has_drawing":true,"has_rendering":false,"has_table":false},
  {"page":2,"type":"PAGE_TYPE","confidence":0.0,"sub_elements":[...],...}
]"""

_SEMAPHORE = asyncio.Semaphore(3)


def _normalise_result(raw: dict) -> dict:
    result = {
        "primary_type": raw.get("type") or raw.get("primary_type", "CONCEPT"),
        "secondary_type": raw.get("secondary_type"),
        "confidence": raw.get("confidence", 0.0),
        "key_elements": raw.get("sub_elements") or raw.get("key_elements", []),
        "has_text": raw.get("has_text", False),
        "has_drawing": raw.get("has_drawing", False),
        "has_rendering": raw.get("has_rendering", False),
        "has_table": raw.get("has_table", False),
    }
    if result["primary_type"] not in PAGE_TYPES:
        result["primary_type"] = "CONCEPT"
    return result


def _classify_pdf_sync(pdf_path: Path) -> list[dict]:
    """PDF를 분류용 저해상도 이미지로 변환 후 배치 단위로 분류.
    - DPI: settings.dpi_classify (기본 72) — 페이지 타입 구분에 충분
    - Model: settings.model_id_classify (기본 Haiku) — 단순 분류 작업이라 Sonnet 불필요"""
    pages = rasterize_pdf(pdf_path, dpi=settings.dpi_classify)

    all_results = []
    for batch_start in range(0, len(pages), BATCH_SIZE):
        batch = pages[batch_start:batch_start + BATCH_SIZE]

        content = []
        for img_bytes, _ in batch:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(img_bytes).decode("utf-8"),
                },
            })
        content.append({"type": "text", "text": CLASSIFY_PROMPT})

        raw_text = call_messages(
            model=settings.model_id_classify,
            max_tokens=3000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        try:
            results = parse_json_response(raw_text)
            if not isinstance(results, list):
                results = [results]
        except Exception:
            results = [{}] * len(batch)

        for i, r in enumerate(results):
            actual_page = batch[i][1] if i < len(batch) else batch_start + i + 1
            all_results.append({**_normalise_result(r), "page": actual_page})

    return all_results


async def classify_all_pages(pdf_path: Path) -> list[dict]:
    """PDF 전체 페이지 분류"""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_classify_pdf_sync, pdf_path)
