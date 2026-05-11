import json
import re
from config import FACILITY_TYPES

AXIS_LABELS_KO = {
    "business_viability":      "사업성",
    "member_benefit":          "조합원 혜택",
    "product_competitiveness": "상품 경쟁력",
    "site_planning":           "단지 계획",
    "community":               "커뮤니티",
    "design_brand":            "디자인·브랜드",
    "constructability":        "시공성",
    "firm_capability":         "회사 역량",
}

AXES = [
    "business_viability", "member_benefit", "product_competitiveness",
    "site_planning", "community", "design_brand",
    "constructability", "firm_capability",
]

PALETTE = [
    '#7CB7E0',  # soft blue
    '#E8B27A',  # soft amber
    '#9DC9A4',  # soft sage
    '#C9A4D8',  # soft lavender
    '#E89A9A',  # soft coral
    '#7AC5C5',  # soft teal
    '#D4A574',  # soft caramel
    '#A8B5D0',  # soft slate-blue
]

AXIS_LABEL_DASH = {
    'business_viability':      ('사업성',          '₩'),
    'member_benefit':          ('조합원 혜택',     '⊙'),
    'product_competitiveness': ('상품 경쟁력',     '□'),
    'site_planning':           ('단지 계획',       '⊞'),
    'community':               ('커뮤니티',        '◎'),
    'design_brand':            ('디자인·브랜드',   '◧'),
    'constructability':        ('시공성',          '⚙'),
    'firm_capability':         ('회사 역량',       '⊕'),
}

COMP_LABEL_MAP = {'yes': '지침충족', 'partial': '부분충족', 'no': '미충족', 'unclear': '불명'}


def _score_bar(score) -> str:
    if score is None:
        return '<span style="color:#4a5568">-</span>'
    pct = int(float(score) * 10)
    color = "#68d391" if float(score) >= 7 else "#f6ad55" if float(score) >= 5 else "#fc8181"
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<div style="flex:1;background:#2d3748;border-radius:3px;height:8px;overflow:hidden">'
        f'<div style="width:{pct}%;background:{color};height:100%;border-radius:3px"></div></div>'
        f'<span style="font-size:12px;color:{color};font-weight:700;min-width:28px">{float(score):.1f}</span>'
        f'</div>'
    )


def _compliance_tag(compliance: str) -> str:
    cfg = {
        "yes":     ("tag-compliant", "지침충족"),
        "partial": ("tag-partial",   "부분충족"),
        "no":      ("tag-no",        "미충족"),
        "unclear": ("tag-unclear",   "불명"),
    }
    cls, label = cfg.get(compliance, ("tag-unclear", "불명"))
    return f'<span class="tag {cls}">{label}</span>'


def _hex_to_rgba(hex_color: str, alpha: float = 0.13) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _compliance_bg_color(compliance: str) -> str:
    return {'yes': '#3a7d5e', 'partial': '#7d5e2a', 'no': '#7d3a3a'}.get(compliance, '#3b466b')


def _fmt_num(n: int) -> str:
    return f'{n:02d}'


def _sec_title(num: int, text: str) -> str:
    return (
        f'<div class="sec-title">'
        f'<span class="sec-num">{_fmt_num(num)}</span>'
        f'<span class="sec-title-text">{text}</span>'
        f'</div>'
    )


def _normalize_floor(raw) -> tuple[int, str] | None:
    """Floor label → (sort_order, normalized_label).
    B5(-5) ... B1(-1) ... 1F(1) ... NF(N) ... ROOF(10000)
    Returns None if unparseable.
    """
    if not raw:
        return None
    s = str(raw).upper().strip()
    if any(k in s for k in ['ROOF', '옥상', 'PENTHOUSE']) or re.fullmatch(r'PH\d?', s):
        return (10000, 'ROOF')
    m = re.search(r'B\s*(\d+)|지하\s*(\d+)', s)
    if m:
        n = int(m.group(1) or m.group(2))
        return (-n, f'B{n}')
    m = re.search(r'(\d+)\s*F|(\d+)\s*층|지상\s*(\d+)', s)
    if m:
        n = int(m.group(1) or m.group(2) or m.group(3))
        if 1 <= n <= 200:
            return (n, f'{n}F')
    return None


_PROGRAM_CATEGORY_RULES = [
    # (category, keywords) — first match wins
    ('core',      ['주차', '기계실', '전기실', '코어', '계단실', '방재', '설비',
                   'PIT', 'PARKING', '저수조', '발전기']),
    ('culture',   ['도서관', '전시', '강당', '갤러리', '공연', '스튜디오', '문화',
                   '박물관', '아트', '시네마', '극장', '미디어']),
    ('commerce',  ['상가', '근린생활', '리테일', '카페', '음식점', '판매', '상업',
                   '식당', 'F&B']),
    ('residence', ['주거', '세대', '아파트', '주호', '유닛', '거실', '침실',
                   'UNIT', '펜트하우스']),
    ('office',    ['사무실', '오피스', '업무', '회의실', 'OFFICE', '비즈니스']),
    ('public',    ['관리', '복지', '주민', '공공', '복합', '커뮤니티', '센터',
                   '청사', '민원', '조합', '지원']),
]


def _categorize_program(text: str) -> str:
    if not text or not isinstance(text, str):
        return 'other'
    upper = text.upper()
    for cat, keywords in _PROGRAM_CATEGORY_RULES:
        for kw in keywords:
            if kw.upper() in upper:
                return cat
    return 'other'


def _has_floor_plan_data(submissions: list[dict]) -> bool:
    for s in submissions:
        ed = s.get('extracted_data', {}) if isinstance(s, dict) else {}
        fps = ed.get('floor_plan', []) if isinstance(ed, dict) else []
        if not isinstance(fps, list):
            continue
        for fp in fps:
            if isinstance(fp, dict) and _normalize_floor(fp.get('floor_level', '')):
                return True
    return False


