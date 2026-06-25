"""
brief_proposal_report_generator.py — 수주 제안서(_proposal) → HTML.

**LLM 호출 없음** (Report Generation Rule). brief_proposal.propose_project 가 만든
_proposal dict 를 화이트 + 건원 RED 자체완결 HTML 로 렌더만 한다. 데이터는 html.escape.
brief_checklist_exporter._HTML_CSS 의 디자인 토큰 계열을 재사용(자체 정의).

섹션: 헤더 → (전략 요약) → 배점 무게중심 카드 → 수주 핵심 테마 →
      설계 접근 방향 → 우선순위 → 리스크·대응 → 착수 체크리스트 → 확인 필요 → 한계.
내용 없는 섹션은 생략(graceful skip).
"""
from __future__ import annotations

import html
from typing import Any


_PROPOSAL_CSS = """
:root{
  --ink:#1a1a1a; --text:#3a3a3a; --muted:#9a9a9a; --line:#ececec;
  --soft:#f7f7f8; --accent:#e60012;
  --high:#e60012; --med:#c47b00; --low:#9a9a9a;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:#fff;color:var(--text);
  font-family:'Apple SD Gothic Neo','Malgun Gothic',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:900px;margin:0 auto;padding:52px 30px 110px}
header.doc{margin-bottom:8px;padding-bottom:22px;border-bottom:2px solid var(--ink)}
header.doc .eyebrow{font-size:12px;letter-spacing:.14em;color:var(--accent);font-weight:700;text-transform:uppercase}
header.doc h1{margin:8px 0 0;font-size:25px;font-weight:700;color:var(--ink);letter-spacing:-.02em;line-height:1.3}
header.doc .meta{margin-top:12px;color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px}
.disclaimer{font-size:12px;color:var(--muted);background:var(--soft);border-radius:8px;padding:10px 14px;margin:18px 0 4px}
section.sec{margin:42px 0 0;scroll-margin-top:62px}
section.sec>h2{display:flex;align-items:center;gap:11px;margin:0 0 16px;
  font-size:18px;font-weight:700;color:var(--ink);letter-spacing:-.01em}
section.sec>h2 .n{display:inline-flex;align-items:center;justify-content:center;
  min-width:25px;height:25px;padding:0 7px;border-radius:7px;
  background:var(--accent);color:#fff;font-size:13px;font-weight:700;flex:0 0 auto}
section.sec>h2 .conf{margin-left:auto;font-size:11.5px;font-weight:600;border:1px solid var(--line);
  border-radius:20px;padding:3px 11px;color:var(--muted)}
section.sec>h2 .conf.high{color:#2a8a3e;border-color:#bfe3c6}
section.sec>h2 .conf.low{color:var(--accent);border-color:#f3c2c6}
.summ{font-size:15px;line-height:1.7;color:var(--ink);border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin:6px 0 4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:8px 0}
.card{border:1px solid var(--line);border-radius:11px;padding:13px 15px;background:#fff}
.card .rk{font-size:11px;color:var(--muted);margin-bottom:5px;letter-spacing:.04em}
.card .nm{font-size:14.5px;font-weight:700;color:var(--ink);line-height:1.3}
.card .v{font-size:18px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums;margin-top:4px}
.card .v .u{font-size:12px;font-weight:500;color:var(--muted);margin-left:2px}
.item{border:1px solid var(--line);border-radius:10px;padding:13px 15px;margin:10px 0;border-left:3px solid var(--accent)}
.item .topic{font-weight:700;color:var(--ink);font-size:15px}
.item .field{margin-top:6px;color:var(--text)}
.item .field .k{color:var(--muted);font-size:12px;font-weight:600;margin-right:6px}
.item .scoring{margin-top:6px;font-size:12.5px;color:var(--accent);font-weight:600}
.cite{font-size:11px;color:var(--muted);background:var(--soft);border-radius:4px;padding:1px 6px;margin-left:4px;white-space:nowrap}
ol.pri{margin:8px 0;padding:0;list-style:none;counter-reset:pri}
ol.pri li{counter-increment:pri;border-bottom:1px solid #f4f4f4;padding:11px 0 11px 44px;position:relative}
ol.pri li::before{content:counter(pri);position:absolute;left:0;top:10px;width:28px;height:28px;
  display:inline-flex;align-items:center;justify-content:center;border-radius:8px;
  background:var(--accent);color:#fff;font-weight:700;font-size:13px}
ol.pri li .focus{font-weight:700;color:var(--ink)}
ol.pri li .focus .w{font-weight:600;color:var(--accent);margin-left:7px;font-size:12.5px}
ol.pri li .why{color:var(--text);margin-top:2px}
.risk{border-left:3px solid var(--low);background:var(--soft);padding:11px 14px;margin:9px 0;border-radius:0 7px 7px 0}
.risk.high{border-color:var(--high)} .risk.medium{border-color:var(--med)}
.risk .rt{font-weight:700;color:var(--ink);font-size:13.5px}
.risk .rt .sev{font-size:11px;color:var(--muted);font-weight:600;margin-left:7px}
.risk.high .rt .sev{color:var(--high)} .risk.medium .rt .sev{color:var(--med)}
.risk .rm{margin-top:4px;color:var(--text)}
ul.list{margin:8px 0;padding-left:20px}
ul.list li{margin:5px 0}
.caveat{margin:16px 0 0;font-size:12px;color:var(--muted)}
footer.doc{margin-top:64px;padding-top:18px;border-top:1px solid var(--line);color:#c0c0c0;font-size:11.5px;text-align:center}
nav.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);
  backdrop-filter:saturate(160%) blur(8px);-webkit-backdrop-filter:saturate(160%) blur(8px);border-bottom:1px solid var(--line)}
nav.top .inner{max-width:900px;margin:0 auto;padding:10px 30px;display:flex;align-items:center;gap:14px}
nav.top .ttl{font-weight:700;color:var(--ink);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:36%}
nav.top .links{display:flex;gap:2px;margin-left:auto;flex-wrap:nowrap;overflow-x:auto}
nav.top .links a{font-size:12.5px;color:var(--muted);text-decoration:none;padding:5px 11px;border-radius:7px;white-space:nowrap}
nav.top .links a:hover{background:var(--soft);color:var(--ink)}
@media print{.wrap{padding:0}body{font-size:12px}section.sec{break-inside:avoid}nav.top{display:none}}
@media(max-width:560px){.wrap{padding:32px 18px 64px}nav.top .ttl{display:none}nav.top .inner{padding:8px 18px}}
"""


