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
/*__THEME__*/
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:#eceae7;color:var(--text);
  font-family:var(--serif);
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:1120px;margin:34px auto;padding:48px 56px 96px;background:#fff;
  border:1px solid var(--line);box-shadow:0 6px 30px rgba(0,0,0,.05)}
header.doc{margin-bottom:8px;padding-bottom:24px;border-bottom:3px solid var(--ink)}
header.doc .eyebrow{font-family:var(--sans);font-size:12px;letter-spacing:.28em;color:var(--accent);font-weight:800;text-transform:uppercase}
header.doc h1{font-family:var(--sans);margin:14px 0 0;font-size:44px;font-weight:900;color:var(--ink);letter-spacing:-.02em;line-height:1.08}
header.doc .meta{font-family:var(--sans);margin-top:16px;color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px}
.disclaimer{font-size:12.5px;color:var(--muted);border:1px solid var(--line);border-left:3px solid var(--faint);padding:12px 16px;margin:18px 0 4px;line-height:1.6}

/* ── 컨셉 표지 (오프닝) ───────────────── */
.cc-cover{margin:26px 0 8px;padding:44px 40px 40px;text-align:center;
  background:linear-gradient(180deg,#fafafa,#fff);border:1px solid var(--line);border-radius:14px}
.cc-eyebrow{font-family:var(--sans);font-size:11px;letter-spacing:.24em;font-weight:800;
  color:var(--muted);text-transform:uppercase;display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:20px}
.cc-keyword{font-family:var(--sans);font-size:64px;font-weight:900;color:var(--accent);
  letter-spacing:-.01em;line-height:1.02;word-break:keep-all}
.cc-keyword::before,.cc-keyword::after{content:"–";color:var(--faint);margin:0 .28em;font-weight:400}
.cc-tagline{font-family:var(--sans);font-size:30px;font-weight:800;color:var(--ink);
  letter-spacing:-.01em;margin:18px 0 4px;word-break:keep-all}
.cc-axes{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin:30px 0 8px}
.cc-axis{flex:1 1 210px;max-width:290px;text-align:left;border-top:3px solid var(--accent);
  padding:12px 4px 0;min-width:180px}
.cc-term{font-family:var(--sans);font-size:19px;font-weight:900;color:var(--ink);letter-spacing:-.01em}
.cc-term .cc-en{font-family:var(--sans);font-size:11.5px;font-weight:600;color:var(--muted);margin-left:8px;letter-spacing:0}
.cc-ko{font-size:13px;color:var(--text);margin-top:5px;line-height:1.55}
.cc-basis{margin-top:8px}
.cc-note{font-size:12px;color:var(--muted);margin-top:26px;line-height:1.6}
@media(max-width:640px){.cc-keyword{font-size:44px}.cc-tagline{font-size:22px}}

/* ── 섹션 ─────────────────────────── */
section.sec{margin:52px 0 0;scroll-margin-top:20px}
section.sec>h2{display:flex;align-items:center;gap:12px;margin:0 0 18px;
  font-family:var(--sans);font-size:27px;font-weight:900;color:var(--ink);letter-spacing:-.02em;
  border-bottom:2px solid var(--ink);padding-bottom:12px}
section.sec>h2 .n{display:inline-flex;align-items:center;justify-content:center;
  min-width:28px;height:28px;padding:0 8px;border-radius:7px;
  background:var(--accent);color:#fff;font-size:14px;font-weight:800;flex:0 0 auto}
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
.law-diag{margin-top:16px;border-top:1px dashed var(--line,#e0ded9);padding-top:14px}
.law-hd{font-size:12px;font-weight:800;letter-spacing:.04em;color:var(--ink);margin-bottom:10px}
.law-tag{display:inline-block;margin-left:6px;font-size:10px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:4px;padding:1px 6px;vertical-align:middle}
.law-card{background:var(--soft);border-radius:8px;padding:11px 14px;margin-bottom:9px}
.law-site{font-size:11.5px;font-weight:700;color:var(--muted);margin-bottom:7px}
.law-refs{margin-top:10px}
.law-refs-hd{font-size:11px;font-weight:800;letter-spacing:.04em;color:var(--muted);text-transform:uppercase;margin-bottom:6px}
.law-ref,.law-ref-lnk{font-size:12px;line-height:1.5;padding:3px 0;border-bottom:1px dotted var(--line)}
.law-ref>summary{cursor:pointer;color:var(--ink)}
.law-ref-body{margin:6px 0 4px;padding:8px 12px;background:var(--soft);border-radius:6px;font-size:11.5px;color:var(--muted);white-space:pre-wrap;line-height:1.6}
.law-ref a,.law-ref-lnk a{color:var(--accent);text-decoration:none}
.law-ref a:hover,.law-ref-lnk a:hover{text-decoration:underline}

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

/* ── 대지 근거 배치 (다이어그램) ── */
.place-syn{font-size:15px;line-height:1.75;color:var(--ink);background:var(--soft);
  border-left:3px solid var(--accent);padding:14px 18px;margin:0 0 16px}
.place-dias{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:8px 0}
.dia-box{border:1px solid var(--line);padding:14px;background:#fff}
.dia-cap{font-size:10.5px;color:var(--faint);text-align:center;margin-top:6px;letter-spacing:.02em}
.pz-tag{font-family:var(--sans);font-size:9.5px;font-weight:700;padding:1px 7px;border-radius:20px;margin-left:8px;vertical-align:middle;white-space:nowrap}
.pz-tag.req{color:#4e7d3e;background:#eef5ea;border:1px solid #cfe3c0}
.pz-tag.inf{color:var(--ai);background:#eaf1f7;border:1px solid #cfe0ee}
.pz.req{background:#fbfcfa}
.lg-req{color:#4e7d3e;font-weight:600}.lg-inf{color:var(--ai);font-weight:600}
.plan-wrap{border:1px solid var(--line);padding:14px;position:relative}
.plan-compass{font-family:var(--sans);font-size:10.5px;font-weight:700;color:var(--muted);margin-bottom:8px;letter-spacing:.08em}
.plan-grid{display:grid;grid-template-columns:1fr 1fr 1fr;grid-auto-rows:1fr;gap:5px;aspect-ratio:1/1}
.plan-cell{border:1px dashed var(--line);border-radius:5px;padding:5px;display:flex;flex-direction:column;gap:3px;
  min-height:0;background:#fcfcfb;position:relative}
.plan-cell.has{background:#fff;border-style:solid}
.plan-pos{font-family:var(--sans);font-size:8.5px;font-weight:700;color:var(--faint);letter-spacing:.05em}
.zt{display:inline-flex;align-items:center;gap:4px;font-size:10px;line-height:1.25;color:var(--ink);
  border:1px solid var(--line);border-left-width:2px;border-radius:3px;padding:2px 5px;background:#fff}
.zdot{width:6px;height:6px;border-radius:50%;flex:0 0 auto}
.sect-wrap{border:1px solid var(--line);padding:14px;display:flex;flex-direction:column;gap:6px}
.sect-band{display:flex;align-items:flex-start;gap:10px;padding:8px 4px;border-bottom:1px dashed var(--line);min-height:40px}
.sect-band:last-of-type{border-bottom:none}
.sect-band.sect-ground{border-bottom:2px solid var(--ink)}
.sect-lv{font-family:var(--sans);font-size:11px;font-weight:700;color:var(--muted);flex:0 0 40px;padding-top:2px}
.sect-zs{display:flex;flex-wrap:wrap;gap:5px;flex:1}
.place-snote{font-size:12.5px;color:var(--muted);margin:10px 0 2px}
.place-snote b{color:var(--accent);font-family:var(--sans);font-size:11px;letter-spacing:.04em}
.place-legend{font-size:11px;color:var(--muted);margin:14px 0 10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.place-site{margin:6px 0 18px;padding-top:4px}
.place-site-hd{font-family:var(--sans);font-size:12px;font-weight:800;letter-spacing:.04em;color:var(--accent);
  border-bottom:1.5px solid var(--accent);padding-bottom:4px;margin:0 0 10px}
.place-zones{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pz{border:1px solid var(--line);border-left:3px solid var(--accent);padding:11px 14px;background:#fff}
.pz-head{font-size:14px;font-weight:700;color:var(--ink);line-height:1.4}
.pz-num{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:5px;
  color:#fff;font-family:var(--sans);font-size:11px;font-weight:800;margin-right:8px;vertical-align:middle;flex:0 0 auto}
.pz-loc{font-family:var(--sans);font-size:10px;font-weight:700;color:#fff;background:var(--muted);
  border-radius:3px;padding:1px 6px;margin-right:7px;vertical-align:middle;letter-spacing:.02em}
.pz-why{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:5px}
.pz-draws{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}
.draw-chip{font-family:var(--sans);font-size:10px;font-weight:600;border-radius:3px;padding:2px 7px;border:1px solid}
.draw-chip.d-site{color:#5a8a3e;border-color:#cfe3c0;background:#eef5ea}
.draw-chip.d-law{color:#2a6496;border-color:#cfe0ee;background:#eaf1f7}
.draw-chip.d-prog{color:#7a3a8e;border-color:#e0cfe8;background:#f4eef7}
.draw-chip.d-score{color:var(--accent);border-color:#f3c2c6;background:#fdf2f3}
.draw-chip.d-spec{color:#b7791f;border-color:#eeddc0;background:#fdf7ea}
.draw-chip.d-etc{color:var(--muted);border-color:var(--line);background:var(--soft)}

/* ── 결정 요약 cockpit ── */
.cockpit{margin:26px 0 8px;border:2px solid var(--ink)}
.cok-head{background:var(--ink);color:#fff;padding:14px 22px;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
.cok-h-l{font-family:var(--sans);font-size:13px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;flex:0 0 auto}
.cok-h-r{font-size:12.5px;color:#c9c9c9;line-height:1.5}
.cok-h-r b{color:#fff}
.cok-grid{display:grid;grid-template-columns:repeat(3,1fr)}
.cok-cell{display:block;text-decoration:none;color:inherit;padding:16px 18px;border-right:1px solid var(--line);
  border-bottom:1px solid var(--line);background:#fff;transition:background .12s}
.cok-cell:nth-child(3n){border-right:none}
.cok-cell:hover{background:var(--soft)}
.cok-label{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.08em;color:var(--accent);text-transform:uppercase}
.cok-value{font-size:15px;font-weight:700;color:var(--ink);line-height:1.45;margin:7px 0 8px;min-height:44px}
.cok-value.big{color:var(--accent)}
.cok-how{font-size:11px;color:var(--muted);border-top:1px dashed var(--line);padding-top:7px}

/* ── 권장 종합안 히어로 ── */
.rec{display:grid;grid-template-columns:150px 1fr;border:2px solid var(--ink);background:#fff;margin:4px 0 12px}
.rec-top{grid-column:1 / -1;display:flex;align-items:center;gap:10px;background:var(--ink);padding:11px 20px}
.rec-eyebrow{font-family:var(--sans);font-size:12px;font-weight:800;letter-spacing:.16em;color:#fff;text-transform:uppercase}
.rec-top .ai-badge{margin-left:auto}
.rec-mass{display:flex;align-items:center;justify-content:center;background:var(--soft);border-right:1px solid var(--line);padding:18px}
.rec-mass svg{width:104px;height:94px}
.rec-body{padding:20px 26px}
.rec-bb-label{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.1em;color:var(--accent);text-transform:uppercase}
.rec-bb{font-family:var(--sans);font-size:22px;font-weight:800;color:var(--ink);letter-spacing:-.01em;line-height:1.3;margin:3px 0 8px}
.rec-why{font-size:14px;color:var(--muted);line-height:1.75}
.rec-why b{color:var(--ink)}
.rec-grafts-label{font-family:var(--sans);font-size:11px;font-weight:700;color:var(--accent);margin:16px 0 8px}
.rec-grafts{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.rec-graft{border:1px solid var(--line);border-left:2px solid var(--accent);padding:10px 13px;background:var(--soft)}
.rg-name{font-size:14px;font-weight:700;color:var(--ink)}
.rg-gain{font-size:12px;color:var(--muted);margin-top:2px}
.rec-cond{margin-top:14px;font-size:12.5px;color:var(--muted);line-height:1.6}
.rec-cond .k{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--faint);
  text-transform:uppercase;margin-right:8px;border:1px solid var(--line);padding:2px 7px;border-radius:20px}
.rec-note{margin-top:16px;padding-top:13px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);line-height:1.65}
.rec-note b{color:var(--ink)}

@media print{.wrap{padding:0}body{font-size:12px}section.sec{break-inside:avoid}nav.top{display:none}}
@media(max-width:720px){
  .wrap{padding:32px 20px 64px;margin:0}
  nav.top .ttl{display:none}
  nav.top .inner{padding:8px 18px}
  header.doc h1{font-size:32px}
  section.sec>h2{font-size:22px}
  .dir-fields{grid-template-columns:1fr}
  .dir-card-svgbox{display:none}
  .waffle-wrap{flex-direction:column}
  .site-fields{grid-template-columns:1fr}
  .site-thumb{width:100%}
  .hero img{height:220px}
  .cok-grid{grid-template-columns:1fr}.cok-cell{border-right:none}
  .rec{grid-template-columns:1fr}.rec-mass{border-right:none;border-bottom:1px solid var(--line)}
  .rec-grafts{grid-template-columns:1fr}
  .place-dias{grid-template-columns:1fr}.place-zones{grid-template-columns:1fr}
}
"""

from services.report_theme import THEME_VARS
# 제안서 = 디자인 기준. :root 를 공유 토큰 단일 소스로 대체 (값 동일, 드리프트 차단).
_PROPOSAL_CSS = _PROPOSAL_CSS.replace("/*__THEME__*/", THEME_VARS)

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


def _concept_cover_html(proposal: dict) -> str:
    """concept_hook → 덱 오프닝 '컨셉 표지' 슬라이드. 없으면 ''.

    한 단어 파르티(keyword) + 3축 슬로건(tagline) + 각 축 ko/en + 근거 앵커.
    'AI 제안 시안'으로 명시(사실 아님) — 팀이 갈아끼울 출발점. 색은 건원 RED 토큰.
    LLM 이 근거 못 달아 concept_hook 을 생략하면 렌더도 skip(graceful).
    """
    hook = proposal.get("concept_hook")
    if not isinstance(hook, dict):
        return ""
    keyword = (hook.get("keyword") or "").strip()
    if not keyword:
        return ""
    axes = [a for a in (hook.get("axes") or []) if isinstance(a, dict) and (a.get("term") or "").strip()]

    tagline = (hook.get("tagline") or "").strip()
    if not tagline and axes:
        tagline = " · ".join(_esc(a.get("term")) for a in axes)
    else:
        tagline = _esc(tagline)

    ax_rows = []
    for a in axes:
        term = _esc((a.get("term") or "").strip())
        ko = _esc((a.get("ko") or "").strip())
        en = (a.get("en") or "").strip()
        en_html = f'<span class="cc-en">{_esc(en)}</span>' if en else ""
        basis_html = _basis_html(a.get("basis"))
        ax_rows.append(
            '<div class="cc-axis">'
            f'<div class="cc-term">{term}{en_html}</div>'
            + (f'<div class="cc-ko">{ko}</div>' if ko else "")
            + (f'<div class="cc-basis">{basis_html}</div>' if basis_html else "")
            + '</div>'
        )
    axes_html = f'<div class="cc-axes">{"".join(ax_rows)}</div>' if ax_rows else ""

    return (
        '<section class="cc-cover">'
        f'<div class="cc-eyebrow">{_AI_BADGE}<span>PROJECT VALUE · 컨셉 시안</span></div>'
        f'<div class="cc-keyword">{_esc(keyword)}</div>'
        + (f'<div class="cc-tagline">{tagline}</div>' if tagline else "")
        + axes_html
        + '<div class="cc-note">AI가 배점·대지 근거 위에서 압축한 <b>컨셉 시안</b>입니다 — '
          '확정된 컨셉이 아니라 설계팀이 갈아끼우는 출발점입니다.</div>'
        '</section>'
    )


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


def _law_diagnosis_html(site_context: dict | None) -> str:
    """_site_context.law_diagnosis (건축법 진단 골격) → '법적 골격' 서브패널. 없으면 ''.

    정북 일조사선 후퇴·가로구역 최고높이·건폐/용적 한도·심의 필수 — brief 에 없던 법적 매스
    골격을 사실로 노출. low_confidence·limit_mismatch 는 주의 밴드로. (LLM 0, 진단 숫자 렌더만)
    """
    diags = [d for d in ((site_context or {}).get("law_diagnosis") or []) if isinstance(d, dict)]
    if not diags:
        return ""

    def _num(v, unit=""):
        return (f"{v:g}{unit}" if isinstance(v, (int, float)) else "")

    cards = ""
    any_low = False
    for d in diags:
        env = d.get("envelope") or {}
        hs = d.get("height_solar") or {}
        rows = []
        # 정북 일조 — 모드 A(용량)는 실제 형상이 없어 north_setback_m(실이격)이 대개 null.
        #   필요이격(shadow_min_setback_m)·적용여부(shadow_applies)·규칙(shadow_setback_rule)을 우선 노출.
        nact, smin = hs.get("north_setback_m"), hs.get("shadow_min_setback_m")
        rule = (hs.get("shadow_setback_rule") or "").strip()
        solar = ""
        if isinstance(nact, (int, float)):
            solar = f"실이격 {nact:g}m"
        elif isinstance(smin, (int, float)):
            solar = f"필요이격 {smin:g}m"
        elif hs.get("shadow_applies"):
            solar = "적용(수동검토 필요)"
        if solar:
            if rule:
                solar += " · " + (rule[:120] + "…" if len(rule) > 120 else rule)
            rows.append(("정북 일조", solar))
        rh = _num(hs.get("road_height_limit_m"), "m")
        if rh:
            rows.append(("가로구역 최고높이", rh))
        bl = _num(env.get("bcr_limit_pct"), "%")
        fl = _num(env.get("far_limit_pct"), "%")
        if bl or fl:
            rows.append(("건폐/용적 한도", " · ".join(x for x in (f"건폐 {bl}" if bl else "", f"용적 {fl}" if fl else "") if x)))
        reviews = [r for r in (d.get("reviews_required") or []) if isinstance(r, dict) and (r.get("name") or "").strip()]
        if reviews:
            rows.append(("필수 심의", " · ".join(_esc(r.get("name")) for r in reviews)))
        if not rows:
            continue
        body = "".join(
            f'<div class="site-field"><div class="sfk">{_esc(k)}</div><div class="sfv">{_esc(v)}</div></div>'
            for k, v in rows
        )
        head = _esc((d.get("site_id") or d.get("address") or "").strip())
        warn = ""
        mm = [m for m in (d.get("limit_mismatch") or []) if isinstance(m, dict)]
        if mm:
            bits = " · ".join(
                f'{_esc(m.get("field"))} brief {_num(m.get("brief_pct"), "%")} ↔ 진단 {_num(m.get("diagnose_limit_pct"), "%")}'
                for m in mm
            )
            warn = f'<div class="site-note" style="margin-top:6px">⚠ brief 수치 재확인 — {bits}</div>'
        if d.get("low_confidence"):
            any_low = True
        cards += (
            '<div class="law-card">'
            + (f'<div class="law-site">{head}</div>' if head else "")
            + f'<div class="site-fields">{body}</div>' + warn + '</div>'
        )

    if not cards:
        return ""

    # 관련 법조문 각주 (Phase 3 — arch-law-graph 원문 있으면 접기, 없으면 law.go.kr 링크만).
    #   found=false/원문 없음 = 링크만(인용 금지 가드). refs 는 전 부지 dedup.
    law_texts = (site_context or {}).get("law_texts") or {}
    refs, _seen_ref = [], set()
    for d in diags:
        for ref in (d.get("law_refs") or []):
            nm = (ref.get("name") or "").strip() if isinstance(ref, dict) else ""
            if nm and nm not in _seen_ref:
                _seen_ref.add(nm)
                refs.append(ref)
    refs_html = ""
    if refs:
        items = ""
        for ref in refs:
            nm, url = ref.get("name"), ref.get("url")
            link = (f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(nm)}</a>'
                    if url else _esc(nm))
            tx = law_texts.get(nm) if isinstance(law_texts, dict) else None
            content = (tx or {}).get("content") if isinstance(tx, dict) else None
            if content and str(content).strip():
                excerpt = str(content).strip()
                excerpt = excerpt[:400] + ("…" if len(excerpt) > 400 else "")
                items += (f'<details class="law-ref"><summary>{link}</summary>'
                          f'<div class="law-ref-body">{_esc(excerpt)}</div></details>')
            else:
                items += f'<div class="law-ref-lnk">{link}</div>'
        refs_html = f'<div class="law-refs"><div class="law-refs-hd">관련 법조문</div>{items}</div>'

    note = "건축법 자동진단(arch-law-diagnose) 되받기 — 허용 한도로 최대 매스 역산 후 진단한 법적 골격."
    if any_low:
        note += " 일부 값은 자동조회·추정(신뢰도 낮음) — 현장·원문 확인 필요."
    return (
        '<div class="law-diag">'
        '<div class="law-hd">법적 골격 <span class="law-tag">건축법 진단</span></div>'
        + cards
        + refs_html
        + f'<div class="site-note" style="margin-top:8px">⚠ {_esc(note)} 정밀 일조사선·층수는 미포함(참고).</div>'
        '</div>'
    )


def _site_context_html(site_context: dict | None, image_b64: str = "", compact: bool = False) -> str:
    """_site_context (VWorld 위성 + AI 판독 + 건축법 진단 골격) → 대지·맥락 섹션. 데이터 없으면 ''.

    compact=True 면 이미지·요약을 히어로가 이미 보여주므로 생략(필드·주의만).
    """
    sc = site_context or {}
    analysis = sc.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}

    law_html = _law_diagnosis_html(sc)
    summary = "" if compact else (analysis.get("overall_summary") or "").strip()
    matched = (sc.get("matched_address") or sc.get("address_input") or "").strip()
    has_fields = any((analysis.get(k) or "").strip() for k, _ in _SITE_FIELDS)
    if not (summary or has_fields or law_html or (image_b64 and not compact)):
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
    # vision 판독 주의 문구는 vision 콘텐츠(요약·필드·이미지)가 있을 때만.
    has_vision = bool(summary or fields or (image_b64 and not compact))
    note = ""
    if has_vision:
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
        + law_html
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

# ── 권장 종합안 + 결정 요약 (결정론, LLM 0) ──────────────────────────

def _dir_name(d: dict) -> str:
    """direction 필드에서 짧은 컨셉명 (—/앞부분)."""
    return (d.get("direction") or "").split("—")[0].strip()


def _recommend(proposal: dict) -> dict | None:
    """5안 중 권장 종합안 도출(결정론): 최고 배점축을 겨냥한 안을 뼈대로,
    볼륨·면적을 깎지 않는 안을 접목, 나머지는 조건부. design_directions 가 없거나
    'N/A(입찰 등)'면 None."""
    dds = [d for d in (proposal.get("design_directions") or []) if isinstance(d, dict)]
    focus = [f for f in (proposal.get("scoring_focus") or []) if isinstance(f, dict)]
    ranked = sorted([f for f in focus if isinstance(f.get("rank"), (int, float))],
                    key=lambda f: f["rank"])
    if len(dds) < 2 or not ranked:
        return None
    # '해당 없음'류(입찰 등) 방어 — 실제 컨셉명이 아니면 스킵
    if any(k in _dir_name(dds[0]) for k in ("해당 없음", "해당없음", "N/A", "없음")):
        return None
    top = ranked[0]
    topcat = top.get("category") or ""
    toppts = top.get("points")

    def _txt(d):
        return f'{d.get("addresses","")} {d.get("scoring_play","")} {d.get("direction","")}'

    scored = []
    for i, d in enumerate(dds):
        s = (3 if topcat and topcat in _txt(d) else 0)
        if isinstance(toppts, (int, float)) and str(int(toppts)) in _txt(d):
            s += 2
        scored.append((s, -i, i))
    backbone = max(scored)[2]

    grafts, conditional = [], []
    for i, d in enumerate(dds):
        if i == backbone:
            continue
        tr = d.get("tradeoffs") or ""
        reduces = ("축소" in tr) or ("연면적" in tr) or ("볼륨" in tr and "줄" in tr)
        if not reduces and len(grafts) < 2:
            grafts.append(i)
        else:
            conditional.append(i)
    return {"backbone": backbone, "grafts": grafts, "conditional": conditional,
            "topcat": topcat, "toppts": toppts, "topw": top.get("weight_pct"), "dds": dds}


def _recommended_synthesis_html(proposal: dict) -> str:
    """권장 종합안 히어로 카드 (설계 접근 섹션 최상단). 없으면 ''."""
    rec = _recommend(proposal)
    if not rec:
        return ""
    dds = rec["dds"]
    bb = dds[rec["backbone"]]

    def _gain(d):
        a = (d.get("addresses") or "")
        return a.split(",")[0].split("과 ")[0].strip()[:44]

    graft_html = "".join(
        f'<div class="rec-graft"><div class="rg-name">{_esc(_dir_name(dds[i]))}</div>'
        f'<div class="rg-gain">{_esc(_gain(dds[i]))} 방어·가점</div></div>'
        for i in rec["grafts"]
    )
    cond = " · ".join(_esc(_dir_name(dds[i])) for i in rec["conditional"])
    topw = int(rec["topw"]) if isinstance(rec["topw"], (int, float)) else ""
    return (
        '<div class="rec">'
        f'<div class="rec-top"><span class="rec-eyebrow">권장 종합안 · RECOMMENDED</span>{_AI_BADGE}</div>'
        f'<div class="rec-mass">{_MASS_SVGS[rec["backbone"] % len(_MASS_SVGS)]}</div>'
        '<div class="rec-body">'
        '<div class="rec-bb-label">뼈대</div>'
        f'<div class="rec-bb">「{_esc(_dir_name(bb))}」 을 중심으로</div>'
        f'<p class="rec-why">배점이 <b>{_esc(rec["topcat"])} {_esc(rec["toppts"])}점'
        f'{f"(전체 {topw}%)" if topw != "" else ""}</b>에 쏠려 있어, 이 안이 최대 승부처를 정면으로 '
        '가져간다. 여기에 서로 상충하지 않는 안을 접목한다.</p>'
        + (f'<div class="rec-grafts-label">+ 접목 (득점축이 달라 양립 가능)</div>'
           f'<div class="rec-grafts">{graft_html}</div>' if graft_html else "")
        + (f'<div class="rec-cond"><span class="k">조건부 옵션</span>{cond} — 심의·부지 여건에 따라 선택 적용</div>' if cond else "")
        + '<div class="rec-note">5개 대안을 비교한 결과의 <b>권장 조합</b>입니다. 상충하는 전제는 '
          '뭉치지 않았으며, <b>최종 컨셉 선택은 설계팀</b>의 몫입니다.</div>'
        '</div></div>'
    )


def _decision_cockpit_html(proposal: dict, bid_structure: dict | None = None) -> str:
    """결정 요약(Decision Brief) — 흩어진 판단을 6칸으로. 결정론, 이미 있는 값만.

    각 칸 = (라벨, 값, 어떻게 나왔나, 앵커). 최소 요약 하나라도 있어야 렌더.
    """
    def _first_sentence(t):
        t = (t or "").strip()
        for sep in [" — ", ". ", "—"]:
            if sep in t:
                return t.split(sep)[0].strip().rstrip(".")
        return t

    def _trunc(t, n=48):
        t = (t or "").strip()
        return (t[:n].rstrip(" ,·") + "…") if len(t) > n else t

    wt = [w for w in (proposal.get("win_themes") or []) if isinstance(w, dict)]
    pr = sorted([p for p in (proposal.get("priorities") or []) if isinstance(p, dict)],
                key=lambda p: p.get("rank") if isinstance(p.get("rank"), (int, float)) else 99)
    risks = [r for r in (proposal.get("risks") or []) if isinstance(r, dict)]
    hi = next((r for r in risks if r.get("severity") == "high"), risks[0] if risks else None)
    conf = {"high": "높음", "medium": "보통", "low": "낮음"}.get(proposal.get("data_confidence"), "")
    rec = _recommend(proposal)
    rec_name = _dir_name(rec["dds"][rec["backbone"]]) if rec else ""

    cells = []
    es = _first_sentence(proposal.get("executive_summary", ""))
    if es:
        cells.append(("발주 의도", _trunc(es, 50), "배점·강조 분포로 해독", "summary"))
    if wt:
        cells.append(("승부처", _trunc(_first_sentence(wt[0].get("theme", "")), 40), "배점 1순위 + 반복 강조", "themes"))
    if rec_name:
        cells.append(("권장 방향", _trunc(rec_name, 36), "최고 배점축 겨냥 + 접목", "directions", True))
    elif bid_structure:
        cells.append(("배점 구조", "사업수행능력 vs 가격 (2층)", "입찰 — 연면적별 차등", "scoring", True))
    if hi:
        cells.append(("최대 리스크", _trunc(_first_sentence(hi.get("risk", "")), 42), "실격·심의 등 방어 필수", "risks"))
    if pr:
        w = pr[0].get("scoring_weight")
        val = _trunc(pr[0].get("focus", "").split("(")[0], 32) + (f" ({w})" if w else "")
        cells.append(("착수 1순위", val, "배점 무게중심 순", "priorities"))
    if conf:
        cells.append(("근거 신뢰도", conf, "판단이 선 데이터", "scoring"))

    cells = [c for c in cells if c[1]]
    if len(cells) < 3:
        return ""

    grid = ""
    for c in cells:
        lb, val, how, href = c[0], c[1], c[2], c[3]
        big = " big" if (len(c) > 4 and c[4]) else ""
        grid += (f'<a class="cok-cell" href="#{href}"><div class="cok-label">{_esc(lb)}</div>'
                 f'<div class="cok-value{big}">{_esc(val)}</div>'
                 f'<div class="cok-how">{_esc(how)}</div></a>')
    return (
        '<section class="cockpit"><div class="cok-head">'
        '<div class="cok-h-l">결정 요약 · DECISION BRIEF</div>'
        '<div class="cok-h-r">AI가 지침서를 읽고 <b>판단한 결론</b> — 각 칸은 아래 근거 섹션으로 연결됩니다. 최종 결정은 설계팀.</div>'
        f'</div><div class="cok-grid">{grid}</div></section>'
    )


_ZONE_COLORS = ["#e60012", "#2a6496", "#5a8a3e", "#c47b00", "#7a3a8e", "#3a8a8e", "#c45a00", "#555"]
_PLAN_ORDER = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"]
_LEVEL_ORDER = ["상층", "중층", "저층", "지하"]
_DRAW_CLS = {"대지": "d-site", "법": "d-law", "프로그램": "d-prog", "배점": "d-score", "특수조건": "d-spec", "특수": "d-spec"}


def _draw_chip(s: str) -> str:
    txt = str(s).strip()
    key = txt.split(":")[0].strip()
    cls = _DRAW_CLS.get(key, "d-etc")
    return f'<span class="draw-chip {cls}">{_esc(txt)}</span>'


def _zreq(z: dict) -> bool:
    return z.get("required") in (True, "true", "True", 1)


_PLAN_XY = {  # 320×320 viewBox, 대지 rect 46..274, 방위 앵커 중심
    "N": (160, 86), "S": (160, 234), "E": (234, 160), "W": (86, 160),
    "NE": (226, 94), "NW": (94, 94), "SE": (226, 226), "SW": (94, 226), "C": (160, 160),
}


def _num_marker(cx, cy, color, num, required):
    """번호 마커(항상 읽힘) — 채움=필수(사실), 점선=AI 추론."""
    fill = color if required else "#fff"
    txt = "#fff" if required else color
    dash = "" if required else ' stroke-dasharray="2.5 2"'
    return (f'<g><rect x="{cx-11:.0f}" y="{cy-11:.0f}" width="22" height="22" rx="4" fill="{fill}" '
            f'stroke="{color}" stroke-width="1.6"{dash}/>'
            f'<text x="{cx:.0f}" y="{cy+4:.0f}" text-anchor="middle" font-size="11.5" font-weight="700" '
            f'font-family="Montserrat,sans-serif" fill="{txt}">{num}</text></g>')


def _zone_plan_svg(zones: list, zc: dict) -> str:
    """조닝 SVG: 방위 앵커에 번호 마커를 겹치지 않게 배치 (부지 1개분)."""
    by_plan: dict[str, list] = {}
    for z in zones:
        p = (z.get("plan") or "C").strip().upper()
        by_plan.setdefault(p if p in _PLAN_XY else "C", []).append(z)
    marks = ""
    for pos, zs in by_plan.items():
        cx, cy = _PLAN_XY[pos]
        n = len(zs)
        for i, z in enumerate(zs):          # 한 방위 여러 개면 가로로 펼침(겹침 방지)
            ox = cx + (i - (n - 1) / 2) * 26
            marks += _num_marker(ox, cy, zc[id(z)], z["_num"], _zreq(z))
    return (
        '<svg viewBox="0 0 320 320" width="100%" style="max-width:340px;display:block;margin:0 auto">'
        '<rect x="46" y="46" width="228" height="228" fill="#fbfbfa" stroke="#141414" stroke-width="1.5"/>'
        '<text x="160" y="34" text-anchor="middle" font-size="12" font-weight="700" font-family="Montserrat,sans-serif" fill="#6f6b66">N ▲</text>'
        '<text x="160" y="296" text-anchor="middle" font-size="10" fill="#a9a5a0">S</text>'
        '<text x="30" y="164" text-anchor="middle" font-size="10" fill="#a9a5a0">W</text>'
        '<text x="290" y="164" text-anchor="middle" font-size="10" fill="#a9a5a0">E</text>'
        + marks + '</svg>'
    )


def _zone_sect_svg(zones: list, zc: dict) -> str:
    """단면 SVG: 층대 밴드에 번호 마커를 좌→우로 나열 (부지 1개분)."""
    _lvy = {"상층": 24, "중층": 70, "저층": 116, "지하": 178}
    band_rects = ""
    for lv, y in _lvy.items():
        band_rects += (f'<rect x="44" y="{y}" width="252" height="38" fill="#f6f4f1" stroke="#e0ded9"/>'
                       f'<text x="52" y="{y+23}" font-size="11" font-weight="700" font-family="Montserrat,sans-serif" fill="#6f6b66">{_esc(lv)}</text>')
    smarks = ""
    for lv, y in _lvy.items():
        zs = [z for z in zones if (z.get("level") or "저층").strip() == lv]
        x = 108
        for z in zs:
            smarks += _num_marker(x, y + 19, zc[id(z)], z["_num"], _zreq(z))
            x += 28
    return (
        '<svg viewBox="0 0 320 224" width="100%" style="max-width:360px;display:block;margin:0 auto">'
        + band_rects
        + '<line x1="38" y1="166" x2="302" y2="166" stroke="#141414" stroke-width="2"/>'
        '<text x="298" y="163" text-anchor="end" font-size="8" fill="#a9a5a0">G.L</text>'
        + smarks + '</svg>'
    )


def _zone_org_svg(zones: list, zc: dict) -> str:
    """OMA식 프로그램 조직 스택 — 층 순서(상층→지하)로 프로그램을 쌓되 지침서 필수 존은
    본체 슬래브(플랫폼), AI 추론 존은 옆으로 밀어낸 in-between(aura) 탭으로 구분한다.

    존별 면적이 없어 **면적 비례가 아니라 조직 다이어그램**(슬래브 높이 균일). 사실(필수)↔
    제안(추론)을 platform/aura 로 2층 분리 — required 플래그가 근거라 정직한 분류. 번호·색은
    다른 배치 다이어그램(plan/section)과 통합(zc·_num 재사용).
    """
    def _lv(z):
        return (z.get("level") or "저층").strip()

    def _clip(s, n):
        s = str(s or "")
        return s if len(s) <= n else s[:n - 1] + "…"

    rank = {lv: i for i, lv in enumerate(_LEVEL_ORDER)}
    idx = {id(z): i for i, z in enumerate(zones)}
    ordered = sorted(zones, key=lambda z: (rank.get(_lv(z), 2), idx[id(z)]))
    has_plat = any(_zreq(z) for z in ordered)
    main = [z for z in ordered if _zreq(z)] if has_plat else ordered
    side = [z for z in ordered if not _zreq(z)] if has_plat else []

    BX, BW, TOP, SLAB_H, GAP = 44, 150, 44, 34, 5
    FONT = "Montserrat,sans-serif"
    tx = BX + BW

    slabs, lvl_ys, y = "", {}, TOP
    for z in main:
        col = zc[id(z)]
        lv = _lv(z)
        lvl_ys.setdefault(lv, []).append(y + SLAB_H / 2)
        nm = _esc(_clip(f'{z["_num"]}. {z.get("program") or ""}', 15))
        cy = y + SLAB_H / 2 + 4
        if _zreq(z):
            slabs += (f'<rect x="{BX}" y="{y}" width="{BW}" height="{SLAB_H}" rx="3" fill="{col}"/>'
                      f'<text x="{BX + 9}" y="{cy:.0f}" font-size="11.5" font-weight="700" '
                      f'font-family="{FONT}" fill="#fff">{nm}</text>')
        else:  # 플랫폼 없는 케이스: aura 를 본체에 점선 슬래브로
            slabs += (f'<rect x="{BX}" y="{y}" width="{BW}" height="{SLAB_H}" rx="3" fill="#fff" '
                      f'stroke="{col}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                      f'<text x="{BX + 9}" y="{cy:.0f}" font-size="11" font-weight="700" '
                      f'font-family="{FONT}" fill="{col}">{nm}</text>')
        y += SLAB_H + GAP
    main_bottom = y

    lvlab = ""
    for lv, ys in lvl_ys.items():
        my = sum(ys) / len(ys)
        lvlab += (f'<text x="40" y="{my + 3:.0f}" text-anchor="end" font-size="9.5" '
                  f'font-family="{FONT}" fill="#a9a5a0">{_esc(lv)}</text>')

    cursor, tabs = TOP, ""
    for z in side:
        col = zc[id(z)]
        ys = lvl_ys.get(_lv(z))
        anchor = (sum(ys) / len(ys)) if ys else (TOP + (main_bottom - TOP) / 2)
        ty = max(anchor, cursor + 20)
        cursor = ty
        nm = _esc(_clip(f'{z["_num"]}. {z.get("program") or ""}', 16))
        tabs += (f'<line x1="{tx}" y1="{anchor:.0f}" x2="{tx + 16}" y2="{ty:.0f}" stroke="{col}" '
                 f'stroke-width="1" stroke-dasharray="3 2"/>'
                 f'<rect x="{tx + 17}" y="{ty - 8:.0f}" width="12" height="16" rx="2" fill="#fff" '
                 f'stroke="{col}" stroke-width="1.3" stroke-dasharray="2.5 2"/>'
                 f'<text x="{tx + 34}" y="{ty + 3:.0f}" font-size="10.5" font-family="{FONT}" '
                 f'fill="{col}">{nm}</text>')

    svg_h = max(main_bottom + 12, cursor + 18)
    hd = ('<text x="119" y="26" text-anchor="middle" font-size="10.5" font-family="' + FONT
          + '" fill="#6f6b66">본체=지침서 필수(플랫폼) · 옆=AI 제안(in-between)</text>')
    return (f'<svg viewBox="0 0 384 {svg_h:.0f}" width="100%" '
            f'style="max-width:440px;display:block;margin:0 auto" '
            f'role="img" aria-label="프로그램 조직 다이어그램">'
            + hd + lvlab + slabs + tabs + '</svg>')


def _zone_diagrams(zones: list, zc: dict) -> str:
    return (
        f'<div class="dia-box" style="grid-column:1/-1">{_zone_org_svg(zones, zc)}'
        f'<div class="dia-cap">프로그램 조직 · OMA식 (본체=지침서 필수 플랫폼 · 옆=AI 제안 in-between · 층 순서 · 면적 비례 아님)</div></div>'
        f'<div class="dia-box">{_zone_plan_svg(zones, zc)}<div class="dia-cap">개념 조닝 (방위 · 번호는 아래 목록)</div></div>'
        f'<div class="dia-box">{_zone_sect_svg(zones, zc)}<div class="dia-cap">개념 단면 (층대 · 번호는 아래 목록)</div></div>'
    )


def _zone_cards(zones: list, zc: dict) -> str:
    """번호 존 카드 (필수/추론 + 교차 근거 색칩)."""
    out = ""
    for z in zones:
        draws = "".join(_draw_chip(x) for x in (z.get("draws_on") or []) if str(x).strip())
        req = _zreq(z)
        tag = ('<span class="pz-tag req">지침서 필수</span>' if req
               else '<span class="pz-tag inf">AI 추론</span>')
        col = zc[id(z)]
        out += (
            f'<div class="pz{" req" if req else ""}" style="border-left-color:{col}">'
            f'<div class="pz-head"><span class="pz-num" style="background:{col}">{z["_num"]}</span>'
            f'<span class="pz-loc">{_esc(z.get("plan"))}·{_esc(z.get("level"))}</span>'
            f'{_esc(z.get("program"))}{tag}</div>'
            + (f'<div class="pz-why">{_esc(z.get("why"))}</div>' if (z.get("why") or "").strip() else "")
            + (f'<div class="pz-draws">{draws}</div>' if draws else "")
            + '</div>'
        )
    return out


_PLACE_LEGEND = (
    '<div class="place-legend"><b>마커:</b> <span class="lg-req">■ 채움=지침서 필수(사실)</span> '
    '<span class="lg-inf">▢ 점선=AI 추론(제안)</span> &nbsp;|&nbsp; <b>근거 색:</b> '
    '<span class="draw-chip d-site">대지</span><span class="draw-chip d-law">법</span>'
    '<span class="draw-chip d-prog">프로그램</span><span class="draw-chip d-score">배점</span>'
    '<span class="draw-chip d-spec">특수조건</span> — 여러 색 = 근거 교차</div>'
)


def _placement_strategy_html(proposal: dict) -> str:
    """대지 근거 배치 → SVG 조닝(방위)·단면(층대) 다이어그램(번호 마커) + 번호 존 카드. 없으면 ''.

    다부지(zone.site 서로 다름)면 **부지별로 다이어그램·카드를 분리**한다 — 한 사각형에 두 부지를
    섞으면 방위(N/S/E/W)가 뭉개지므로. 번호는 전체 통합(1..N), 색도 통합. 단부지면 종전과 동일.
    required=true(지침서 명시)=채운 마커, false(AI 추론)=점선. draws_on 색으로 교차 근거 시각화.
    """
    ps = proposal.get("placement_strategy")
    if not isinstance(ps, dict):
        return ""
    zones = [z for z in (ps.get("zones") or []) if isinstance(z, dict) and (z.get("program") or "").strip()]
    if not zones:
        return ""
    # 번호(1-base) + 색 — 부지 분리와 무관하게 전체 통합(카드↔다이어그램 대조 유지)
    for i, z in enumerate(zones):
        z["_num"] = i + 1
    zc = {id(z): _ZONE_COLORS[i % len(_ZONE_COLORS)] for i, z in enumerate(zones)}

    # ── 부지별 그룹핑 (등장 순서 보존). site 라벨이 2개 이상 실제로 갈릴 때만 분리 ──
    groups: dict[str, list] = {}
    order: list[str] = []
    for z in zones:
        k = (z.get("site") or "").strip()
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(z)
    multi = len([k for k in order if k]) > 1

    if multi:
        body = ""
        for k in order:
            zs = groups[k]
            hd = f'<div class="place-site-hd">{_esc(k) if k else "부지 미지정"}</div>'
            body += (
                '<div class="place-site">' + hd
                + '<div class="place-dias">' + _zone_diagrams(zs, zc) + '</div>'
                + f'<div class="place-zones">{_zone_cards(zs, zc)}</div>'
                + '</div>'
            )
    else:
        body = (
            '<div class="place-dias">' + _zone_diagrams(zones, zc) + '</div>'
            + f'<div class="place-zones">{_zone_cards(zones, zc)}</div>'
        )

    syn = (ps.get("synthesis") or "").strip()
    snote = (ps.get("section_note") or "").strip()
    return (
        '<section id="placement" class="sec">'
        '<h2><span class="n">·</span>대지 근거 배치 ' + _AI_BADGE + '</h2>'
        + (f'<div class="place-syn">{_esc(syn)}</div>' if syn else "")
        + (f'<div class="place-snote"><b>단면 원리</b> · {_esc(snote)}</div>' if snote else "")
        + _PLACE_LEGEND
        + body
        + '<div class="caveat">개념 다이어그램 — 방위·층대는 근거 기반 추론(정확한 도면·층수 아님). '
          '<b>지침서가 위치를 명시한 존(필수)은 그대로 반영</b>, 나머지는 AI 배치 제안. 최종 배치는 설계팀.</div>'
        '</section>'
    )


def _bid_structure_html(bid_structure: dict | None) -> str:
    """입찰 2층 배점 구조(_bid_structure) → 섹션. 공모(None)면 ''. (하위 PQ표는 배점 무게중심 와플이 담당)"""
    bs = bid_structure if isinstance(bid_structure, dict) else None
    if not bs:
        return ""
    tl = bs.get("top_layer") or {}
    axes = [a for a in (tl.get("axes") or []) if isinstance(a, dict)]
    if not axes:
        return ""
    basis = tl.get("basis_dimension") or "연면적"

    def _pct(v):
        return f"{float(v):g}" if isinstance(v, (int, float)) else _esc(v)

    rows = ""
    exact = [a for a in axes if a.get("bands") and any(b.get("min_sqm") or b.get("max_sqm") for b in a["bands"])]
    if exact:
        labels = [(b.get("label") or "").split(":")[0].strip() for b in exact[0]["bands"]]
        head = "".join(f'<th>{_esc(l)}</th>' for l in labels)
        for a in axes:
            if a.get("bands") and any(b.get("min_sqm") or b.get("max_sqm") for b in a["bands"]):
                cells = "".join(f'<td>{_pct(b.get("weight_pct"))}%</td>' for b in a["bands"])
            elif a.get("weight_range"):
                lo, hi = a["weight_range"]; cells = f'<td colspan="{max(1,len(labels))}">{_pct(lo)}~{_pct(hi)}%</td>'
            else:
                cells = f'<td colspan="{max(1,len(labels))}">—</td>'
            rows += f'<tr><td>{_esc(a.get("name"))}</td>{cells}</tr>'
        table = f'<table class="dir-matrix"><thead><tr><th>상위 배점 축</th>{head}</tr></thead><tbody>{rows}</tbody></table>'
    else:
        lis = "".join(
            f'<li>{_esc(a.get("name"))} — '
            + (f'{_pct(a["weight_range"][0])}~{_pct(a["weight_range"][1])}%' if a.get("weight_range") else "비율 미확보")
            + '</li>' for a in axes)
        table = f'<ul class="list">{lis}<li class="muted">구간별 상세(%)는 추출에서 확보되지 않음 — 원문 확인 권장.</li></ul>'
    app = (tl.get("applicable") or {})
    note = _esc(app.get("note") or "")
    return (
        '<section id="bidstruct" class="sec">'
        '<h2><span class="n">·</span>2층 배점 구조 <span style="font-size:12px;font-weight:600;color:var(--muted)">· 설계자 선정 입찰</span></h2>'
        f'<div class="summ" style="border:none;padding:0;margin:0 0 10px;font-size:13.5px;color:var(--muted)">'
        f'종합평점 = 사업수행능력평가 × w% + 가격평가 × (100−w)%. w 는 <b>{_esc(basis)}</b> 규모별 차등.</div>'
        + table
        + (f'<div class="site-note" style="margin-top:10px">⚠ {note}</div>' if note else "")
        + '</section>'
    )


def to_proposal_html(
    proposal: dict,
    brief_name: str = "",
    facility_label: str = "",
    site_context: dict | None = None,
    site_image_b64: str = "",
    feasibility: dict | None = None,
    bid_structure: dict | None = None,
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

    cover_html = _concept_cover_html(proposal)   # 덱 오프닝 컨셉 표지 (concept_hook 있을 때만)
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

    # 결정 요약 cockpit(최상단) + 권장 종합안(설계 접근 직전) — 결정론, LLM 0.
    cockpit_html = _decision_cockpit_html(proposal, bid_structure)
    rec_html = _recommended_synthesis_html(proposal)

    body = (
        cockpit_html
        + legend_html
        + summary_html
        + facts_html
        + site_html
        + _scoring_waffle(proposal)
        + _bid_structure_html(bid_structure)
        + _win_themes_html(proposal)
        + rec_html
        + directions_html
        + interp_html
        + _placement_strategy_html(proposal)
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
        + cover_html
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
