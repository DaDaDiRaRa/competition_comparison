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
import io
import json
from pathlib import Path

from config import settings, axes_keys_for
from services.llm_client import call_messages
from services.utils import get_page_text, ocr_page, parse_json_response, rasterize_pdf, rasterize_page_tiled, safe_encode_image

_BRIEF_REQ_SYSTEM = (
    "You are an architectural competition brief analyst. "
    "Extract structured requirements from already-parsed competition brief data. "
    "Respond ONLY in JSON. Use Korean for all descriptions."
)

_BRIEF_REQ_PROMPT_TEMPLATE = """\
TASK: extract_brief_requirements
AXES: {axes_str}

BRIEF_DATA (already extracted from PDF):
{brief_json}

Map the brief's requirements/constraints to the competition axes.
Extract evaluation criteria (배점표) if present.
List any special design or technical requirements.

OUTPUT_ONLY_JSON:
{
  "requirements": [{"axis": "<axis_key>", "description": "<Korean 30chars>", "weight_pct": null}],
  "evaluation_criteria": [{"item": "<Korean>", "points": null}],
  "special_requirements": ["<Korean 30chars>"]
}"""

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
# BRIEF_* 타입(9개)은 이 dict에서 전용 스키마로 추출.
# 구 submission 타입 override(AREA_TABLE/TECHNICAL/SPECIAL_SPACE)도 하위호환 유지.
EXTRACTION_PROMPTS_BRIEF: dict[str, dict] = {
    # ── 신규 BRIEF_* 타입 ─────────────────────────────────────────────────────
    "BRIEF_OVERVIEW": {
        "priority": 1,
        "instruction": (
            'EXTRACT competition overview from this brief page. Respond JSON ONLY.\n'
            '{"competition_name":"","organizer":"","budget_won":null,'
            '"schedule":{"submission_deadline":"","winner_announcement":"","qa_period":""},'
            '"eligible_applicants":"","awards":[{"rank":"","prize_won":null}],'
            '"brief_summary":""}'
        ),
    },
    "BRIEF_PROJECT_INFO": {
        "priority": 1,
        "instruction": (
            'EXTRACT project overview data from this competition brief page. '
            'Respond JSON ONLY.\n'
            '{\n'
            '"competition_name":"","organizer":"","competition_type":"",\n'
            '"sites":[\n'
            '  {"site_id":"","address":"","zoning":"","scope":"","facilities":[],\n'
            '   "site_area_sqm":null,"floor_area_sqm":null,\n'
            '   "building_coverage_pct":null,"floor_area_ratio_pct":null,\n'
            '   "max_height_m":null,"open_space_sqm":null,"open_space_notes":""}\n'
            '],\n'
            '"construction_cost_100m_won":null,"design_cost_100m_won":null,\n'
            '"construction_period_months":null,\n'
            '"budget_notes":[],"special_conditions":[]\n'
            '}\n\n'
            'FIELD NOTES:\n'
            '- site_id: use label from brief exactly (부지1/부지2, A/B, 단일부지, etc.); '
            'if no label given use "단일부지"\n'
            '- zoning: 용도지역·지구 as a single string (e.g. "제2종 일반주거지역")\n'
            '- scope: 공모범위·건축구분 (e.g. "신축", "해체 및 신축", "리모델링")\n'
            '- facilities: list of 도입시설 strings for this site\n'
            '- construction_cost_100m_won: 예정 공사비 in 억원 as number. '
            'UNIT CONVERSION (convert to 억원 before storing): '
            '"억원" → as-is / "백만원" → ÷100 / "만원" → ÷10000. '
            'Examples: "268,611백만원" → 2686 / "26.9억원" → 26.9 / "26,900만원" → 26.9. '
            'null if not stated.\n'
            '- design_cost_100m_won: 예정 설계비 in 억원 as number. '
            'Apply same unit conversion as construction_cost_100m_won. null if not stated.\n'
            '- construction_period_months: 공사 기간 in months as integer (null if not stated)\n'
            '- budget_notes: list of cost basis strings (공사비 산정 기준, 포함 항목 등)\n'
            '- special_conditions: list of special condition strings (면적 허용 오차 ±5% 등)\n'
            '- sites: one entry per site; if multiple sites (부지1/부지2 등) appear, '
            'create one sites[] entry per site — do NOT merge into one entry\n'
            'KOREAN LABEL → FIELD MAPPING (find these labels in tables on the page):\n'
            '  "건폐율(%)" or "건폐율" → sites[].building_coverage_pct (number only, e.g. 60)\n'
            '  "용적률(%)" or "용적률" → sites[].floor_area_ratio_pct (number only, e.g. 400)\n'
            '  "대지면적(㎡)" or "대지면적" → sites[].site_area_sqm\n'
            '  "건축규모" or "연면적(㎡)" or "연면적" → sites[].floor_area_sqm\n'
            '  "높이(m)" or "최고높이" or "건축물높이" → sites[].max_height_m\n'
            '  "공개공지(㎡)" or "공개공지면적" → sites[].open_space_sqm\n'
            'PARENTHETICAL PREFIX RULE: values like "(완화) 460%" or "(조건부) 50m" — '
            'extract the NUMBER only, ignore the parenthetical prefix entirely\n'
            '- Do NOT invent values. null if not visible on page.'
        ),
    },
    "BRIEF_SITE": {
        "priority": 2,
        "instruction": (
            'EXTRACT site information from this competition brief page. Respond JSON ONLY.\n'
            '{"address":"","site_area_sqm":null,"zoning":"","current_use":"",'
            '"surrounding_context":"","transportation":[],'
            '"site_constraints":[],"notable_features":[]}'
        ),
    },
    "BRIEF_PROGRAM": {
        "priority": 1,
        "instruction": (
            'EXTRACT required program and area from this competition brief. '
            'Respond JSON ONLY. Use exact numbers if visible, null if not visible.\n'
            'If multiple sites (부지) appear, list each in the "sites" array; '
            'for a single site use exactly one entry.\n'
            '{\n'
            '"total_required_floor_area_sqm":null,\n'
            '"max_floors_above":null,"max_floors_below":null,"required_parking":null,\n'
            '"estimated_construction_cost":"",\n'
            '"estimated_design_fee":"",\n'
            '"design_period":"",\n'
            '"sites":[\n'
            '  {"site_id":"부지1","address":"","zoning":[],"construction_type":"",\n'
            '   "building_use":"","facilities":[],"site_area_sqm":null,\n'
            '   "floor_area_sqm":null,"building_coverage_limit_pct":null,\n'
            '   "floor_area_ratio_limit_pct":null,"max_height_m":null,\n'
            '   "public_open_space_sqm":null,"public_open_space_notes":""}\n'
            '],\n'
            '"area_rows":[\n'
            '  {"row_type":"space","name":"","area":null,"subtotal_area":null,\n'
            '   "is_subtotal":false,"note":"","dept":""}\n'
            '],\n'
            '"shared_areas":[{"name":"","area_sqm":null,"notes":""}]\n'
            '}\n\n'
            'FIELD NOTES:\n'
            '- sites[].zoning: list of all 지역지구 strings\n'
            '- sites[].construction_type: 건축구분 (e.g. "해체 및 신축")\n'
            '- sites[].building_use: 건축용도\n'
            '- sites[].facilities: list of 도입시설 strings for this site\n'
            '- sites[].public_open_space_sqm: 공개공지 최소 면적 ㎡ (null if not stated)\n'
            '- sites[].public_open_space_notes: 공개공지 추가 조건\n'
            '- area_rows[]: 면적 프로그램 표의 각 행을 flat 리스트로 추출 '
            '(계층 재구성은 코드가 담당 — LLM은 각 행의 종류만 판단).\n'
            '  row_type 기준 (들여쓰기·폰트 크기·굵기 등으로 판단):\n'
            '    "site_total" — 부지 합계·총 합계 행 (표 최상위)\n'
            '    "facility"   — 구청·보건소·어린이집 등 시설 단위\n'
            '    "bureau"     — 직무공간·행정국·구민이용공간 등 국/대영역 단위\n'
            '    "division"   — 이무과·복지정책과 등 과/중간영역 단위\n'
            '    "space"      — 사무공간·비화창고 등 실제 세부공간 (표 최하위)\n'
            '  area: 왼쪽 컬럼 면적(세부공간 실면적, ㎡). 표에 없으면 null.\n'
            '  subtotal_area: 오른쪽 컬럼 면적(과·국·시설 합계, ㎡). 없으면 null.\n'
            '  is_subtotal: true = 소계·합계·그룹 레이블 행(직접 사용 공간 없음).\n'
            '    조건: 이름에 "합계"·"소계"·"①②③" 포함, 또는 하위 공간 없는 그룹 헤더.\n'
            '  note: 배치 조건·특기사항 등 비고 컬럼 텍스트.\n'
            '  dept: 소관부서 컬럼 값. 컬럼 없으면 "".\n'
            '  중요: 소계·합계 행의 면적은 subtotal_area에만 기록, area=null.\n'
            '        소계 행을 area_rows에 포함하되 is_subtotal=true 표시.\n'
            '- shared_areas[]: 공용·설비·주차 등 여러 시설이 공유하는 면적\n'
            '- estimated_construction_cost: 예정 공사비 (억/만원 단위 포함)\n'
            '- estimated_design_fee: 예정 설계비 텍스트\n'
            '- design_period: 예정 설계 기간 텍스트\n'
            '- Do NOT invent values. null/[] if not visible on page.'
        ),
    },
    "BRIEF_DESIGN_MASSING": {
        "priority": 1,
        "instruction": (
            'EXTRACT site planning, massing and circulation guidelines from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"building_setback_m":null,'
            '"open_space_requirements":[],'
            '"parking_requirements":[],'
            '"pedestrian_requirements":[],'
            '"connection_requirements":[],'
            '"height_strategy":"",'
            '"massing_guidelines":[]}'
            '\n\nFIELD NOTES:\n'
            '- building_setback_m: numeric setback distance from boundary (meters), null if not specified\n'
            '- open_space_requirements[]: 공개공지·외부공간 조성 요구사항 문자열 목록\n'
            '- parking_requirements[]: 주차 동선·진입 관련 지침 문자열 목록\n'
            '- pedestrian_requirements[]: 보행 환경·보행로 관련 지침\n'
            '- connection_requirements[]: 인접 건물·지하철·공공공간 연결 요건\n'
            '- height_strategy: 높이 계획 방향 (단일 문자열, 수치 제한이 아닌 매싱 전략)\n'
            '- massing_guidelines[]: 그 외 배치·매싱 관련 지침 문자열 목록\n'
            '- Do NOT invent values. null/[] if not visible on page.'
        ),
    },
    "BRIEF_DESIGN_FACADE": {
        "priority": 1,
        "instruction": (
            'EXTRACT facade, materials and landscape guidelines from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"primary_materials":[],'
            '"prohibited_materials":[],'
            '"color_requirements":[],'
            '"facade_guidelines":[],'
            '"landscape_requirements":[]}'
            '\n\nFIELD NOTES:\n'
            '- primary_materials[]: 지정 또는 권장 외장 마감재 목록\n'
            '- prohibited_materials[]: 사용 금지 재료 목록\n'
            '- color_requirements[]: 색채 계획 관련 지침 문자열 목록\n'
            '- facade_guidelines[]: 입면 디자인·파사드 구성 관련 지침\n'
            '- landscape_requirements[]: 조경·경관 관련 요구사항\n'
            '- Do NOT invent values. null/[] if not visible on page.'
        ),
    },
    "BRIEF_DESIGN_SUSTAIN": {
        "priority": 1,
        "instruction": (
            'EXTRACT sustainability, energy and certification requirements from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"required_certifications":[{"name":"","required_grade":""}],'
            '"renewable_energy_min_pct":null,'
            '"energy_guidelines":[],'
            '"sustainability_requirements":[]}'
            '\n\nFIELD NOTES:\n'
            '- required_certifications[]: 필수 인증 목록. name=인증명(G-SEED/ZEB/LEED/BF인증 등), required_grade=요구 등급 문자열\n'
            '- renewable_energy_min_pct: 신재생에너지 최소 의무 비율(%), null if not specified\n'
            '- energy_guidelines[]: 에너지 절약·BEMS 등 에너지 관련 지침 문자열 목록\n'
            '- sustainability_requirements[]: 그 외 친환경·지속가능성 요구사항\n'
            '- Do NOT invent values. null/[] if not visible on page.'
        ),
    },
    "BRIEF_DESIGN_SPECIAL": {
        "priority": 1,
        "instruction": (
            'EXTRACT special, security and safety requirements from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"security_requirements":[],'
            '"accessibility_requirements":[],'
            '"safety_requirements":[],'
            '"special_technical_requirements":[]}'
            '\n\nFIELD NOTES:\n'
            '- security_requirements[]: 보안·CPTED·범죄예방 관련 요구사항\n'
            '- accessibility_requirements[]: 장애인 편의·유니버설디자인·BF 관련 요구사항\n'
            '- safety_requirements[]: 소방·내진·방재·철도보호구역 관련 안전 요구사항\n'
            '- special_technical_requirements[]: 그 외 특수 기술 요건\n'
            '- Do NOT invent values. null/[] if not visible on page.'
        ),
    },
    "BRIEF_DESIGN_GUIDE": {
        "priority": 1,
        "instruction": (
            'EXTRACT general design guidelines and requirements from this competition brief. '
            'Respond JSON ONLY.\n'
            '{"design_requirements":[],"height_limit_m":null,'
            '"setback_requirements":[],"materials_required":[],'
            '"sustainability_requirements":[],"concept_direction":"",'
            '"prohibited_items":[],"special_guidelines":[]}'
        ),
    },
    "BRIEF_TECHNICAL": {
        "priority": 2,
        "instruction": (
            'EXTRACT technical requirements from this competition brief. Respond JSON ONLY.\n'
            '{"structural_requirements":"","hvac_requirements":"",'
            '"required_energy_grade":"","required_certifications":[],'
            '"special_technical_requirements":[]}'
        ),
    },
    "BRIEF_REGULATIONS": {
        "priority": 2,
        "instruction": (
            'EXTRACT legal and zoning regulations from this competition brief. '
            'Respond JSON ONLY. Use exact numbers if visible.\n'
            '{"zoning_district":"","building_coverage_ratio_limit_pct":null,'
            '"floor_area_ratio_limit_pct":null,"height_limit_m":null,'
            '"setback_rules":[],"special_regulations":[]}'
        ),
    },
    "BRIEF_EVALUATION": {
        "priority": 1,
        "instruction": (
            'EXTRACT evaluation criteria and scoring table from this competition brief page. '
            'This page may have merged cells (병합 셀) where one 비중/배점 value spans multiple rows or categories — '
            'capture that with shared_with. '
            'Respond JSON ONLY.\n'
            '{"total_points":null,'
            '"evaluation_categories":['
            '{"name":"","points":null,'
            '"shared_with":[],'
            '"sub_items":[""]}'
            '],'
            '"evaluation_method":"","jury_composition":"",'
            '"disqualification_criteria":[]}'
            '\n\nFIELD NOTES:\n'
            '- total_points: integer sum of all top-level 배점/비중 values (typically 100)\n'
            '- evaluation_categories[].name: 구분 or 평가항목 label\n'
            '- evaluation_categories[].points: 배점 or 비중 값 — integer. '
            '표기 변환 규칙: "30점" → 30 / "30%" → 30 / "○ (30)" → 30 / '
            '"0.30" → 30 (비율이면 ×100). '
            '실제 수치가 표에 보이지 않을 때만 null (0은 실제 0점일 때만 사용).\n'
            '- 병합 셀 처리 (중요): 비중 컬럼의 숫자가 여러 행에 걸친 병합 셀로 표시된 경우, '
            '해당 숫자는 그 셀에 포함된 모든 구분이 공유하는 비중이다. '
            '예: 배치계획+공간계획이 하나의 40 셀로 묶여 있으면 그룹 전체 비중이 40이고 각각 20씩이 아님. '
            'shared_with 배열에 함께 묶인 구분명을 기록하고 '
            'points는 그룹 대표(첫 번째) 항목에만 기록, 나머지는 null. '
            '하위 세부항목은 evaluation_categories에 추가하지 말고 sub_items에 기입.\n'
            '- 검증: sum(evaluation_categories[].points where points is not null) ≈ total_points(±5). '
            '합계가 total_points를 크게 초과하면 병합 셀 중복 집계이므로 반드시 수정할 것.\n'
            '- evaluation_categories[].shared_with: list of sibling category names '
            'when the cell is merged across multiple rows (empty list [] if not merged)\n'
            '- evaluation_categories[].sub_items: list of detailed criteria strings '
            'nested under this category (항목 or 세부 내용); empty list [] if none\n'
            '- 컬럼명이 비중/배점/점수가 아니어도 수치 컬럼이 합계 ≈ 100이면 배점으로 추출할 것'
        ),
    },
    "BRIEF_SUBMISSION": {
        "priority": 3,  # 제출 형식 — 비교분석 기여 없음, 스킵
        "instruction": (
            'EXTRACT submission requirements from this brief. Respond JSON ONLY.\n'
            '{"required_documents":[],"file_formats":[],"submission_scale":"",'
            '"submission_method":""}'
        ),
    },
    "BRIEF_ADMIN": {
        "priority": 3,  # 행정절차 — 추출 가치 없음, 스킵
        "instruction": (
            'EXTRACT admin info from this brief. Respond JSON ONLY.\n'
            '{"contact":"","qa_method":"","important_dates":[]}'
        ),
    },

    # ── 구 submission 타입 override (하위호환 — is_brief=True 구 데이터용) ─────
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

# digital text tier(Tier 0) 제외 대상: fitz.get_text()는 표 열 순서가 뒤섞여 숫자 오독 위험.
# 이 타입들은 OCR_FIRST → tiled vision 경로를 그대로 사용.
# BRIEF_PROGRAM / BRIEF_REGULATIONS: 실별 면적표·법규 수치표 → 마찬가지로 제외.
DIGITAL_TEXT_EXCLUDE_TYPES = {
    "AREA_TABLE", "TECHNICAL", "INCENTIVE_TABLE",
    "BUSINESS_VIABILITY", "AREA_INCREASE",
    "BRIEF_PROGRAM", "BRIEF_REGULATIONS", "BRIEF_EVALUATION",
    "BRIEF_PROJECT_INFO",
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


# ── BRIEF_EVALUATION 다중 페이지 수직 스택 ────────────────────────────────────
def _stack_images_vertically(images_bytes: list[bytes]) -> bytes:
    """여러 PNG bytes를 수직으로 이어붙여 단일 PNG bytes 반환."""
    from PIL import Image
    imgs = [Image.open(io.BytesIO(b)) for b in images_bytes]
    max_w = max(img.width for img in imgs)
    total_h = sum(img.height for img in imgs)
    canvas = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for img in imgs:
        if img.mode != "RGB":
            img = img.convert("RGB")
        canvas.paste(img, (0, y))
        y += img.height
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


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


# ── 디지털 텍스트 추출 (이미지 토큰 0, OCR 불필요) ────────────────────────────
def _extract_digital_text_only(
    pdf_path: Path,
    page_index: int,
    page_num: int,
    page_type: str,
    prompt_cfg: dict,
) -> dict | None:
    """
    fitz.get_text()로 임베딩 텍스트 추출 → Haiku 구조화 (Tier 0).
    이미지를 Claude에 전송하지 않으므로 입력 이미지 토큰이 0.
    PaddleOCR 설치 불필요.

    Returns None if embedded text is insufficient (< OCR_MIN_CHARS) → caller
    falls back to OCR_FIRST / tiled / vision.
    """
    raw_text = get_page_text(pdf_path, page_index)
    if len(raw_text.strip()) < OCR_MIN_CHARS:
        return None  # 임베딩 텍스트 없음 → 이미지 기반 PDF, 폴백

    content = [
        {
            "type": "text",
            "text": (
                "다음 텍스트는 건축 설계공모 PDF 페이지에서 직접 추출한 임베딩 텍스트입니다.\n\n"
                f"--- 페이지 텍스트 ---\n{raw_text}\n---\n\n"
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

    return {"page": page_num, "type": page_type, "data": data, "_source": "digital_haiku"}


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

    # ── BRIEF_EVALUATION 다중 페이지 스택 추출 (수정 1·2·3) ──────────────────
    # is_brief=True이고 BRIEF_EVALUATION 페이지가 2개 이상이면
    # 해당 페이지 이미지를 수직으로 이어붙여 LLM에 한 번만 전달.
    pages_by_num: dict[int, bytes] = {pnum: img for img, pnum in all_pages}
    eval_page_nums: list[int] = sorted(
        pg for pg, pt in type_by_page.items() if pt == "BRIEF_EVALUATION"
    ) if is_brief else []
    precomputed_eval: dict | None = None

    if is_brief and len(eval_page_nums) >= 2:
        eval_imgs = [pages_by_num[pg] for pg in eval_page_nums if pg in pages_by_num]
        stacked_img = _stack_images_vertically(eval_imgs)
        _base_cfg = EXTRACTION_PROMPTS_BRIEF["BRIEF_EVALUATION"]
        # 스택 이미지 전용 추가 지침: 페이지 경계를 넘는 병합 셀 인식 강화
        _stacked_note = (
            f'\n[주의: 이 이미지는 {len(eval_imgs)}개 연속 페이지를 수직으로 이어붙인 것입니다. '
            '표가 페이지 경계에서 잘려 이어지는 경우, 다음 페이지 첫 행부터 같은 표의 연속으로 인식하라. '
            '병합 셀 배점은 해당 셀에 포함된 모든 구분 항목이 공유하며, '
            'shared_with 배열에 형제 항목명을 기록하고 '
            'points는 그룹 첫 항목에만, 나머지는 null로 설정하라.]'
        )
        _eval_prompt_cfg = {
            **_base_cfg,
            "instruction": _base_cfg["instruction"] + _stacked_note,
        }
        precomputed_eval = _extract_page_sync(
            stacked_img, eval_page_nums[0], "BRIEF_EVALUATION", _eval_prompt_cfg
        )
        # 수정 3: points_sum_warning — null 제외 합계가 95~105 범위 밖이면 경고
        _cats = precomputed_eval.get("data", {}).get("evaluation_categories") or []
        _pts_sum = sum(c["points"] for c in _cats if isinstance(c.get("points"), (int, float)))
        if _pts_sum > 0 and not (95 <= _pts_sum <= 105):
            precomputed_eval["data"]["points_sum_warning"] = True
        precomputed_eval["_stacked_pages"] = eval_page_nums

    stacked_eval_set: set[int] = set(eval_page_nums) if precomputed_eval else set()

    # ── BRIEF_PROGRAM 다중 페이지 스택 추출 ──────────────────────────────────────
    # 면적표가 연속 페이지에 걸칠 때 5페이지씩 청크로 이어붙여 한 번에 추출.
    # area_rows flat 방식이므로 청크 결과를 단순 extend()로 병합.
    _PROG_CHUNK = 5   # 청크당 최대 페이지 수

    prog_page_nums: list[int] = sorted(
        pg for pg, pt in type_by_page.items() if pt == "BRIEF_PROGRAM"
    ) if is_brief else []
    precomputed_program: dict | None = None

    if is_brief and len(prog_page_nums) >= 2:
        _prog_base_cfg = EXTRACTION_PROMPTS_BRIEF["BRIEF_PROGRAM"]
        _prog_chunks = [
            prog_page_nums[i:i + _PROG_CHUNK]
            for i in range(0, len(prog_page_nums), _PROG_CHUNK)
        ]
        _merged_rows: list = []
        _first_data: dict = {}

        for _ci, _chunk in enumerate(_prog_chunks):
            _chunk_imgs = [pages_by_num[pg] for pg in _chunk if pg in pages_by_num]
            _stacked = _stack_images_vertically(_chunk_imgs)
            _n_total = len(_prog_chunks)

            if _n_total > 1:
                if _ci == 0:
                    _note = (
                        f'\n[이 이미지는 {_n_total}개 청크 중 1번째입니다. '
                        '요약 필드(sites, total_required_floor_area_sqm 등)는 여기서만 채우고, '
                        'area_rows는 이 페이지들에 해당하는 행만 추출하세요.]'
                    )
                else:
                    _note = (
                        f'\n[이 이미지는 {_n_total}개 청크 중 {_ci+1}번째입니다. '
                        '면적표가 이어지므로 area_rows만 채우고 '
                        'sites 등 요약 필드는 비워두세요.]'
                    )
                _cfg = {**_prog_base_cfg, "instruction": _prog_base_cfg["instruction"] + _note}
            else:
                _cfg = _prog_base_cfg

            _res = _extract_page_sync(_stacked, _chunk[0], "BRIEF_PROGRAM", _cfg)
            _data = _res.get("data") or {}
            if _ci == 0:
                _first_data = {k: v for k, v in _data.items() if k != "area_rows"}
            _merged_rows.extend(_data.get("area_rows") or [])

        _first_data["area_rows"] = _merged_rows
        precomputed_program = {
            "page": prog_page_nums[0],
            "type": "BRIEF_PROGRAM",
            "data": _first_data,
            "_stacked_pages": prog_page_nums,
        }

    stacked_prog_set: set[int] = set(prog_page_nums) if precomputed_program else set()

    sem = asyncio.Semaphore(4)

    async def extract_one(img_bytes: bytes, page_num: int) -> dict:
        # BRIEF_EVALUATION 스택 결과: 첫 페이지는 미리 계산된 결과, 나머지는 빈 마커
        if page_num in stacked_eval_set:
            if page_num == eval_page_nums[0]:
                return precomputed_eval
            return {"page": page_num, "type": "BRIEF_EVALUATION", "data": {}, "_merged": True}

        # BRIEF_PROGRAM 스택 결과: 동일 패턴
        if page_num in stacked_prog_set:
            if page_num == prog_page_nums[0]:
                return precomputed_program
            return {"page": page_num, "type": "BRIEF_PROGRAM", "data": {}, "_merged": True}

        page_type = type_by_page.get(page_num, "CONCEPT")
        confidence = confidence_by_page.get(page_num, 1.0)

        # ── 스킵: 비교분석에 미사용 페이지
        # BRIEF_* 타입은 EXTRACTION_PROMPTS에 없으므로 EXTRACTION_PROMPTS_BRIEF 먼저 조회.
        priority_limit = settings.extraction_priority_limit
        if is_brief and page_type in EXTRACTION_PROMPTS_BRIEF:
            cfg_for_check = EXTRACTION_PROMPTS_BRIEF[page_type]
        else:
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
            # ── Tier 0 — digital text fast-path: fitz.get_text() → Haiku
            # 이미지 토큰 0, PaddleOCR 불필요. 임베딩 텍스트 없는 이미지 기반 PDF는 자동 폴백.
            # 표 레이아웃 타입(DIGITAL_TEXT_EXCLUDE_TYPES)은 열 순서 왜곡 위험 → 제외.
            if effective_type not in DIGITAL_TEXT_EXCLUDE_TYPES:
                digital_result = await asyncio.to_thread(
                    _extract_digital_text_only,
                    pdf_path, page_num - 1, page_num, effective_type, prompt_cfg,
                )
                if digital_result is not None:
                    return digital_result
                # 임베딩 텍스트 부족 → 이하 OCR_FIRST / tiled / vision으로 폴백

            # ── Tier 1 — OCR fast-path: AREA_TABLE / TECHNICAL / SUSTAINABILITY
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
def _extract_brief_reqs_sync(brief_trimmed: dict, axes_str: str) -> dict:
    prompt = (_BRIEF_REQ_PROMPT_TEMPLATE
              .replace("{axes_str}", axes_str)
              .replace("{brief_json}",
                       json.dumps(brief_trimmed, ensure_ascii=False, separators=(",", ":"))))
    try:
        raw = call_messages(
            model=settings.model_id_classify,
            max_tokens=2000,
            temperature=0,
            system=_BRIEF_REQ_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json_response(raw)
    except Exception:
        return {"requirements": [], "evaluation_criteria": [], "special_requirements": []}


async def extract_brief_requirements(brief_data: dict, facility_type: str = "") -> dict:
    """지침서 추출 데이터에서 평가 요구사항을 구조화.

    Returns:
        {
            "requirements": [{"axis": str, "description": str, "weight_pct": float|null}],
            "evaluation_criteria": [{"item": str, "points": int|null}],
            "special_requirements": [str]
        }
    """
    relevant_keys = {
        # 구 submission 타입 경로 (레거시 / AREA_TABLE 분류 경우)
        "area_table", "special_space", "technical", "_quantitative",
        "circulation", "sustainability", "site_plan",
        # 새 BRIEF taxonomy 경로 (classify_all_pages_brief 사용 시)
        "brief_program", "brief_evaluation", "brief_design_guide",
        "brief_technical", "brief_regulations", "brief_site",
    }
    trimmed = {k: v for k, v in brief_data.items() if k in relevant_keys}
    if not trimmed:
        return {"requirements": [], "evaluation_criteria": [], "special_requirements": []}
    axes_str = "|".join(axes_keys_for(facility_type))
    return await asyncio.to_thread(_extract_brief_reqs_sync, trimmed, axes_str)


def should_extract(page_type: str, priority_limit: int = 2) -> bool:
    cfg = EXTRACTION_PROMPTS.get(page_type, FALLBACK_PROMPT)
    return cfg["priority"] <= priority_limit


def _merge_brief_project_info_pages(items: list[dict]) -> dict:
    """여러 BRIEF_PROJECT_INFO 페이지 추출 결과를 단일 dict로 통합.

    동일 지침서에서 p.4(위치·용도지구 표)와 p.5(대지면적·건폐율·용적률 수치 표)처럼
    정성 데이터와 정량 데이터가 다른 페이지에 흩어져 있을 때 사용.
    - 상위 scalar 필드: first-non-null wins
    - sites[]: site_id로 매칭 후 필드별 first-non-null wins
    - 리스트 필드(budget_notes, special_conditions): 순서 유지 합집합
    """
    _SITE_FIELDS = [
        "site_id", "address", "zoning", "scope", "facilities",
        "site_area_sqm", "floor_area_sqm",
        "building_coverage_pct", "floor_area_ratio_pct",
        "max_height_m", "open_space_sqm", "open_space_notes",
    ]
    _TOP_SCALARS = ["competition_name", "organizer", "competition_type",
                    "construction_cost_100m_won", "design_cost_100m_won",
                    "construction_period_months"]
    _TOP_LISTS = ["budget_notes", "special_conditions"]

    merged: dict = {}

    # 상위 scalar: first-non-null
    for key in _TOP_SCALARS:
        for item in items:
            v = item.get(key)
            if v is not None:
                merged[key] = v
                break
        else:
            merged[key] = None

    # 상위 list: 순서 유지 합집합
    for key in _TOP_LISTS:
        seen: list = []
        seen_set: set = set()
        for item in items:
            for v in (item.get(key) or []):
                if v not in seen_set:
                    seen.append(v)
                    seen_set.add(v)
        merged[key] = seen

    # sites[]: site_id로 매칭, 필드별 first-non-null
    import re as _re
    def _norm_sid(s: str) -> str:
        """'부지1(구청·구의회)' → '부지1' : 괄호 내 설명 제거 후 공백 정리."""
        return _re.sub(r'\s*\([^)]*\)\s*$', '', (s or "").strip()).strip()

    sites_by_id: dict[str, dict] = {}
    sites_order: list[str] = []
    for item in items:
        for site in (item.get("sites") or []):
            raw_sid = site.get("site_id") or "단일부지"
            sid = _norm_sid(raw_sid)
            if sid not in sites_by_id:
                sites_by_id[sid] = {f: None for f in _SITE_FIELDS}
                sites_by_id[sid]["site_id"] = sid  # 정규화된 ID 저장
                sites_order.append(sid)
            acc = sites_by_id[sid]
            for field in _SITE_FIELDS:
                if field == "site_id":
                    continue
                v = site.get(field)
                if field == "facilities":
                    # 시설 목록: 합집합 (순서 유지)
                    existing = acc.get("facilities") or []
                    existing_set = set(existing)
                    for fac in (v or []):
                        if fac not in existing_set:
                            existing.append(fac)
                            existing_set.add(fac)
                    acc["facilities"] = existing
                elif v is not None and acc.get(field) is None:
                    acc[field] = v

    # 부지N 번호 키가 존재하면 fallback/설명문 orphan 제거
    import re as _re2
    numbered = [s for s in sites_order if _re2.match(r'부지\d+', s)]
    if len(numbered) >= 2:
        sites_order = numbered
        sites_by_id = {s: sites_by_id[s] for s in numbered}

    merged["sites"] = [sites_by_id[sid] for sid in sites_order]
    merged["_page"] = items[0].get("_page")  # 첫 페이지 번호 보존
    return merged


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

    # BRIEF_PROJECT_INFO 다중 페이지 deep-merge:
    # pages with qualitative data (address/zoning) and numeric data (area/bcr/far)
    # are separate pages → merge sites[] by site_id, first-non-null wins per field.
    bpi_raw = result.get("brief_project_info")
    if isinstance(bpi_raw, list) and len(bpi_raw) > 1:
        result["brief_project_info"] = _merge_brief_project_info_pages(bpi_raw)

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

    # 새 BRIEF taxonomy 경로: brief_program / brief_regulations 필드명 리매핑
    # area_table 경로가 이미 채운 필드는 덮어쓰지 않음 (first-write wins 유지)
    _brief_remap = {
        # brief_program 키 → _quantitative 키
        "total_required_floor_area_sqm": "total_floor_area_sqm",
        "site_area_sqm":                 "site_area_sqm",
        "building_coverage_limit_pct":   "building_coverage_ratio_pct",  # brief_program
        "floor_area_ratio_limit_pct":    "floor_area_ratio_pct",         # brief_program + brief_regulations 공통
        "max_floors_above":              "floors_above",
        "max_floors_below":              "floors_below",
        "required_parking":              "parking_count",
        # brief_regulations 추가 키 (brief_program과 필드명 다름)
        "building_coverage_ratio_limit_pct": "building_coverage_ratio_pct",
    }
    bp_list = result.get("brief_program", [])
    if isinstance(bp_list, dict):
        bp_list = [bp_list]
    br_list = result.get("brief_regulations", [])
    if isinstance(br_list, dict):
        br_list = [br_list]
    for entry in bp_list + br_list:
        if not isinstance(entry, dict):
            continue
        for src, dst in _brief_remap.items():
            v = entry.get(src)
            if v is not None and dst not in quant:
                quant[dst] = v

    # sites[0] 대표값 보완 — 복수 부지 공모에서 top-level 단일값이 null일 때 사용
    _sites_remap = {
        "site_area_sqm":              "site_area_sqm",
        "building_coverage_limit_pct":"building_coverage_ratio_pct",
        "floor_area_ratio_limit_pct": "floor_area_ratio_pct",
    }
    for entry in bp_list:
        if not isinstance(entry, dict):
            continue
        sites = entry.get("sites") or []
        if not sites or not isinstance(sites[0], dict):
            continue
        s0 = sites[0]
        for src, dst in _sites_remap.items():
            v = s0.get(src)
            if v is not None and dst not in quant:
                quant[dst] = v

    result["_quantitative"] = quant
    return result