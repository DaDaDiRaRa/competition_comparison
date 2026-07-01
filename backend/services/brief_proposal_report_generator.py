"""
brief_proposal_report_generator.py — 수주 제안서(_proposal) → HTML (PPT형 스크롤 덱).

**LLM 호출 없음** (Report Generation Rule). brief_proposal.propose_project 가 만든
_proposal dict 를 화이트 + 건원 RED 자체완결 HTML 로 렌더만 한다. 데이터는 html.escape.

레이아웃: 통일 캔버스(배경색 분리 없음) · 밀도 높게(나란히 배치) · 글→도식 치환.
- 배점 무게중심: 100칸 와플 차트 SVG + 범례
- 설계 접근 방향: 한눈 매트릭스 + 상세 카드(공간전략/포기/근거 + 매스 실루엣)
"""
from __future__ import annotations

import html
import math
from typing import Any


_WAFFLE_COLORS = [
    "#e60012", "#c47b00", "#2a6496", "#5a8a3e",
    "#7a3a8e", "#3a8a8e", "#c45a00", "#6a6a6a",
]

# 5가지 컨셉 매스 실루엣 (측면 개념 실루엣, 평면 도식 아님)
_MASS_SVGS = [
    '<svg viewBox="0 0 80 72" width="80" height="72" fill="none" stroke="#1a1a1a" stroke-width="1.5" aria-hidden="true">'
    '<rect x="15" y="10" width="18" height="54" rx="1"/>'
    '<rect x="47" y="20" width="18" height="44" rx="1"/>'
    '<line x1="8" y1="66" x2="72" y2="66"/></svg>',

    '<svg viewBox="0 0 80 72" width="80" height="72" fill="none" stroke="#1a1a1a" stroke-width="1.5" aria-hidden="true">'
    '<rect x="12" y="36" width="56" height="28" rx="1"/>'
    '<rect x="28" y="12" width="26" height="26" rx="1"/>'
    '<line x1="8" y1="66" x2="72" y2="66"/></svg>',

    '<svg viewBox="0 0 80 72" width="80" height="72" fill="none" stroke="#1a1a1a" stroke-width="1.5" aria-hidden="true">'
    '<rect x="10" y="12" width="16" height="52" rx="1"/>'
    '<rect x="28" y="26" width="16" height="38" rx="1"/>'
    '<rect x="46" y="40" width="16" height="24" rx="1"/>'
    '<line x1="6" y1="66" x2="68" y2="66"/></svg>',

    '<svg viewBox="0 0 80 72" width="80" height="72" fill="none" stroke="#1a1a1a" stroke-width="1.5" aria-hidden="true">'
    '<rect x="8" y="30" width="64" height="34" rx="1"/>'
    '<rect x="22" y="16" width="22" height="16" rx="1"/>'
    '<line x1="4" y1="66" x2="76" y2="66"/></svg>',

    '<svg viewBox="0 0 80 72" width="80" height="72" fill="none" stroke="#1a1a1a" stroke-width="1.5" aria-hidden="true">'
    '<rect x="8" y="18" width="20" height="46" rx="1"/>'
    '<rect x="31" y="10" width="20" height="54" rx="1"/>'
    '<rect x="54" y="28" width="18" height="36" rx="1"/>'
    '<line x1="4" y1="66" x2="76" y2="66"/></svg>',
]

_CIRCLE_NUMS = "①②③④⑤⑥⑦⑧⑨⑩"

