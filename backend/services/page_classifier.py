import asyncio
import base64
from pathlib import Path

from config import settings, PAGE_TYPES, BRIEF_PAGE_TYPES
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


# ══════════════════════════════════════════════════════════════════════════════
# 지침서(Brief) 전용 분류기
# 제안서 27개 타입과 별개의 taxonomy (BRIEF_PAGE_TYPES 9개).
# B-plan: 면적 숫자 표(실별 면적·주차수량 등)가 있으면 BRIEF_PROGRAM 우선,
#         텍스트만인 설계 지침은 BRIEF_DESIGN_GUIDE.
# ══════════════════════════════════════════════════════════════════════════════

BRIEF_SYSTEM_PROMPT = (
    "You are an architectural competition brief (설계공모 지침서) page classifier. "
    "You analyze pages from Korean competition brief documents that specify requirements "
    "for design submissions. Respond ONLY in the specified JSON format. "
    "Do NOT add explanations or natural language."
)

BRIEF_CLASSIFY_PROMPT = """\
TASK: Classify each provided page image from a competition brief (설계공모 지침서).

RULES:
- For each image, select exactly ONE primary type from the list below
- Confidence: 0.0-1.0
- PRIORITY RULE 1 (area table): If a page contains BOTH design guidelines text AND a room-by-room area table \
(실별 면적표 — rows are room names, columns are area/㎡), classify as BRIEF_PROGRAM — the numeric table takes priority
- PRIORITY RULE 2 (scoring table): If a page contains an actual 배점표 — a TABLE whose ROWS are evaluation \
categories (구분/항목) and COLUMNS include 비중/배점/점수 with numeric values summing to ~100 — classify as \
BRIEF_EVALUATION. The scoring table OVERRIDES BRIEF_DESIGN_GUIDE. \
Do NOT apply this rule for: schedule tables, jury roster tables, submission checklist tables, or pages that \
merely mention "배점" in prose without an actual numeric scoring table.
- PRIORITY RULE 3 (project scale table): If a page has a table where ROWS are named 대지면적, 건폐율, 용적률, \
높이(or 건축규모/연면적), and COLUMNS are sites or facility types, classify as BRIEF_PROJECT_INFO — this OVERRIDES \
BRIEF_PROGRAM even though numbers are present. KEY: the ROW names distinguish this from BRIEF_PROGRAM \
(BRIEF_PROGRAM has room names as rows; BRIEF_PROJECT_INFO has scale metric names as rows).

BRIEF_PAGE_TYPES:
- BRIEF_OVERVIEW: 공모개요. Purpose, schedule, eligibility, submission deadline, organizer info. Summary/introduction pages. NO numeric construction scale table — text/list only.
- BRIEF_PROJECT_INFO: 사업 개요 수치표. Page with a table where ROWS are site-level scale metrics (대지면적, 건폐율, 용적률, 최고높이, 건축규모/연면적, 공개공지) and COLUMNS are sites or facility types (부지1/부지2, 어린이집/구청사/커뮤니티센터 등). Column headers may be site labels (부지1, A, B) OR facility-type names (어린이집, 공공업무시설 등) — both count. Additional signals: 예정 공사비, 설계비, 공사기간. DISTINGUISH → BRIEF_OVERVIEW (text-only purpose/background/schedule, no numeric table) / BRIEF_PROGRAM (ROW names are room/space names like 회의실·로비, not metric names like 대지면적·건폐율) / BRIEF_REGULATIONS (zoning code text without project-specific numeric table).
- BRIEF_SITE: 대상지 현황. Site location map, aerial photo, cadastral map, site area, surrounding context. No design requirements — descriptive only.
- BRIEF_PROGRAM: 면적 프로그램. Room-by-room area table (실별 면적표 — ROW names are space/room names like 회의실, 로비, 주차장), floor-by-floor use table, required parking count, gross/net area requirements. NOTE: if the table ROWS are metric names (대지면적, 건폐율, 용적률, 높이) rather than room names, use BRIEF_PROJECT_INFO instead.
- BRIEF_DESIGN_MASSING: 배치·매싱·동선 지침. Site layout, setbacks, open space, pedestrian/vehicle circulation, parking access, building connections. 신호어: 배치계획, 이격거리, 세트백, 공개공지, 동선, 보행환경, 연결통로, 주차동선.
- BRIEF_DESIGN_FACADE: 입면·재료·경관 지침. Facade design, exterior cladding materials/finishes, color/color-scheme guidelines, skyline, landscape. \
신호어(하나라도 있으면 BRIEF_DESIGN_GUIDE보다 우선): 입면, 외장재, 마감재, 외벽, 파사드, 색상, 색채, 경관, 외관디자인, 커튼월, 금속판넬, \
유리(외벽), 알루미늄, 목재, 석재, 루버, 차양, 외피, 창호비율, 조경기준, 주재료, 부재료, 금지재료. \
강화조건: 사용 가능/불가 재료 목록, 색채 기준, 외장 마감 규정 중 하나라도 있으면 반드시 BRIEF_DESIGN_FACADE (BRIEF_DESIGN_GUIDE 금지).
- BRIEF_DESIGN_SUSTAIN: 친환경·에너지·인증 지침. Green building certifications, energy requirements, renewable energy mandates. \
신호어(하나라도 있으면 최우선 선택): G-SEED, ZEB, LEED, BEMS, BF인증, 녹색건축인증, 에너지효율등급, 에너지절약, 에너지성능, 제로에너지, \
신재생에너지, 의무비율, 태양광, 지열, 연료전지, 친환경, 녹색건축, 인증등급, 탄소중립, 탄소저감, 에너지등급. \
강화조건: 특정 인증(G-SEED/ZEB/LEED/BF 등) 취득 의무, 신재생에너지 비율 수치, 에너지 성능 등급 요건 중 하나라도 있으면 \
다른 내용이 섞여도 반드시 BRIEF_DESIGN_SUSTAIN (BRIEF_DESIGN_GUIDE 금지).
- BRIEF_DESIGN_SPECIAL: 특수·보안·안전 지침. Crime prevention (CPTED), fire safety, seismic design, universal design, disability access, railway protection zones. 신호어: 방재, CPTED, 범죄예방, 장애인, 유니버설디자인, 소방, 내진, 철도보호.
- BRIEF_DESIGN_GUIDE: 기타 설계 지침 (폴백). ONLY use when NONE of the four specific types above apply. If facade/material/color signals OR sustainability/certification signals are present, choose the specific type instead.
- BRIEF_TECHNICAL: 기술 기준. Structural requirements, MEP specifications, fire safety, seismic standards, smart building criteria.
- BRIEF_REGULATIONS: 법규 기준. Zoning district, building coverage ratio (건폐율), floor area ratio (용적률), height restrictions, setback rules — legal codes and ordinances.
- BRIEF_EVALUATION: 심사 기준 배점표. REQUIRED: an actual TABLE whose ROWS are evaluation categories (구분/항목) \
AND COLUMNS include 비중/배점/점수 with numeric values that together sum to approximately 100. \
NOT BRIEF_EVALUATION if: (a) only prose description of evaluation process with no actual table, \
(b) page is an evaluation SCHEDULE (심사 일정/일자) → BRIEF_ADMIN, \
(c) page lists 제출 서류 with checkboxes → BRIEF_SUBMISSION, \
(d) jury composition (심사위원 명단/구성) without a scoring table → BRIEF_ADMIN, \
(e) table exists but rows are dates/documents/persons, not evaluation categories.
- BRIEF_SUBMISSION: 제출 기준. Required drawing list, file format specifications (DWG/PDF/BIM), submission method, document scale requirements.
- BRIEF_ADMIN: 행정 절차. Q&A schedule, contact information, amendment notices, administrative forms, jury roster. No design content — skip extraction.

BRIEF_EVALUATION vs BRIEF_DESIGN_GUIDE family — decision guide:
  • Actual 배점표 table (rows=평가항목, cols=비중/배점, values sum ~100) → BRIEF_EVALUATION
  • Prose mentions "배점" or "심사기준" but NO numeric scoring table on the page → BRIEF_ADMIN or BRIEF_DESIGN_GUIDE
  • Bullet points (•) or paragraphs describing design requirements, NO scoring table → one of the 5 BRIEF_DESIGN_* types below
  • Table present but columns are area/floor/quantity (not scoring weights) → BRIEF_PROGRAM (not BRIEF_EVALUATION)
  • Table present but rows are dates/persons/documents → BRIEF_ADMIN or BRIEF_SUBMISSION (not BRIEF_EVALUATION)

BRIEF_DESIGN sub-types — priority order (check top-down, pick FIRST that matches):
  1. BRIEF_DESIGN_SUSTAIN: ANY of {G-SEED, ZEB, LEED, BF인증, 에너지효율등급, 신재생에너지, 태양광, 친환경인증, 에너지등급} → ALWAYS BRIEF_DESIGN_SUSTAIN, even if other content mixed in.
  2. BRIEF_DESIGN_SPECIAL: CPTED, 방재, 소방, 내진, 장애인, 보안 dominant.
  3. BRIEF_DESIGN_FACADE: ANY of {외장재, 마감재, 색채계획, 파사드, 커튼월, 금속판넬, 조경기준, 루버, 금지재료} → BRIEF_DESIGN_FACADE preferred over GUIDE.
  4. BRIEF_DESIGN_MASSING: 배치, 이격거리, 동선, 공개공지, 주차동선 dominant.
  5. BRIEF_DESIGN_GUIDE: FALLBACK ONLY — use only when 1-4 signals are ALL absent. Do NOT default to GUIDE if any specific signal exists.

BRIEF_PROJECT_INFO vs BRIEF_OVERVIEW vs BRIEF_PROGRAM — decision guide:
  • Table ROWS = 대지면적, 건폐율, 용적률, 높이, 건축규모/연면적 (metric names), COLUMNS = sites or facility types → BRIEF_PROJECT_INFO (PRIORITY RULE 3 applies — overrides BRIEF_PROGRAM)
  • Text-only overview (목적·배경·일정·자격) with NO numeric table → BRIEF_OVERVIEW
  • Table ROWS = room/space names (회의실, 로비, 주차장, 어린이집 면적 등), COLUMNS = area/㎡ values → BRIEF_PROGRAM
  • TRICK: Column headers being facility names (어린이집, 구청사) does NOT make it BRIEF_PROGRAM — check the ROW names to decide

RESPOND JSON ONLY as an array, one object per image:
[
  {"page":1,"type":"BRIEF_PAGE_TYPE","confidence":0.0,"has_area_table":false,"has_scoring_table":false,"has_text_guidelines":true},
  {"page":2,"type":"BRIEF_PAGE_TYPE","confidence":0.0,"has_area_table":false,"has_scoring_table":true,"has_text_guidelines":false}
]
has_scoring_table: true if the page has a table with 비중/배점/점수 columns or values summing to ~100."""


