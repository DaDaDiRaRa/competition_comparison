"""Individual submission report generator — no LLM calls, pure HTML rendering."""
from __future__ import annotations

from config import FACILITY_TYPES

_RESULT_BADGE = {
    "win":        ('<span style="background:#b7791f;color:#fefcbf;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">★ 당선</span>'),
    "contracted": ('<span style="background:#276749;color:#c6f6d5;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">◆ 수의계약</span>'),
    "lose":       ('<span style="background:#742a2a;color:#fed7d7;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">낙선</span>'),
}

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
       background: #0f1117; color: #e2e8f0; padding: 24px; font-size: 14px; }
.wrap { max-width: 1100px; margin: 0 auto; }
.hdr { background: #1a1f2e; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
       border-left: 4px solid #90cdf4; }
.hdr-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.hdr-title { font-size: 22px; font-weight: 700; color: #e2e8f0; }
.hdr-sub { font-size: 13px; color: #a0aec0; }
.hdr-meta { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px; }
.hdr-meta span { font-size: 12px; color: #718096; }
.hdr-meta strong { color: #e2e8f0; }

.sec { background: #1a1f2e; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }
.sec-title { font-size: 15px; font-weight: 700; color: #90cdf4; margin-bottom: 14px;
             padding-bottom: 8px; border-bottom: 1px solid #2d3748; }

.kv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.kv { background: #0d1117; border-radius: 6px; padding: 10px 14px; }
.kv-label { font-size: 11px; color: #718096; margin-bottom: 3px; }
.kv-value { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.kv-unit { font-size: 11px; color: #a0aec0; font-weight: 400; }

.concept-card { background: #0d1117; border-radius: 8px; padding: 16px; margin-bottom: 10px; }
.concept-name { font-size: 18px; font-weight: 700; color: #f6e05e; margin-bottom: 6px; }
.concept-type { font-size: 12px; color: #90cdf4; background: #1e2d40;
                padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 10px; }
.concept-strategy { font-size: 13px; color: #cbd5e0; line-height: 1.7; }
.keywords { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.kw { background: #1a2e40; color: #90cdf4; font-size: 12px; padding: 3px 10px;
      border-radius: 20px; border: 1px solid #2c5282; }

.floor-table { width: 100%; border-collapse: collapse; }
.floor-table th { background: #0d1117; padding: 8px 12px; text-align: left;
                  font-size: 12px; color: #a0aec0; border-bottom: 1px solid #2d3748; }
.floor-table td { padding: 8px 12px; border-bottom: 1px solid #1e2533;
                  font-size: 13px; vertical-align: top; }
.floor-table tr:hover td { background: rgba(144,205,244,0.03); }
.floor-level { font-weight: 600; color: #e2e8f0; }
.prog-list { display: flex; flex-wrap: wrap; gap: 4px; }
.prog-tag { background: #1e2533; color: #a0aec0; font-size: 11px;
            padding: 2px 7px; border-radius: 3px; }

.elev-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.elev-card { background: #0d1117; border-radius: 6px; padding: 12px; }
.elev-dir { font-size: 12px; font-weight: 700; color: #90cdf4; text-transform: uppercase;
            margin-bottom: 6px; }
.elev-row { font-size: 12px; color: #a0aec0; margin-bottom: 3px; }
.elev-row strong { color: #e2e8f0; }

.note-list { display: flex; flex-direction: column; gap: 6px; }
.note-item { background: #0d1117; border-radius: 6px; padding: 10px 14px;
             font-size: 13px; color: #cbd5e0; line-height: 1.6;
             border-left: 3px solid #4a5568; }
.note-item.accent { border-left-color: #90cdf4; }

.dist-bar-wrap { display: flex; flex-direction: column; gap: 6px; }
.dist-row { display: flex; align-items: center; gap: 8px; }
.dist-label { font-size: 12px; color: #a0aec0; min-width: 120px; }
.dist-bar-bg { flex: 1; background: #0d1117; border-radius: 3px; height: 14px; overflow: hidden; }
.dist-bar-fill { height: 100%; border-radius: 3px; background: #2c5282; }
.dist-count { font-size: 12px; color: #718096; min-width: 28px; text-align: right; }

.footer { text-align: center; color: #4a5568; font-size: 12px; margin-top: 24px; padding: 12px; }
</style>
"""


def _safe_list(val) -> list:
    if isinstance(val, list):
        return val
    return []


def _flatten_items(section_list: list) -> list:
    """Some sections store items in `_items`; others are flat. Flatten both."""
    result = []
    for entry in section_list:
        if isinstance(entry, dict) and "_items" in entry:
            result.extend(entry["_items"] if isinstance(entry["_items"], list) else [])
        elif isinstance(entry, dict):
            result.append(entry)
    return result


def _kv_block(label: str, value, unit: str = "") -> str:
    if value is None or value == "" or value == []:
        return ""
    disp = f"{value:,}" if isinstance(value, (int, float)) else str(value)
    unit_html = f' <span class="kv-unit">{unit}</span>' if unit else ""
    return (
        f'<div class="kv">'
        f'<div class="kv-label">{label}</div>'
        f'<div class="kv-value">{disp}{unit_html}</div>'
        f'</div>'
    )


def _section_header(title: str) -> str:
    return f'<div class="sec-title">{title}</div>'


# ── 각 섹션 렌더러 ──────────────────────────────────────────────────────────────

def _render_cover(cover: dict) -> str:
    sub_code = cover.get("submission_code", "")
    submitter = cover.get("submitter", "")
    if not sub_code and not submitter:
        return ""
    rows = ""
    if sub_code:
        rows += _kv_block("제출 번호", sub_code)
    if submitter:
        rows += _kv_block("제출자", submitter)
    return (
        f'<div class="sec">'
        f'{_section_header("표지 정보")}'
        f'<div class="kv-grid">{rows}</div>'
        f'</div>'
    )


def _render_concept(concepts: list) -> str:
    if not concepts:
        return ""
    html = ""
    for c in concepts:
        if not isinstance(c, dict):
            continue
        name_ko = c.get("concept_name_ko", "")
        name_en = c.get("concept_name_en", "")
        name = name_ko or name_en or ""
        if name_ko and name_en and name_ko != name_en:
            name = f"{name_ko} ({name_en})"
        massing = c.get("massing_type", "")
        strategy = c.get("main_strategy", "")
        circ = c.get("circulation_concept", "")
        keywords = c.get("keywords", [])

        kws_html = "".join(f'<span class="kw">{k}</span>' for k in keywords if k)
        kws_section = f'<div class="keywords">{kws_html}</div>' if kws_html else ""

        type_badge = f'<span class="concept-type">매스: {massing}</span>' if massing else ""
        strat_html = f'<div class="concept-strategy">{strategy}</div>' if strategy else ""
        circ_html = (
            f'<div class="concept-strategy" style="margin-top:8px;color:#a0aec0">'
            f'<strong style="color:#718096">동선 전략: </strong>{circ}</div>'
        ) if circ else ""

        html += (
            f'<div class="concept-card">'
            f'<div class="concept-name">{name}</div>'
            f'{type_badge}'
            f'{kws_section}'
            f'{strat_html}'
            f'{circ_html}'
            f'</div>'
        )

    if not html:
        return ""
    return f'<div class="sec">{_section_header("설계 컨셉")}{html}</div>'


def _render_site_plan(site_plans: list) -> str:
    if not site_plans:
        return ""
    rows = []
    for sp in site_plans:
        if not isinstance(sp, dict):
            continue
        for label, key, unit in [
            ("주 출입 방향", "main_entrance_direction", ""),
            ("차량 진입", "vehicle_access_direction", ""),
            ("오픈스페이스 전략", "open_space_strategy", ""),
            ("보행 전략", "pedestrian_strategy", ""),
            ("조경 컨셉", "landscape_concept", ""),
        ]:
            val = sp.get(key)
            if val:
                rows.append(f'<div class="note-item accent">'
                            f'<strong style="color:#90cdf4">{label}: </strong>{val}</div>')
    if not rows:
        return ""
    content = "".join(rows)
    return f'<div class="sec">{_section_header("배치 · 조경")}<div class="note-list">{content}</div></div>'


def _render_floor_plan(floor_plans: list) -> str:
    floors = []
    for page in floor_plans:
        if not isinstance(page, dict):
            continue
        items = page.get("_items", [])
        if isinstance(items, list):
            floors.extend(items)
        else:
            # flat structure
            if page.get("floor_level"):
                floors.append(page)

    if not floors:
        return ""

    rows_html = ""
    for fl in floors:
        if not isinstance(fl, dict):
            continue
        level = fl.get("floor_level", "")
        programs = fl.get("main_programs", []) or []
        pub_programs = fl.get("public_programs_on_this_floor", []) or []
        core = fl.get("core_type", "")
        core_count = fl.get("core_count")

        all_progs = list(dict.fromkeys(programs + pub_programs))
        prog_tags = "".join(f'<span class="prog-tag">{p}</span>' for p in all_progs if p)

        core_txt = ""
        if core or core_count:
            parts = []
            if core_count:
                parts.append(f"{core_count}코어")
            if core:
                parts.append(core)
            core_txt = " · ".join(parts)

        rows_html += (
            f'<tr>'
            f'<td><span class="floor-level">{level}</span></td>'
            f'<td><div class="prog-list">{prog_tags}</div></td>'
            f'<td style="font-size:12px;color:#718096">{core_txt}</td>'
            f'</tr>'
        )

    return (
        f'<div class="sec">'
        f'{_section_header("평면 구성")}'
        f'<div style="overflow-x:auto">'
        f'<table class="floor-table">'
        f'<thead><tr><th>층</th><th>주요 프로그램</th><th>코어</th></tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div></div>'
    )


def _render_section(sections: list) -> str:
    if not sections:
        return ""
    items = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        h = sec.get("total_height_m")
        fh = sec.get("typical_floor_height_m")
        struct = sec.get("structural_system_visible", "")
        feats = sec.get("key_spatial_features", []) or []
        underground = sec.get("underground_levels")

        if h:
            items.append(f'<div class="note-item"><strong>최고 높이: </strong>{h}m'
                         + (f' · 기준층 높이 {fh}m' if fh else '') + '</div>')
        if underground:
            items.append(f'<div class="note-item"><strong>지하 층수: </strong>B{underground}층</div>')
        if struct:
            items.append(f'<div class="note-item accent"><strong>구조 시스템: </strong>{struct}</div>')
        for feat in feats[:4]:
            if feat:
                items.append(f'<div class="note-item">{feat}</div>')

    if not items:
        return ""
    return (
        f'<div class="sec">'
        f'{_section_header("단면 분석")}'
        f'<div class="note-list">{"".join(items)}</div>'
        f'</div>'
    )


def _render_elevation(elevations: list) -> str:
    items = _flatten_items(elevations)
    if not items:
        return ""
    cards = ""
    for el in items:
        if not isinstance(el, dict):
            continue
        direction = el.get("facade_direction", "")
        mat1 = el.get("primary_material", "")
        mat2 = el.get("secondary_material", "")
        system = el.get("facade_system", "")
        shading = el.get("shading_device", "")
        transp = el.get("transparency_ratio", "")

        rows = ""
        if mat1:
            rows += f'<div class="elev-row">주재료: <strong>{mat1}</strong>'
            if mat2:
                rows += f' + {mat2}'
            rows += '</div>'
        if system:
            rows += f'<div class="elev-row">파사드: <strong>{system}</strong></div>'
        if shading:
            rows += f'<div class="elev-row">차양: <strong>{shading}</strong></div>'
        if transp:
            rows += f'<div class="elev-row">투명도: <strong>{transp}</strong></div>'

        if rows:
            dir_label = {
                "east": "동", "west": "서", "south": "남", "north": "북",
            }.get(direction, direction)
            cards += (
                f'<div class="elev-card">'
                f'<div class="elev-dir">{dir_label} 입면</div>'
                f'{rows}</div>'
            )

    if not cards:
        return ""
    return (
        f'<div class="sec">'
        f'{_section_header("입면 · 파사드")}'
        f'<div class="elev-grid">{cards}</div>'
        f'</div>'
    )


def _render_quantitative(quant: dict) -> str:
    if not quant:
        return ""
    fields = [
        ("연면적", "total_floor_area_sqm", "㎡"),
        ("대지면적", "site_area_sqm", "㎡"),
        ("건축면적", "building_area_sqm", "㎡"),
        ("건폐율", "building_coverage_ratio_pct", "%"),
        ("용적률", "floor_area_ratio_pct", "%"),
        ("지상 층수", "floors_above", "층"),
        ("지하 층수", "floors_below", "층"),
        ("최고 높이", "max_height_m", "m"),
        ("주차 대수", "parking_count", "대"),
    ]
    blocks = ""
    for label, key, unit in fields:
        val = quant.get(key)
        if val is not None and val != "":
            if isinstance(val, float):
                disp = f"{val:,.2f}"
            elif isinstance(val, int):
                disp = f"{val:,}"
            else:
                disp = str(val)
            blocks += (
                f'<div class="kv">'
                f'<div class="kv-label">{label}</div>'
                f'<div class="kv-value">{disp} <span class="kv-unit">{unit}</span></div>'
                f'</div>'
            )
    if not blocks:
        return ""
    return (
        f'<div class="sec">'
        f'{_section_header("정량 데이터")}'
        f'<div class="kv-grid">{blocks}</div>'
        f'</div>'
    )


def _render_sustainability(sust_list: list) -> str:
    if not sust_list:
        return ""
    items = []
    for s in sust_list:
        if not isinstance(s, dict):
            continue
        cert = s.get("green_certification", "")
        grade = s.get("energy_grade_target", "")
        renew = s.get("renewable_energy", []) or []
        water = s.get("water_management", []) or []
        carbon = s.get("carbon_reduction_strategies", []) or []

        if cert:
            items.append(f'<div class="note-item accent"><strong>녹색건축인증: </strong>{cert}</div>')
        if grade:
            items.append(f'<div class="note-item"><strong>에너지등급 목표: </strong>{grade}</div>')
        for r in renew[:3]:
            if r:
                items.append(f'<div class="note-item">⚡ {r}</div>')
        for w in water[:2]:
            if w:
                items.append(f'<div class="note-item">💧 {w}</div>')
        for c in carbon[:2]:
            if c:
                items.append(f'<div class="note-item">{c}</div>')

    if not items:
        return ""
    return (
        f'<div class="sec">'
        f'{_section_header("지속가능성")}'
        f'<div class="note-list">{"".join(items)}</div>'
        f'</div>'
    )


def _render_technical(tech_list: list) -> str:
    if not tech_list:
        return ""
    items = []
    for t in tech_list:
        if not isinstance(t, dict):
            continue
        struct = t.get("structural_system", "")
        found = t.get("foundation_type", "")
        hvac = t.get("hvac_system", "")
        feats = t.get("smart_building_features", []) or []
        fire = t.get("fire_safety_features", []) or []

        if struct:
            items.append(f'<div class="note-item accent"><strong>구조: </strong>{struct}</div>')
        if found:
            items.append(f'<div class="note-item"><strong>기초: </strong>{found}</div>')
        if hvac:
            items.append(f'<div class="note-item"><strong>HVAC: </strong>{hvac}</div>')
        for feat in feats[:2]:
            if feat:
                items.append(f'<div class="note-item">🔧 {feat}</div>')
        for f in fire[:2]:
            if f:
                items.append(f'<div class="note-item">{f}</div>')

    if not items:
        return ""
    return (
        f'<div class="sec">'
        f'{_section_header("구조 · 기술")}'
        f'<div class="note-list">{"".join(items)}</div>'
        f'</div>'
    )


def _render_page_dist(page_dist: dict, total: int) -> str:
    if not page_dist or not total:
        return ""
    PAGE_KR = {
        "COVER": "표지", "TOC_HERO": "목차·대표이미지", "SITE_CONTEXT": "대지분석",
        "CONCEPT": "설계컨셉", "SPECIAL_SPACE": "특별공간", "RENDERING_EXT": "외부투시도",
        "RENDERING_INT": "내부투시도", "SITE_PLAN": "배치도", "LANDSCAPE": "조경",
        "FLOOR_PLAN": "평면도", "SECTION": "단면도", "ELEVATION": "입면도",
        "CIRCULATION": "동선", "HEALTH_CENTER": "건강센터", "TECHNICAL": "기술",
        "AREA_TABLE": "면적표", "SUSTAINABILITY": "지속가능성",
        "UNIT_PLAN": "단위세대", "INCENTIVE_TABLE": "인센티브표", "BRANDING": "브랜딩",
    }
    sorted_dist = sorted(page_dist.items(), key=lambda x: x[1], reverse=True)
    bars = ""
    for pt, cnt in sorted_dist:
        pct = int(cnt / total * 100)
        label = PAGE_KR.get(pt, pt)
        bars += (
            f'<div class="dist-row">'
            f'<span class="dist-label">{label}</span>'
            f'<div class="dist-bar-bg"><div class="dist-bar-fill" style="width:{pct}%"></div></div>'
            f'<span class="dist-count">{cnt}p</span>'
            f'</div>'
        )
    return (
        f'<div class="sec">'
        f'{_section_header(f"페이지 구성 ({total}p)")}'
        f'<div class="dist-bar-wrap">{bars}</div>'
        f'</div>'
    )


# ── 메인 함수 ──────────────────────────────────────────────────────────────────

def generate_submission_report(sub_doc: dict) -> str:
    company = sub_doc.get("company", "")
    result = sub_doc.get("result", "")
    competition_id = sub_doc.get("competition_id", "")
    facility_type = sub_doc.get("facility_type", "")
    total_pages = sub_doc.get("total_pages", 0)
    page_dist = sub_doc.get("page_distribution", {})
    ed = sub_doc.get("extracted_data", {})

    cover_raw = ed.get("cover")
    cover = (cover_raw[0] if cover_raw else {}) if isinstance(cover_raw, list) else (cover_raw or {})
    if not isinstance(cover, dict):
        cover = {}
    comp_name = cover.get("competition_name") or competition_id
    facility_label = FACILITY_TYPES.get(facility_type, facility_type)

    result_badge = _RESULT_BADGE.get(result, "")

    header = f"""
    <div class="hdr">
      <div class="hdr-top">
        <span style="background:#2b4c7e;color:#90cdf4;font-size:11px;padding:3px 10px;
                     border-radius:20px;font-weight:700">{facility_label}</span>
        {result_badge}
      </div>
      <div class="hdr-title">{company}</div>
      <div class="hdr-sub">{comp_name}</div>
      <div class="hdr-meta">
        <span>총 <strong>{total_pages}페이지</strong></span>
        <span>시설 유형: <strong>{facility_label}</strong></span>
      </div>
    </div>"""

    quant = ed.get("_quantitative") or {}
    # site_plan 첫 번째 항목에 면적 데이터가 있을 수 있으므로 병합
    for sp in _safe_list(ed.get("site_plan")):
        if isinstance(sp, dict):
            for k in ("site_area_sqm", "building_area_sqm", "total_floor_area_sqm",
                      "building_coverage_ratio_pct", "floor_area_ratio_pct",
                      "floors_above", "floors_below", "max_height_m", "parking_count"):
                if quant.get(k) is None and sp.get(k) is not None:
                    quant[k] = sp[k]

    sections = "".join([
        _render_cover(cover),
        _render_concept(_safe_list(ed.get("concept"))),
        _render_quantitative(quant),
        _render_floor_plan(_safe_list(ed.get("floor_plan"))),
        _render_site_plan(_safe_list(ed.get("site_plan"))),
        _render_section(_safe_list(ed.get("section"))),
        _render_elevation(_safe_list(ed.get("elevation"))),
        _render_sustainability(_safe_list(ed.get("sustainability"))),
        _render_technical(_safe_list(ed.get("technical"))),
        _render_page_dist(page_dist, total_pages),
    ])

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{company} — {comp_name}</title>
{_CSS}
</head>
<body>
<div class="wrap">
{header}
{sections}
<div class="footer">Competition Analyzer — 개별 제안서 리포트 · {company}</div>
</div>
</body>
</html>"""