_PROPOSAL_CSS = """
:root{
  --ink:#1a1a1a;--text:#3a3a3a;--muted:#9a9a9a;--line:#e8e8e8;
  --soft:#f7f7f8;--accent:#e60012;
  --high:#e60012;--med:#c47b00;--low:#9a9a9a;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:#fff;color:var(--text);
  font-family:'Apple SD Gothic Neo','Malgun Gothic',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;padding:52px 30px 110px}
header.doc{margin-bottom:8px;padding-bottom:22px;border-bottom:2px solid var(--ink)}
header.doc .eyebrow{font-size:12px;letter-spacing:.14em;color:var(--accent);font-weight:700;text-transform:uppercase}
header.doc h1{margin:8px 0 0;font-size:25px;font-weight:700;color:var(--ink);letter-spacing:-.02em;line-height:1.3}
header.doc .meta{margin-top:12px;color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px}
.disclaimer{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:18px 0 4px}

/* ── 섹션 ─────────────────────────── */
section.sec{margin:38px 0 0;scroll-margin-top:58px}
section.sec>h2{display:flex;align-items:center;gap:10px;margin:0 0 14px;
  font-size:17px;font-weight:700;color:var(--ink);letter-spacing:-.01em}
section.sec>h2 .n{display:inline-flex;align-items:center;justify-content:center;
  min-width:24px;height:24px;padding:0 6px;border-radius:6px;
  background:var(--accent);color:#fff;font-size:12px;font-weight:700;flex:0 0 auto}
section.sec>h2 .conf{margin-left:auto;font-size:11px;font-weight:600;border:1px solid var(--line);
  border-radius:20px;padding:3px 10px;color:var(--muted)}
section.sec>h2 .conf.high{color:#2a8a3e;border-color:#bfe3c6}
section.sec>h2 .conf.low{color:var(--accent);border-color:#f3c2c6}

/* ── 전략 요약 ───────────────────── */
.summ{font-size:15.5px;line-height:1.75;color:var(--ink);
  border-left:3px solid var(--accent);padding:4px 0 4px 16px;margin:4px 0}

/* ── 대지·맥락 분석 ──────────────── */
.site-wrap{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
.site-thumb{flex:0 0 auto;width:280px;max-width:100%}
.site-thumb img{width:100%;border-radius:10px;border:1px solid var(--line);display:block}
.site-thumb .cap{font-size:11px;color:var(--muted);margin-top:5px;text-align:center}
.site-main{flex:1;min-width:280px}
.site-summary{font-size:14.5px;line-height:1.7;color:var(--ink);
  border-left:3px solid var(--accent);padding:4px 0 4px 14px;margin:0 0 12px}
.site-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px 18px}
.site-field .sfk{font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--muted);text-transform:uppercase;margin-bottom:2px}
.site-field .sfv{font-size:13px;color:var(--text)}
.site-note{margin-top:13px;font-size:11.5px;color:var(--muted);background:var(--soft);border-radius:6px;padding:8px 12px;line-height:1.55}

/* ── 히어로 (대지 실측 이미지) ───── */
.hero{margin:20px 0 6px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.hero img{width:100%;height:360px;object-fit:cover;object-position:center;display:block}
.hero .hero-cap{padding:13px 18px}
.hero .hero-src{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.hero .hero-sum{font-size:15px;line-height:1.7;color:var(--ink);margin-top:5px;font-weight:600}

/* ── 사업 규모 팩트 밴드 (실추출) ── */
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(116px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:6px 0}
.fact{background:#fff;padding:14px 16px}
.fact .fv{font-size:21px;font-weight:800;color:var(--ink);letter-spacing:-.02em;line-height:1.1}
.fact .fv .u{font-size:12px;font-weight:600;color:var(--muted);margin-left:2px}
.fact .fk{font-size:11px;color:var(--muted);margin-top:5px;font-weight:600}
.facts-note{font-size:11px;color:var(--muted);margin-top:6px}

/* ── 와플 차트 ───────────────────── */
.waffle-wrap{display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap}
.waffle-legend{display:flex;flex-direction:column;gap:7px;min-width:160px}
.waffle-legend-item{display:flex;align-items:center;gap:8px;font-size:12.5px}
.waffle-legend-item .dot{width:12px;height:12px;border-radius:3px;flex:0 0 auto}
.waffle-legend-item .lname{color:var(--ink);font-weight:600}
.waffle-legend-item .lpts{color:var(--muted);margin-left:2px}

/* ── 테마 카드 ───────────────────── */
.theme-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:6px 0}
.theme-card{border:1px solid var(--line);border-radius:10px;padding:14px 16px;border-left:3px solid var(--accent)}
.theme-card .tc-title{font-size:15px;font-weight:700;color:var(--ink)}
.theme-card .tc-rat{margin-top:5px;color:var(--text);font-size:13.5px}
.theme-card .tc-link{margin-top:6px;font-size:12.5px;color:var(--accent);font-weight:600}

/* ── 방향 매트릭스 ───────────────── */
.dir-matrix{width:100%;border-collapse:collapse;margin:8px 0 20px;font-size:13px}
.dir-matrix th{text-align:left;font-size:11.5px;color:var(--muted);font-weight:600;
  letter-spacing:.05em;padding:6px 10px;border-bottom:2px solid var(--ink)}
.dir-matrix td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;color:var(--text)}
.dir-matrix td:first-child{font-weight:700;color:var(--ink);white-space:nowrap}
.dir-matrix tr:last-child td{border-bottom:none}
.dir-matrix .dn{color:var(--accent);margin-right:5px}

/* ── 방향 상세 카드 ─────────────── */
.dir-cards{display:flex;flex-direction:column;gap:12px;margin-top:4px}
.dir-card{border:1px solid var(--line);border-radius:11px;overflow:hidden}
.dir-card-head{display:flex;align-items:stretch;gap:0}
.dir-card-main{flex:1;padding:14px 16px}
.dir-card-svgbox{display:flex;align-items:center;justify-content:center;
  padding:12px 16px;border-left:1px solid var(--line);min-width:112px;color:var(--muted)}
.dir-card-title{font-size:15px;font-weight:700;color:var(--ink);margin-bottom:8px}
.dir-card-title .num{color:var(--accent);margin-right:6px}
.dir-card-narr{font-size:13px;color:var(--text);line-height:1.75;margin:-2px 0 11px}
.dir-fields{display:grid;grid-template-columns:1fr 1fr;gap:6px 16px}
.dir-field .dfk{font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--muted);margin-bottom:2px;text-transform:uppercase}
.dir-field .dfv{font-size:13px;color:var(--text)}
.dir-card-basis{padding:7px 16px 12px;font-size:11.5px;color:var(--muted);border-top:1px solid var(--line);background:#fafafa}

/* ── 2층 범례 (사실 vs AI 해석) ──── */
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin:16px 0 2px;
  padding:11px 16px;border:1px solid var(--line);border-radius:10px;background:var(--soft);font-size:12px}
.legend .lg-h{font-weight:700;color:var(--ink);margin-right:2px}
.legend .lg-item{display:flex;align-items:center;gap:7px;color:var(--text)}
.ai-badge{display:inline-flex;align-items:center;font-size:10.5px;font-weight:700;letter-spacing:.04em;
  color:#2a6496;background:#eaf1f7;border:1px solid #cfe0ee;border-radius:20px;padding:2px 9px;vertical-align:middle}
section.sec>h2 .ai-badge{margin-left:8px}

/* ── AI 해석 리스트 (프로그램·매스·단계) ── */
ul.interp{list-style:none;margin:6px 0;padding:0}
ul.interp li{padding:13px 0;border-bottom:1px solid #f4f4f4;display:flex;flex-direction:column;gap:5px}
ul.interp li:last-child{border-bottom:none}
ul.interp .ic{font-size:14px;font-weight:700;color:var(--ink);line-height:1.55}
ul.interp .id{font-size:13px;color:var(--text);line-height:1.75;margin-top:1px}

/* ── 우선순위 ────────────────────── */
ol.pri{margin:8px 0;padding:0;list-style:none;counter-reset:pri}
ol.pri li{counter-increment:pri;display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #f4f4f4}
ol.pri li:last-child{border-bottom:none}
ol.pri li::before{content:counter(pri);display:inline-flex;align-items:center;justify-content:center;
  min-width:26px;height:26px;border-radius:7px;background:var(--accent);
  color:#fff;font-weight:700;font-size:12px;flex:0 0 auto;margin-top:1px}
ol.pri li .pri-body{flex:1}
ol.pri li .focus{font-weight:700;color:var(--ink)}
ol.pri li .w{font-weight:600;color:var(--accent);margin-left:7px;font-size:12px}
ol.pri li .why{color:var(--text);margin-top:2px;font-size:13px}

/* ── 리스크 ──────────────────────── */
.risk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin:6px 0}
.risk{border-left:3px solid var(--low);padding:11px 14px;border-radius:0 8px 8px 0;
  border:1px solid var(--line);border-left-width:3px}
.risk.high{border-left-color:var(--high)}
.risk.medium{border-left-color:var(--med)}
.risk .rt{font-weight:700;color:var(--ink);font-size:13.5px}
.risk .sev{font-size:11px;color:var(--muted);font-weight:600;margin-left:7px}
.risk.high .sev{color:var(--high)} .risk.medium .sev{color:var(--med)}
.risk .rm{margin-top:5px;color:var(--text);font-size:13px}
.risk .rm .k{color:var(--muted);font-size:11px;font-weight:700;margin-right:5px;letter-spacing:.04em}

/* ── 리스트 섹션 ─────────────────── */
ul.list{margin:8px 0;padding-left:20px}
ul.list li{margin:5px 0;font-size:13.5px}
.checklist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin:6px 0}
.check-item{display:flex;align-items:flex-start;gap:7px;font-size:13px;color:var(--text)}
.check-item::before{content:"☐";color:var(--accent);font-size:15px;flex:0 0 auto;margin-top:-1px}

/* ── 공통 ────────────────────────── */
.cite{font-size:11px;color:var(--muted);background:var(--soft);border-radius:4px;
  padding:1px 5px;margin-left:3px;white-space:nowrap}
.caveat{margin:16px 0 0;font-size:12px;color:var(--muted)}

/* ── 근거 미확인 수치 검산 ─────────── */
.numcheck{border:1px solid #f3c2c6;background:#fdf2f3;border-radius:10px;padding:13px 16px;margin:6px 0}
.numcheck .nc-h{font-size:12.5px;font-weight:700;color:var(--accent);margin-bottom:8px}
.numcheck ul{list-style:none;margin:0;padding:0}
.numcheck li{font-size:12.5px;color:var(--text);padding:4px 0;line-height:1.55}
.numcheck li .nv{font-weight:800;color:var(--accent);font-family:'Montserrat',monospace}
.numcheck li .nctx{color:var(--muted)}

/* ── 참고 사례 (다른 공모) ─────────── */
.refcase{border:1px solid var(--line);background:var(--soft);border-radius:10px;padding:13px 16px;margin:6px 0}
.refcase .rc-h{font-size:12.5px;font-weight:700;color:var(--text);margin-bottom:10px}
.refcase .rc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.refcase .rc-card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.refcase .rc-src{font-size:11px;color:var(--accent);font-weight:700;margin-bottom:3px}
.refcase .rc-name{font-size:12px;font-weight:700;color:var(--ink);margin-bottom:4px}
.refcase .rc-body{font-size:12px;color:var(--text);line-height:1.6}
footer.doc{margin-top:64px;padding-top:18px;border-top:1px solid var(--line);color:#c0c0c0;font-size:11.5px;text-align:center}

/* ── 상단 nav ────────────────────── */
nav.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);
  backdrop-filter:saturate(160%) blur(8px);-webkit-backdrop-filter:saturate(160%) blur(8px);
  border-bottom:1px solid var(--line)}
nav.top .inner{max-width:960px;margin:0 auto;padding:9px 30px;display:flex;align-items:center;gap:14px}
nav.top .ttl{font-weight:700;color:var(--ink);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:34%}
nav.top .links{display:flex;gap:2px;margin-left:auto;flex-wrap:nowrap;overflow-x:auto}
nav.top .links a{font-size:12px;color:var(--muted);text-decoration:none;padding:4px 10px;border-radius:6px;white-space:nowrap}
nav.top .links a:hover{background:var(--soft);color:var(--ink)}

@media print{.wrap{padding:0}body{font-size:12px}section.sec{break-inside:avoid}nav.top{display:none}}
@media(max-width:600px){
  .wrap{padding:32px 18px 64px}
  nav.top .ttl{display:none}
  nav.top .inner{padding:8px 18px}
  .dir-fields{grid-template-columns:1fr}
  .dir-card-svgbox{display:none}
  .waffle-wrap{flex-direction:column}
  .site-fields{grid-template-columns:1fr}
  .site-thumb{width:100%}
  .hero img{height:220px}
}
"""

