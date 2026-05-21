"""Individual submission report generator — no LLM calls, pure HTML rendering."""
from __future__ import annotations

from config import facility_label as _facility_label

_RESULT_BADGE = {
    "win":        ('<span style="background:#b7791f;color:#fefcbf;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">★ 당선</span>'),
    "contracted": ('<span style="background:#15803d;color:#bbf7d0;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">◆ 수의계약</span>'),
    "lose":       ('<span style="background:#b91c1c;color:#fee2e2;font-size:12px;padding:3px 10px;'
                   'border-radius:20px;font-weight:700">낙선</span>'),
}

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
       background: #fafafa; color: #1f2937; padding: 24px; font-size: 14px; }
.wrap { max-width: 1100px; margin: 0 auto; }
.hdr { background: #ffffff; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
       border-left: 4px solid #334155; }
.hdr-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.hdr-title { font-size: 22px; font-weight: 700; color: #1f2937; }
.hdr-sub { font-size: 13px; color: #4b5563; }
.hdr-meta { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px; }
.hdr-meta span { font-size: 12px; color: #6b7280; }
.hdr-meta strong { color: #1f2937; }

.sec { background: #ffffff; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }
.sec-title { font-size: 15px; font-weight: 700; color: #334155; margin-bottom: 14px;
             padding-bottom: 8px; border-bottom: 1px solid #e5e7eb; }

.kv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.kv { background: #f9fafb; border-radius: 6px; padding: 10px 14px; }
.kv-label { font-size: 11px; color: #6b7280; margin-bottom: 3px; }
.kv-value { font-size: 14px; font-weight: 600; color: #1f2937; }
.kv-unit { font-size: 11px; color: #4b5563; font-weight: 400; }

.concept-card { background: #f9fafb; border-radius: 8px; padding: 16px; margin-bottom: 10px; }
.concept-name { font-size: 18px; font-weight: 700; color: #f6e05e; margin-bottom: 6px; }
.concept-type { font-size: 12px; color: #334155; background: #1e2d40;
                padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 10px; }
.concept-strategy { font-size: 13px; color: #374151; line-height: 1.7; }
.keywords { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.kw { background: #1a2e40; color: #334155; font-size: 12px; padding: 3px 10px;
      border-radius: 20px; border: 1px solid #475569; }

.floor-table { width: 100%; border-collapse: collapse; }
.floor-table th { background: #f9fafb; padding: 8px 12px; text-align: left;
                  font-size: 12px; color: #4b5563; border-bottom: 1px solid #e5e7eb; }
.floor-table td { padding: 8px 12px; border-bottom: 1px solid #1e2533;
                  font-size: 13px; vertical-align: top; }
.floor-table tr:hover td { background: rgba(144,205,244,0.03); }
.floor-level { font-weight: 600; color: #1f2937; }
.prog-list { display: flex; flex-wrap: wrap; gap: 4px; }
.prog-tag { background: #1e2533; color: #4b5563; font-size: 11px;
            padding: 2px 7px; border-radius: 3px; }

.elev-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.elev-card { background: #f9fafb; border-radius: 6px; padding: 12px; }
.elev-dir { font-size: 12px; font-weight: 700; color: #334155; text-transform: uppercase;
            margin-bottom: 6px; }
.elev-row { font-size: 12px; color: #4b5563; margin-bottom: 3px; }
.elev-row strong { color: #1f2937; }

.note-list { display: flex; flex-direction: column; gap: 6px; }
.note-item { background: #f9fafb; border-radius: 6px; padding: 10px 14px;
             font-size: 13px; color: #374151; line-height: 1.6;
             border-left: 3px solid #6b7280; }
.note-item.accent { border-left-color: #334155; }

.dist-bar-wrap { display: flex; flex-direction: column; gap: 6px; }
.dist-row { display: flex; align-items: center; gap: 8px; }
.dist-label { font-size: 12px; color: #4b5563; min-width: 120px; }
.dist-bar-bg { flex: 1; background: #f9fafb; border-radius: 3px; height: 14px; overflow: hidden; }
.dist-bar-fill { height: 100%; border-radius: 3px; background: #475569; }
.dist-count { font-size: 12px; color: #6b7280; min-width: 28px; text-align: right; }

.footer { text-align: center; color: #6b7280; font-size: 12px; margin-top: 24px; padding: 12px; }
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
            f'<div class="concept-strategy" style="margin-top:8px;color:#4b5563">'
            f'<strong style="color:#6b7280">동선 전략: </strong>{circ}</div>'
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
                            f'<strong style="color:#334155">{label}: </strong>{val}</div>')
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
            f'<td style="font-size:12px;color:#6b7280">{core_txt}</td>'
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
        # 재건축 전용 타입
        "BUSINESS_VIABILITY": "사업성", "AREA_INCREASE": "면적증가",
        "VIEW_ANALYSIS": "조망분석", "COMMUNITY_PROGRAM": "커뮤니티",
        "COMPANY_PORTFOLIO": "회사실적", "CONSTRUCTION_PLAN": "시공계획",
        "UNIT_PLAN_PENTHOUSE": "펜트하우스",
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


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH #3-1/5 — 재건축 전용 helper utilities + 핵심메시지 + 사업성 renderer
# ═══════════════════════════════════════════════════════════════════════════════

def _to_list(val) -> list:
    """dict / list / None 모두 list로 정규화. _safe_list의 dict-미지원 보완."""
    if val is None:
        return []
    if isinstance(val, dict):
        return [val]
    if isinstance(val, list):
        return [v for v in val if v]
    return []


def _won_str(won):
    """원 단위 숫자 → 한국식 축약 (150_000_000_000 → '1,500억'). null-safe."""
    if won is None:
        return None
    try:
        v = float(won)
    except (TypeError, ValueError):
        return str(won)
    sign = '-' if v < 0 else ''
    v = abs(v)
    if v >= 1e12:
        return f'{sign}{v / 1e12:,.1f}조'
    if v >= 1e8:
        return f'{sign}{v / 1e8:,.0f}억'
    if v >= 1e4:
        return f'{sign}{v / 1e4:,.0f}만'
    return f'{sign}{v:,.0f}원'


def _pct_str(value):
    """퍼센트 값 포맷. null-safe."""
    if value is None:
        return None
    try:
        return f'{float(value):.1f}%'
    except (TypeError, ValueError):
        return str(value)


def _tag_cluster(items: list, color: str = '#334155') -> str:
    """키워드 태그 클러스터 HTML. 빈 항목 자동 필터."""
    items = [str(i) for i in (items or []) if i]
    if not items:
        return ''
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:7px">'
        + ''.join(
            f'<span style="background:{color}1a;color:{color};font-size:11px;'
            f'padding:3px 9px;border-radius:3px;border:1px solid {color}33">{t}</span>'
            for t in items
        )
        + '</div>'
    )


def _note_item(text: str, accent: bool = False) -> str:
    """노트 아이템 한 줄. accent=True면 강조 왼쪽 바."""
    if not text:
        return ''
    border = '#334155' if accent else '#6b7280'
    return (
        f'<div style="background:#f9fafb;border-radius:5px;padding:9px 13px;'
        f'margin-bottom:6px;font-size:13px;color:#374151;line-height:1.6;'
        f'border-left:3px solid {border}">{text}</div>'
    )


def _kv_card(label: str, value, unit: str = '', hl: bool = False) -> str:
    """강화 KV 카드. null/빈값 자동 skip. hl=True면 황금색 강조."""
    if value is None or value == '' or value == []:
        return ''
    if isinstance(value, float) and value == int(value):
        value = int(value)
    disp = f'{value:,}' if isinstance(value, (int, float)) else str(value)
    col = '#f6e05e' if hl else '#1f2937'
    brd = ';border:1px solid #f6e05e33' if hl else ''
    u = f' <span style="font-size:11px;color:#4b5563">{unit}</span>' if unit else ''
    return (
        f'<div style="background:#f9fafb;border-radius:6px;padding:12px 16px{brd}">'
        f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px">{label}</div>'
        f'<div style="font-size:17px;font-weight:700;color:{col}">{disp}{u}</div>'
        f'</div>'
    )


def _kv_grid(*blocks: str, cols: int = 3) -> str:
    """KV 카드를 N-column grid로 묶음. 빈 블록 자동 제거, 컬럼 수 자동 조정."""
    filled = [b for b in blocks if b]
    if not filled:
        return ''
    actual_cols = min(len(filled), cols)
    return (
        f'<div style="display:grid;grid-template-columns:repeat({actual_cols},1fr);'
        f'gap:10px;margin-bottom:14px">'
        + ''.join(filled)
        + '</div>'
    )


def _sec_open(title: str, icon: str = '', badge: str = '') -> str:
    """섹션 열기 (기존 sec + sec-title CSS 재사용)."""
    b = (
        f'<span style="font-size:10px;background:#1a2e40;color:#334155;'
        f'padding:2px 8px;border-radius:10px;margin-left:8px;font-weight:400">{badge}</span>'
    ) if badge else ''
    ic = f'<span style="opacity:0.7;margin-right:6px">{icon}</span>' if icon else ''
    return f'<div class="sec" style="margin-bottom:16px"><div class="sec-title">{ic}{title}{b}</div>'


def _sec_close() -> str:
    return '</div>'


def _missing(label: str) -> str:
    """페이지 검출됐지만 추출 필드 비어있을 때 가시적 placeholder."""
    return (
        f'<div style="background:#f9fafb;border-radius:5px;padding:11px 15px;'
        f'border:1px dashed #e5e7eb;color:#6b7280;font-size:12px;margin-bottom:8px">'
        f'⚠ {label} 페이지 검출됨 — 추출 필드 비어있음 (PDF 내 텍스트 인식 확인 필요)'
        f'</div>'
    )


# ── 핵심 메시지 (BRANDING + CONCEPT 통합) ─────────────────────────────────────

def _render_key_message(branding_list: list, concept_list: list) -> str:
    """브랜드 아이덴티티 + 설계 컨셉을 하나의 섹션으로 통합."""
    brand = branding_list[0] if branding_list and isinstance(branding_list[0], dict) else {}
    concept = concept_list[0] if concept_list and isinstance(concept_list[0], dict) else {}
    if not brand and not concept:
        return ''

    # ── 브랜드명 ──
    name_ko = brand.get('brand_name_ko') or concept.get('concept_name_ko') or ''
    name_en = brand.get('brand_name_en') or concept.get('concept_name_en') or ''
    name_html = ''
    if name_ko:
        name_html = (
            f'<div style="font-size:26px;font-weight:800;color:#f6e05e;'
            f'letter-spacing:-0.01em;margin-bottom:2px">{name_ko}</div>'
            + (f'<div style="font-size:13px;color:#6b7280;margin-bottom:8px">{name_en}</div>'
               if name_en and name_en != name_ko else '')
        )
    elif name_en:
        name_html = f'<div style="font-size:24px;font-weight:800;color:#f6e05e;margin-bottom:8px">{name_en}</div>'

    # ── 슬로건 ──
    slogan = brand.get('main_slogan', '')
    slogan_html = (
        f'<div style="font-size:14px;color:#1f2937;font-style:italic;padding:8px 12px;'
        f'border-left:3px solid #f6e05e;margin-bottom:12px;background:#ffffff;'
        f'border-radius:0 4px 4px 0">{slogan}</div>'
    ) if slogan else ''

    # ── 컨셉 배지 ──
    massing = concept.get('massing_type', '')
    metaphor = concept.get('metaphor_reference', '')
    badges = (
        (f'<span style="background:#1e2d40;color:#334155;font-size:11px;'
         f'padding:3px 9px;border-radius:3px;margin-right:6px">매스: {massing}</span>'
         if massing else '')
        + (f'<span style="background:#ede9fe;color:#a78bfa;font-size:11px;'
           f'padding:3px 9px;border-radius:3px">참조: {metaphor}</span>'
           if metaphor else '')
    )
    badges_html = f'<div style="margin-bottom:10px">{badges}</div>' if badges else ''

    # ── 전략 ──
    main_strat = concept.get('main_strategy', '')
    sub_strats = _to_list(concept.get('sub_strategies'))
    strat_html = (
        (_note_item(main_strat, accent=True) if main_strat else '')
        + ''.join(_note_item(s) for s in sub_strats[:4] if isinstance(s, str) and s)
    )

    # ── 서브 슬로건 ──
    sub_slogans = _to_list(brand.get('sub_slogans'))
    sub_slogan_html = ''.join(_note_item(s) for s in sub_slogans[:3] if isinstance(s, str) and s)

    # ── 키워드 + 타깃 태그 ──
    kws = list(dict.fromkeys(
        k for k in (
            _to_list(concept.get('keywords')) + _to_list(brand.get('premium_keywords'))
        ) if isinstance(k, str) and k
    ))
    targets = list(dict.fromkeys(
        t for t in (
            _to_list(concept.get('target_user'))
            + ([brand.get('target_lifestyle')] if brand.get('target_lifestyle') else [])
        ) if isinstance(t, str) and t
    ))

    body = (
        '<div style="background:#f9fafb;border-radius:8px;padding:18px 20px">'
        + name_html + slogan_html + badges_html + strat_html + sub_slogan_html
        + _tag_cluster(kws, '#334155')
        + (_tag_cluster(targets, '#ea580c') if targets else '')
        + '</div>'
    )
    return _sec_open('핵심 메시지', '✦', 'BRANDING · CONCEPT') + body + _sec_close()


# ── 사업성 (BUSINESS_VIABILITY) ───────────────────────────────────────────────

def _render_business_viability(bv_list: list) -> str:
    """자산가치·분담금·용적률·사업비 핵심 지표. 복수 페이지 각각 sub-block으로."""
    if not bv_list:
        return ''
    all_html = ''
    for item in bv_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items()
                     if k != '_page' and v not in (None, '', [], {})}
        if not non_empty:
            all_html += _missing('BUSINESS_VIABILITY')
            continue

        page = item.get('_page', '')
        pg_html = (
            f'<div style="font-size:10px;color:#6b7280;margin-bottom:8px">p{page}</div>'
        ) if page else ''

        # 자산가치
        av_won = _won_str(item.get('asset_value_increase_won'))
        av_multi = item.get('asset_value_multiplier')
        av_disp = av_won or ''
        if av_multi:
            m = int(av_multi) if isinstance(av_multi, float) and av_multi == int(av_multi) else av_multi
            av_disp = (av_disp + f' ({m}배)') if av_disp else f'{m}배'

        # 분담금
        contrib = _won_str(item.get('member_contribution_change_won'))
        contrib_pct = _pct_str(item.get('member_contribution_change_pct'))
        contrib_disp = (contrib + (f' ({contrib_pct})' if contrib_pct else '')) if contrib else (contrib_pct or '')

        kv_top = _kv_grid(
            _kv_card('조합원 자산가치 증가', av_disp, hl=True) if av_disp else '',
            _kv_card('분담금 변화', contrib_disp, hl=bool(contrib)) if contrib_disp else '',
            _kv_card('평당 분양가', _won_str(item.get('sale_price_per_pyeong_won')), '원/평')
            if item.get('sale_price_per_pyeong_won') else '',
            cols=3,
        )

        # 용적률 인센티브
        fb, fi, ff = _pct_str(item.get('far_base_pct')), _pct_str(item.get('far_incentive_pct')), _pct_str(item.get('far_final_pct'))
        far_html = ''
        if any([fb, fi, ff]):
            far_html = (
                '<div style="background:#f9fafb;border-radius:6px;padding:12px 16px;margin-bottom:10px">'
                '<div style="font-size:11px;color:#6b7280;margin-bottom:8px">용적률 인센티브</div>'
                '<div style="display:flex;align-items:center;gap:8px;font-size:13px">'
                + (f'<span style="color:#4b5563">기준 {fb}</span>' if fb else '')
                + (f'<span style="color:#6b7280">→</span><span style="color:#334155">+인센티브 {fi}</span>' if fi else '')
                + (f'<span style="color:#6b7280">→</span>'
                   f'<span style="font-weight:700;color:#f6e05e">최종 {ff}</span>' if ff else '')
                + '</div></div>'
            )

        kv_mid = _kv_grid(
            _kv_card('일반분양', item.get('general_sale_units'), '세대') if item.get('general_sale_units') else '',
            _kv_card('조합원', item.get('member_units'), '세대') if item.get('member_units') else '',
            _kv_card('공사비 절감', _won_str(item.get('construction_cost_savings_won'))) if item.get('construction_cost_savings_won') else '',
            _kv_card('공기 단축', item.get('period_reduction_months'), '개월') if item.get('period_reduction_months') else '',
            cols=4,
        )

        messages = _to_list(item.get('key_messages'))
        msg_html = ''.join(
            _note_item(m, accent=(i == 0))
            for i, m in enumerate(messages)
            if isinstance(m, str) and m
        )

        all_html += (
            f'<div style="margin-bottom:12px">'
            f'{pg_html}{kv_top}{far_html}{kv_mid}{msg_html}'
            f'</div>'
        )

    return (_sec_open('사업성', '₩', 'BUSINESS_VIABILITY') + all_html + _sec_close()) if all_html else ''


# ── 조합원 혜택: 실사용면적 증가 (AREA_INCREASE) ──────────────────────────────

def _render_area_increase(ai_list: list) -> str:
    """기존 vs 재건축 후 면적 비교 테이블 + 요약."""
    if not ai_list:
        return ''
    all_html = ''
    _th = 'background:#f9fafb;padding:7px 12px;font-size:11px;color:#6b7280;border-bottom:1px solid #e5e7eb'
    for item in ai_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items() if k != '_page' and v not in (None, '', [], {})}
        if not non_empty:
            all_html += _missing('AREA_INCREASE')
            continue
        page = item.get('_page', '')
        pg_html = f'<div style="font-size:10px;color:#6b7280;margin-bottom:8px">p{page}</div>' if page else ''

        # 면적 비교 테이블
        pairs = [p for p in (item.get('unit_pairs') or []) if isinstance(p, dict)]
        rows = ''
        for p in pairs:
            ex_t = p.get('existing_type', '') or ''
            ex_s = p.get('existing_actual_sqm')
            rv_t = p.get('redev_type', '') or ''
            rv_s = p.get('redev_actual_sqm')
            inc_p = p.get('increase_pyeong')
            inc_pct = _pct_str(p.get('increase_pct'))
            _td = 'padding:8px 12px;border-bottom:1px solid #1e2533'
            rows += (
                f'<tr>'
                f'<td style="{_td};color:#4b5563">{ex_t}</td>'
                f'<td style="{_td};color:#4b5563;text-align:right">{"" if ex_s is None else f"{ex_s:.1f}㎡"}</td>'
                f'<td style="{_td};color:#1f2937;font-weight:600">{rv_t}</td>'
                f'<td style="{_td};color:#1f2937;font-weight:600;text-align:right">{"" if rv_s is None else f"{rv_s:.1f}㎡"}</td>'
                f'<td style="{_td};color:#16a34a;font-weight:700;text-align:right">{"" if inc_p is None else f"+{inc_p:.0f}평"}</td>'
                f'<td style="{_td};color:#16a34a;text-align:right">{"" if inc_pct is None else f"↑{inc_pct}"}</td>'
                f'</tr>'
            )
        table_html = ''
        if rows:
            table_html = (
                '<div style="overflow-x:auto;margin-bottom:14px">'
                '<table style="width:100%;border-collapse:collapse">'
                '<thead><tr>'
                f'<th style="{_th};text-align:left">기존 타입</th>'
                f'<th style="{_th};text-align:right">기존 면적</th>'
                f'<th style="{_th};text-align:left">재건축 후 타입</th>'
                f'<th style="{_th};text-align:right">재건축 후 면적</th>'
                f'<th style="{_th};text-align:right">면적 증가</th>'
                f'<th style="{_th};text-align:right">증가율</th>'
                f'</tr></thead><tbody>{rows}</tbody></table></div>'
            )

        max_multi = item.get('max_increase_multiplier')
        avg_p = item.get('average_increase_pyeong')
        kv_s = _kv_grid(
            _kv_card('최대 면적 배수', f'{max_multi}배' if max_multi else None, hl=True),
            _kv_card('평균 증가', avg_p, '평') if avg_p else '',
            cols=2,
        )
        msg = item.get('key_message', '')
        all_html += f'<div style="margin-bottom:12px">{pg_html}{table_html}{kv_s}{_note_item(msg, accent=True) if msg else ""}</div>'

    return (_sec_open('실사용면적 증가', '↑', 'AREA_INCREASE') + all_html + _sec_close()) if all_html else ''


# ── 조합원 혜택: 조망·남향 (VIEW_ANALYSIS) ────────────────────────────────────

def _render_view_analysis(va_list: list) -> str:
    """남향%·강뷰%·더블뷰%·조합원 조망 보장% 대형 KV + 전략 노트."""
    if not va_list:
        return ''
    all_html = ''
    for item in va_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items() if k != '_page' and v not in (None, '', [], {})}
        if not non_empty:
            all_html += _missing('VIEW_ANALYSIS')
            continue
        page = item.get('_page', '')
        pg_html = f'<div style="font-size:10px;color:#6b7280;margin-bottom:8px">p{page}</div>' if page else ''

        kv_top = _kv_grid(
            _kv_card('남향 배치', _pct_str(item.get('south_facing_units_pct')), hl=True) if item.get('south_facing_units_pct') is not None else '',
            _kv_card('강·수변 조망', _pct_str(item.get('river_view_units_pct'))) if item.get('river_view_units_pct') is not None else '',
            _kv_card('더블 조망', _pct_str(item.get('double_view_units_pct'))) if item.get('double_view_units_pct') is not None else '',
            _kv_card('조합원 조망 보장', _pct_str(item.get('member_units_view_guarantee_pct')), hl=True) if item.get('member_units_view_guarantee_pct') is not None else '',
            cols=4,
        )
        targets = [str(t) for t in _to_list(item.get('view_targets')) if t]
        strategy = item.get('site_layout_strategy', '')
        msg = item.get('key_message', '')
        all_html += (
            f'<div style="margin-bottom:12px">{pg_html}{kv_top}'
            + (_tag_cluster(targets, '#16a34a') if targets else '')
            + (_note_item(strategy, accent=True) if strategy else '')
            + (_note_item(msg) if msg and msg != strategy else '')
            + '</div>'
        )
    return (_sec_open('조망·남향 배치', '⊙', 'VIEW_ANALYSIS') + all_html + _sec_close()) if all_html else ''


# ── 상품 경쟁력: 표준 단위세대 (UNIT_PLAN) ────────────────────────────────────

def _render_unit_plan_std(up_list: list) -> str:
    """평형별 카드 갤러리. 면적·LDK·특징 태그 포함."""
    if not up_list:
        return ''
    cards = []
    total_units = 0
    for item in up_list:
        if not isinstance(item, dict):
            continue
        u_type = item.get('unit_type', '')
        actual_p = item.get('actual_area_pyeong')
        actual_s = item.get('actual_area_sqm')
        supply_s = item.get('supply_area_sqm')
        service_s = item.get('service_area_sqm')
        count = item.get('unit_count')
        ldk = item.get('ldk_layout', '')
        bath = item.get('bathroom_count')
        core = item.get('core_type', '')
        features = [str(f) for f in _to_list(item.get('key_features')) if f]

        non_empty = {k: v for k, v in item.items() if k not in ('_page', 'error') and v not in (None, '', [], {})}
        if not non_empty:
            continue

        if count:
            try:
                total_units += int(count)
            except (TypeError, ValueError):
                pass

        area_parts = []
        if supply_s:
            area_parts.append(f'공급 {supply_s:.1f}㎡')
        if actual_s:
            area_parts.append(f'실사용 {actual_s:.1f}㎡')
        if service_s:
            area_parts.append(f'서비스 {service_s:.1f}㎡')

        meta = ' · '.join(filter(None, [ldk, f'욕실 {bath}개' if bath else '', f'코어: {core}' if core else '']))

        p_disp = int(actual_p) if isinstance(actual_p, float) and actual_p == int(actual_p) else actual_p

        card = (
            '<div style="background:#f9fafb;border-radius:6px;padding:14px 16px;border-top:3px solid #475569">'
            f'<div style="font-size:17px;font-weight:800;color:#334155;margin-bottom:2px">{u_type}</div>'
            + (f'<div style="font-size:24px;font-weight:700;color:#1f2937">{p_disp}<span style="font-size:12px;color:#6b7280;font-weight:400">평</span></div>' if actual_p else '')
            + (f'<div style="font-size:11px;color:#6b7280">{count}세대</div>' if count else '')
            + (f'<div style="font-size:11px;color:#6b7280;line-height:1.7;margin:4px 0">{"  /  ".join(area_parts)}</div>' if area_parts else '')
            + (f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px">{meta}</div>' if meta else '')
            + (_tag_cluster(features, '#334155') if features else '')
            + '</div>'
        )
        cards.append(card)

    if not cards:
        return ''
    summary = (f'<div style="font-size:12px;color:#6b7280;margin-bottom:10px">총 {total_units}세대</div>') if total_units else ''
    n = min(len(cards), 4)
    grid = f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:10px">{"".join(cards)}</div>'
    return _sec_open('단위세대', '□', 'UNIT_PLAN') + summary + grid + _sec_close()


# ── 상품 경쟁력: 펜트하우스 (UNIT_PLAN_PENTHOUSE) ─────────────────────────────

def _render_unit_plan_penthouse(upp_list: list) -> str:
    """펜트하우스 전용 — 황금 테두리 프리미엄 카드."""
    if not upp_list:
        return ''
    cards = []
    for item in upp_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items() if k not in ('_page', 'error') and v not in (None, '', [], {})}
        if not non_empty:
            cards.append(_missing('UNIT_PLAN_PENTHOUSE'))
            continue

        u_type = item.get('unit_type', '')
        actual_p = item.get('actual_area_pyeong')
        actual_s = item.get('actual_area_sqm')
        count = item.get('unit_count')
        terrace_s = item.get('terrace_area_sqm')
        ceiling_m = item.get('ceiling_height_m')
        open_sides = item.get('open_sides')
        sig = [str(f) for f in _to_list(item.get('signature_features')) if f]
        lux = [str(k) for k in _to_list(item.get('luxury_keywords')) if k]

        area_rows = ''.join(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
            f'border-bottom:1px solid #1e2533;font-size:12px">'
            f'<span style="color:#6b7280">{lbl}</span>'
            f'<span style="color:#1f2937">{v:.1f}㎡</span></div>'
            for lbl, v in [
                ('전용', item.get('exclusive_area_sqm')),
                ('공급', item.get('supply_area_sqm')),
                ('서비스', item.get('service_area_sqm')),
                ('테라스', terrace_s),
            ] if v
        )
        spec_tags = [s for s in [
            f'천장고 {ceiling_m}m' if ceiling_m else '',
            f'{open_sides}면 개방' if open_sides else '',
            f'{count}세대' if count else '',
        ] if s]
        p_disp = int(actual_p) if isinstance(actual_p, float) and actual_p == int(actual_p) else actual_p

        cards.append(
            '<div style="background:#f9fafb;border-radius:8px;padding:18px 20px;'
            'border:2px solid #f6e05e33;border-top:4px solid #f6e05e">'
            f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:8px">'
            f'<div style="font-size:20px;font-weight:800;color:#f6e05e">{u_type}</div>'
            f'<span style="background:#b7791f;color:#fefcbf;font-size:10px;padding:2px 7px;border-radius:10px;font-weight:700">펜트하우스</span>'
            f'</div>'
            + (f'<div style="font-size:32px;font-weight:800;color:#1f2937;margin-bottom:6px">'
               f'{p_disp}<span style="font-size:14px;color:#6b7280;font-weight:400">평</span>'
               + (f' <span style="font-size:13px;color:#4b5563">({actual_s:.2f}㎡)</span>' if actual_s else '')
               + '</div>' if actual_p else '')
            + (f'<div style="margin:10px 0">{area_rows}</div>' if area_rows else '')
            + (_tag_cluster(spec_tags, '#f6e05e') if spec_tags else '')
            + (_tag_cluster(sig, '#ea580c') if sig else '')
            + (_tag_cluster(lux, '#a78bfa') if lux else '')
            + '</div>'
        )

    if not cards:
        return ''
    n = min(len(cards), 3)
    grid = f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:12px">{"".join(cards)}</div>'
    return _sec_open('펜트하우스', '★', 'UNIT_PLAN_PENTHOUSE') + grid + _sec_close()


# ── 섹션 내 소제목 헬퍼 ──────────────────────────────────────────────────────

def _sub_header(title: str) -> str:
    """섹션 내 소제목 구분선 (섹션 아이콘 없이 컴팩트하게)."""
    return (
        f'<div style="font-size:12px;font-weight:700;color:#4b5563;'
        f'letter-spacing:0.05em;margin:14px 0 8px;padding-bottom:4px;'
        f'border-bottom:1px solid #1e2533">{title}</div>'
    )


# ── 단지 계획 (SITE_PLAN + SITE_CONTEXT + LANDSCAPE 통합) ─────────────────────

def _render_site_planning(sp_list: list, sc_list: list, lc_list: list) -> str:
    """배치 전략 + 대지 분석 + 조경 계획을 단지계획 섹션 하나로."""
    if not any([sp_list, sc_list, lc_list]):
        return ''
    body = ''

    # ── 배치 전략 (SITE_PLAN) ──
    sp_html = ''
    for item in sp_list:
        if not isinstance(item, dict):
            continue
        note_pairs = [
            ('주 출입 방향', item.get('main_entrance_direction')),
            ('차량 진입',    item.get('vehicle_access_direction')),
            ('오픈스페이스', item.get('open_space_strategy')),
        ]
        sp_html += ''.join(
            _note_item(f'<strong style="color:#6b7280">{lbl}: </strong>{val}', accent=(i == 0))
            for i, (lbl, val) in enumerate(note_pairs)
            if val and val not in ('', [])
        )
    if sp_html:
        body += _sub_header('배치 전략') + sp_html

    # ── 대지 분석 (SITE_CONTEXT) ──
    sc_html = ''
    for item in sc_list:
        if not isinstance(item, dict):
            continue
        strategy  = item.get('urban_strategy', '')
        hist      = item.get('historical_context', '')
        green_net = item.get('green_network', '')
        issues     = [str(v) for v in _to_list(item.get('site_issues'))                if v]
        facilities = [str(v) for v in _to_list(item.get('surrounding_facilities'))     if v]
        transport  = [str(v) for v in _to_list(item.get('transportation_connections')) if v]

        if strategy:   sc_html += _note_item(strategy, accent=True)
        if hist:       sc_html += _note_item(hist)
        if green_net:  sc_html += _note_item(green_net)
        if facilities:
            sc_html += ('<div style="margin-top:6px"><span style="font-size:11px;color:#6b7280">주변 시설: </span>'
                        + _tag_cluster(facilities, '#16a34a') + '</div>')
        if transport:
            sc_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">교통: </span>'
                        + _tag_cluster(transport, '#334155') + '</div>')
        if issues:
            sc_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">사이트 이슈: </span>'
                        + _tag_cluster(issues, '#dc2626') + '</div>')
    if sc_html:
        body += _sub_header('대지 분석') + sc_html

    # ── 조경 계획 (LANDSCAPE) ──
    lc_html = ''
    for item in lc_list:
        if not isinstance(item, dict):
            continue
        green_pct = _pct_str(item.get('green_area_ratio_pct'))
        concept   = item.get('key_landscape_concept', '')
        connect   = item.get('connection_to_surroundings', '')
        water     = item.get('water_feature', False)
        trees     = [str(v) for v in _to_list(item.get('tree_types'))       if v]
        programs  = [str(v) for v in _to_list(item.get('outdoor_programs')) if v]
        pavement  = [str(v) for v in _to_list(item.get('pavement_types'))   if v]

        lc_html += _kv_grid(
            _kv_card('녹지율', green_pct) if green_pct else '',
            _kv_card('수경 시설', '✓ 있음', hl=True) if water else '',
            cols=2,
        )
        if concept:  lc_html += _note_item(concept, accent=True)
        if connect:  lc_html += _note_item(connect)
        if trees:
            lc_html += ('<div style="margin-top:6px"><span style="font-size:11px;color:#6b7280">수종: </span>'
                        + _tag_cluster(trees, '#16a34a') + '</div>')
        if programs:
            lc_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">야외 프로그램: </span>'
                        + _tag_cluster(programs, '#334155') + '</div>')
        if pavement:
            lc_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">포장재: </span>'
                        + _tag_cluster(pavement, '#4b5563') + '</div>')
    if lc_html:
        body += _sub_header('조경 계획') + lc_html

    return (_sec_open('단지 계획', '⊞', 'SITE_PLAN · CONTEXT · LANDSCAPE') + body + _sec_close()) if body else ''


# ── 커뮤니티 (COMMUNITY_PROGRAM + SPECIAL_SPACE 통합) ─────────────────────────

def _render_community(cp_list: list, ss_list: list) -> str:
    """커뮤니티 프로그램 + 특별 공간을 커뮤니티 섹션 하나로."""
    if not any([cp_list, ss_list]):
        return ''
    body = ''

    # ── 커뮤니티 프로그램 (COMMUNITY_PROGRAM) ──
    cp_html = ''
    for item in cp_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items()
                     if k != '_page' and v not in (None, '', [], {}, False)}
        if not non_empty:
            cp_html += _missing('COMMUNITY_PROGRAM')
            continue

        count   = item.get('total_program_count')
        area_ph = item.get('area_per_household_pyeong')
        sky     = item.get('sky_community_present', False)
        sig     = [str(v) for v in _to_list(item.get('signature_facilities')) if v]
        hotel   = [str(v) for v in _to_list(item.get('hotel_style_features')) if v]
        premium = [str(v) for v in _to_list(item.get('premium_keywords'))     if v]
        msg     = item.get('key_message', '')

        cp_html += _kv_grid(
            _kv_card('프로그램 수',  count,   '개',      hl=True) if count   else '',
            _kv_card('세대당 면적', area_ph, '평/세대', hl=bool(area_ph)) if area_ph else '',
            _kv_card('스카이 커뮤니티', '✓ 있음', hl=True) if sky else '',
            cols=3,
        )
        if sig:
            cp_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">시그니처 시설: </span>'
                        + _tag_cluster(sig, '#ea580c') + '</div>')
        if hotel:
            cp_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">호텔식 서비스: </span>'
                        + _tag_cluster(hotel, '#334155') + '</div>')
        if premium:
            cp_html += _tag_cluster(premium, '#a78bfa')
        if msg:
            cp_html += _note_item(msg, accent=True)

    if cp_html:
        body += _sub_header('커뮤니티 프로그램') + cp_html

    # ── 특별 공간 (SPECIAL_SPACE) — 페이지별 카드 ──
    ss_cards = []
    for item in ss_list:
        if not isinstance(item, dict):
            continue
        name     = item.get('space_name', '') or ''
        s_type   = item.get('space_type', '')  or ''
        features = [str(v) for v in _to_list(item.get('key_features'))   if v]
        users    = [str(v) for v in _to_list(item.get('target_users'))    if v]
        strategy = item.get('spatial_strategy', '')

        if not any([name, features, strategy]):
            continue

        type_color = {
            'community': '#16a34a', 'culture': '#334155', 'lobby': '#ea580c',
            'rooftop':   '#f6e05e', 'children': '#dc2626', 'council': '#a78bfa',
        }.get(s_type, '#4b5563')

        ss_cards.append(
            f'<div style="background:#f9fafb;border-radius:6px;padding:14px 16px;'
            f'border-top:3px solid {type_color}">'
            + (f'<div style="font-size:14px;font-weight:700;color:#1f2937;margin-bottom:4px">{name}</div>' if name else '')
            + (f'<span style="background:{type_color}1a;color:{type_color};font-size:10px;'
               f'padding:2px 7px;border-radius:3px;margin-bottom:8px;display:inline-block">{s_type}</span>' if s_type else '')
            + (_tag_cluster(features, '#334155') if features else '')
            + (_tag_cluster(users, '#ea580c')    if users    else '')
            + (_note_item(strategy)              if strategy else '')
            + '</div>'
        )

    if ss_cards:
        n = min(len(ss_cards), 3)
        body += (
            _sub_header(f'특별 공간 ({len(ss_cards)}개)')
            + f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:10px">{"".join(ss_cards)}</div>'
        )

    return (_sec_open('커뮤니티', '◎', 'COMMUNITY_PROGRAM · SPECIAL_SPACE') + body + _sec_close()) if body else ''


# ── 디자인·외관 (CONCEPT 상세 + ELEVATION 통합) ────────────────────────────────

def _render_design(concept_list: list, elevation_list: list) -> str:
    """설계 전략 상세(sub_strategies·metaphor) + 방위별 입면 파사드.
    concept의 name·main_strategy·keywords는 key_message에서 다루므로 여기선 제외."""
    if not any([concept_list, elevation_list]):
        return ''
    body = ''

    # ── 설계 전략 상세 (CONCEPT sub_strategies / metaphor) ──
    cv_html = ''
    for item in concept_list:
        if not isinstance(item, dict):
            continue
        sub_strats = [str(s) for s in _to_list(item.get('sub_strategies')) if s]
        metaphor   = item.get('metaphor_reference', '')
        cv_html += ''.join(_note_item(s) for s in sub_strats)
        if metaphor:
            cv_html += _note_item(f'레퍼런스: {metaphor}')
    if cv_html:
        body += _sub_header('설계 전략 상세') + cv_html

    # ── 입면·파사드 (ELEVATION — 방위별 카드) ──
    el_cards = []
    for item in elevation_list:
        if not isinstance(item, dict):
            continue
        direction = item.get('facade_direction', '') or ''
        mat1    = item.get('primary_material', '')
        mat2    = item.get('secondary_material', '')
        system  = item.get('facade_system', '')
        shading = item.get('shading_device', '')
        green   = item.get('green_facade', False)
        transp  = item.get('transparency_ratio', '')
        rhythm  = item.get('facade_rhythm', '')

        if not any([mat1, mat2, system, shading, transp]):
            continue

        dir_ko = {'north': '북', 'south': '남', 'east': '동', 'west': '서'}.get(direction, direction)
        title  = f'{dir_ko}측 입면' if dir_ko else '입면'
        _td = 'display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1e2533;font-size:12px'
        rows = ''.join(
            f'<div style="{_td}"><span style="color:#6b7280">{lbl}</span>'
            f'<span style="color:#1f2937;font-weight:500">{val}</span></div>'
            for lbl, val in [
                ('주 마감재',    mat1),
                ('보조 마감재',  mat2),
                ('파사드 시스템', system),
                ('차양 장치',    shading),
                ('투명도',      transp),
                ('파사드 리듬',  rhythm),
            ] if val
        )
        green_row = (
            f'<div style="{_td}"><span style="color:#6b7280">그린 파사드</span>'
            f'<span style="color:#16a34a;font-weight:500">✓</span></div>'
        ) if green else ''

        el_cards.append(
            f'<div style="background:#f9fafb;border-radius:6px;padding:14px 16px;border-top:3px solid #6b7280">'
            f'<div style="font-size:14px;font-weight:700;color:#1f2937;margin-bottom:8px">{title}</div>'
            f'{rows}{green_row}'
            f'</div>'
        )

    if el_cards:
        n = min(len(el_cards), 4)
        body += (
            _sub_header('입면·파사드')
            + f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:10px">{"".join(el_cards)}</div>'
        )

    return (_sec_open('디자인·외관', '◧', 'CONCEPT · ELEVATION') + body + _sec_close()) if body else ''


# ── 시공성 (CONSTRUCTION_PLAN) ─────────────────────────────────────────────────

def _render_construction_plan(cp_list: list) -> str:
    """공기 단축·공사비·지하주차 효율 핵심 지표."""
    if not cp_list:
        return ''
    all_html = ''
    for item in cp_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items() if k != '_page' and v not in (None, '', [], {})}
        if not non_empty:
            all_html += _missing('CONSTRUCTION_PLAN')
            continue

        page = item.get('_page', '')
        pg_html = f'<div style="font-size:10px;color:#6b7280;margin-bottom:8px">p{page}</div>' if page else ''

        period   = item.get('period_reduction_months')
        savings  = _won_str(item.get('cost_savings_won'))
        ug_lev   = item.get('underground_parking_levels')
        ug_dep   = item.get('underground_excavation_depth_m')
        park_ph  = item.get('parking_per_household')
        deck_h   = item.get('deck_floor_height_m')
        smart    = [str(v) for v in _to_list(item.get('smart_parking_features'))  if v]
        strats   = [str(v) for v in _to_list(item.get('construction_strategies')) if v]

        kv_top = _kv_grid(
            _kv_card('공기 단축', period,  '개월', hl=True) if period  else '',
            _kv_card('공사비 절감', savings, hl=True)       if savings else '',
            cols=2,
        )
        kv_mid = _kv_grid(
            _kv_card('지하 주차장',  ug_lev,  '층') if ug_lev  else '',
            _kv_card('굴착 깊이',    ug_dep,  'm')  if ug_dep  else '',
            _kv_card('세대당 주차',  park_ph, '대') if park_ph else '',
            _kv_card('데크층 높이',  deck_h,  'm')  if deck_h  else '',
            cols=4,
        )
        tag_html = ''
        if smart:
            tag_html += ('<div style="margin-top:6px"><span style="font-size:11px;color:#6b7280">스마트 주차: </span>'
                         + _tag_cluster(smart, '#334155') + '</div>')
        if strats:
            tag_html += ('<div style="margin-top:4px"><span style="font-size:11px;color:#6b7280">시공 전략: </span>'
                         + _tag_cluster(strats, '#ea580c') + '</div>')

        all_html += f'<div style="margin-bottom:12px">{pg_html}{kv_top}{kv_mid}{tag_html}</div>'

    return (_sec_open('시공성', '⚙', 'CONSTRUCTION_PLAN') + all_html + _sec_close()) if all_html else ''


# ── 회사 역량 (COMPANY_PORTFOLIO) ─────────────────────────────────────────────

def _render_company_portfolio(port_list: list) -> str:
    """회사 통계·신용·어워드·유사 프로젝트·임원진."""
    if not port_list:
        return ''
    all_html = ''
    for item in port_list:
        if not isinstance(item, dict):
            continue
        non_empty = {k: v for k, v in item.items() if k != '_page' and v not in (None, '', [], {})}
        if not non_empty:
            all_html += _missing('COMPANY_PORTFOLIO')
            continue

        page = item.get('_page', '')
        pg_html = f'<div style="font-size:10px;color:#6b7280;margin-bottom:8px">p{page}</div>' if page else ''

        firm     = item.get('firm_name', '')
        emps     = item.get('total_employees')
        licensed = item.get('licensed_architects')
        revenue  = _won_str(item.get('financial_revenue_won'))
        credit   = item.get('credit_rating', '')
        awards   = [str(v) for v in _to_list(item.get('design_awards')) if v]
        projects = [p for p in _to_list(item.get('similar_projects'))   if isinstance(p, dict)]
        execs    = [e for e in _to_list(item.get('key_executives'))      if isinstance(e, dict)]

        firm_html = (
            f'<div style="font-size:18px;font-weight:700;color:#1f2937;margin-bottom:10px">{firm}</div>'
        ) if firm else ''

        kv_stats = _kv_grid(
            _kv_card('직원 수',     emps,     '명', hl=False) if emps     else '',
            _kv_card('등록 건축사', licensed, '명')           if licensed else '',
            _kv_card('매출액',      revenue)                   if revenue  else '',
            _kv_card('신용 등급',   credit,         hl=True)  if credit   else '',
            cols=4,
        )

        award_html = (
            '<div style="margin-top:6px"><span style="font-size:11px;color:#6b7280">디자인 어워드: </span>'
            + _tag_cluster(awards, '#f6e05e') + '</div>'
        ) if awards else ''

        # 유사 프로젝트 미니카드
        proj_html = ''
        if projects:
            proj_cards = ''.join(
                f'<div style="background:#f9fafb;border-radius:5px;padding:10px 12px">'
                f'<div style="font-size:12px;font-weight:600;color:#334155">{p.get("name","")}</div>'
                + (f'<div style="font-size:10px;color:#6b7280">{p.get("year","")}</div>' if p.get("year") else '')
                + (f'<div style="font-size:11px;color:#6b7280;margin-top:3px;line-height:1.5">{p.get("highlight","")}</div>' if p.get("highlight") else '')
                + '</div>'
                for p in projects[:6]
            )
            n = min(len(projects[:6]), 3)
            proj_html = (
                '<div style="font-size:11px;color:#6b7280;margin:10px 0 6px">유사 프로젝트</div>'
                f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:8px">{proj_cards}</div>'
            )

        # 임원진 태그
        exec_tags = [
            f'{e.get("name","")}{"(" + e.get("role","") + ")" if e.get("role") else ""}'
            for e in execs if e.get('name')
        ]
        exec_html = (
            '<div style="margin-top:8px"><span style="font-size:11px;color:#6b7280">임원진: </span>'
            + _tag_cluster(exec_tags, '#4b5563') + '</div>'
        ) if exec_tags else ''

        all_html += f'<div style="margin-bottom:12px">{pg_html}{firm_html}{kv_stats}{award_html}{proj_html}{exec_html}</div>'

    return (_sec_open('회사 역량', '⊕', 'COMPANY_PORTFOLIO') + all_html + _sec_close()) if all_html else ''


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
    facility_label = _facility_label(facility_type)

    result_badge = _RESULT_BADGE.get(result, "")

    header = f"""
    <div class="hdr">
      <div class="hdr-top">
        <span style="background:#2b4c7e;color:#334155;font-size:11px;padding:3px 10px;
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
    for sp in _to_list(ed.get("site_plan")):
        if isinstance(sp, dict):
            for k in ("site_area_sqm", "building_area_sqm", "total_floor_area_sqm",
                      "building_coverage_ratio_pct", "floor_area_ratio_pct",
                      "floors_above", "floors_below", "max_height_m", "parking_count"):
                if quant.get(k) is None and sp.get(k) is not None:
                    quant[k] = sp[k]

    sections = "".join([
        # 1. 핵심 메시지 (BRANDING + CONCEPT 통합)
        _render_key_message(
            _to_list(ed.get("branding")),
            _to_list(ed.get("concept")),
        ),
        # 2. 사업성
        _render_business_viability(_to_list(ed.get("business_viability"))),
        # 3. 실사용면적 증가
        _render_area_increase(_to_list(ed.get("area_increase"))),
        # 4. 조망·남향 배치
        _render_view_analysis(_to_list(ed.get("view_analysis"))),
        # 5. 표준 단위세대
        _render_unit_plan_std(_to_list(ed.get("unit_plan"))),
        # 6. 펜트하우스
        _render_unit_plan_penthouse(_to_list(ed.get("unit_plan_penthouse"))),
        # 7. 단지 계획 (배치·대지분석·조경 통합)
        _render_site_planning(
            _to_list(ed.get("site_plan")),
            _to_list(ed.get("site_context")),
            _to_list(ed.get("landscape")),
        ),
        # 8. 커뮤니티 (프로그램 + 특별공간 통합)
        _render_community(
            _to_list(ed.get("community_program")),
            _to_list(ed.get("special_space")),
        ),
        # 9. 디자인·외관 (컨셉 상세 + 입면 통합)
        _render_design(
            _to_list(ed.get("concept")),
            _to_list(ed.get("elevation")),
        ),
        # 10. 시공성
        _render_construction_plan(_to_list(ed.get("construction_plan"))),
        # 11. 회사 역량
        _render_company_portfolio(_to_list(ed.get("company_portfolio"))),
        # 12. 페이지 구성 (항상 표시 — 패턴 진단용)
        _render_page_dist(page_dist, total_pages),
        # ── 부록 (공공공모 섹션 — 재건축에선 후순위) ──────────────────
        _render_quantitative(quant),
        _render_floor_plan(_safe_list(ed.get("floor_plan"))),
        _render_section(_safe_list(ed.get("section"))),
        _render_sustainability(_safe_list(ed.get("sustainability"))),
        _render_technical(_safe_list(ed.get("technical"))),
        # 표지 정보 (참조용)
        _render_cover(cover),
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
