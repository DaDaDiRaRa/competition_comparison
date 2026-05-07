"""
data_extractor.py — PDF 페이지별 설계 데이터 추출

변경 이력:
  - JPEG → PNG : 무손실 압축으로 숫자/텍스트 오독 방지
  - media_type  : image/png 고정 (무손실 PNG와 일치)
  - 템플릿      : .replace() 사용 — JSON 중괄호 KeyError 방지 (CLAUDE.md 규칙)
  - page_map    : 분류 결과를 받아 타입별 최적 프롬프트 적용
  - 타일 분할   : AREA_TABLE·TECHNICAL 페이지는 2×2 분할 전송
                  → Claude 실효 해상도 1.6배 향상, 면적표 숫자 오독 해소
"""

import asyncio
import base64
from pathlib import Path

import anthropic

from config import settings
from services.utils import parse_json_response, rasterize_pdf, rasterize_page_tiled

# ── 시스템 프롬프트 ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an architectural document data extractor for Korean design competition reports "
    "(설계공모 설계설명서). "
    "RULES: "
    "- Extract ONLY what is visually present on the page. "
    "- Use Korean for Korean text, English for English text. "
    "- Numbers must be exact if visible, null if not visible. "
    "- Do NOT guess or infer data that is not on the page. "
    "- Respond ONLY in the specified JSON format, no explanations."
)