_CONF_LABEL = {"high": "높음", "medium": "보통", "low": "낮음 (근거 부족)"}
_SEV_LABEL   = {"high": "높음", "medium": "중간",  "low": "낮음"}


def _esc(v: Any) -> str:
    if v is None:
        return ""
    return html.escape(str(v), quote=True)


def _basis_html(b) -> str:
    items = b if isinstance(b, list) else ([b] if b else [])
    items = [str(x).strip() for x in items if str(x).strip()]
    if not items:
        return ""
    parts = " · ".join(_esc(x) for x in items)
    return f'<span class="cite">근거 {parts}</span>'


# "AI 해석" 배지 — 사실/해석 2층 구분 (legend·directions·interp 섹션 공통 단일 소스)
_AI_BADGE = '<span class="ai-badge">AI 해석</span>'


def _sat_src_label(sc: dict | None) -> str:
    """위성 이미지 출처 라벨 (지적도 합성 여부에 따라). hero·site 섹션 공통 단일 소스."""
    return "VWorld 위성 + 연속지적도" if (sc or {}).get("has_cadastral") else "VWorld 위성"


# ── 와플 차트 ────────────────────────────────────────────────────────

def _waffle_cells(focus_ranked: list) -> list[tuple[str, str, int]]:
    """최대잉여법으로 100칸 배분 → [(category, color, count)]."""
    items = [(f, _WAFFLE_COLORS[i % len(_WAFFLE_COLORS)])
             for i, f in enumerate(focus_ranked)
             if isinstance(f.get("weight_pct"), (int, float)) and f["weight_pct"] > 0]
    if not items:
        return []
    floored = [(f, c, int(f["weight_pct"])) for f, c in items]
    remainder = 100 - sum(x[2] for x in floored)
    fracs = sorted(((f["weight_pct"] % 1, i) for i, (f, c, _) in enumerate(floored)), reverse=True)
    for _, idx in fracs[:max(0, remainder)]:
        f, c, n = floored[idx]
        floored[idx] = (f, c, n + 1)
    return [(f.get("category") or "", c, n) for f, c, n in floored]


