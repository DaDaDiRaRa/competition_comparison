import asyncio
import base64
from pathlib import Path

from config import settings, PAGE_TYPES
from services.llm_client import call_messages
from services.utils import parse_json_response, rasterize_pdf

BATCH_SIZE = 5  # 한 번에 처리할 최대 페이지 수

# 재건축 신규 타입: 신뢰도 < 0.65일 때 안전한 기존 타입으로 다운그레이드
# false-positive 차단으로 분류 안정성 보장
REDEV_TYPES_STRICT = {
    "BUSINESS_VIABILITY", "AREA_INCREASE", "VIEW_ANALYSIS",
    "COMMUNITY_PROGRAM", "COMPANY_PORTFOLIO", "CONSTRUCTION_PLAN",
    "UNIT_PLAN_PENTHOUSE",
}
REDEV_FALLBACK = {
    "BUSINESS_VIABILITY":   "AREA_TABLE",
    "AREA_INCREASE":        "AREA_TABLE",
    "VIEW_ANALYSIS":        "SITE_PLAN",
    "COMMUNITY_PROGRAM":    "SPECIAL_SPACE",
    "COMPANY_PORTFOLIO":    "BRANDING",
    "CONSTRUCTION_PLAN":    "TECHNICAL",
    "UNIT_PLAN_PENTHOUSE":  "UNIT_PLAN",
}
REDEV_CONFIDENCE_FLOOR = 0.65

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
- SITE_PLAN: top-down site layout with buildings, roads, north arrow. NOT view %-focused (that's VIEW_ANALYSIS) — overall organization
- LANDSCAPE: planting plan, green areas, outdoor design
- FLOOR_PLAN: architectural floor plan with room labels, grid lines
- SECTION: vertical section/cut drawing with floor levels
- ELEVATION: facade front view drawing
- CIRCULATION: movement/flow diagrams with arrows
- HEALTH_CENTER: 보건소 related content (plans, concepts, sections)
- TECHNICAL: structural/MEP/fire/environmental engineering
- AREA_TABLE: total area breakdown for the PROPOSED building (current-state only). 연면적·건축면적·건폐율·용적률·층수·주차. NOT before/after comparison — single-state breakdown
- SUSTAINABILITY: green/ESG/energy/environmental strategies
- UNIT_PLAN: STANDARD (non-penthouse) single unit floor plan + area table. NOT penthouse — penthouse goes to UNIT_PLAN_PENTHOUSE
- INCENTIVE_TABLE: FAR ratio-only comparison (base/applied/final %). pure FAR analysis. NOT redev member benefit framing
- BRANDING: brand name, slogan, marketing keywords. Large typography, NO design diagrams
- BUSINESS_VIABILITY: redevelopment business case page. asset value increase numbers, member contribution change, general sale unit count, FAR before/after, sale price per pyeong. financial proposition focus, NOT design
- AREA_INCREASE: before-vs-after area COMPARISON table for redevelopment. paired columns 기존 vs 재건축 후 with increase ratio. NOT a single-state area table — must show before/after pairing
- VIEW_ANALYSIS: view rights page with percentages. south-facing %, river/water view %, double view %, member-unit view guarantee %. site diagram with view direction arrows. NOT a site plan — view % is dominant content
- COMMUNITY_PROGRAM: signature community facility marketing page. program count, area-per-household (평/세대), sky lounge / infinity pool / hotel-style amenities. branded list of premium amenities, NOT a floor plan
- COMPANY_PORTFOLIO: firm credentials page. employee count, financial rating, design awards, similar redevelopment projects with thumbnails, executive profiles. NOT design content
- CONSTRUCTION_PLAN: construction strategy page. months reduced, cost savings amount, underground parking levels, deck height, smart parking. time/money savings claims focus
- UNIT_PLAN_PENTHOUSE: penthouse unit plan with luxury features (terrace, infinity pool, 3-side opening, 천장 2.7m+). usually labeled "PA"/"PH"/"165PA". select OVER UNIT_PLAN when penthouse markers visible

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

    # 재건축 신규 타입은 신뢰도 낮으면 안전한 기존 타입으로 다운그레이드
    pt = result["primary_type"]
    if pt in REDEV_TYPES_STRICT and result["confidence"] < REDEV_CONFIDENCE_FLOOR:
        result["primary_type"] = REDEV_FALLBACK[pt]

    return result


def _call_classify(batch: list) -> list[dict]:
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
        return results
    except Exception:
        return []


def _classify_batch_with_validation(batch: list, max_retries: int = 2) -> list[dict]:
    for _ in range(max_retries + 1):
        results = _call_classify(batch)
        if isinstance(results, list) and len(results) == len(batch):
            return results
    # 재시도해도 길이 불일치면 1페이지씩 개별 분류로 폴백
    fallback = []
    for single in batch:
        res = _call_classify([single])
        fallback.append(res[0] if res else {})
    return fallback


def _fallback_entry(page: int) -> dict:
    return {**_normalise_result({}), "page": page}


def _enforce_page_uniqueness(all_results: list[dict], expected_total: int) -> list[dict]:
    by_page = {r["page"]: r for r in all_results}  # 중복 시 마지막 값 유지
    return [by_page.get(p, _fallback_entry(p)) for p in range(1, expected_total + 1)]


def _classify_pdf_sync(pdf_path: Path) -> list[dict]:
    """PDF를 분류용 저해상도 이미지로 변환 후 배치 단위로 분류.
    - DPI: settings.dpi_classify (기본 72) — 페이지 타입 구분에 충분
    - Model: settings.model_id_classify (기본 Haiku) — 단순 분류 작업이라 Sonnet 불필요"""
    pages = rasterize_pdf(pdf_path, dpi=settings.dpi_classify)

    all_results = []
    for batch_start in range(0, len(pages), BATCH_SIZE):
        batch = pages[batch_start:batch_start + BATCH_SIZE]
        raw_results = _classify_batch_with_validation(batch)

        for i, r in enumerate(raw_results):
            actual_page = batch[i][1] if i < len(batch) else batch_start + i + 1
            all_results.append({**_normalise_result(r), "page": actual_page})

    return _enforce_page_uniqueness(all_results, len(pages))


async def classify_all_pages(pdf_path: Path) -> list[dict]:
    """PDF 전체 페이지 분류"""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_classify_pdf_sync, pdf_path)
