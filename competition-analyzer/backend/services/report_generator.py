import json
from config import FACILITY_TYPES

AXIS_LABELS_KO = {
    "concept": "개념",
    "mass": "배치·매스",
    "landscape": "조경",
    "program": "프로그램",
    "facade": "파사드",
    "technical": "기술",
    "quantitative": "정량",
}

AXES = ["concept", "mass", "landscape", "program", "facade", "technical", "quantitative"]

PALETTE = [
    '#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#264653',
    '#9B5DE5', '#F15BB5', '#00BBF9',
]

AXIS_LABEL_DASH = {
    'concept':      ('설계 컨셉',      '◈'),
    'mass':         ('매스 전략',      '◼'),
    'landscape':    ('공이·조경 연계', '◉'),
    'program':      ('프로그램 구성',  '▲'),
    'facade':       ('파사드·외관',    '◧'),
    'technical':    ('구조·기술',      '⚙'),
    'quantitative': ('정량 데이터',    '≡'),
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
    return {'yes': '#2f855a', 'partial': '#744210', 'no': '#742a2a'}.get(compliance, '#2d3748')


_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
       background: #0f1117; color: #e2e8f0; padding: 24px; font-size: 14px; }
.page-wrap { max-width: 1400px; margin: 0 auto; }

.hdr { background: #1a1f2e; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
       border-left: 4px solid #90cdf4; }
.hdr-title { font-size: 22px; font-weight: 700; color: #90cdf4; margin-bottom: 10px; }
.hdr-meta { display: flex; gap: 24px; flex-wrap: wrap; }
.hdr-meta span { color: #a0aec0; font-size: 13px; }
.hdr-meta strong { color: #e2e8f0; }

.sec { background: #1a1f2e; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; }
.sec-title { font-size: 16px; font-weight: 700; color: #90cdf4; margin-bottom: 16px;
             padding-bottom: 8px; border-bottom: 1px solid #2d3748; }

.sub-cards { display: flex; gap: 12px; flex-wrap: wrap; }
.sub-card { flex: 1; min-width: 150px; background: #0d1117; border-radius: 8px; padding: 14px;
            border: 1px solid #2d3748; }
.sub-card.winner { border-color: #f6d860; }
.badge-win { background: #b7791f; color: #fefcbf; font-size: 11px; padding: 2px 8px;
             border-radius: 20px; font-weight: 700; display: inline-block; margin-bottom: 6px; }
.badge-contracted { background: #276749; color: #c6f6d5; font-size: 11px; padding: 2px 8px;
             border-radius: 20px; font-weight: 700; display: inline-block; margin-bottom: 6px; }
.badge-lose { background: #742a2a; color: #fed7d7; font-size: 11px; padding: 2px 8px;
              border-radius: 20px; font-weight: 700; display: inline-block; margin-bottom: 6px; }
.sub-company { font-size: 15px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
.sub-pages { font-size: 12px; color: #718096; }

.cmp-table { width: 100%; border-collapse: collapse; }
.cmp-table th { background: #0d1117; padding: 10px 12px; text-align: left; font-size: 12px;
                color: #a0aec0; border-bottom: 1px solid #2d3748; }
.cmp-table td { padding: 10px 12px; border-bottom: 1px solid #1e2533; vertical-align: top; }
.cmp-table tr:hover td { background: rgba(144,205,244,0.03); }
.ax-label { font-weight: 700; color: #e2e8f0; font-size: 13px; }

.tag { display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 4px; margin: 1px; }
.tag-strength { background: #1c4532; color: #9ae6b4; }
.tag-weakness { background: #3b1111; color: #feb2b2; }
.tag-compliant { background: #1c4532; color: #9ae6b4; }
.tag-partial   { background: #44361b; color: #f6ad55; }
.tag-no        { background: #3b1111; color: #feb2b2; }
.tag-unclear   { background: #1a202c; color: #a0aec0; }
.notes { font-size: 11px; color: #718096; margin-top: 4px; line-height: 1.5; }

.rank-list { display: flex; gap: 10px; flex-wrap: wrap; }
.rank-item { background: #0d1117; border-radius: 8px; padding: 10px 16px;
             display: flex; align-items: center; gap: 10px; }
.rank-no { font-size: 22px; font-weight: 900; color: #2d3748; }
.rank-no.r1 { color: #f6d860; }
.rank-no.r2 { color: #a0aec0; }
.rank-no.r3 { color: #c5713a; }
.rank-co { font-size: 14px; font-weight: 600; }

.diff-list { display: flex; flex-direction: column; gap: 8px; }
.diff-item { background: #0d1117; border-radius: 6px; padding: 10px 14px; font-size: 13px;
             border-left: 3px solid #90cdf4; }
.diff-win  { border-left-color: #68d391; }
.diff-lose { border-left-color: #fc8181; }

.winner-box { background: rgba(246,216,96,0.05); border: 1px solid rgba(246,216,96,0.2);
              border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.winner-box-title { font-size: 15px; font-weight: 700; color: #f6d860; margin-bottom: 12px; }
.w-axis { margin-bottom: 12px; }
.w-axis-label { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 4px; }

/* ── Dashboard / accordion section ── */
.db-wrap { background: #0a0a0a !important; }
.db-sub-label { font-size: 11px; color: #666; letter-spacing: 0.15em; margin-bottom: 4px; }
.db-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; color: #fff; }
.db-count { font-size: 13px; color: #666; margin-top: 6px; margin-bottom: 20px; }
.db-rank-block { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; padding: 20px; margin-bottom: 20px; }
.db-rank-label { font-size: 13px; font-weight: 700; color: #aaa; letter-spacing: 0.1em; margin-bottom: 12px; }
.db-rank-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.db-rank-card { border-radius: 4px; padding: 10px 16px; min-width: 140px; }
.db-rank-medal { font-size: 20px; margin-bottom: 4px; }
.db-rank-name { font-size: 14px; font-weight: 700; }
.db-rank-meta { font-size: 11px; color: #666; margin-top: 2px; }
.db-keydiff { background: rgba(230,57,70,0.08); border: 1px solid rgba(230,57,70,0.2);
  border-radius: 2px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #e9c46a; }
.db-filter-bar { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; align-items: center; }
.db-filter-label { font-size: 11px; color: #666; margin-right: 4px; }
.db-filter-btn { border-radius: 2px; font-size: 12px; font-weight: 600; cursor: pointer;
  padding: 4px 14px; transition: all 0.15s; font-family: inherit; }
.db-expand-all { background: transparent; border: 1px solid rgba(255,255,255,0.1);
  color: #666; padding: 4px 14px; border-radius: 2px; font-size: 12px; cursor: pointer;
  margin-left: auto; font-family: inherit; }
.db-axis-row { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 2px; margin-bottom: 12px; overflow: hidden; }
.db-axis-header { width: 100%; background: none; border: none; color: #e0e0e0;
  padding: 16px 20px; display: flex; align-items: center; gap: 12px; cursor: pointer;
  font-size: 15px; font-family: inherit; text-align: left; }
.db-axis-icon { font-size: 18px; opacity: 0.6; }
.db-axis-name { font-weight: 600; letter-spacing: 0.02em; }
.db-chevron { margin-left: auto; opacity: 0.4; font-size: 12px; transition: transform 0.2s; }
.db-axis-content { padding: 0 20px 20px; }
.db-cards-grid { display: grid; gap: 10px; }
.db-axis-card { background: rgba(0,0,0,0.3); border-radius: 2px; padding: 16px; min-width: 0; }
.db-card-company { font-size: 11px; font-weight: 700; margin-bottom: 6px; letter-spacing: 0.05em; }
.db-card-score { font-size: 22px; font-weight: 800; color: #f6e05e; margin-bottom: 6px; }
.db-card-score-unit { font-size: 11px; color: #666; font-weight: 400; }
.db-card-notes { font-size: 12px; color: #aaa; line-height: 1.7; margin-bottom: 10px; }
.db-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.db-card-tag { font-size: 10px; padding: 2px 8px; border-radius: 2px; font-weight: 500; }
.db-card-strength { font-size: 11px; margin-bottom: 4px; }
.db-card-weakness { font-size: 11px; }
.db-compliance-badge { font-size: 10px; padding: 2px 8px; border-radius: 2px;
  color: #fff; font-weight: 600; display: inline-block; margin-top: 8px; }

.footer { text-align: center; color: #4a5568; font-size: 12px; margin-top: 30px; padding: 12px; }
</style>
"""


def _generate_dashboard_section(
    comp_subs: dict,
    ranking: list,
    key_diff: list,
    winners: list,
    submissions: list,
    axes: list,
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
        is_exp = (axis == 'concept')
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
        f'<div class="db-title">경쟁사 제안서 비교 분석</div>'
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
  var expandedAxes = ['concept'];

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
    year           = meta.get("year", "")
    client         = meta.get("client", "")
    location       = meta.get("location", "")
    facility_label = FACILITY_TYPES.get(facility_type, facility_type)

    comp_subs        = comparison.get("submissions", {})
    ranking          = comparison.get("ranking", [])
    key_diff         = comparison.get("key_differentiators", [])
    winner_strengths = comparison.get("winner_strengths", [])
    loser_weaknesses = comparison.get("loser_weaknesses", [])
    winners          = [s["company"] for s in submissions if s.get("result") in ("win", "contracted")]

    company_list   = list(comp_subs.keys())
    axes_with_data = [ax for ax in AXES if any(ax in comp_subs.get(c, {}) for c in company_list)]

    # ── 헤더 ──────────────────────────────────────────────
    header = f"""
    <div class="hdr">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
        <span style="background:#2b4c7e;color:#90cdf4;font-size:11px;padding:3px 10px;border-radius:20px;font-weight:700">당선작 분석 리포트</span>
        <span style="background:#1a3528;color:#68d391;font-size:11px;padding:3px 10px;border-radius:20px;font-weight:700">{facility_label}</span>
      </div>
      <div class="hdr-title">{comp_name}</div>
      <div class="hdr-meta">
        <span><strong>{year}년</strong></span>
        <span>발주처: <strong>{client}</strong></span>
        <span>위치: <strong>{location}</strong></span>
        <span>참여 제안서: <strong>{len(submissions)}개</strong></span>
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
    )

    # ── 참여 제안서 카드 ──────────────────────────────────
    cards = ""
    for s in submissions:
        company = s["company"]
        result  = s.get("result", "")
        pages   = s.get("total_pages", 0)
        if result == "win":
            badge = '<span class="badge-win">★ 당선</span>'
        elif result == "contracted":
            badge = '<span class="badge-contracted">◆ 수의계약</span>'
        else:
            badge = '<span class="badge-lose">낙선</span>'
        wcls   = " winner" if result in ("win", "contracted") else ""
        cards += f'<div class="sub-card{wcls}">{badge}<div class="sub-company">{company}</div><div class="sub-pages">{pages}페이지</div></div>'

    sub_section = f'<div class="sec"><div class="sec-title">참여 제안서</div><div class="sub-cards">{cards}</div></div>'

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
      <div class="sec-title">설계 축별 비교 분석</div>
      <div style="overflow-x:auto">
        <table class="cmp-table">
          <thead><tr><th style="min-width:90px">분석 축</th>{th_cols}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>"""

    # ── 종합 순위 ─────────────────────────────────────────
    rank_cls   = {0: "r1", 1: "r2", 2: "r3"}
    rank_items = "".join(
        f'<div class="rank-item"><span class="rank-no {rank_cls.get(i, "")}">{i+1}</span>'
        f'<span class="rank-co">{c}{"  ★" if c in winners else ""}</span></div>'
        for i, c in enumerate(ranking)
    )
    ranking_section = (
        f'<div class="sec"><div class="sec-title">종합 순위</div><div class="rank-list">{rank_items}</div></div>'
        if ranking else ""
    )

    # ── 주요 차별화 요소 ──────────────────────────────────
    diff_items  = "".join(f'<div class="diff-item">{d}</div>' for d in key_diff)
    diff_section = (
        f'<div class="sec"><div class="sec-title">주요 차별화 요소</div><div class="diff-list">{diff_items}</div></div>'
        if key_diff else ""
    )

    # ── 당선/낙선 요약 ────────────────────────────────────
    ws_items   = "".join(f'<div class="diff-item diff-win">{w}</div>' for w in winner_strengths)
    lw_items   = "".join(f'<div class="diff-item diff-lose">{w}</div>' for w in loser_weaknesses)
    ws_section = (
        f'<div class="sec"><div class="sec-title">당선작 우월 요인</div><div class="diff-list">{ws_items}</div></div>'
        if ws_items else ""
    )
    lw_section = (
        f'<div class="sec"><div class="sec-title">낙선작 공통 약점</div><div class="diff-list">{lw_items}</div></div>'
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
        f'<div class="sec"><div class="sec-title">당선작 강점 분석</div>{winner_boxes}</div>'
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