def _render_floor_matrix(submissions: list[dict], section_num: int) -> str:
    by_company: dict[str, dict[str, list[str]]] = {}
    sort_orders: dict[str, int] = {}
    company_order: list[str] = []

    for s in submissions:
        if not isinstance(s, dict):
            continue
        company = s.get('company', '?')
        company_order.append(company)
        ed = s.get('extracted_data', {})
        fps = ed.get('floor_plan', []) if isinstance(ed, dict) else []
        agg: dict[str, list[str]] = {}
        if isinstance(fps, list):
            for fp in fps:
                if not isinstance(fp, dict):
                    continue
                norm = _normalize_floor(fp.get('floor_level', ''))
                if not norm:
                    continue
                order, label = norm
                sort_orders[label] = order
                progs = fp.get('main_programs', [])
                if not isinstance(progs, list):
                    continue
                bucket = agg.setdefault(label, [])
                for p in progs:
                    if isinstance(p, str) and p.strip() and p not in bucket:
                        bucket.append(p.strip())
        by_company[company] = agg

    if not sort_orders:
        return ''

    floor_labels = sorted(sort_orders.keys(), key=lambda l: sort_orders[l])
    palette_map = {s.get('company', f'?{i}'): PALETTE[i % len(PALETTE)]
                   for i, s in enumerate(submissions) if isinstance(s, dict)}

    th_cells = '<th class="mtx-floor-col">층</th>'
    for c in company_order:
        color = palette_map.get(c, '#999')
        th_cells += f'<th style="border-top:3px solid {color}">{c}</th>'

    rows = ''
    for label in floor_labels:
        cells = ''
        for c in company_order:
            progs = by_company.get(c, {}).get(label, [])
            if not progs:
                cells += '<td class="mtx-cell empty">—</td>'
                continue
            cat = _categorize_program(progs[0])
            items = ''.join(f'<div class="mtx-prog-item">{p}</div>' for p in progs)
            cells += f'<td class="mtx-cell mtx-cat-{cat}"><div class="mtx-prog-list">{items}</div></td>'
        rows += f'<tr><td class="mtx-floor">{label}</td>{cells}</tr>'

    legend_items = [
        ('주거',       'residence'),
        ('공공·지원',  'public'),
        ('문화·특화',  'culture'),
        ('상업',       'commerce'),
        ('사무·업무',  'office'),
        ('코어·공용',  'core'),
        ('기타',       'other'),
    ]
    legend_html = ''.join(
        f'<div class="mtx-legend-item">'
        f'<span class="mtx-legend-swatch mtx-cat-{cat}"></span>{label}</div>'
        for label, cat in legend_items
    )

    return (
        f'<div class="sec">'
        f'{_sec_title(section_num, "층별 프로그램 비교")}'
        f'<div class="matrix-wrap">'
        f'<table class="matrix-table">'
        f'<thead><tr>{th_cells}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
        f'<div class="mtx-legend">{legend_html}</div>'
        f'</div>'
    )


_QUANT_FIELDS = [
    # (key, label_kr, sub, unit, fmt)
    ('site_area_sqm',               '대지면적', 'site area',         '㎡', ',.1f'),
    ('building_area_sqm',           '건축면적', 'building area',     '㎡', ',.1f'),
    ('total_floor_area_sqm',        '연면적',   'total floor area',  '㎡', ',.1f'),
    ('building_coverage_ratio_pct', '건폐율',   'BCR',               '%',  '.2f'),
    ('floor_area_ratio_pct',        '용적률',   'FAR',               '%',  '.2f'),
    ('floors_above',                '지상층수', 'floors above',      '층', '.0f'),
    ('floors_below',                '지하층수', 'floors below',      '층', '.0f'),
    ('parking_count',               '주차대수', 'parking',           '대', ',.0f'),
]


def _extract_quant_value(s: dict, field: str):
    if not isinstance(s, dict):
        return None
    ed = s.get('extracted_data', {})
    if not isinstance(ed, dict):
        return None
    q = ed.get('_quantitative', {})
    if not isinstance(q, dict):
        return None
    val = q.get(field)
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _has_quant_data(submissions: list[dict]) -> bool:
    for s in submissions:
        for key, *_ in _QUANT_FIELDS:
            if _extract_quant_value(s, key) is not None:
                return True
    return False


def _calc_recommended(values: list, winners_mask: list[bool], fmt: str) -> str:
    winner_pool = [v for v, w in zip(values, winners_mask) if w and v is not None]
    pool = winner_pool if winner_pool else [v for v in values if v is not None]
    if not pool:
        return '—'
    lo, hi = min(pool), max(pool)
    if abs(lo - hi) < 1e-6:
        return f'{lo:{fmt}}'
    return f'{lo:{fmt}} ~ {hi:{fmt}}'


def _render_quant_table(submissions: list[dict], section_num: int) -> str:
    valid_subs = [s for s in submissions if isinstance(s, dict)]
    if not valid_subs:
        return ''
    companies = [s.get('company', '?') for s in valid_subs]
    winners_mask = [s.get('result') in ('win', 'contracted') for s in valid_subs]
    palette_map = {s.get('company', f'?{i}'): PALETTE[i % len(PALETTE)]
                   for i, s in enumerate(valid_subs)}

    th_cells = '<th class="qt-label-col">항목</th>'
    for c, w in zip(companies, winners_mask):
        color = palette_map.get(c, '#999')
        winner_mark = ' ★' if w else ''
        th_cells += f'<th style="border-top:3px solid {color}">{c}{winner_mark}</th>'
    th_cells += '<th class="qt-rec">권장 범위</th>'

    rows = ''
    for key, label, sub, unit, fmt in _QUANT_FIELDS:
        values = [_extract_quant_value(s, key) for s in valid_subs]
        if all(v is None for v in values):
            continue
        cells = ''
        for v, w in zip(values, winners_mask):
            if v is None:
                cells += '<td class="qt-val qt-empty">—</td>'
            else:
                cls = 'qt-val qt-winner' if w else 'qt-val'
                cells += (f'<td class="{cls}">{v:{fmt}}'
                          f'<span class="qt-unit">{unit}</span></td>')
        rec = _calc_recommended(values, winners_mask, fmt)
        rec_html = (f'{rec}<span class="qt-unit">{unit}</span>'
                    if rec != '—' else '—')
        rows += (f'<tr><td class="qt-label">{label}'
                 f'<span class="qt-label-sub">{sub}</span></td>'
                 f'{cells}<td class="qt-rec">{rec_html}</td></tr>')

    if not rows:
        return ''

    return (
        f'<div class="sec">'
        f'{_sec_title(section_num, "정량 데이터 비교")}'
        f'<div style="overflow-x:auto"><table class="qt-table">'
        f'<thead><tr>{th_cells}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
        f'<div class="qt-footnote">'
        f'※ 권장 범위는 당선작 기준 최소~최대값입니다. 당선작이 없는 경우 전체 출품작 기준.'
        f'</div></div>'
    )


