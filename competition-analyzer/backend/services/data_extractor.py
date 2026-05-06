import asyncio
from pathlib import Path

import anthropic

from config import settings
from services.utils import encode_image, parse_json_response

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

# Priority: 1=critical, 2=important, 3=supplementary
EXTRACTION_PROMPTS: dict[str, dict] = {
    "COVER": {
        "priority": 3,
        "instruction": """\
EXTRACT from this cover page. Respond JSON ONLY.
{"competition_name":"","submission_code":"","submitter":""}""",
    },
    "CONCEPT": {
        "priority": 1,
        "instruction": """\
EXTRACT from this design concept page. Respond JSON ONLY.
{
  "concept_name_ko": "",
  "concept_name_en": "",
  "keywords": [],
  "massing_type": "horizontal|vertical|stepped|stacked|hybrid|formal_tower",
  "main_strategy": "",
  "sub_strategies": [],
  "metaphor_reference": "",
  "target_user": []
}""",
    },
    "TOC_HERO": {
        "priority": 1,
        "instruction": """\
EXTRACT from this TOC/hero page. Respond JSON ONLY.
{
  "concept_name_ko": "",
  "concept_name_en": "",
  "toc_sections": [{"section": "", "page_start": 0}],
  "total_sections": 0,
  "has_hero_rendering": true,
  "rendering_view_type": "aerial|street|park|night"
}""",
    },
    "SITE_CONTEXT": {
        "priority": 2,
        "instruction": """\
EXTRACT from this site context page. Respond JSON ONLY.
{
  "site_issues": [],
  "surrounding_facilities": [],
  "urban_strategy": "",
  "transportation_connections": [],
  "historical_context": "",
  "green_network": ""
}""",
    },
    "SITE_PLAN": {
        "priority": 1,
        "instruction": """\
EXTRACT from this site plan. Respond JSON ONLY. Use exact numbers if visible.
{
  "site_area_sqm": null,
  "building_area_sqm": null,
  "total_floor_area_sqm": null,
  "building_coverage_ratio_pct": null,
  "floor_area_ratio_pct": null,
  "building_height_m": null,
  "floors_above": null,
  "floors_below": null,
  "parking_count": null,
  "scale": "",
  "main_entrance_direction": "",
  "vehicle_access_direction": "",
  "open_space_strategy": ""
}""",
    },
    "FLOOR_PLAN": {
        "priority": 2,
        "instruction": """\
EXTRACT from this floor plan. Respond JSON ONLY.
{
  "floor_level": "",
  "scale": "",
  "main_programs": [],
  "core_count": 0,
  "core_type": "center|side|dual|distributed",
  "office_layout": "open|closed|hybrid",
  "public_programs_on_this_floor": [],
  "special_spaces": [],
  "has_outdoor_terrace": false
}""",
    },
    "SECTION": {
        "priority": 1,
        "instruction": """\
EXTRACT from this section drawing. Respond JSON ONLY.
{
  "section_direction": "longitudinal|transverse",
  "total_height_m": null,
  "typical_floor_height_m": null,
  "ground_floor_height_m": null,
  "underground_levels": null,
  "underground_depth_m": null,
  "structural_system_visible": "",
  "atrium_present": false,
  "setback_visible": false,
  "key_spatial_features": []
}""",
    },
    "ELEVATION": {
        "priority": 1,
        "instruction": """\
EXTRACT from this elevation drawing. Respond JSON ONLY.
{
  "facade_direction": "north|south|east|west",
  "primary_material": "",
  "secondary_material": "",
  "facade_system": "curtain_wall|precast|brick|stone|metal_panel|louver|mega_panel|unitized",
  "shading_device": "",
  "green_facade": false,
  "transparency_ratio": "high|medium|low",
  "facade_rhythm": "uniform|varied|gradient"
}""",
    },
    "RENDERING_EXT": {
        "priority": 3,
        "instruction": """\
EXTRACT from this exterior rendering. Respond JSON ONLY.
{
  "view_type": "aerial|street|park|corner|distant",
  "time_of_day": "day|dusk|night",
  "massing_impression": "",
  "facade_material_visible": [],
  "landscape_elements": [],
  "human_activity_shown": [],
  "sky_treatment": "clear|cloudy|dramatic"
}""",
    },
    "RENDERING_INT": {
        "priority": 3,
        "instruction": """\
EXTRACT from this interior rendering. Respond JSON ONLY.
{
  "space_type": "",
  "ceiling_type": "exposed|finished|double_height|atrium",
  "natural_light": "abundant|moderate|minimal",
  "furniture_style": "modern|traditional|mixed",
  "material_palette": [],
  "user_activities_shown": []
}""",
    },
    "LANDSCAPE": {
        "priority": 2,
        "instruction": """\
EXTRACT from this landscape plan. Respond JSON ONLY.
{
  "green_area_ratio_pct": null,
  "tree_types": [],
  "outdoor_programs": [],
  "water_feature": false,
  "pavement_types": [],
  "connection_to_surroundings": "",
  "key_landscape_concept": ""
}""",
    },
    "CIRCULATION": {
        "priority": 2,
        "instruction": """\
EXTRACT from this circulation plan. Respond JSON ONLY.
{
  "pedestrian_main_access": [],
  "vehicle_access": [],
  "service_access": "",
  "emergency_route": "",
  "barrier_free_route": "",
  "subway_connection": false,
  "drop_off_location": ""
}""",
    },
    "SPECIAL_SPACE": {
        "priority": 2,
        "instruction": """\
EXTRACT from this special space planning page. Respond JSON ONLY.
{
  "space_name": "",
  "space_type": "lobby|community|culture|office|council|children|rooftop|plaza|other",
  "key_features": [],
  "target_users": [],
  "spatial_strategy": ""
}""",
    },
    "HEALTH_CENTER": {
        "priority": 2,
        "instruction": """\
EXTRACT from this health center page. Respond JSON ONLY.
{
  "page_content_type": "concept|floor_plan|section|elevation|rendering",
  "health_programs": [],
  "floors_dedicated": null,
  "separate_entrance": false,
  "key_planning_strategy": ""
}""",
    },
    "TECHNICAL": {
        "priority": 2,
        "instruction": """\
EXTRACT from this technical review page. Respond JSON ONLY.
{
  "technical_domain": "structural|mep|fire|environmental|energy|acoustic|it",
  "structural_system": "",
  "foundation_type": "",
  "hvac_system": "",
  "energy_strategies": [],
  "green_certification_target": "",
  "fire_safety_features": [],
  "smart_building_features": []
}""",
    },
    "AREA_TABLE": {
        "priority": 1,
        "instruction": """\
EXTRACT from this area/cost table. Respond JSON ONLY. Use exact numbers if visible.
{
  "total_floor_area_sqm": null,
  "area_above_ground_sqm": null,
  "area_below_ground_sqm": null,
  "building_area_sqm": null,
  "site_area_sqm": null,
  "building_coverage_ratio_pct": null,
  "floor_area_ratio_pct": null,
  "parking_count": null,
  "floors_above": null,
  "floors_below": null,
  "estimated_total_cost": "",
  "cost_per_sqm": "",
  "program_areas": []
}""",
    },
    "SUSTAINABILITY": {
        "priority": 2,
        "instruction": """\
EXTRACT from this sustainability page. Respond JSON ONLY.
{
  "green_certification": "",
  "energy_grade_target": "",
  "renewable_energy": [],
  "water_management": [],
  "carbon_reduction_strategies": [],
  "smart_building": [],
  "key_sustainability_concept": ""
}""",
    },
}