def _waffle_svg(cells: list) -> str:
    cell_px, gap = 12, 2
    step = cell_px + gap
    dim = step * 10 - gap  # 138

    flat: list[str] = []
    for _, color, count in cells:
        flat.extend([color] * count)
    flat.extend(["#e8e8e8"] * (100 - len(flat)))

    rects = []
    for i, color in enumerate(flat[:100]):
        col, row = i % 10, i // 10
        rects.append(
            f'<rect x="{col*step}" y="{row*step}" width="{cell_px}" height="{cell_px}" '
            f'fill="{color}" rx="2"/>'
        )
    return (
        f'<svg viewBox="0 0 {dim} {dim}" width="{dim}" height="{dim}" '
        f'style="display:block;flex:0 0 auto" aria-hidden="true">'
        + "".join(rects) + "</svg>"
    )


def _scoring_waffle(proposal: dict) -> str:
    focus = [f for f in (proposal.get("scoring_focus") or []) if isinstance(f, dict)]
    ranked = sorted([f for f in focus if isinstance(f.get("rank"), (int, float))],
                    key=lambda f: f["rank"])[:8]
    if not ranked:
        return ""
    cells = _waffle_cells(ranked)
    if not cells:
        return ""

    legend_items = []
    for cat, color, n in cells:
        pts_f = next((f for f in ranked if (f.get("category") or "") == cat), {})
        pts = pts_f.get("points")
        pts_txt = f'{pts:g}점' if isinstance(pts, (int, float)) else f'{n}%'
        legend_items.append(
            f'<div class="waffle-legend-item">'
            f'<span class="dot" style="background:{color}"></span>'
            f'<span class="lname">{_esc(cat)}</span>'
            f'<span class="lpts">{_esc(pts_txt)}</span>'
            f'</div>'
        )

    return (
        '<section id="scoring" class="sec">'
        '<h2><span class="n">·</span>배점 무게중심</h2>'
        '<div class="waffle-wrap">'
        + _waffle_svg(cells)
        + '<div class="waffle-legend">' + "".join(legend_items) + '</div>'
        '</div></section>'
    )


# ── 대지·맥락 분석 ───────────────────────────────────────────────────

_SITE_FIELDS = [
    ("orientation",      "향 · 형상"),
    ("road_access",      "도로 접면"),
    ("surrounding_uses", "주변 용도"),
    ("natural_assets",   "자연 자원"),
    ("special_context",  "특이사항"),
]


def _hero_html(site_context: dict | None, image_b64: str = "") -> str:
    """대지 실측(위성+지적도) 이미지를 덱 최상단 히어로로. 이미지 없으면 ''.

    '상상이 아니라 실측'을 첫 화면에 — 캡션엔 주소·출처 + 대지 요약.
    """
    sc = site_context or {}
    if not image_b64:
        return ""
    analysis = sc.get("analysis") if isinstance(sc.get("analysis"), dict) else {}
    matched = (sc.get("matched_address") or sc.get("address_input") or "").strip()
    summary = (analysis.get("overall_summary") or "").strip()
    src = _sat_src_label(sc)
    src_line = " · ".join(x for x in [_esc(matched), _esc(src)] if x)
    return (
        '<div class="hero">'
        f'<img src="data:image/jpeg;base64,{image_b64}" alt="대지 위성·지적도 실측" />'
        '<div class="hero-cap">'
        f'<div class="hero-src">{src_line}</div>'
        + (f'<div class="hero-sum">{_esc(summary)}</div>' if summary else "")
        + '</div></div>'
    )


# ── 사업 규모 팩트 밴드 (지침서 실추출 — 날조 0) ─────────────────────

_FACT_FIELDS = [
    ("site_area_sqm",          "㎡",   "부지면적", lambda v: f"{v:,.0f}"),
    ("floor_area_ratio_pct",   "%",    "용적률",   lambda v: f"{v:g}"),
    ("building_coverage_pct",  "%",    "건폐율",   lambda v: f"{v:g}"),
    ("max_height_m",           "m",    "최고높이", lambda v: f"{v:g}"),
]
_FACT_TOPLEVEL = [
    ("construction_cost_100m_won", "억",   "공사비",   lambda v: f"{v:,.0f}"),
    ("design_cost_100m_won",       "억",   "설계비",   lambda v: f"{v:,.0f}"),
    ("construction_period_months", "개월", "공사기간", lambda v: f"{v:g}"),
]