def _insight_box(title: str, items: list[str]) -> str:
    if not items:
        return ''
    li = ''.join(f'<li class="insight-item">{x}</li>' for x in items if x)
    return (
        f'<div class="insight-box">'
        f'<div class="insight-title">{title}</div>'
        f'<ul class="insight-list">{li}</ul>'
        f'</div>'
    )


_CSS = """
<style>
:root {
  /* surfaces */
  --bg-base:        #1a2138;
  --bg-elevated:    #222b46;
  --bg-card:        #171d33;
  --bg-deep:        #0e1428;
  /* borders */
  --border-subtle:  #2c3656;
  --border-strong:  #3b466b;
  /* text */
  --text-primary:   #f5f7fb;
  --text-secondary: #cbd5e0;
  --text-muted:     #a0aec0;
  --text-faint:     #718096;
  --text-fade:      #4a5568;
  /* accents */
  --accent-blue:    #90cdf4;
  --accent-gold:    #d4af37;
  --accent-gold-soft: rgba(212,175,55,0.12);
  --accent-mint:    #68d391;
  --accent-coral:   #fc8181;
  /* tag palette (softer) */
  --tag-strength:   #76d7a3; --tag-strength-bg: rgba(118,215,163,0.13);
  --tag-weakness:   #f4a4a4; --tag-weakness-bg: rgba(244,164,164,0.13);
  --tag-partial:    #f6c87a; --tag-partial-bg:  rgba(246,200,122,0.13);
  --tag-unclear:    #a0aec0; --tag-unclear-bg:  rgba(160,174,192,0.10);
  /* matrix categories — used as cell backgrounds (light pastels) in chunk 3-4 */
  --cat-residence:  #f5d6c0;
  --cat-public:     #f5c0d0;
  --cat-culture:    #d8c5e8;
  --cat-commerce:   #fff2c0;
  --cat-office:     #c5e0d8;
  --cat-core:       #d0d8e0;
  --cat-other:      #e0e0e8;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Pretendard', 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
  background: var(--bg-base); color: var(--text-secondary);
  padding: 24px; font-size: 14px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
.page-wrap { max-width: 1400px; margin: 0 auto; }

/* Header */
.hdr {
  background: var(--bg-elevated); border-radius: 8px;
  padding: 28px 32px; margin-bottom: 18px;
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--accent-gold);
}
.hdr-badges {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; flex-wrap: wrap;
}
.hdr-badge {
  font-size: 10px; font-weight: 700; padding: 4px 10px;
  border-radius: 3px; letter-spacing: 0.1em;
  text-transform: uppercase;
}
.hdr-badge-primary {
  background: var(--accent-gold-soft); color: var(--accent-gold);
  border: 1px solid rgba(212,175,55,0.3);
}
.hdr-badge-facility {
  background: rgba(144,205,244,0.10); color: var(--accent-blue);
  border: 1px solid rgba(144,205,244,0.25);
}
.hdr-title {
  font-size: 26px; font-weight: 800; color: var(--text-primary);
  margin-bottom: 14px; letter-spacing: -0.015em; line-height: 1.3;
}
.hdr-meta { display: flex; gap: 28px; flex-wrap: wrap; }
.hdr-meta span { color: var(--text-muted); font-size: 13px; }
.hdr-meta strong { color: var(--text-primary); font-weight: 600; }
.hdr-meta-divider {
  display: inline-block; width: 1px; height: 12px;
  background: var(--border-strong); margin: 0 4px;
  vertical-align: middle;
}

/* Sections */
.sec {
  background: var(--bg-elevated); border-radius: 8px;
  padding: 24px 28px; margin-bottom: 16px;
  border: 1px solid var(--border-subtle);
}
.sec-title {
  display: flex; align-items: center; gap: 12px;
  font-size: 14px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 18px; padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
  letter-spacing: 0.04em;
}
.sec-num {
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--bg-deep);
  border: 1px solid var(--border-strong);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 800; color: var(--accent-gold);
  letter-spacing: 0;
  flex-shrink: 0;
}
.sec-title-text { flex: 1; }
/* Dashboard num indicator */
.db-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--bg-deep);
  border: 1px solid var(--border-strong);
  font-size: 11px; font-weight: 800; color: var(--accent-gold);
  letter-spacing: 0; margin-right: 12px;
  vertical-align: middle;
}
/* Insight box (key findings under matrices/tables) */
.insight-box {
  background: rgba(212,175,55,0.06);
  border: 1px solid rgba(212,175,55,0.18);
  border-left: 3px solid var(--accent-gold);
  border-radius: 4px;
  padding: 14px 18px; margin-top: 16px;
}
.insight-title {
  font-size: 11px; font-weight: 700; color: var(--accent-gold);
  letter-spacing: 0.1em; text-transform: uppercase;
  margin-bottom: 10px;
}
.insight-list { margin: 0; padding-left: 18px; list-style: none; }
.insight-item {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 6px; line-height: 1.7;
  position: relative;
}
.insight-item::before {
  content: '▸'; color: var(--accent-gold);
  position: absolute; left: -16px; font-size: 10px; top: 4px;
}
.insight-item:last-child { margin-bottom: 0; }

/* ── Floor program matrix ── */
.matrix-wrap { overflow-x: auto; margin-top: 4px; }
.matrix-table {
  width: 100%; border-collapse: collapse; min-width: 700px;
}
.matrix-table thead th {
  background: var(--bg-deep); color: var(--text-muted);
  font-weight: 700; letter-spacing: 0.05em;
  border-bottom: 2px solid var(--border-strong);
  font-size: 11px; padding: 10px 12px;
  text-align: left; white-space: nowrap;
}
.matrix-table thead .mtx-floor-col {
  width: 56px; min-width: 56px; text-align: center;
}
.matrix-table tbody td {
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
  padding: 7px 10px;
  font-size: 11px; line-height: 1.55;
}
.matrix-table tbody .mtx-floor {
  font-weight: 700; color: var(--text-secondary);
  background: var(--bg-deep);
  text-align: center; padding: 8px 6px;
  font-size: 12px; min-width: 50px;
  border-right: 1px solid var(--border-strong);
}
.mtx-cell { color: #2d3748; }
.mtx-cell.empty {
  background: transparent; color: var(--text-fade);
  text-align: center; font-style: normal;
}
.mtx-cat-residence { background: var(--cat-residence); }
.mtx-cat-public    { background: var(--cat-public); }
.mtx-cat-culture   { background: var(--cat-culture); }
.mtx-cat-commerce  { background: var(--cat-commerce); }
.mtx-cat-office    { background: var(--cat-office); }
.mtx-cat-core      { background: var(--cat-core); }
.mtx-cat-other     { background: var(--cat-other); }
.mtx-prog-list { display: flex; flex-direction: column; gap: 2px; }
.mtx-prog-item { font-size: 11px; }

/* Legend */
.mtx-legend {
  display: flex; gap: 16px; flex-wrap: wrap; margin-top: 14px;
  padding: 10px 14px; background: var(--bg-deep); border-radius: 4px;
  border: 1px solid var(--border-subtle);
}
.mtx-legend-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--text-muted);
}
.mtx-legend-swatch { width: 14px; height: 14px; border-radius: 2px; }

/* ── Quantitative comparison table ── */
.qt-table { width: 100%; border-collapse: collapse; min-width: 700px; }
.qt-table th, .qt-table td {
  padding: 11px 14px; font-size: 12px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: right; vertical-align: middle;
}
.qt-table thead th {
  background: var(--bg-deep); color: var(--text-muted);
  font-weight: 700; font-size: 10px;
  letter-spacing: 0.08em; text-transform: uppercase;
  border-bottom: 2px solid var(--border-strong);
  white-space: nowrap;
}
.qt-table thead .qt-label-col {
  text-align: left; min-width: 160px;
}
.qt-table .qt-label {
  text-align: left; font-weight: 600;
  color: var(--text-primary); background: var(--bg-deep);
  border-right: 1px solid var(--border-subtle);
}
.qt-table .qt-label-sub {
  font-size: 10px; color: var(--text-faint); display: block;
  margin-top: 2px; font-weight: 400; letter-spacing: 0;
}
.qt-table .qt-val { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.qt-table .qt-val.qt-winner { color: var(--accent-gold); font-weight: 700; }
.qt-table .qt-empty { color: var(--text-fade); }
.qt-table .qt-unit { color: var(--text-faint); font-weight: 400; font-size: 10px; margin-left: 2px; }
.qt-table thead .qt-rec, .qt-table tbody .qt-rec {
  background: var(--accent-gold-soft);
  color: var(--accent-gold); font-weight: 700;
  border-left: 1px solid rgba(212,175,55,0.3);
}
.qt-table tbody tr:hover td { background: rgba(144,205,244,0.03); }
.qt-table tbody tr:hover .qt-rec { background: rgba(212,175,55,0.18); }
.qt-footnote {
  font-size: 11px; color: var(--text-faint); margin-top: 10px;
  letter-spacing: 0.02em;
}

/* Submission cards */
.sub-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.sub-card {
  flex: 1; min-width: 170px;
  background: var(--bg-card); border-radius: 6px;
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-top: 3px solid var(--border-strong);
  position: relative;
}
.sub-card.winner {
  border-top-color: var(--accent-gold);
  background: linear-gradient(180deg, var(--accent-gold-soft) 0%, var(--bg-card) 60%);
  box-shadow: 0 0 0 1px rgba(212,175,55,0.2) inset;
}
.sub-card-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px;
}
.sub-color-dot {
  width: 10px; height: 10px; border-radius: 50%;
  flex-shrink: 0;
}
.sub-card-letter {
  font-size: 12px; font-weight: 800; color: var(--text-muted);
  letter-spacing: 0.08em; text-transform: uppercase;
  flex: 1;
}
.badge-win, .badge-contracted, .badge-lose {
  font-size: 10px; padding: 2px 8px; border-radius: 3px;
  font-weight: 700; display: inline-block;
  letter-spacing: 0.08em;
}
.badge-win {
  background: var(--accent-gold-soft); color: var(--accent-gold);
  border: 1px solid rgba(212,175,55,0.3);
}
.badge-contracted {
  background: rgba(104,211,145,0.13); color: var(--accent-mint);
  border: 1px solid rgba(104,211,145,0.3);
}
.badge-lose {
  background: rgba(160,174,192,0.10); color: var(--text-muted);
  border: 1px solid rgba(160,174,192,0.2);
}
.sub-company { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.sub-pages { font-size: 11px; color: var(--text-faint); letter-spacing: 0.05em; }
.sub-pages strong { color: var(--text-secondary); font-weight: 600; }

/* Comparison table */
.cmp-table { width: 100%; border-collapse: separate; border-spacing: 0; }
.cmp-table th {
  background: var(--bg-deep); padding: 12px 14px; text-align: left;
  font-size: 11px; color: var(--text-muted); font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase;
  border-bottom: 1px solid var(--border-strong);
}
.cmp-table td {
  padding: 12px 14px; border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
}
.cmp-table tr:hover td { background: rgba(144,205,244,0.04); }
.ax-label { font-weight: 700; color: var(--text-primary); font-size: 13px; }

/* Tags */
.tag {
  display: inline-block; font-size: 11px; padding: 2px 8px;
  border-radius: 3px; margin: 1px 2px 1px 0; font-weight: 500;
}
.tag-strength  { background: var(--tag-strength-bg); color: var(--tag-strength); }
.tag-weakness  { background: var(--tag-weakness-bg); color: var(--tag-weakness); }
.tag-compliant { background: var(--tag-strength-bg); color: var(--tag-strength); }
.tag-partial   { background: var(--tag-partial-bg);  color: var(--tag-partial); }
.tag-no        { background: var(--tag-weakness-bg); color: var(--tag-weakness); }
.tag-unclear   { background: var(--tag-unclear-bg);  color: var(--tag-unclear); }
.notes { font-size: 11px; color: var(--text-faint); margin-top: 6px; line-height: 1.6; }

/* Ranking */
.rank-list { display: flex; gap: 10px; flex-wrap: wrap; }
.rank-item {
  background: var(--bg-card); border-radius: 6px;
  padding: 12px 18px; display: flex; align-items: center; gap: 12px;
  border: 1px solid var(--border-subtle);
}
.rank-no { font-size: 24px; font-weight: 900; color: var(--border-strong); }
.rank-no.r1 { color: var(--accent-gold); }
.rank-no.r2 { color: var(--text-muted); }
.rank-no.r3 { color: #c5713a; }
.rank-co { font-size: 14px; font-weight: 600; color: var(--text-primary); }

/* Differentiator / win-loss */
.diff-list { display: flex; flex-direction: column; gap: 8px; }
.diff-item {
  background: var(--bg-card); border-radius: 4px;
  padding: 12px 16px; font-size: 13px; color: var(--text-secondary);
  border-left: 3px solid var(--accent-blue);
}
.diff-win  { border-left-color: var(--accent-mint); }
.diff-lose { border-left-color: var(--accent-coral); }

/* Winner highlight */
.winner-box {
  background: var(--accent-gold-soft);
  border: 1px solid rgba(212,175,55,0.25);
  border-radius: 6px; padding: 18px 20px; margin-bottom: 12px;
}
.winner-box-title {
  font-size: 14px; font-weight: 700; color: var(--accent-gold);
  margin-bottom: 14px; letter-spacing: 0.05em;
}
.w-axis { margin-bottom: 14px; }
.w-axis-label { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 5px; }

/* ── Dashboard / accordion section ── */
.db-wrap {
  background: var(--bg-elevated) !important;
  border-color: var(--border-subtle);
}
.db-sub-label {
  font-size: 10px; color: var(--text-faint);
  letter-spacing: 0.18em; margin-bottom: 6px; font-weight: 600;
  text-transform: uppercase;
}
.db-title {
  font-size: 22px; font-weight: 800;
  letter-spacing: -0.015em; color: var(--text-primary);
}
.db-count { font-size: 12px; color: var(--text-faint); margin-top: 8px; margin-bottom: 22px; }

.db-rank-block {
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: 6px; padding: 18px 20px; margin-bottom: 18px;
}
.db-rank-label {
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  letter-spacing: 0.12em; margin-bottom: 12px; text-transform: uppercase;
}
.db-rank-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.db-rank-card { border-radius: 5px; padding: 10px 16px; min-width: 140px; }
.db-rank-medal { font-size: 20px; margin-bottom: 4px; }
.db-rank-name { font-size: 14px; font-weight: 700; }
.db-rank-meta { font-size: 11px; color: var(--text-faint); margin-top: 3px; }

.db-keydiff {
  background: var(--accent-gold-soft);
  border: 1px solid rgba(212,175,55,0.25);
  border-radius: 4px; padding: 12px 16px; margin-bottom: 18px;
  font-size: 13px; color: var(--accent-gold);
}

.db-filter-bar {
  display: flex; gap: 8px; margin-bottom: 22px;
  flex-wrap: wrap; align-items: center;
}
.db-filter-label {
  font-size: 10px; color: var(--text-faint);
  margin-right: 4px; letter-spacing: 0.12em; font-weight: 600;
}
.db-filter-btn {
  border-radius: 3px; font-size: 12px; font-weight: 600; cursor: pointer;
  padding: 5px 14px; transition: all 0.15s; font-family: inherit;
}
.db-expand-all {
  background: transparent; border: 1px solid var(--border-strong);
  color: var(--text-muted); padding: 5px 14px; border-radius: 3px;
  font-size: 12px; cursor: pointer; margin-left: auto; font-family: inherit;
  transition: all 0.15s;
}
.db-expand-all:hover { color: var(--text-primary); border-color: var(--text-muted); }

.db-axis-row {
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: 5px; margin-bottom: 10px; overflow: hidden;
  transition: border-color 0.2s;
}
.db-axis-header {
  width: 100%; background: none; border: none;
  color: var(--text-secondary);
  padding: 14px 20px; display: flex; align-items: center; gap: 14px;
  cursor: pointer; font-size: 14px; font-family: inherit; text-align: left;
  transition: background 0.15s;
}
.db-axis-header:hover { background: rgba(144,205,244,0.04); }
.db-axis-icon { font-size: 16px; opacity: 0.7; color: var(--accent-gold); }
.db-axis-name { font-weight: 600; letter-spacing: 0.02em; color: var(--text-primary); }
.db-chevron { margin-left: auto; opacity: 0.5; font-size: 11px; transition: transform 0.2s; }
.db-axis-content { padding: 0 20px 20px; }
.db-cards-grid { display: grid; gap: 10px; }
.db-axis-card {
  background: var(--bg-deep); border-radius: 4px; padding: 16px; min-width: 0;
  border: 1px solid var(--border-subtle);
}
.db-card-company {
  font-size: 11px; font-weight: 700; margin-bottom: 8px;
  letter-spacing: 0.05em;
}
.db-card-score {
  font-size: 22px; font-weight: 800; color: var(--accent-gold);
  margin-bottom: 6px;
}
.db-card-score-unit { font-size: 11px; color: var(--text-faint); font-weight: 400; }
.db-card-notes {
  font-size: 12px; color: var(--text-secondary);
  line-height: 1.65; margin-bottom: 10px;
}
.db-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.db-card-tag {
  font-size: 10px; padding: 2px 8px; border-radius: 3px;
  font-weight: 500;
}
.db-card-strength { font-size: 11px; margin-bottom: 4px; color: var(--text-muted); }
.db-card-weakness { font-size: 11px; color: var(--text-muted); }
.db-compliance-badge {
  font-size: 10px; padding: 3px 9px; border-radius: 3px;
  color: #fff; font-weight: 600; display: inline-block; margin-top: 8px;
  letter-spacing: 0.05em;
}

.footer {
  text-align: center; color: var(--text-fade); font-size: 11px;
  margin-top: 30px; padding: 16px;
  letter-spacing: 0.05em;
}

/* ── Print / PPT export mode ── */
@media print {
  @page {
    size: A4 landscape;
    margin: 10mm 12mm;
  }
  /* Preserve dark theme + accent colors when printed (presentation use) */
  *, *::before, *::after {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }
  body { padding: 0; font-size: 11px; }
  .page-wrap { max-width: none; padding: 0; }

  /* Page-break control — keep sections intact */
  .hdr { page-break-after: avoid; margin-bottom: 10px; }
  .sec { page-break-inside: avoid; margin-bottom: 10px; padding: 16px 18px; }
  .db-axis-row { page-break-inside: avoid; margin-bottom: 8px; }
  .winner-box { page-break-inside: avoid; }
  .matrix-table tr, .qt-table tr, .cmp-table tr { page-break-inside: avoid; }
  .matrix-table thead, .qt-table thead, .cmp-table thead { display: table-header-group; }

  /* Force-expand all accordions and hide interactive UI */
  .db-axis-content { display: block !important; }
  .db-chevron { display: none !important; }
  .db-filter-bar { display: none !important; }
  .db-expand-all { display: none !important; }
  .db-axis-header { cursor: default; padding: 12px 16px; }
  .db-axis-header:hover { background: none; }

  /* Disable hover effects */
  .cmp-table tr:hover td,
  .qt-table tbody tr:hover td,
  .qt-table tbody tr:hover .qt-rec { background: inherit; }

  /* Slightly reduce display fonts for print */
  .hdr-title { font-size: 22px; margin-bottom: 10px; }
  .db-title { font-size: 18px; }
  .sec-title { font-size: 13px; margin-bottom: 14px; }
  .db-card-score { font-size: 18px; }
  .footer { margin-top: 12px; padding: 8px; }
}
</style>
"""