_CONF_LABEL = {"high": "높음", "medium": "보통", "low": "낮음 (근거 부족)"}
_SEV_LABEL = {"high": "높음", "medium": "중간", "low": "낮음"}


def _esc(v: Any) -> str:
    if v is None:
        return ""
    return html.escape(str(v), quote=True)


def _basis_html(b) -> str:
    items = b if isinstance(b, list) else ([b] if b else [])
    items = [str(x).strip() for x in items if str(x).strip()]
    return f'<span class="cite">근거 {_esc(" · ".join(items))}</span>' if items else ""


def _scoring_cards(proposal: dict) -> str:
    """결정론 scoring_focus → 배점 무게중심 카드 (상위 6개, 명시 배점 우선)."""
    focus = [f for f in (proposal.get("scoring_focus") or []) if isinstance(f, dict)]
    ranked = sorted(
        [f for f in focus if f.get("rank")],
        key=lambda f: f.get("rank") or 99,
    )[:6]
    if not ranked:
        return ""
    cards = []
    for f in ranked:
        name = _esc((f.get("category") or "").strip())
        pts = f.get("points")
        wt = f.get("weight_pct")
        v = f"{pts:g}점" if isinstance(pts, (int, float)) else ""
        u = f'<span class="u">({wt:g}%)</span>' if isinstance(wt, (int, float)) else ""
        cards.append(
            f'<div class="card"><div class="rk">배점 {f.get("rank")}순위</div>'
            f'<div class="nm">{name}</div><div class="v">{_esc(v)}{u}</div></div>'
        )
    return ('<section id="scoring" class="sec"><h2><span class="n">·</span>배점 무게중심</h2>'
            '<div class="cards">' + "".join(cards) + '</div></section>')


def _win_themes_html(proposal: dict) -> str:
    themes = [t for t in (proposal.get("win_themes") or []) if isinstance(t, dict)]
    blocks = []
    for t in themes:
        topic = _esc((t.get("theme") or "").strip())
        if not topic:
            continue
        rat = (t.get("rationale") or "").strip()
        rat_html = f'<div class="field">{_esc(rat)}</div>' if rat else ""
        link = (t.get("scoring_link") or "").strip()
        link_html = f'<div class="scoring">↳ {_esc(link)}</div>' if link else ""
        blocks.append(
            f'<div class="item"><div class="topic">{topic}</div>{rat_html}{link_html}'
            f'<div class="field">{_basis_html(t.get("basis"))}</div></div>'
        )
    if not blocks:
        return ""
    return ('<section id="themes" class="sec"><h2><span class="n">1</span>수주 핵심 테마</h2>'
            + "".join(blocks) + '</section>')


def _directions_html(proposal: dict) -> str:
    dirs = [d for d in (proposal.get("design_directions") or []) if isinstance(d, dict)]
    blocks = []
    for d in dirs:
        direction = _esc((d.get("direction") or "").strip())
        if not direction:
            continue
        addr = (d.get("addresses") or "").strip()
        addr_html = f'<div class="field"><span class="k">대응</span>{_esc(addr)}</div>' if addr else ""
        tr = (d.get("tradeoffs") or "").strip()
        tr_html = f'<div class="field"><span class="k">유의</span>{_esc(tr)}</div>' if tr else ""
        blocks.append(
            f'<div class="item"><div class="topic">{direction}</div>{addr_html}{tr_html}'
            f'<div class="field">{_basis_html(d.get("basis"))}</div></div>'
        )
    if not blocks:
        return ""
    return ('<section id="directions" class="sec"><h2><span class="n">2</span>설계 접근 방향 (후보)</h2>'
            + "".join(blocks) + '</section>')