# ── 타입별 추출 스키마 ─────────────────────────────────────────────────────────
# priority: 1=critical, 2=important, 3=supplementary
EXTRACTION_PROMPTS: dict[str, dict] = {
    "COVER": {
        "priority": 3,
        "instruction": (
            'EXTRACT from this cover page. Respond JSON ONLY.\n'
            '{"competition_name":"","submission_code":"","submitter":""}'
        ),
    },
    "CONCEPT": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this design concept page. Respond JSON ONLY.\n'
            '{"concept_name_ko":"","concept_name_en":"","keywords":[],'
            '"massing_type":"horizontal|vertical|stepped|stacked|hybrid|formal_tower",'
            '"main_strategy":"","sub_strategies":[],"metaphor_reference":"","target_user":[]}'
        ),
    },
    "TOC_HERO": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this TOC/hero page. Respond JSON ONLY.\n'
            '{"concept_name_ko":"","concept_name_en":"",'
            '"toc_sections":[{"section":"","page_start":0}],'
            '"total_sections":0,"has_hero_rendering":true,'
            '"rendering_view_type":"aerial|street|park|night"}'
        ),
    },
    "SITE_CONTEXT": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this site context page. Respond JSON ONLY.\n'
            '{"site_issues":[],"surrounding_facilities":[],"urban_strategy":"",'
            '"transportation_connections":[],"historical_context":"","green_network":""}'
        ),
    },
    "SITE_PLAN": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this site plan. Respond JSON ONLY. Use exact numbers if visible.\n'
            '{"site_area_sqm":null,"building_area_sqm":null,"total_floor_area_sqm":null,'
            '"building_coverage_ratio_pct":null,"floor_area_ratio_pct":null,'
            '"building_height_m":null,"floors_above":null,"floors_below":null,'
            '"parking_count":null,"scale":"","main_entrance_direction":"",'
            '"vehicle_access_direction":"","open_space_strategy":""}'
        ),
    },
    "FLOOR_PLAN": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this floor plan. Respond JSON ONLY.\n'
            '{"floor_level":"","scale":"","main_programs":[],"core_count":0,'
            '"core_type":"center|side|dual|distributed","office_layout":"open|closed|hybrid",'
            '"public_programs_on_this_floor":[],"special_spaces":[],"has_outdoor_terrace":false}'
        ),
    },
    "SECTION": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this section drawing. Respond JSON ONLY.\n'
            '{"section_direction":"longitudinal|transverse","total_height_m":null,'
            '"typical_floor_height_m":null,"ground_floor_height_m":null,'
            '"underground_levels":null,"underground_depth_m":null,'
            '"structural_system_visible":"","atrium_present":false,'
            '"setback_visible":false,"key_spatial_features":[]}'
        ),
    },
    "ELEVATION": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this elevation drawing. Respond JSON ONLY.\n'
            '{"facade_direction":"north|south|east|west","primary_material":"",'
            '"secondary_material":"","facade_system":'
            '"curtain_wall|precast|brick|stone|metal_panel|louver|mega_panel|unitized",'
            '"shading_device":"","green_facade":false,'
            '"transparency_ratio":"high|medium|low","facade_rhythm":"uniform|varied|gradient"}'
        ),
    },
    "RENDERING_EXT": {
        "priority": 3,
        "instruction": (
            'EXTRACT from this exterior rendering. Respond JSON ONLY.\n'
            '{"view_type":"aerial|street|park|corner|distant","time_of_day":"day|dusk|night",'
            '"massing_impression":"","facade_material_visible":[],"landscape_elements":[],'
            '"human_activity_shown":[],"sky_treatment":"clear|cloudy|dramatic"}'
        ),
    },
    "RENDERING_INT": {
        "priority": 3,
        "instruction": (
            'EXTRACT from this interior rendering. Respond JSON ONLY.\n'
            '{"space_type":"","ceiling_type":"exposed|finished|double_height|atrium",'
            '"natural_light":"abundant|moderate|minimal","furniture_style":"modern|traditional|mixed",'
            '"material_palette":[],"user_activities_shown":[]}'
        ),
    },
    "LANDSCAPE": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this landscape plan. Respond JSON ONLY.\n'
            '{"green_area_ratio_pct":null,"tree_types":[],"outdoor_programs":[],'
            '"water_feature":false,"pavement_types":[],"connection_to_surroundings":"",'
            '"key_landscape_concept":""}'
        ),
    },
    "CIRCULATION": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this circulation plan. Respond JSON ONLY.\n'
            '{"pedestrian_main_access":[],"vehicle_access":[],"service_access":"",'
            '"emergency_route":"","barrier_free_route":"","subway_connection":false,'
            '"drop_off_location":""}'
        ),
    },
    "SPECIAL_SPACE": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this special space planning page. Respond JSON ONLY.\n'
            '{"space_name":"","space_type":'
            '"lobby|community|culture|office|council|children|rooftop|plaza|other",'
            '"key_features":[],"target_users":[],"spatial_strategy":""}'
        ),
    },
    "HEALTH_CENTER": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this health center page. Respond JSON ONLY.\n'
            '{"page_content_type":"concept|floor_plan|section|elevation|rendering",'
            '"health_programs":[],"floors_dedicated":null,"separate_entrance":false,'
            '"key_planning_strategy":""}'
        ),
    },
    "TECHNICAL": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this technical review page. Respond JSON ONLY.\n'
            '{"technical_domain":"structural|mep|fire|environmental|energy|acoustic|it",'
            '"structural_system":"","foundation_type":"","hvac_system":"",'
            '"energy_strategies":[],"green_certification_target":"",'
            '"fire_safety_features":[],"smart_building_features":[]}'
        ),
    },
    "AREA_TABLE": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this area/cost table. Respond JSON ONLY. Use exact numbers if visible.\n'
            '{"total_floor_area_sqm":null,"area_above_ground_sqm":null,'
            '"area_below_ground_sqm":null,"building_area_sqm":null,"site_area_sqm":null,'
            '"building_coverage_ratio_pct":null,"floor_area_ratio_pct":null,'
            '"parking_count":null,"floors_above":null,"floors_below":null,'
            '"estimated_total_cost":"","cost_per_sqm":"","program_areas":[]}'
        ),
    },
    "SUSTAINABILITY": {
        "priority": 2,
        "instruction": (
            'EXTRACT from this sustainability page. Respond JSON ONLY.\n'
            '{"green_certification":"","energy_grade_target":"","renewable_energy":[],'
            '"water_management":[],"carbon_reduction_strategies":[],'
            '"smart_building":[],"key_sustainability_concept":""}'
        ),
    },
}