def _facts_band_html(feasibility: dict | None) -> str:
    """feasibility_export 의 실추출 수치를 대형 숫자 밴드로. 데이터 없으면 ''.

    첨부물의 '지어낸 분양가·ROI'와 정반대 — 지침서에서 뽑은 사실 숫자만.
    """
    fe = feasibility if isinstance(feasibility, dict) else {}
    sites = [s for s in (fe.get("sites") or []) if isinstance(s, dict)]
    s0 = sites[0] if sites else {}

    facts = []
    for key, unit, label, fmt in _FACT_FIELDS:
        v = s0.get(key)
        if isinstance(v, (int, float)):
            facts.append((fmt(v), unit, label))
    for key, unit, label, fmt in _FACT_TOPLEVEL:
        v = fe.get(key)
        if isinstance(v, (int, float)):
            facts.append((fmt(v), unit, label))
    if not facts:
        return ""

    cells = "".join(
        f'<div class="fact"><div class="fv">{_esc(v)}<span class="u">{_esc(u)}</span></div>'
        f'<div class="fk">{_esc(k)}</div></div>'
        for v, u, k in facts
    )
    multi = (
        f'<div class="facts-note">부지 {len(sites)}곳 중 대표(1번지) 기준</div>'
        if len(sites) > 1 else ""
    )
    return (
        '<section id="facts" class="sec">'
        '<h2><span class="n">·</span>사업 규모 <span style="font-size:12px;font-weight:600;color:var(--muted)">· 지침서 추출 사실</span></h2>'
        f'<div class="facts">{cells}</div>'
        + multi
        + '</section>'
    )


def _site_context_html(site_context: dict | None, image_b64: str = "", compact: bool = False) -> str:
    """_site_context (VWorld 위성 + AI 판독) → 대지·맥락 섹션. 데이터 없으면 ''.

    compact=True 면 이미지·요약을 히어로가 이미 보여주므로 생략(필드·주의만).
    """
    sc = site_context or {}
    analysis = sc.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}

    summary = "" if compact else (analysis.get("overall_summary") or "").strip()
    matched = (sc.get("matched_address") or sc.get("address_input") or "").strip()
    has_fields = any((analysis.get(k) or "").strip() for k, _ in _SITE_FIELDS)
    if not (summary or has_fields or (image_b64 and not compact)):
        return ""

    thumb = ""
    if image_b64 and not compact:
        src_lbl = _sat_src_label(sc)
        cap = (_esc(matched) + " · " if matched else "") + src_lbl
        thumb = (
            '<div class="site-thumb">'
            f'<img src="data:image/jpeg;base64,{image_b64}" alt="대지 위성사진" />'
            f'<div class="cap">{cap}</div>'
            '</div>'
        )

    fields = ""
    for k, label in _SITE_FIELDS:
        v = (analysis.get(k) or "").strip()
        if not v:
            continue
        fields += (
            '<div class="site-field">'
            f'<div class="sfk">{_esc(label)}</div>'
            f'<div class="sfv">{_esc(v)}</div>'
            '</div>'
        )

    conf = (analysis.get("confidence") or "").lower()
    conf_lbl = _CONF_LABEL.get(conf, "")
    caveats = [str(c).strip() for c in (analysis.get("caveats") or []) if str(c).strip()]
    note_bits = ["위성 영상 AI 판독 기반 — 현장 답사·지적도로 확인 필요 (추론 포함)"]
    if conf_lbl:
        note_bits.append(f"판독 신뢰도 {conf_lbl}")
    note = '<div class="site-note">⚠ ' + " · ".join(_esc(x) for x in note_bits)
    if caveats:
        note += "<br>" + " · ".join(_esc(c) for c in caveats)
    note += "</div>"

    main = (
        '<div class="site-main">'
        + (f'<div class="site-summary">{_esc(summary)}</div>' if summary else "")
        + (f'<div class="site-fields">{fields}</div>' if fields else "")
        + note
        + '</div>'
    )

    return (
        '<section id="site" class="sec">'
        '<h2><span class="n">·</span>대지 · 맥락 분석</h2>'
        '<div class="site-wrap">' + thumb + main + '</div>'
        '</section>'
    )


# ── 핵심 테마 ────────────────────────────────────────────────────────

def _win_themes_html(proposal: dict) -> str:
    themes = [t for t in (proposal.get("win_themes") or []) if isinstance(t, dict)]
    cards = []
    for t in themes:
        topic = _esc((t.get("theme") or "").strip())
        if not topic:
            continue
        rat = (t.get("rationale") or "").strip()
        link = (t.get("scoring_link") or "").strip()
        cards.append(
            f'<div class="theme-card">'
            f'<div class="tc-title">{topic}</div>'
            + (f'<div class="tc-rat">{_esc(rat)}</div>' if rat else "")
            + (f'<div class="tc-link">↳ {_esc(link)}</div>' if link else "")
            + f'<div style="margin-top:6px">{_basis_html(t.get("basis"))}</div>'
            f'</div>'
        )
    if not cards:
        return ""
    return (
        '<section id="themes" class="sec">'
        '<h2><span class="n">1</span>수주 핵심 테마</h2>'
        '<div class="theme-grid">' + "".join(cards) + '</div>'
        '</section>'
    )


# ── 설계 접근 방향 (매트릭스 + 상세 카드) ───────────────────────────