def _generate_dashboard_section(
    comp_subs: dict,
    ranking: list,
    key_diff: list,
    winners: list,
    submissions: list,
    axes: list,
    section_num: int = 1,
) -> str:
    companies = list(comp_subs.keys())
    n = len(companies)
    colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(companies)}
    meta_map = {s['company']: s for s in submissions}
    medals = ['🥇', '🥈', '🥉']

    # Ranking block
    rank_html = ''
    for i, company in enumerate(ranking):
        color = colors.get(company, '#aaa')
        meta = meta_map.get(company, {})
        result_txt = {'win': '✓ 당선', 'contracted': '수의계약'}.get(meta.get('result', ''), '낙선')
        rank_html += (
            f'<div class="db-rank-card" style="background:{_hex_to_rgba(color, 0.08)};border:1px solid {color}">'
            f'<div class="db-rank-medal">{medals[i] if i < 3 else str(i + 1) + "."}</div>'
            f'<div class="db-rank-name" style="color:{color}">{company}</div>'
            f'<div class="db-rank-meta">{result_txt} · {meta.get("total_pages", 0)}p</div>'
            f'</div>'
        )
    rank_section = (
        f'<div class="db-rank-block"><div class="db-rank-label">종합 순위</div>'
        f'<div class="db-rank-cards">{rank_html}</div></div>'
    ) if ranking else ''

    keydiff_section = (
        f'<div class="db-keydiff"><strong style="color:#fc8181">핵심 차별화 요소: </strong>'
        f'{" · ".join(key_diff)}</div>'
    ) if key_diff else ''

    # Filter bar
    filter_btns = '<span class="db-filter-label">FILTER</span>'
    for company in companies:
        color = colors[company]
        co_esc = company.replace("'", "\\'")
        filter_btns += (
            f'<button class="db-filter-btn" data-company="{company}" data-color="{color}"'
            f' onclick="dbToggleCompany(\'{co_esc}\')"'
            f' style="background:{_hex_to_rgba(color, 0.13)};border:1px solid {color};color:{color}">'
            f'{company}</button>'
        )
    filter_btns += (
        '<button class="db-expand-all" id="db-expand-all-btn" onclick="dbToggleAll()">모두 펼치기</button>'
    )
    filter_section = f'<div class="db-filter-bar">{filter_btns}</div>'

    # Axis accordion rows
    axis_rows = ''
    for axis in axes:
        label, icon = AXIS_LABEL_DASH.get(axis, (axis, '•'))
        is_exp = (axis == 'business_viability')
        content_style = '' if is_exp else 'display:none'
        chevron_style = 'transform:rotate(180deg)' if is_exp else ''
        border_col = 'rgba(255,255,255,0.2)' if is_exp else 'rgba(255,255,255,0.08)'

        cards_html = ''
        for company in companies:
            color = colors[company]
            d = comp_subs.get(company, {}).get(axis, {})
            if not d:
                cards_html += (
                    f'<div class="db-axis-card" data-company="{company}" style="border-top:3px solid {color}">'
                    f'<div class="db-card-company" style="color:{color}">{company}</div>'
                    f'<div style="color:#444;font-size:12px">데이터 없음</div></div>'
                )
                continue

            score = d.get('score')
            notes = d.get('notes', '')
            strengths = d.get('strengths', [])
            weaknesses = d.get('weaknesses', [])
            compliance = d.get('brief_compliance', '')

            score_html = (
                f'<div class="db-card-score">{float(score):.1f}'
                f'<span class="db-card-score-unit"> /10</span></div>'
            ) if score is not None else ''

            notes_html = f'<div class="db-card-notes">{notes}</div>' if notes else ''

            all_kws = [f'▲ {s}' for s in strengths[:3]] + [f'▼ {w}' for w in weaknesses[:3]]
            tags_html = ''.join(
                f'<span class="db-card-tag" style="background:{_hex_to_rgba(color, 0.13)};color:{color}">{kw}</span>'
                for kw in all_kws
            )

            str_html = (
                f'<div class="db-card-strength"><span style="color:#4CAF50;font-weight:600">▲ 강점 </span>'
                f'<span style="color:#999">{" · ".join(strengths)}</span></div>'
            ) if strengths else ''

            weak_html = (
                f'<div class="db-card-weakness"><span style="color:#FF7043;font-weight:600">▼ 약점 </span>'
                f'<span style="color:#999">{" · ".join(weaknesses)}</span></div>'
            ) if weaknesses else ''

            comp_label = COMP_LABEL_MAP.get(compliance, '')
            comp_badge = (
                f'<span class="db-compliance-badge" style="background:{_compliance_bg_color(compliance)}">'
                f'{comp_label}</span>'
            ) if comp_label else ''

            cards_html += (
                f'<div class="db-axis-card" data-company="{company}" style="border-top:3px solid {color}">'
                f'<div class="db-card-company" style="color:{color}">{company}</div>'
                f'{score_html}{notes_html}'
                f'<div class="db-card-tags">{tags_html}</div>'
                f'{str_html}{weak_html}{comp_badge}'
                f'</div>'
            )

        axis_rows += (
            f'<div class="db-axis-row" id="db-row-{axis}" style="border-color:{border_col}">'
            f'<button class="db-axis-header" onclick="dbToggleAxis(\'{axis}\')">'
            f'<span class="db-axis-icon">{icon}</span>'
            f'<span class="db-axis-name">{label}</span>'
            f'<span class="db-chevron" id="db-chevron-{axis}" style="{chevron_style}">▼</span>'
            f'</button>'
            f'<div class="db-axis-content" id="db-content-{axis}" style="{content_style}">'
            f'<div class="db-cards-grid" id="db-grid-{axis}" style="grid-template-columns:repeat({n},1fr)">'
            f'{cards_html}</div></div></div>'
        )

    return (
        f'<div class="sec db-wrap">'
        f'<div class="db-sub-label">COMPETITION ANALYSIS · 비교 분석 대시보드</div>'
        f'<div class="db-title"><span class="db-num">{_fmt_num(section_num)}</span>경쟁사 제안서 비교 분석</div>'
        f'<div class="db-count">{n}개 출품사 · {len(axes)}개 분석 카테고리</div>'
        f'{rank_section}{keydiff_section}{filter_section}{axis_rows}'
        f'</div>'
    )