def _priorities_html(proposal: dict) -> str:
    pris = [p for p in (proposal.get("priorities") or []) if isinstance(p, dict)]
    pris = sorted(pris, key=lambda p: p.get("rank") if isinstance(p.get("rank"), (int, float)) else 99)
    lis = []
    for p in pris:
        focus = _esc((p.get("focus") or "").strip())
        if not focus:
            continue
        wt = (str(p.get("scoring_weight")).strip() if p.get("scoring_weight") else "")
        wt_html = f'<span class="w">{_esc(wt)}</span>' if wt else ""
        why = (p.get("why") or "").strip()
        why_html = f'<div class="why">{_esc(why)}</div>' if why else ""
        lis.append(f'<li><span class="focus">{focus}{wt_html}</span>{why_html}</li>')
    if not lis:
        return ""
    return ('<section id="priorities" class="sec"><h2><span class="n">3</span>착수 우선순위</h2>'
            '<ol class="pri">' + "".join(lis) + '</ol></section>')


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
        sev_html = f'<span class="sev">{_esc(sev_lbl)}</span>' if sev_lbl else ""
        mit = (r.get("mitigation") or "").strip()
        mit_html = f'<div class="rm"><span class="k" style="color:var(--muted);font-size:12px;font-weight:600;margin-right:6px">대응</span>{_esc(mit)}</div>' if mit else ""
        blocks.append(
            f'<div class="risk {sev_cls}"><div class="rt">{risk}{sev_html}</div>{mit_html}'
            f'<div class="rm">{_basis_html(r.get("basis"))}</div></div>'
        )
    if not blocks:
        return ""
    return ('<section id="risks" class="sec"><h2><span class="n">4</span>리스크 · 대응</h2>'
            + "".join(blocks) + '</section>')


def _list_section(proposal: dict, key: str, sec_id: str, n: str, title: str) -> str:
    items = [str(x).strip() for x in (proposal.get(key) or []) if str(x).strip()]
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(x)}</li>" for x in items)
    return (f'<section id="{sec_id}" class="sec"><h2><span class="n">{n}</span>{_esc(title)}</h2>'
            f'<ul class="list">{lis}</ul></section>')


def to_proposal_html(proposal: dict, brief_name: str = "", facility_label: str = "") -> str:
    """_proposal dict → 자체완결 HTML 문자열 (LLM 호출 없음)."""
    proposal = proposal or {}
    title = (brief_name or "").strip() or "프로젝트 수주 제안서"

    conf = (proposal.get("data_confidence") or "").lower()
    conf_cls = conf if conf in _CONF_LABEL else ""
    conf_lbl = _CONF_LABEL.get(conf, "")
    conf_html = f'<span class="conf {conf_cls}">근거 신뢰도 {_esc(conf_lbl)}</span>' if conf_lbl else ""

    summary = (proposal.get("executive_summary") or "").strip()
    summary_html = (
        f'<section id="summary" class="sec"><h2><span class="n">·</span>전략 요약{conf_html}</h2>'
        f'<div class="summ">{_esc(summary)}</div></section>'
    ) if summary else ""

    meta_bits = []
    if facility_label:
        meta_bits.append(f'<span>{_esc(facility_label)}</span>')
    if proposal.get("generated_at"):
        meta_bits.append(f'<span>{_esc(proposal.get("generated_at"))}</span>')
    if proposal.get("model_id"):
        meta_bits.append(f'<span>모델 {_esc(proposal.get("model_id"))}</span>')

    body = (
        summary_html
        + _scoring_cards(proposal)
        + _win_themes_html(proposal)
        + _directions_html(proposal)
        + _priorities_html(proposal)
        + _risks_html(proposal)
        + _list_section(proposal, "kickoff_checklist", "kickoff", "5", "착수 체크리스트")
        + _list_section(proposal, "open_questions", "questions", "6", "발주처 확인 필요")
    )

    caveats = [str(c).strip() for c in (proposal.get("caveats") or []) if str(c).strip()]
    caveat_html = (
        '<section id="caveats" class="sec"><h2><span class="n">·</span>한계</h2>'
        '<ul class="list">' + "".join(f"<li>{_esc(c)}</li>" for c in caveats) + "</ul></section>"
    ) if caveats else ""

    nav_links = (
        '<a href="#summary">요약</a><a href="#themes">핵심 테마</a>'
        '<a href="#directions">접근 방향</a><a href="#priorities">우선순위</a>'
        '<a href="#risks">리스크</a><a href="#kickoff">체크리스트</a>'
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
        "<div class='disclaimer'>본 제안서는 추출된 지침서 데이터에 근거한 <b>수주 전략 가설</b>입니다. "
        "사실 주장(지침서가 요구·강조·배점하는 것)에는 근거를 인용하며, 전략·접근 방향은 제안이고 "
        "실제 심사 결과를 보장하지 않습니다. 최종 판단은 설계팀의 몫입니다.</div>"
        + body
        + caveat_html
        + "<footer class='doc'>Competition Analyzer · 지침서 기반 수주 제안서 (AI 생성 · 당락 예측 아님)</footer>"
        "</div></body></html>"
    )