def _direction_matrix(dirs: list) -> str:
    if not dirs:
        return ""
    rows = []
    for i, d in enumerate(dirs):
        num = _CIRCLE_NUMS[i] if i < len(_CIRCLE_NUMS) else str(i + 1)
        name = _esc((d.get("direction") or "").strip())
        addr = _esc((d.get("addresses") or "").strip())
        tr   = _esc((d.get("tradeoffs") or "").strip())
        rows.append(
            f'<tr><td><span class="dn">{_esc(num)}</span>{name}</td>'
            f'<td>{addr}</td><td>{tr}</td></tr>'
        )
    return (
        '<table class="dir-matrix">'
        '<thead><tr><th>안</th><th>접근 방향</th><th>포기·유의</th></tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table>'
    )


def _direction_cards(dirs: list) -> str:
    if not dirs:
        return ""
    cards = []
    for i, d in enumerate(dirs):
        num   = _CIRCLE_NUMS[i] if i < len(_CIRCLE_NUMS) else str(i + 1)
        name  = _esc((d.get("direction") or "").strip())
        narr  = _esc((d.get("narrative") or "").strip())
        addr  = _esc((d.get("addresses") or "").strip())
        tr    = _esc((d.get("tradeoffs") or "").strip())
        basis = _basis_html(d.get("basis"))
        svg   = _MASS_SVGS[i % len(_MASS_SVGS)]

        play = _esc((d.get("scoring_play") or "").strip())     # 득점 (Phase 2)
        srat = _esc((d.get("site_rationale") or "").strip())   # 이 부지라서 (Phase 2)

        def _field(k, v):
            return (
                '<div class="dir-field">'
                f'<div class="dfk">{k}</div>'
                f'<div class="dfv">{v}</div>'
                '</div>'
            ) if v else ""

        fields = (
            _field("공간전략", addr)
            + _field("득점", play)
            + _field("포기·유의", tr)
            + _field("이 부지라서", srat)
        )

        cards.append(
            '<div class="dir-card">'
            '<div class="dir-card-head">'
            '<div class="dir-card-main">'
            f'<div class="dir-card-title"><span class="num">{_esc(num)}</span>{name}</div>'
            + (f'<div class="dir-card-narr">{narr}</div>' if narr else "")
            + (f'<div class="dir-fields">{fields}</div>' if fields else "")
            + '</div>'
            f'<div class="dir-card-svgbox">{svg}</div>'
            '</div>'
            + (f'<div class="dir-card-basis">{basis}</div>' if basis else "")
            + '</div>'
        )
    return '<div class="dir-cards">' + "".join(cards) + '</div>'


def _directions_html(proposal: dict) -> str:
    dirs = [d for d in (proposal.get("design_directions") or []) if isinstance(d, dict)]
    if not dirs:
        return ""
    return (
        '<section id="directions" class="sec">'
        '<h2><span class="n">2</span>설계 접근 방향'
        + _AI_BADGE + '</h2>'
        + _direction_matrix(dirs)
        + _direction_cards(dirs)
        + '</section>'
    )


# ── AI 해석 확장층 (프로그램·매스·단계 — Phase 2) ──────────────────────

def _interp_section(proposal: dict, key: str, sec_id: str, title: str) -> str:
    """{claim, basis} 리스트 → 'AI 해석' 배지 단 확장 섹션. 각 항목에 근거 앵커.

    1층 사실 위에서 AI가 추론한 제안층 — 사실로 위장하지 않게 배지·앵커로 명시.
    """
    items = [x for x in (proposal.get(key) or []) if isinstance(x, dict)]
    lis = []
    for it in items:
        claim = _esc((it.get("claim") or "").strip())
        if not claim:
            continue
        detail = _esc((it.get("detail") or "").strip())
        basis = _basis_html(it.get("basis"))
        lis.append(
            f'<li><div class="ic">{claim}</div>'
            + (f'<div class="id">{detail}</div>' if detail else "")
            + (basis or "")
            + '</li>'
        )
    if not lis:
        return ""
    return (
        f'<section id="{sec_id}" class="sec">'
        f'<h2><span class="n">·</span>{_esc(title)}{_AI_BADGE}</h2>'
        '<ul class="interp">' + "".join(lis) + '</ul>'
        '</section>'
    )


def _number_flags_html(proposal: dict) -> str:
    """근거 미확인 수치 검산 결과(`_number_flags`)를 경고 밴드로. 없으면 ''.

    제안서 서술에 나왔지만 지침서 추출 데이터에서 확인 안 된 숫자 — 일반지식·추정일
    수 있으니 인용 전 원문 확인하라는 투명성 신호 (숫자 수정 0, 플래그만).
    """
    flags = [f for f in (proposal.get("_number_flags") or []) if isinstance(f, dict)]
    if not flags:
        return ""
    rows = []
    for f in flags[:20]:
        val = _esc((f.get("value") or "").strip())
        ctx = _esc((f.get("context") or "").strip())
        if not val:
            continue
        rows.append(f'<li><span class="nv">{val}</span> · <span class="nctx">…{ctx}…</span></li>')
    if not rows:
        return ""
    return (
        '<section id="numcheck" class="sec">'
        '<h2><span class="n">·</span>근거 미확인 수치</h2>'
        '<div class="numcheck">'
        '<div class="nc-h">⚠ 아래 수치는 지침서 추출 데이터에서 확인되지 않았습니다 '
        '— 일반지식·추정일 수 있으니 인용 전 원문 확인 필요</div>'
        '<ul>' + "".join(rows) + '</ul>'
        '</div></section>'
    )