def _dashboard_js(axes: list) -> str:
    axes_json = json.dumps(axes)
    return f"""<script>
(function() {{
  var allAxes = {axes_json};
  var selectedCompanies = [];
  var expandedAxes = ['business_viability'];

  function hexToRgba(hex, a) {{
    var r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
    return 'rgba('+r+','+g+','+b+','+a+')';
  }}

  function applyFilter() {{
    document.querySelectorAll('.db-cards-grid').forEach(function(grid) {{
      var visible = 0;
      grid.querySelectorAll('.db-axis-card').forEach(function(card) {{
        var co = card.getAttribute('data-company');
        var show = selectedCompanies.length === 0 || selectedCompanies.indexOf(co) !== -1;
        card.style.display = show ? '' : 'none';
        if (show) visible++;
      }});
      grid.style.gridTemplateColumns = 'repeat('+Math.max(visible,1)+', 1fr)';
    }});
    document.querySelectorAll('.db-filter-btn').forEach(function(btn) {{
      var co = btn.getAttribute('data-company');
      var color = btn.getAttribute('data-color');
      var active = selectedCompanies.length === 0 || selectedCompanies.indexOf(co) !== -1;
      btn.style.background = active ? hexToRgba(color, 0.13) : 'transparent';
      btn.style.borderColor = active ? color : 'rgba(255,255,255,0.1)';
      btn.style.color = active ? color : '#555';
    }});
  }}

  window.dbToggleCompany = function(co) {{
    var idx = selectedCompanies.indexOf(co);
    if (idx === -1) selectedCompanies.push(co); else selectedCompanies.splice(idx, 1);
    applyFilter();
  }};

  window.dbToggleAxis = function(axisId) {{
    var content = document.getElementById('db-content-'+axisId);
    var chevron = document.getElementById('db-chevron-'+axisId);
    var row = document.getElementById('db-row-'+axisId);
    var idx = expandedAxes.indexOf(axisId);
    if (idx !== -1) {{
      expandedAxes.splice(idx, 1);
      content.style.display = 'none';
      chevron.style.transform = 'rotate(0deg)';
      row.style.borderColor = 'rgba(255,255,255,0.08)';
    }} else {{
      expandedAxes.push(axisId);
      content.style.display = '';
      chevron.style.transform = 'rotate(180deg)';
      row.style.borderColor = 'rgba(255,255,255,0.2)';
    }}
    updateExpandBtn();
  }};

  window.dbToggleAll = function() {{
    expandedAxes = (expandedAxes.length === allAxes.length) ? [] : allAxes.slice();
    allAxes.forEach(function(axisId) {{
      var content = document.getElementById('db-content-'+axisId);
      var chevron = document.getElementById('db-chevron-'+axisId);
      var row = document.getElementById('db-row-'+axisId);
      var exp = expandedAxes.indexOf(axisId) !== -1;
      if (content) content.style.display = exp ? '' : 'none';
      if (chevron) chevron.style.transform = exp ? 'rotate(180deg)' : 'rotate(0deg)';
      if (row) row.style.borderColor = exp ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.08)';
    }});
    updateExpandBtn();
  }};

  function updateExpandBtn() {{
    var btn = document.getElementById('db-expand-all-btn');
    if (btn) btn.textContent = (expandedAxes.length === allAxes.length) ? '모두 접기' : '모두 펼치기';
  }}
}}());
</script>"""


