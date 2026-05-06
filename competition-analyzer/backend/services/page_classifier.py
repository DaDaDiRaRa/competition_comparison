import asyncio
from pathlib import Path

import anthropic

from config import settings, PAGE_TYPES
from services.utils import encode_pdf, parse_json_response

SYSTEM_PROMPT = (
    "You are an architectural document page classifier. "
    "You analyze pages from Korean architectural design competition reports "
    "(설계공모 설계설명서). Respond ONLY in the specified JSON format. "
    "Do NOT add explanations or natural language."
)

CLASSIFY_PROMPT = """\
TASK: Classify all pages in this PDF document.

RULES:
- For each page, select exactly ONE primary type from the list below
- If page contains multiple types (e.g., rendering + diagram), pick the DOMINANT one
- Confidence: 0.0-1.0

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

RESPOND JSON ONLY as an array, one object per page:
[
  {"page":1,"type":"PAGE_TYPE","confidence":0.0,"sub_elements":["list","of","visible","elements"],"has_text":true,"has_drawing":true,"has_rendering":false,"has_table":false},
  {"page":2,"type":"PAGE_TYPE","confidence":0.0,"sub_elements":[...],...}
]"""

_SEMAPHORE = asyncio.Semaphore(6)


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
    """PDF를 Claude API로 분류 (모든 페이지)"""
    client = anthropic.Anthropic(api_key=settings.api_key)
    pdf_data = encode_pdf(pdf_path)

    response = client.messages.create(
        model=settings.model_id,
        max_tokens=2000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        },
                    },
                    {"type": "text", "text": CLASSIFY_PROMPT},
                ],
            }
        ],
    )

    try:
        results = parse_json_response(response.content[0].text)
        if not isinstance(results, list):
            results = [results]
    except Exception as e:
        return [{"page": 1, "error": f"분류 실패: {str(e)}"}]

    return [
        {**_normalise_result(r), "page": r.get("page", i + 1)}
        for i, r in enumerate(results)
    ]


async def classify_all_pages(pdf_path: Path) -> list[dict]:
    """PDF 전체 페이지 분류"""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_classify_pdf_sync, pdf_path)