def _reference_cases_html(proposal: dict) -> str:
    """참고한 기존 사례(_reference_cases) 를 별도 섹션으로 노출. 없으면 ''.

    다른 공모의 자료임을 명확히 라벨링 — 이 지침서의 사실 근거와 혼동되지 않게.
    """
    ref = proposal.get("_reference_cases")
    if not isinstance(ref, dict) or not ref:
        return ""

    cards = []
    for c in (ref.get("case_excerpts") or [])[:6]:
        if not isinstance(c, dict):
            continue
        strategy = _esc((c.get("main_strategy") or "").strip())
        if not strategy:
            continue
        name = _esc(c.get("competition_name") or c.get("competition_id") or "")
        company = _esc(c.get("company") or "")
        concept = _esc(c.get("concept_name_ko") or "")
        label = " · ".join(x for x in [company, concept] if x)
        cards.append(
            '<div class="rc-card"><div class="rc-src">당선 사례</div>'
            f'<div class="rc-name">{name}' + (f' <span style="font-weight:400">({label})</span>' if label else "") + '</div>'
            f'<div class="rc-body">{strategy}</div></div>'
        )
    for c in (ref.get("concept_comparison_excerpts") or [])[:6]:
        if not isinstance(c, dict):
            continue
        text = _esc((c.get("text") or "").strip())
        if not text:
            continue
        name = _esc(c.get("competition_name") or c.get("competition_id") or "")
        axis = _esc(c.get("axis") or "")
        cards.append(
            '<div class="rc-card"><div class="rc-src">비교분석 사례</div>'
            f'<div class="rc-name">{name}' + (f' · {axis}' if axis else "") + '</div>'
            f'<div class="rc-body">{text}</div></div>'
        )

    ps = ref.get("pattern_summary") or {}
    note = _esc((ps.get("note") or "").strip())
    note_html = f'<div class="rc-h">{note}</div>' if note else ""

    if not cards and not note_html:
        return ""
    return (
        '<section id="refcases" class="sec">'
        '<h2><span class="n">·</span>참고 사례</h2>'
        '<div class="refcase">'
        '<div class="rc-h">ⓘ 아래는 동일 시설유형의 <b>다른 공모</b> 사례입니다 — '
        '이 지침서의 사실 근거가 아니라 아이디어 참고용입니다.</div>'
        + note_html
        + (f'<div class="rc-grid">{"".join(cards)}</div>' if cards else "")
        + '</div></section>'
    )


def _legend_html() -> str:
    """2층 범례 — 사실(근거 인용) vs AI 해석(추론·제안). 차별화 선언."""
    return (
        '<div class="legend">'
        '<span class="lg-h">읽는 법 ·</span>'
        '<span class="lg-item">'
        '<span class="cite">근거 p.N</span> 지침서·대지에서 확인된 <b>사실</b></span>'
        '<span class="lg-item">'
        f'{_AI_BADGE} 그 사실 위에서 AI가 추론한 <b>제안</b> (검증 필요)</span>'
        '</div>'
    )


# ── 착수 우선순위 ────────────────────────────────────────────────────

def _priorities_html(proposal: dict) -> str:
    pris = [p for p in (proposal.get("priorities") or []) if isinstance(p, dict)]
    pris = sorted(pris, key=lambda p: p.get("rank") if isinstance(p.get("rank"), (int, float)) else 99)
    lis = []
    for p in pris:
        focus = _esc((p.get("focus") or "").strip())
        if not focus:
            continue
        wt = str(p.get("scoring_weight") or "").strip()
        why = (p.get("why") or "").strip()
        lis.append(
            f'<li><div class="pri-body">'
            f'<span class="focus">{focus}'
            + (f'<span class="w">{_esc(wt)}</span>' if wt else "")
            + '</span>'
            + (f'<div class="why">{_esc(why)}</div>' if why else "")
            + '</div></li>'
        )
    if not lis:
        return ""
    return (
        '<section id="priorities" class="sec">'
        '<h2><span class="n">3</span>착수 우선순위</h2>'
        '<ol class="pri">' + "".join(lis) + '</ol>'
        '</section>'
    )


# ── 리스크 ──────────────────────────────────────────────────────────

def _risks_html(proposal: dict) -> str:
    risks = [r for r in (proposal.get("risks") or []) if isinstance(r, dict)]
    order = {"high": 0, "medium": 1, "low": 2}
    risks = sorted(risks, key=lambda r: order.get((r.get("severity") or "").lower(), 9))
    blocks = []
    for r in risks:
        risk = _esc((r.get("risk") or "").strip())
        if not risk:
            continue
        sev = (r.get("severity") or "").lower()
        sev_cls = sev if sev in _SEV_LABEL else ""
        sev_lbl = _SEV_LABEL.get(sev, "")
        mit = (r.get("mitigation") or "").strip()
        blocks.append(
            f'<div class="risk {sev_cls}">'
            f'<div class="rt">{risk}'
            + (f'<span class="sev">{_esc(sev_lbl)}</span>' if sev_lbl else "")
            + '</div>'
            + (f'<div class="rm"><span class="k">대응</span>{_esc(mit)}</div>' if mit else "")
            + f'<div class="rm">{_basis_html(r.get("basis"))}</div>'
            + '</div>'
        )
    if not blocks:
        return ""
    return (
        '<section id="risks" class="sec">'
        '<h2><span class="n">4</span>리스크 · 대응</h2>'
        '<div class="risk-grid">' + "".join(blocks) + '</div>'
        '</section>'
    )


# ── 체크리스트 · 확인 필요 ───────────────────────────────────────────

