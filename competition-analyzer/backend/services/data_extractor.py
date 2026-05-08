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

from config import settings
from services.llm_client import call_messages
from services.utils import ocr_page, parse_json_response, rasterize_pdf, rasterize_page_tiled, safe_encode_image

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
    "UNIT_PLAN": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this unit type plan page. Respond JSON ONLY.\n'
            '{"unit_type":"","supply_area_sqm":null,"service_area_sqm":null,'
            '"actual_area_sqm":null,"actual_area_pyeong":null,"unit_count":null,'
            '"core_type":"","ldk_layout":"","bathroom_count":null,"key_features":[]}'
        ),
    },
    "INCENTIVE_TABLE": {
        "priority": 1,
        "instruction": (
            'EXTRACT from this incentive ratio comparison table. '
            'Respond JSON ONLY. Use exact percentages if visible.\n'
            '{"base_far_pct":null,"applied_far_pct":null,"final_far_pct":null,'
            '"incentive_items":[{"name":"","ratio_pct":null}],'
            '"comparison_basis":[]}'
        ),
    },
    "BRANDING": {
        "priority": 3,
        "instruction": (
            'EXTRACT from this branding page. Respond JSON ONLY.\n'
            '{"brand_name_en":"","brand_name_ko":"","main_slogan":"",'
            '"sub_slogans":[],"target_lifestyle":"","premium_keywords":[]}'
        ),
    },
    "BUSINESS_VIABILITY": {
        "priority": 1,
        "instruction": (
            'EXTRACT business viability data from this Korean redevelopment proposal page. '
            'Respond JSON ONLY.\n'
            '{"asset_value_increase_won":null,"asset_value_multiplier":null,'
            '"member_contribution_change_won":null,"member_contribution_change_pct":null,'
            '"general_sale_units":null,"member_units":null,"sale_price_per_pyeong_won":null,'
            '"far_base_pct":null,"far_incentive_pct":null,"far_final_pct":null,'
            '"construction_cost_savings_won":null,"period_reduction_months":null,'
            '"key_messages":[]}'
        ),
    },
    "AREA_INCREASE": {
        "priority": 1,
        "instruction": (
            'EXTRACT existing-vs-redeveloped area comparison from this page. '
            'Respond JSON ONLY. Pair each existing unit type with its redeveloped counterpart.\n'
            '{"comparison_basis":"existing_vs_redeveloped",'
            '"unit_pairs":[{"existing_type":"","existing_actual_sqm":null,'
            '"redev_type":"","redev_actual_sqm":null,'
            '"increase_sqm":null,"increase_pyeong":null,"increase_pct":null}],'
            '"max_increase_multiplier":null,"average_increase_pyeong":null,'
            '"key_message":""}'
        ),
    },
    "VIEW_ANALYSIS": {
        "priority": 2,
        "instruction": (
            'EXTRACT view rights analysis from this site planning page. Respond JSON ONLY.\n'
            '{"south_facing_units_pct":null,"river_view_units_pct":null,'
            '"double_view_units_pct":null,"member_units_view_guarantee_pct":null,'
            '"view_targets":[],"site_layout_strategy":"","key_message":""}'
        ),
    },
    "COMMUNITY_PROGRAM": {
        "priority": 2,
        "instruction": (
            'EXTRACT signature community facility data from this Korean redevelopment page. '
            'Respond JSON ONLY.\n'
            '{"total_program_count":null,"area_per_household_pyeong":null,'
            '"signature_facilities":[],"sky_community_present":false,'
            '"hotel_style_features":[],"premium_keywords":[],"key_message":""}'
        ),
    },
    "COMPANY_PORTFOLIO": {
        "priority": 2,
        "instruction": (
            'EXTRACT firm credentials data from this page. Respond JSON ONLY.\n'
            '{"firm_name":"","total_employees":null,"licensed_architects":null,'
            '"financial_revenue_won":null,"credit_rating":"","design_awards":[],'
            '"similar_projects":[{"name":"","year":null,"highlight":""}],'
            '"key_executives":[{"name":"","role":""}]}'
        ),
    },
    "CONSTRUCTION_PLAN": {
        "priority": 2,
        "instruction": (
            'EXTRACT construction strategy data from this page. Respond JSON ONLY.\n'
            '{"period_reduction_months":null,"cost_savings_won":null,'
            '"underground_parking_levels":null,"underground_excavation_depth_m":null,'
            '"parking_per_household":null,"deck_floor_height_m":null,'
            '"smart_parking_features":[],"construction_strategies":[]}'
        ),
    },
    "UNIT_PLAN_PENTHOUSE": {
        "priority": 1,
        "instruction": (
            'EXTRACT penthouse unit plan data from this page. Respond JSON ONLY.\n'
            '{"unit_type":"","unit_count":null,'
            '"exclusive_area_sqm":null,"supply_area_sqm":null,"service_area_sqm":null,'
            '"actual_area_sqm":null,"actual_area_pyeong":null,'
            '"terrace_area_sqm":null,"ceiling_height_m":null,"open_sides":null,'
            '"signature_features":[],"luxury_keywords":[]}'
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
TILE_PAGE_TYPES = {
    "AREA_TABLE", "TECHNICAL", "INCENTIVE_TABLE",
    "BUSINESS_VIABILITY", "AREA_INCREASE",
}

# 추출 스킵 임계: priority가 이 값 이상이면 Claude 호출 생략 (토큰 절감)
# priority=3 타입(COVER/RENDERING_EXT/RENDERING_INT)은 비교분석 입력에 거의 기여하지 않음
SKIP_PRIORITY_THRESHOLD = 3

# ── 토큰 절감 설정 ────────────────────────────────────────────────────────────
# OCR 우선 추출: PaddleOCR(무료·로컬)로 텍스트를 읽고 Haiku로 구조화.
# Sonnet + 이미지 전송을 피해 페이지당 ~90% 비용 절감.
# OCR 결과가 불충분(< OCR_MIN_CHARS)하면 자동으로 기존 vision 추출로 fallback.
OCR_FIRST_TYPES = {
    "AREA_TABLE", "TECHNICAL", "SUSTAINABILITY",
    "BUSINESS_VIABILITY", "AREA_INCREASE", "COMPANY_PORTFOLIO", "CONSTRUCTION_PLAN",
}
OCR_MIN_CHARS = 80  # 이 글자수 미만이면 OCR 불충분 → vision fallback

# 스킵 대상: 비교분석에 사용되지 않는 시각 위주 페이지.
# settings.extraction_priority_limit=3으로 올리면 기존 동작(전 페이지 추출) 복원.
SKIP_PAGE_TYPES = {"COVER", "RENDERING_EXT", "RENDERING_INT"}

# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────
def _b64(img_bytes: bytes) -> str:
    return base64.standard_b64encode(img_bytes).decode("utf-8")


def _image_block(img_bytes: bytes) -> dict:
    safe_bytes, fmt = safe_encode_image(img_bytes, fmt="png")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": f"image/{fmt}",
            "data": _b64(safe_bytes),
        },
    }