FALLBACK_PROMPT = {
    "priority": 3,
    "instruction": """\
EXTRACT key information from this page. Respond JSON ONLY.
{"key_elements":[],"text_content":[]}""",
}


def _extract_page_sync(image_path: Path, page_type: str) -> dict:
    prompt_cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    client = anthropic.Anthropic(api_key=settings.api_key)
    img_data, media_type = encode_image(image_path)

    response = client.messages.create(
        model=settings.model_id,
        max_tokens=800,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": img_data},
                    },
                    {"type": "text", "text": prompt_cfg["instruction"]},
                ],
            }
        ],
    )

    return parse_json_response(response.content[0].text)


async def extract_page(image_path: Path, page_type: str) -> dict:
    return await asyncio.to_thread(_extract_page_sync, image_path, page_type)


def should_extract(page_type: str, priority_limit: int = 2) -> bool:
    cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    return cfg["priority"] <= priority_limit


def merge_extracted_data(page_classifications: list[dict], extractions: list[dict]) -> dict:
    """Merge per-page extractions by type, same as Node 2 merge_by_type."""
    merged: dict[str, dict] = {}
    for cls, ext in zip(page_classifications, extractions):
        pt = cls.get("primary_type", "UNKNOWN")
        if pt not in merged:
            merged[pt] = {"count": 0, "pages": [], "combined_data": []}
        merged[pt]["count"] += 1
        merged[pt]["pages"].append(cls.get("page", 0))
        merged[pt]["combined_data"].append({**ext, "_page": cls.get("page", 0)})

    # Flat shortcut: first occurrence of each critical type
    result: dict = {"_by_type": merged}
    for pt, bucket in merged.items():
        key = pt.lower()
        items = bucket["combined_data"]
        result[key] = items[0] if len(items) == 1 else items

    # Aggregate quantitative fields from AREA_TABLE + SITE_PLAN
    quant: dict = {}
    for src_key in ("area_table", "site_plan"):
        src = result.get(src_key, {})
        if isinstance(src, list):
            src = src[0] if src else {}
        for field in (
            "total_floor_area_sqm", "site_area_sqm", "building_area_sqm",
            "building_coverage_ratio_pct", "floor_area_ratio_pct",
            "floors_above", "floors_below", "parking_count",
        ):
            if field in src and src[field] is not None:
                quant[field] = src[field]
    result["_quantitative"] = quant

    return result