def _normalise_brief_result(raw: dict) -> dict:
    result = {
        "primary_type": raw.get("type") or raw.get("primary_type", "BRIEF_DESIGN_GUIDE"),
        "secondary_type": raw.get("secondary_type"),
        "confidence": raw.get("confidence", 0.0),
        "key_elements": raw.get("sub_elements") or raw.get("key_elements", []),
        "has_text": raw.get("has_text", False),
        "has_drawing": raw.get("has_drawing", False),
        "has_rendering": raw.get("has_rendering", False),
        "has_table": raw.get("has_area_table", raw.get("has_table", False)),
        "has_scoring_table": raw.get("has_scoring_table", False),
    }
    if result["primary_type"] not in BRIEF_PAGE_TYPES:
        result["primary_type"] = "BRIEF_DESIGN_GUIDE"
    # BRIEF_EVALUATION 검증: LLM이 has_scoring_table=False로 보고하면 배점표 없음 → BRIEF_ADMIN 다운그레이드
    # (오분류 API 호출 방지 — p.94/p.117 같이 배점 관련 텍스트만 있는 페이지 제거)
    if result["primary_type"] == "BRIEF_EVALUATION" and not result.get("has_scoring_table", False):
        result["primary_type"] = "BRIEF_ADMIN"
    return result