def _call_claude(content: list, max_tokens: int = 4000) -> str:
    """Claude 단일 호출 (provider 추상화 경유). temperature=0 고정으로 재현성 보장."""
    return call_messages(
        model=settings.model_id,
        max_tokens=max_tokens,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )


# ── 개별 페이지 추출 ──────────────────────────────────────────────────────────
def _extract_page_sync(
    img_bytes: bytes,
    page_num: int,
    page_type: str,
    prompt_cfg: dict | None = None,
) -> dict:
    """단일 페이지를 타입 전용 프롬프트로 개별 추출. 배치 없이 1페이지 = 1 호출."""
    if prompt_cfg is None:
        prompt_cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    content = [
        _image_block(img_bytes),
        {"type": "text", "text": prompt_cfg["instruction"]},
    ]
    try:
        raw = _call_claude(content, max_tokens=2000)
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
        raw = _call_claude(content, max_tokens=4000)
        data = parse_json_response(raw)
    except Exception as e:
        data = {"error": str(e)}

    return {"page": page_num, "type": page_type, "data": data, "_tiled": True}


# ── OCR 텍스트 추출 (이미지 토큰 0) ──────────────────────────────────────────
def _extract_ocr_text_only(
    pdf_path: Path,
    page_index: int,
    page_num: int,
    page_type: str,
    prompt_cfg: dict,
) -> dict | None:
    """
    PaddleOCR(무료) → Haiku(저렴)로 페이지 추출.
    이미지를 Claude에 전송하지 않으므로 입력 이미지 토큰이 0.

    Returns None if OCR text is insufficient (< OCR_MIN_CHARS) → caller falls
    back to vision extraction.
    """
    raw_text = ocr_page(pdf_path, page_index, dpi=300)
    if len(raw_text.strip()) < OCR_MIN_CHARS:
        return None  # OCR 불충분 → vision fallback

    content = [
        {
            "type": "text",
            "text": (
                "다음 텍스트는 건축 설계공모 PDF 페이지에서 OCR 추출한 내용입니다.\n\n"
                f"--- OCR 텍스트 ---\n{raw_text}\n---\n\n"
                f"{prompt_cfg['instruction']}"
            ),
        }
    ]
    try:
        raw = call_messages(
            model=settings.model_id_classify,  # Haiku — 텍스트 구조화는 Sonnet 불필요
            max_tokens=2000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        data = parse_json_response(raw)
    except Exception as e:
        data = {"error": str(e)}

    return {"page": page_num, "type": page_type, "data": data, "_source": "ocr_haiku"}


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

        # ── 스킵: 비교분석에 미사용 페이지 (COVER, RENDERING_EXT/INT)
        priority_limit = settings.extraction_priority_limit
        cfg_for_check = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
        if cfg_for_check["priority"] > priority_limit or page_type in SKIP_PAGE_TYPES:
            return {"page": page_num, "type": page_type, "data": {}, "_skipped": True}

        # 신뢰도 낮은 TILE 타입은 일반 타입으로 다운그레이드
        effective_type = page_type
        if page_type in TILE_PAGE_TYPES and confidence < CONFIDENCE_DOWNGRADE_THRESHOLD:
            effective_type = "CONCEPT"

        # 프롬프트 선택: brief 전용 → 일반
        if is_brief and effective_type in EXTRACTION_PROMPTS_BRIEF:
            prompt_cfg = EXTRACTION_PROMPTS_BRIEF[effective_type]
        else:
            prompt_cfg = EXTRACTION_PROMPTS.get(effective_type, FALLBACK_PROMPT)

        # priority=3 페이지는 Claude 호출 없이 빈 데이터로 통과 (토큰 절감)
        if prompt_cfg.get("priority", 3) >= SKIP_PRIORITY_THRESHOLD:
            return {"page": page_num, "type": effective_type, "data": {}, "_skipped": True}

        async with sem:
            # ── OCR fast-path: AREA_TABLE / TECHNICAL / SUSTAINABILITY
            # PaddleOCR(무료·로컬) → Haiku(저렴). 이미지 토큰 0.
            # OCR 결과 불충분 시 자동으로 아래 vision 경로로 fallback.
            if effective_type in OCR_FIRST_TYPES:
                ocr_result = await asyncio.to_thread(
                    _extract_ocr_text_only,
                    pdf_path, page_num - 1, page_num, effective_type, prompt_cfg,
                )
                if ocr_result is not None:
                    return ocr_result
                # OCR 불충분 → 이하 vision 추출로 계속

            if page_num in tile_page_nums:
                return await asyncio.to_thread(
                    _extract_tiled, pdf_path, page_num - 1, page_num, effective_type
                )
            return await asyncio.to_thread(
                _extract_page_sync, img_bytes, page_num, effective_type, prompt_cfg
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
    at_list = result.get("area_table", [])
    if isinstance(at_list, dict):
        at_list = [at_list]
    sp_list = result.get("site_plan", [])
    if isinstance(sp_list, dict):
        sp_list = [sp_list]

    # area_table 전체 → site_plan 전체 순서로 순회, first-write wins (area_table 우선)
    for entry in at_list + sp_list:
        if not isinstance(entry, dict):
            continue
        for field in quant_fields:
            v = entry.get(field)
            if v is not None and field not in quant:
                quant[field] = v

    result["_quantitative"] = quant
    return result