def generate_comparison_report(
    meta: dict,
    submissions: list[dict],
    comparison: dict,
) -> str:
    comp_name      = meta.get("competition_name", "")
    facility_type  = meta.get("facility_type", "")
    project_number = meta.get("project_number", "")
    year           = meta.get("year", "")  # legacy fallback for older projects
    client         = meta.get("client", "")
    location       = meta.get("location", "")
    facility_label = FACILITY_TYPES.get(facility_type, facility_type)
    project_label  = project_number or (f"{year}년" if year else "")

    comp_subs        = comparison.get("submissions", {})
    ranking          = comparison.get("ranking", [])
    key_diff         = comparison.get("key_differentiators", [])
    winner_strengths = comparison.get("winner_strengths", [])
    loser_weaknesses = comparison.get("loser_weaknesses", [])
    winners          = [s["company"] for s in submissions if s.get("result") in ("win", "contracted")]

    company_list   = list(comp_subs.keys())
    axes_with_data = [ax for ax in AXES if any(ax in comp_subs.get(c, {}) for c in company_list)]

    # Section counter — used to number each main section
    sec_counter = [0]
    def _next_n() -> int:
        sec_counter[0] += 1
        return sec_counter[0]

    # ── 헤더 ──────────────────────────────────────────────
    header = f"""
    <div class="hdr">
      <div class="hdr-badges">
        <span class="hdr-badge hdr-badge-primary">당선작 분석 리포트</span>
        <span class="hdr-badge hdr-badge-facility">{facility_label}</span>
      </div>
      <div class="hdr-title">{comp_name}</div>
      <div class="hdr-meta">
        {f'<span>프로젝트번호 <strong>{project_label}</strong></span>' if project_label else ''}
        <span>발주처 <strong>{client}</strong></span>
        <span>위치 <strong>{location}</strong></span>
        <span>참여 제안서 <strong>{len(submissions)}개</strong></span>
      </div>
    </div>"""

    # ── 아코디언 대시보드 ─────────────────────────────────
    dashboard_section = _generate_dashboard_section(
        comp_subs=comp_subs,
        ranking=ranking,
        key_diff=key_diff,
        winners=winners,
        submissions=submissions,
        axes=axes_with_data,
        section_num=_next_n(),
    )

    # ── 참여 제안서 카드 ──────────────────────────────────
    cards = ""
    for i, s in enumerate(submissions):
        company = s["company"]
        result  = s.get("result", "")
        pages   = s.get("total_pages", 0)
        color   = PALETTE[i % len(PALETTE)]
        letter  = chr(ord('A') + i) if i < 26 else f'#{i+1}'
        if result == "win":
            badge = '<span class="badge-win">★ 당선</span>'
        elif result == "contracted":
            badge = '<span class="badge-contracted">◆ 수의계약</span>'
        else:
            badge = '<span class="badge-lose">낙선</span>'
        wcls = " winner" if result in ("win", "contracted") else ""
        cards += (
            f'<div class="sub-card{wcls}" style="border-top-color:{color}">'
            f'<div class="sub-card-head">'
            f'<span class="sub-color-dot" style="background:{color}"></span>'
            f'<span class="sub-card-letter">{letter}안</span>'
            f'{badge}'
            f'</div>'
            f'<div class="sub-company">{company}</div>'
            f'<div class="sub-pages"><strong>{pages}</strong> 페이지</div>'
            f'</div>'
        )

    sub_section = f'<div class="sec">{_sec_title(_next_n(), "참여 제안서")}<div class="sub-cards">{cards}</div></div>'

    # ── 비교 테이블 ───────────────────────────────────────
    th_cols = "".join(
        f'<th style="{"background:#2d3748;color:#f6d860;" if c in winners else ""}min-width:200px">{c}{"  ★" if c in winners else ""}</th>'
        for c in company_list
    )

    rows = ""
    for axis in AXES:
        label = AXIS_LABELS_KO.get(axis, axis)
        cells = ""
        for company in company_list:
            ax         = comp_subs.get(company, {}).get(axis, {})
            score      = ax.get("score")
            strengths  = ax.get("strengths", [])
            weaknesses = ax.get("weaknesses", [])
            compliance = ax.get("brief_compliance", "unclear")
            notes      = ax.get("notes", "")

            s_tags  = "".join(f'<span class="tag tag-strength">{t}</span>' for t in strengths)
            w_tags  = "".join(f'<span class="tag tag-weakness">{t}</span>' for t in weaknesses)
            cell_bg = "rgba(246,216,96,0.03)" if company in winners else ""
            cells  += (
                f'<td style="background:{cell_bg}">'
                f'{_score_bar(score)}'
                f'<div style="margin-top:6px">{_compliance_tag(compliance)}</div>'
                f'<div style="margin-top:5px">{s_tags}</div>'
                f'<div style="margin-top:3px">{w_tags}</div>'
                + (f'<div class="notes">{notes}</div>' if notes else "")
                + "</td>"
            )

        rows += f'<tr><td style="min-width:90px;background:#0d1117"><div class="ax-label">{label}</div></td>{cells}</tr>'

    table_section = f"""
    <div class="sec">
      {_sec_title(_next_n(), "설계 축별 비교 분석")}
      <div style="overflow-x:auto">
        <table class="cmp-table">
          <thead><tr><th style="min-width:90px">분석 축</th>{th_cols}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>"""

    # ── 층별 프로그램 매트릭스 (data dependent) ──────────
    floor_matrix_section = (
        _render_floor_matrix(submissions, _next_n())
        if _has_floor_plan_data(submissions) else ""
    )

    # ── 정량 데이터 비교표 (data dependent) ──────────────
    quant_table_section = (
        _render_quant_table(submissions, _next_n())
        if _has_quant_data(submissions) else ""
    )

    # ── 종합 순위 ─────────────────────────────────────────
    rank_cls   = {0: "r1", 1: "r2", 2: "r3"}
    rank_items = "".join(
        f'<div class="rank-item"><span class="rank-no {rank_cls.get(i, "")}">{i+1}</span>'
        f'<span class="rank-co">{c}{"  ★" if c in winners else ""}</span></div>'
        for i, c in enumerate(ranking)
    )
    ranking_section = (
        f'<div class="sec">{_sec_title(_next_n(), "종합 순위")}<div class="rank-list">{rank_items}</div></div>'
        if ranking else ""
    )

    # ── 주요 차별화 요소 ──────────────────────────────────
    diff_items  = "".join(f'<div class="diff-item">{d}</div>' for d in key_diff)
    diff_section = (
        f'<div class="sec">{_sec_title(_next_n(), "주요 차별화 요소")}<div class="diff-list">{diff_items}</div></div>'
        if key_diff else ""
    )

    # ── 당선/낙선 요약 ────────────────────────────────────
    ws_items   = "".join(f'<div class="diff-item diff-win">{w}</div>' for w in winner_strengths)
    lw_items   = "".join(f'<div class="diff-item diff-lose">{w}</div>' for w in loser_weaknesses)
    ws_section = (
        f'<div class="sec">{_sec_title(_next_n(), "당선작 우월 요인")}<div class="diff-list">{ws_items}</div></div>'
        if ws_items else ""
    )
    lw_section = (
        f'<div class="sec">{_sec_title(_next_n(), "낙선작 공통 약점")}<div class="diff-list">{lw_items}</div></div>'
        if lw_items else ""
    )

    # ── 당선작 강점 분석 ──────────────────────────────────
    winner_boxes = ""
    for winner in winners:
        wd         = comp_subs.get(winner, {})
        axis_items = ""
        for axis in AXES:
            ax        = wd.get(axis, {})
            strengths = ax.get("strengths", [])
            notes     = ax.get("notes", "")
            score     = ax.get("score")
            if not strengths and not notes:
                continue
            label     = AXIS_LABELS_KO.get(axis, axis)
            score_txt = f" ({float(score):.1f})" if score is not None else ""
            tags      = "".join(f'<span class="tag tag-strength">{t}</span>' for t in strengths)
            axis_items += (
                f'<div class="w-axis"><div class="w-axis-label">{label}{score_txt}</div>'
                f'<div>{tags}</div>'
                + (f'<div class="notes">{notes}</div>' if notes else "")
                + "</div>"
            )

        if axis_items:
            winner_boxes += (
                f'<div class="winner-box"><div class="winner-box-title">★ {winner} — 당선 강점 분석</div>'
                f'{axis_items}</div>'
            )

    winner_section = (
        f'<div class="sec">{_sec_title(_next_n(), "당선작 강점 분석")}{winner_boxes}</div>'
        if winner_boxes else ""
    )

    # ── 최종 조합 ─────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{comp_name} — 비교 분석 리포트</title>
{_CSS}
</head>
<body>
<div class="page-wrap">
{header}
{dashboard_section}
{sub_section}
{table_section}
{floor_matrix_section}
{quant_table_section}
{ranking_section}
{diff_section}
{ws_section}
{lw_section}
{winner_section}
<div class="footer">Competition Analyzer — 자동 생성 비교 리포트 · {comp_name}</div>
</div>
{_dashboard_js(axes_with_data)}
</body>
</html>"""
