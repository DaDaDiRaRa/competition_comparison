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

# 타일 분할 적용 대상: 정보 밀도가 높아 전체 페이지 전송 시 숫자 오독 위험
TILE_PAGE_TYPES = {"AREA_TABLE", "TECHNICAL"}

# 배치 크기: Claude API 1회 호출당 최대 이미지 수
EXTRACT_BATCH_SIZE = 10


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


# ── 일반 배치 추출 ─────────────────────────────────────────────────────────────
_BATCH_PROMPT_TEMPLATE = (
    "TASK: Extract data from each page shown below.\n\n"
    "For each page, identify its type and extract relevant data.\n"
    "Output a JSON array, one object per page.\n\n"
    "PAGE_TYPE_SCHEMAS:\n"
    "SCHEMA_PLACEHOLDER\n\n"
    "RULES:\n"
    "- Extract ONLY what is visually present\n"
    "- Numbers must be exact if visible, null if not visible\n"
    "- Use Korean for Korean text, English for English text\n\n"
    'RESPOND JSON ONLY:\n'
    '[{"page":1,"type":"PAGE_TYPE","data":{...}}, ...]'
)


def _build_batch_prompt(page_map: list[dict] | None) -> str:
    """
    page_map이 있으면 이미 분류된 타입 정보를 프롬프트에 포함.
    → Claude가 타입 추측 없이 추출에만 집중할 수 있음.
    .replace() 사용 — JSON 중괄호로 인한 KeyError 방지 (CLAUDE.md 규칙).
    """
    if page_map:
        schema_lines = []
        seen = set()
        for p in page_map:
            pt = p.get("primary_type", "UNKNOWN")
            if pt not in seen and pt in EXTRACTION_PROMPTS:
                seen.add(pt)
                cfg = EXTRACTION_PROMPTS[pt]
                schema_lines.append(f"- {pt}: {cfg['instruction'].split(chr(10))[-1]}")
        schema_str = "\n".join(schema_lines)
    else:
        schema_str = "\n".join(
            f"- {pt}: {cfg['instruction'].split(chr(10))[-1]}"
            for pt, cfg in EXTRACTION_PROMPTS.items()
        )

    return _BATCH_PROMPT_TEMPLATE.replace("SCHEMA_PLACEHOLDER", schema_str)


def _extract_batch(
    client: anthropic.Anthropic,
    batch: list[tuple[bytes, int]],
    page_map: list[dict] | None,
) -> list[dict]:
    """
    이미지 배치 → Claude → JSON 리스트 반환.
    page_map이 있으면 각 이미지 앞에 페이지 번호/타입 레이블 추가.
    """
    prompt = _build_batch_prompt(page_map)

    content: list[dict] = []
    for idx, (img_bytes, page_num) in enumerate(batch):
        if page_map and idx < len(page_map):
            pt = page_map[idx].get("primary_type", "UNKNOWN")
            content.append({"type": "text", "text": f"[Page {page_num} — {pt}]"})
        content.append(_image_block(img_bytes))
    content.append({"type": "text", "text": prompt})

    try:
        raw = _call_claude(client, content, max_tokens=8000)
        results = parse_json_response(raw)
        if not isinstance(results, list):
            results = [results]
    except Exception as e:
        return [{"page": batch[0][1], "type": "UNKNOWN", "data": {}, "error": str(e)}]

    for i, r in enumerate(results):
        r["page"] = batch[i][1] if i < len(batch) else batch[0][1] + i
    return results


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
def _extract_pdf_sync(pdf_path: Path, page_map: list[dict] | None = None) -> list[dict]:
    """
    PDF 전체 추출.

    Parameters
    ----------
    pdf_path : Path
        추출할 PDF 경로.
    page_map : list[dict] | None
        page_classifier 결과. 있으면 타입별 최적화 적용.
        형식: [{"page":1, "primary_type":"COVER", ...}, ...]

    Returns
    -------
    list[dict]
        [{"page":N, "type":"...", "data":{...}}, ...]
    """
    client = anthropic.Anthropic(api_key=settings.api_key)

    # 1. 전체 페이지 PNG 래스터라이즈 (150 DPI, 무손실)
    all_pages: list[tuple[bytes, int]] = rasterize_pdf(pdf_path, dpi=150, fmt="png")

    # 2. 타일 분할 대상 페이지 인덱스 파악
    tile_indices: set[int] = set()
    if page_map:
        for entry in page_map:
            pt = entry.get("primary_type", "")
            pg = entry.get("page", 0)
            if pt in TILE_PAGE_TYPES and pg > 0:
                tile_indices.add(pg - 1)  # 0-based index

    # 3. 일반 배치 추출 (타일 대상 페이지 제외)
    normal_pages = [p for p in all_pages if (p[1] - 1) not in tile_indices]
    all_results: list[dict] = []

    for batch_start in range(0, len(normal_pages), EXTRACT_BATCH_SIZE):
        batch = normal_pages[batch_start:batch_start + EXTRACT_BATCH_SIZE]

        # 해당 배치의 page_map 슬라이싱
        batch_page_nums = {p[1] for p in batch}
        batch_map = (
            [e for e in page_map if e.get("page", 0) in batch_page_nums]
            if page_map else None
        )

        all_results.extend(_extract_batch(client, batch, batch_map))

    # 4. 타일 분할 추출 (AREA_TABLE · TECHNICAL)
    if page_map:
        for entry in page_map:
            pg = entry.get("page", 0)
            idx = pg - 1
            if idx in tile_indices:
                pt = entry.get("primary_type", "AREA_TABLE")
                tiled_result = _extract_tiled(client, pdf_path, idx, pg, pt)
                all_results.append(tiled_result)

    # 5. 페이지 번호 순 정렬
    all_results.sort(key=lambda r: r.get("page", 0))
    return all_results


async def extract_pdf(pdf_path: Path, page_map: list[dict] | None = None) -> list[dict]:
    """PDF 전체 데이터 추출 (비동기 진입점)."""
    async with asyncio.Semaphore(6):
        return await asyncio.to_thread(_extract_pdf_sync, pdf_path, page_map)


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

    정량 데이터 우선순위:
      AREA_TABLE (타일 추출, 가장 정확) > SITE_PLAN > 나머지
    """
    merged: dict[str, dict] = {}

    for cls, ext in zip(page_classifications, extractions):
        pt = cls.get("primary_type", "UNKNOWN")
        if pt not in merged:
            merged[pt] = {"count": 0, "pages": [], "combined_data": []}
        merged[pt]["count"] += 1
        merged[pt]["pages"].append(cls.get("page", 0))

        ext_data = ext.get("data", ext)
        merged[pt]["combined_data"].append({**ext_data, "_page": cls.get("page", 0)})

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