FALLBACK_PROMPT = {
    "priority": 3,
    "instruction": (
        'EXTRACT key information from this page. Respond JSON ONLY.\n'
        '{"key_elements":[],"text_content":[]}'
    ),
}

# ── 지침서(Brief) 전용 추출 스키마 ─────────────────────────────────────────────
# 지침서의 AREA_TABLE은 설계 결과가 아닌 '요구사항'이므로 전용 스키마 사용.
# 이 dict에 없는 타입은 기존 EXTRACTION_PROMPTS를 그대로 사용.
EXTRACTION_PROMPTS_BRIEF: dict[str, dict] = {
    "AREA_TABLE": {
        "priority": 1,
        "instruction": (
            'EXTRACT program requirements from this design competition brief area/program table. '
            'Respond JSON ONLY. Use exact numbers if visible, null if not visible.\n'
            '{"site_area_sqm":null,"total_required_area_sqm":null,'
            '"building_coverage_limit_pct":null,"floor_area_ratio_limit_pct":null,'
            '"max_floors_above":null,"max_floors_below":null,"parking_required":null,'
            '"estimated_budget":"",'
            '"room_program":[{"name":"","area_sqm":null,"count":1,"notes":""}],'
            '"zone_summary":[{"zone":"","area_sqm":null}]}'
        ),
    },
    "TECHNICAL": {
        "priority": 2,
        "instruction": (
            'EXTRACT technical requirements from this design competition brief. Respond JSON ONLY.\n'
            '{"required_structural_system":"","required_energy_grade":"",'
            '"required_certifications":[],"special_requirements":[]}'
        ),
    },
    "SPECIAL_SPACE": {
        "priority": 1,
        "instruction": (
            'EXTRACT required special space specifications from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"space_name":"","required_area_sqm":null,"required_count":1,'
            '"required_features":[],"design_guidelines":[]}'
        ),
    },
}

# 분류 신뢰도 하한: 이 미만이면 TILE_PAGE_TYPES도 일반 추출로 다운그레이드
CONFIDENCE_DOWNGRADE_THRESHOLD = 0.7

# 타일 분할 적용 대상: 정보 밀도가 높아 전체 페이지 전송 시 숫자 오독 위험
TILE_PAGE_TYPES = {"AREA_TABLE", "TECHNICAL"}

# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────
def _b64(img_bytes: bytes) -> str:
    return base64.standard_b64encode(img_bytes).decode("utf-8")