def _checklist_html(proposal: dict, key: str, sec_id: str, n: str, title: str) -> str:
    items = [str(x).strip() for x in (proposal.get(key) or []) if str(x).strip()]
    if not items:
        return ""
    cells = "".join(f'<div class="check-item">{_esc(x)}</div>' for x in items)
    return (
        f'<section id="{sec_id}" class="sec">'
        f'<h2><span class="n">{n}</span>{_esc(title)}</h2>'
        f'<div class="checklist-grid">{cells}</div>'
        '</section>'
    )


# ── 메인 렌더 ────────────────────────────────────────────────────────

def to_proposal_html(
    proposal: dict,
    brief_name: str = "",
    facility_label: str = "",
    site_context: dict | None = None,
    site_image_b64: str = "",
    feasibility: dict | None = None,
) -> str:
    """_proposal dict → 자체완결 HTML 문자열 (PPT형 스크롤 덱, LLM 호출 없음).

    - site_image_b64 가 있으면 덱 최상단에 대지 실측(위성+지적도) 히어로.
    - site_context 의 판독 필드는 '대지·맥락' 섹션으로(히어로 있으면 compact).
    - feasibility(feasibility_export) 가 있으면 '사업 규모' 실추출 팩트 밴드.
    """
    proposal = proposal or {}
    title = (brief_name or "").strip() or "프로젝트 수주 제안서"

    conf = (proposal.get("data_confidence") or "").lower()
    conf_cls = conf if conf in _CONF_LABEL else ""
    conf_lbl = _CONF_LABEL.get(conf, "")
    conf_html = (
        f'<span class="conf {conf_cls}">근거 신뢰도 {_esc(conf_lbl)}</span>'
        if conf_lbl else ""
    )

    summary = (proposal.get("executive_summary") or "").strip()
    summary_html = (
        '<section id="summary" class="sec">'
        f'<h2><span class="n">·</span>전략 요약{conf_html}</h2>'
        f'<div class="summ">{_esc(summary)}</div>'
        '</section>'
    ) if summary else ""

    meta_bits = []
    if facility_label:
        meta_bits.append(f'<span>{_esc(facility_label)}</span>')
    if proposal.get("generated_at"):
        meta_bits.append(f'<span>{_esc(proposal.get("generated_at"))}</span>')
    if proposal.get("model_id"):
        meta_bits.append(f'<span>모델 {_esc(proposal.get("model_id"))}</span>')

    hero_html = _hero_html(site_context, site_image_b64)
    site_html = _site_context_html(site_context, site_image_b64, compact=bool(hero_html))
    facts_html = _facts_band_html(feasibility)

    # Phase 2: AI 해석 확장층 (프로그램·매스·단계). 있을 때만 렌더.
    directions_html = _directions_html(proposal)
    interp_html = (
        _interp_section(proposal, "program_directions", "program", "프로그램 방향")
        + _interp_section(proposal, "massing_strategy",  "massing", "매스 전략")
        + _interp_section(proposal, "phasing",           "phasing", "단계 접근")
    )
    # 해석 마커가 실제로 쓰일 때만 범례 노출
    legend_html = _legend_html() if (interp_html or directions_html) else ""
    refcases_html = _reference_cases_html(proposal)

    body = (
        legend_html
        + summary_html
        + facts_html
        + site_html
        + _scoring_waffle(proposal)
        + _win_themes_html(proposal)
        + directions_html
        + interp_html
        + _priorities_html(proposal)
        + _risks_html(proposal)
        + _checklist_html(proposal, "kickoff_checklist", "kickoff", "5", "착수 체크리스트")
        + _checklist_html(proposal, "open_questions",    "questions", "6", "발주처 확인 필요")
        + _number_flags_html(proposal)
        + refcases_html
    )

    caveats = [str(c).strip() for c in (proposal.get("caveats") or []) if str(c).strip()]
    caveat_html = (
        '<section id="caveats" class="sec">'
        '<h2><span class="n">·</span>한계</h2>'
        '<ul class="list">' + "".join(f"<li>{_esc(c)}</li>" for c in caveats) + '</ul>'
        '</section>'
    ) if caveats else ""

    nav_links = (
        '<a href="#summary">요약</a>'
        + ('<a href="#facts">규모</a>' if facts_html else "")
        + ('<a href="#site">대지</a>' if site_html else "")
        + '<a href="#themes">핵심 테마</a>'
        '<a href="#directions">접근 방향</a>'
        + ('<a href="#program">프로그램</a>' if interp_html else "")
        + '<a href="#priorities">우선순위</a>'
        '<a href="#risks">리스크</a>'
        '<a href="#kickoff">체크리스트</a>'
        + ('<a href="#refcases">참고 사례</a>' if refcases_html else "")
    )

    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(title)} · 수주 제안서</title><style>{_PROPOSAL_CSS}</style></head>"
        "<body>"
        f"<nav class='top'><div class='inner'><div class='ttl'>{_esc(title)}</div>"
        f"<div class='links'>{nav_links}</div></div></nav>"
        "<div class='wrap'>"
        "<header class='doc'><div class='eyebrow'>PROJECT PROPOSAL</div>"
        f"<h1>{_esc(title)}</h1>"
        f"<div class='meta'>{''.join(meta_bits)}</div></header>"
        + hero_html
        + "<div class='disclaimer'>"
        "본 제안서는 추출된 지침서 데이터에 근거한 <b>수주 전략 가설</b>입니다. "
        "사실 주장(지침서가 요구·강조·배점하는 것)에는 근거를 인용하며, "
        "전략·접근 방향은 제안이고 실제 심사 결과를 보장하지 않습니다. "
        "최종 판단은 설계팀의 몫입니다.</div>"
        + body
        + caveat_html
        + "<footer class='doc'>"
        "Competition Analyzer · 지침서 기반 수주 제안서 (AI 생성 · 당락 예측 아님)"
        "</footer>"
        "</div></body></html>"
    )