def _call_classify_brief(batch: list) -> list[dict]:
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
    content.append({"type": "text", "text": BRIEF_CLASSIFY_PROMPT})

    raw_text = call_messages(
        model=settings.model_id_classify,
        max_tokens=3000,
        temperature=0,
        system=BRIEF_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    try:
        results = parse_json_response(raw_text)
        if not isinstance(results, list):
            results = [results]
        return results
    except Exception:
        return []


def _classify_brief_batch_with_validation(batch: list, max_retries: int = 2) -> list[dict]:
    for _ in range(max_retries + 1):
        results = _call_classify_brief(batch)
        if isinstance(results, list) and len(results) == len(batch):
            return results
    fallback = []
    for single in batch:
        res = _call_classify_brief([single])
        fallback.append(res[0] if res else {})
    return fallback


def _fallback_brief_entry(page: int) -> dict:
    return {**_normalise_brief_result({}), "page": page}


def _classify_brief_pdf_sync(pdf_path: Path) -> list[dict]:
    """지침서 PDF를 배치 단위로 분류 (BRIEF_PAGE_TYPES 9개 taxonomy)."""
    pages = rasterize_pdf(pdf_path, dpi=settings.dpi_classify)

    all_results = []
    for batch_start in range(0, len(pages), BATCH_SIZE):
        batch = pages[batch_start:batch_start + BATCH_SIZE]
        raw_results = _classify_brief_batch_with_validation(batch)

        for i, r in enumerate(raw_results):
            actual_page = batch[i][1] if i < len(batch) else batch_start + i + 1
            all_results.append({**_normalise_brief_result(r), "page": actual_page})

    # 결과 정렬 및 누락 페이지 폴백
    by_page = {r["page"]: r for r in all_results}
    return [by_page.get(p, _fallback_brief_entry(p)) for p in range(1, len(pages) + 1)]


async def classify_all_pages_brief(pdf_path: Path) -> list[dict]:
    """지침서 PDF 전체 페이지 분류 (BRIEF taxonomy)."""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_classify_brief_pdf_sync, pdf_path)