def _image_block(img_bytes: bytes) -> dict:
    """PNG 이미지 블록 생성. media_type을 image/png로 고정."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",   # ← JPEG에서 PNG로 변경
            "data": _b64(img_bytes),
        },
    }


def _call_claude(client: anthropic.Anthropic, content: list, max_tokens: int = 4000) -> str:
    """Claude API 단일 호출. temperature=0 고정으로 재현성 보장."""
    response = client.messages.create(
        model=settings.model_id,
        max_tokens=max_tokens,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


# ── 개별 페이지 추출 ──────────────────────────────────────────────────────────
def _extract_page_sync(
    client: anthropic.Anthropic,
    img_bytes: bytes,
    page_num: int,
    page_type: str,
    prompt_cfg: dict | None = None,
) -> dict:
    """단일 페이지를 타입 전용 프롬프트로 개별 추출. 배치 없이 1페이지 = 1 API 호출."""
    if prompt_cfg is None:
        prompt_cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    content = [
        _image_block(img_bytes),
        {"type": "text", "text": prompt_cfg["instruction"]},
    ]
    try:
        raw = _call_claude(client, content, max_tokens=2000)
        data = parse_json_response(raw)
    except Exception as e:
        data = {"error": str(e)}
    return {"page": page_num, "type": page_type, "data": data}


# ── 타일 분할 추출 (AREA_TABLE · TECHNICAL) ────────────────────────────────────
_TILE_PROMPT_TEMPLATE = (
    "This is a high-density PAGE_TYPE_PLACEHOLDER page split into 4 tiles (2×2 grid).\n"
    "Tiles are ordered: [top-left] [top-right] [bottom-left] [bottom-right].\n"
    "Read all tiles together as one page and extract the complete data.\n\n"
    "SCHEMA:\n"
    "SCHEMA_PLACEHOLDER\n\n"
    "RULES:\n"
    "- Use exact numbers visible in any tile, null if not visible\n"
    "- Numbers may span across tile boundaries — read all tiles before deciding\n"
    "- Respond JSON ONLY, no explanation"
)

_TILE_LABELS = ["[타일 1/4 — 좌상]", "[타일 2/4 — 우상]", "[타일 3/4 — 좌하]", "[타일 4/4 — 우하]"]


def _extract_tiled(
    client: anthropic.Anthropic,
    pdf_path: Path,
    page_index: int,
    page_num: int,
    page_type: str,
) -> dict:
    """
    단일 페이지를 2×2 타일로 분할하여 추출.
    Claude 실효 해상도: 전체 페이지(1568px) → 타일 1개(1240px, 리사이즈 없음)
    → 작은 숫자/표 인식률 1.6배 향상.
    """
    tiles = rasterize_page_tiled(pdf_path, page_index, dpi=150, fmt="png")
    cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    schema = cfg["instruction"].split("\n")[-1]  # JSON 스키마 부분만

    prompt = (
        _TILE_PROMPT_TEMPLATE
        .replace("PAGE_TYPE_PLACEHOLDER", page_type)
        .replace("SCHEMA_PLACEHOLDER", schema)
    )

    content: list[dict] = []
    for label, tile_bytes in zip(_TILE_LABELS, tiles):
        content.append({"type": "text", "text": label})
        content.append(_image_block(tile_bytes))
    content.append({"type": "text", "text": prompt})

    try:
        raw = _call_claude(client, content, max_tokens=4000)
        data = parse_json_response(raw)
    except Exception as e:
        data = {"error": str(e)}

    return {"page": page_num, "type": page_type, "data": data, "_tiled": True}


# ── 메인 추출 로직 ─────────────────────────────────────────────────────────────
async def extract_pdf(
    pdf_path: Path,
    page_map: list[dict] | None = None,
    is_brief: bool = False,
) -> list[dict]:
    """PDF 전체 데이터 추출.

    is_brief=True: 지침서(지침서) 모드. AREA_TABLE/TECHNICAL/SPECIAL_SPACE에
                   brief 전용 요구사항 스키마 적용, 타일 분할 비활성화.
    is_brief=False: 제안서 모드. 신뢰도 >= CONFIDENCE_DOWNGRADE_THRESHOLD인
                    TILE_PAGE_TYPES 페이지만 타일 분할 추출 적용.
    """
    client = anthropic.Anthropic(api_key=settings.api_key)
    all_pages: list[tuple[bytes, int]] = rasterize_pdf(pdf_path, dpi=150, fmt="png")

    type_by_page: dict[int, str] = {}
    confidence_by_page: dict[int, float] = {}
    tile_page_nums: set[int] = set()
    if page_map:
        for entry in page_map:
            pg = entry.get("page", 0)
            pt = entry.get("primary_type", "CONCEPT")
            conf = float(entry.get("confidence", 1.0))
            type_by_page[pg] = pt
            confidence_by_page[pg] = conf
            # 타일 분할: 제안서이고 신뢰도 충분한 경우만
            if pt in TILE_PAGE_TYPES and not is_brief and conf >= CONFIDENCE_DOWNGRADE_THRESHOLD:
                tile_page_nums.add(pg)

    sem = asyncio.Semaphore(4)

    async def extract_one(img_bytes: bytes, page_num: int) -> dict:
        page_type = type_by_page.get(page_num, "CONCEPT")
        confidence = confidence_by_page.get(page_num, 1.0)

        # 신뢰도 낮은 TILE 타입은 일반 타입으로 다운그레이드
        effective_type = page_type
        if page_type in TILE_PAGE_TYPES and confidence < CONFIDENCE_DOWNGRADE_THRESHOLD:
            effective_type = "CONCEPT"

        # 프롬프트 선택: brief 전용 → 일반
        if is_brief and effective_type in EXTRACTION_PROMPTS_BRIEF:
            prompt_cfg = EXTRACTION_PROMPTS_BRIEF[effective_type]
        else:
            prompt_cfg = EXTRACTION_PROMPTS.get(effective_type, FALLBACK_PROMPT)

        async with sem:
            if page_num in tile_page_nums:
                return await asyncio.to_thread(
                    _extract_tiled, client, pdf_path, page_num - 1, page_num, effective_type
                )
            return await asyncio.to_thread(
                _extract_page_sync, client, img_bytes, page_num, effective_type, prompt_cfg
            )

    results = await asyncio.gather(*[extract_one(img, pnum) for img, pnum in all_pages])
    return sorted(results, key=lambda r: r.get("page", 0))


# ── 유틸리티 ──────────────────────────────────────────────────────────────────
def should_extract(page_type: str, priority_limit: int = 2) -> bool:
    cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    return cfg["priority"] <= priority_limit


def merge_extracted_data(
    page_classifications: list[dict],
    extractions: list[dict],
) -> dict:
    """
    페이지별 분류·추출 결과를 타입별로 병합.

    - 페이지 번호 키 기반 매칭: zip 대신 dict lookup으로 중복 분류 결과 안전 처리
    - list 방어: 모델이 JSON 배열을 반환한 경우 {"_items": [...]}로 래핑
    정량 데이터 우선순위: AREA_TABLE > SITE_PLAN
    """
    # 추출 결과를 페이지 번호로 인덱싱
    ext_by_page: dict[int, dict] = {e.get("page", 0): e for e in extractions}

    merged: dict[str, dict] = {}
    seen_pages: set[int] = set()

    for cls in page_classifications:
        pg = cls.get("page", 0)
        if pg in seen_pages:
            continue  # Haiku 배치 응답에서 발생하는 중복 페이지 스킵
        seen_pages.add(pg)

        pt = cls.get("primary_type", "UNKNOWN")
        if pt not in merged:
            merged[pt] = {"count": 0, "pages": [], "combined_data": []}
        merged[pt]["count"] += 1
        merged[pt]["pages"].append(pg)

        ext = ext_by_page.get(pg, {})
        ext_data = ext.get("data", {})
        if isinstance(ext_data, list):
            ext_data = {"_items": ext_data}  # 모델이 배열 반환 시 안전 래핑
        merged[pt]["combined_data"].append({**ext_data, "_page": pg})

    result: dict = {"_by_type": merged}
    for pt, bucket in merged.items():
        key = pt.lower()
        items = bucket["combined_data"]
        result[key] = items[0] if len(items) == 1 else items

    # 정량 데이터: AREA_TABLE 우선, SITE_PLAN 보완
    # AREA_TABLE은 타일 추출로 가장 신뢰도 높음
    quant_fields = (
        "total_floor_area_sqm", "area_above_ground_sqm", "area_below_ground_sqm",
        "site_area_sqm", "building_area_sqm",
        "building_coverage_ratio_pct", "floor_area_ratio_pct",
        "floors_above", "floors_below", "parking_count",
    )
    quant: dict = {}

    # 낮은 우선순위 소스부터 채우고 높은 우선순위가 덮어씀
    for src_key in ("site_plan", "area_table"):   # area_table이 나중 → 우선
        src = result.get(src_key, {})
        if isinstance(src, list):
            src = src[0] if src else {}
        for field in quant_fields:
            if src.get(field) is not None:
                quant[field] = src[field]

    result["_quantitative"] = quant
    return result