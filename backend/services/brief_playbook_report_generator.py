"""
brief_playbook_report_generator.py — 경험 기반 처방(_playbook) → HTML.

**LLM 호출 없음** (Report Generation Rule). brief_playbook.build_playbook 가 만든
_playbook dict 를 화이트 + 건원 RED 자체완결 HTML 로 렌더만 한다. 데이터는 html.escape.

두 층을 시각적으로 분리:
  · [과거·사실] 당선 교훈 · 낙선 함정 · 당락 축 — 근거 칩(source)으로 과거 공모 표기.
  · [AI 해석] 이 지침서 적용(applications) — "AI 해석" 배지 + 과거 앵커(rooted_in) +
    이 지침서 앵커(basis) 동시 노출.

축적 데이터가 없으면(has_accumulated_data=False) 안내 카드만 렌더 (연료 없음 graceful).
"""
from __future__ import annotations

import html
from typing import Any


_CONF_LABEL = {"high": "높음", "medium": "보통", "low": "낮음", "none": "없음"}
_ITEM_CONF_LABEL = {"strong": "뚜렷", "tentative": "약한 신호"}


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else "")).replace("\n", "<br>")


def _as_list(v) -> list:
    if isinstance(v, list):
        return v
    if v in (None, ""):
        return []
    return [v]


_CSS = """
:root{
  --ink:#1a1a1a;--text:#3a3a3a;--muted:#9a9a9a;--line:#e8e8e8;
  --soft:#f7f7f8;--accent:#e60012;
  --past:#2a6496;--past-bg:#eef4fa;--interp:#7a3a8e;--interp-bg:#f4eef8;
  --strong:#5a8a3e;--tentative:#c47b00;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:#fff;color:var(--text);
  font-family:var(--sans);
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:52px 30px 110px}
header.doc{margin-bottom:8px;padding-bottom:22px;border-bottom:2px solid var(--ink)}
header.doc .eyebrow{font-size:12px;letter-spacing:.14em;color:var(--accent);font-weight:700;text-transform:uppercase}
header.doc h1{margin:8px 0 0;font-size:24px;font-weight:700;color:var(--ink);letter-spacing:-.02em;line-height:1.3}
header.doc .meta{margin-top:12px;color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 18px}
.disclaimer{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:18px 0 4px}

/* 표본 근거 밴드 */
.basis-band{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0 4px}
.basis-card{flex:1 1 120px;border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:var(--soft)}
.basis-card .num{font-size:26px;font-weight:800;color:var(--ink);letter-spacing:-.02em;line-height:1}
.basis-card .lbl{margin-top:5px;font-size:12px;color:var(--muted)}

/* 범례 */
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:18px 0 2px;font-size:12px;color:var(--muted)}
.legend .k{display:inline-flex;align-items:center;gap:6px}
.dot{width:10px;height:10px;border-radius:3px;display:inline-block}
.dot.past{background:var(--past)}.dot.interp{background:var(--interp)}

/* 섹션 */
section.sec{margin:36px 0 0;scroll-margin-top:20px}
section.sec>h2{display:flex;align-items:center;gap:9px;margin:0 0 6px;font-size:17px;font-weight:700;color:var(--ink)}
section.sec>h2 .tag{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;letter-spacing:.02em}
.tag.past{color:var(--past);background:var(--past-bg)}
.tag.interp{color:var(--interp);background:var(--interp-bg)}
.sec .sub{margin:0 0 14px;font-size:12.5px;color:var(--muted)}
.summ{font-size:15px;line-height:1.7;color:var(--ink);background:var(--soft);border-left:3px solid var(--accent);padding:16px 18px;border-radius:0 8px 8px 0}

/* 카드 리스트 */
.cards{display:flex;flex-direction:column;gap:12px}
.card{border:1px solid var(--line);border-radius:10px;padding:15px 17px}
.card.past{border-left:3px solid var(--past)}
.card.interp{border-left:3px solid var(--interp);background:linear-gradient(0deg,#fdfcfe,#fff)}
.card .hd{font-size:14.5px;font-weight:700;color:var(--ink);margin-bottom:5px;line-height:1.45}
.card .bd{font-size:13.5px;color:var(--text)}
.card .row{margin-top:8px;font-size:12.5px;color:var(--text)}
.card .row .rk{color:var(--muted);font-weight:600;margin-right:6px}
.chips{margin-top:9px;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;padding:2px 9px;border-radius:20px;border:1px solid var(--line);color:var(--muted);background:#fff}
.chip.src{color:var(--past);border-color:#cfe0ef;background:var(--past-bg)}
.chip.anchor{color:var(--accent);border-color:#f3ccd0;background:#fdf2f3}
.chip.conf-strong{color:var(--strong);border-color:#d3e4c6}
.chip.conf-tentative{color:var(--tentative);border-color:#eeddc0}
.badge-interp{font-size:10.5px;font-weight:700;color:var(--interp);background:var(--interp-bg);padding:2px 8px;border-radius:20px;margin-left:auto}
.card .hdwrap{display:flex;align-items:flex-start;gap:8px}

.empty{border:1px dashed var(--line);border-radius:12px;padding:30px 26px;text-align:center;color:var(--muted);background:var(--soft);margin:26px 0}
.empty .big{font-size:16px;color:var(--ink);font-weight:700;margin-bottom:8px}
ul.list{margin:6px 0 0;padding-left:18px}ul.list li{margin:4px 0;font-size:13px;color:var(--text)}
.caveats{margin-top:14px;font-size:12.5px;color:var(--muted)}
"""

from services.report_theme import THEME_VARS
# 공유 디자인 토큰(--sans/--serif 등) 주입 — 단일 소스. playbook 로컬 :root 는 근접 값 유지.
_CSS = THEME_VARS + _CSS


def _conf_chip(conf: str) -> str:
    c = (conf or "").lower()
    lbl = _ITEM_CONF_LABEL.get(c)
    if not lbl:
        return ""
    return f'<span class="chip conf-{_esc(c)}">{_esc(lbl)}</span>'


def _basis_band(pb: dict) -> str:
    db = pb.get("data_basis") or {}
    cells = [
        (db.get("win_n", 0), "과거 당선 (건)"),
        (db.get("lose_n", 0), "과거 낙선 (건)"),
        (db.get("case_count", 0), "당선작 발췌"),
        (db.get("comparison_count", 0), "비교분석 발췌"),
    ]
    cards = "".join(
        f'<div class="basis-card"><div class="num">{_esc(n)}</div>'
        f'<div class="lbl">{_esc(lbl)}</div></div>'
        for n, lbl in cells
    )
    return (
        '<div class="basis-band">' + cards + '</div>'
        '<p class="sub" style="margin:8px 0 0">이 시설유형에서 우리 회사가 축적한 과거 데이터 위에 선 처방입니다 '
        '— 표본이 클수록 신뢰도가 올라갑니다.</p>'
    )


def _legend() -> str:
    return (
        '<div class="legend">'
        '<span class="k"><span class="dot past"></span>과거·사실 — 다른 공모의 축적 데이터</span>'
        '<span class="k"><span class="dot interp"></span>AI 해석 — 과거 교훈을 이 지침서에 적용한 추론</span>'
        '</div>'
    )


def _lesson_cards(items: list, kind: str) -> str:
    """winning_lessons / losing_pitfalls 카드 (과거·사실)."""
    key = "lesson" if kind == "win" else "pitfall"
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        head = (it.get(key) or "").strip()
        if not head:
            continue
        ev = (it.get("evidence") or "").strip()
        src = (it.get("source") or "").strip()
        chips = ""
        if src:
            chips += f'<span class="chip src">{_esc(src)}</span>'
        chips += _conf_chip(it.get("confidence"))
        out.append(
            '<div class="card past">'
            f'<div class="hd">{_esc(head)}</div>'
            + (f'<div class="bd">{_esc(ev)}</div>' if ev else "")
            + (f'<div class="chips">{chips}</div>' if chips else "")
            + '</div>'
        )
    return '<div class="cards">' + "".join(out) + '</div>' if out else ""


def _application_cards(items: list) -> str:
    """applications 카드 (AI 해석 — 과거×이 지침서 교차 앵커)."""
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        guide = (it.get("guidance") or "").strip()
        if not guide:
            continue
        rooted = (it.get("rooted_in") or "").strip()
        anchor = (it.get("brief_anchor") or "").strip()
        basis = [str(b).strip() for b in _as_list(it.get("basis")) if str(b).strip()]

        rows = ""
        if rooted:
            rows += f'<div class="row"><span class="rk">과거 교훈</span>{_esc(rooted)}</div>'
        if anchor:
            rows += f'<div class="row"><span class="rk">이 지침서</span>{_esc(anchor)}</div>'
        chips = "".join(f'<span class="chip anchor">{_esc(b)}</span>' for b in basis)
        chips += _conf_chip(it.get("confidence"))
        out.append(
            '<div class="card interp">'
            '<div class="hdwrap">'
            f'<div class="hd" style="flex:1">{_esc(guide)}</div>'
            '<span class="badge-interp">AI 해석</span>'
            '</div>'
            + rows
            + (f'<div class="chips">{chips}</div>' if chips else "")
            + '</div>'
        )
    return '<div class="cards">' + "".join(out) + '</div>' if out else ""


def _watch_cards(items: list) -> str:
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        axis = (it.get("axis") or "").strip()
        if not axis:
            continue
        why = (it.get("why") or "").strip()
        src = (it.get("source") or "").strip()
        out.append(
            '<div class="card past">'
            f'<div class="hd">{_esc(axis)}</div>'
            + (f'<div class="bd">{_esc(why)}</div>' if why else "")
            + (f'<div class="chips"><span class="chip src">{_esc(src)}</span></div>' if src else "")
            + '</div>'
        )
    return '<div class="cards">' + "".join(out) + '</div>' if out else ""


def _section(title: str, tag_cls: str, tag_lbl: str, sub: str, body: str) -> str:
    if not body:
        return ""
    tag = f'<span class="tag {tag_cls}">{_esc(tag_lbl)}</span>' if tag_lbl else ""
    sub_html = f'<p class="sub">{_esc(sub)}</p>' if sub else ""
    return (
        '<section class="sec">'
        f'<h2>{_esc(title)}{tag}</h2>'
        + sub_html + body +
        '</section>'
    )


def _doc(title: str, inner: str) -> str:
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head>"
        f"<body><div class='wrap'>{inner}</div></body></html>"
    )


def to_playbook_html(
    playbook: dict,
    brief_name: str = "",
    facility_label: str = "",
) -> str:
    """_playbook dict → 자체완결 HTML 문자열 (LLM 호출 없음)."""
    pb = playbook or {}
    title = (brief_name or "").strip() or "경험 기반 처방"

    meta_bits = []
    if facility_label:
        meta_bits.append(f'<span>{_esc(facility_label)}</span>')
    if pb.get("generated_at"):
        meta_bits.append(f'<span>{_esc(pb.get("generated_at"))}</span>')
    if pb.get("model_id"):
        meta_bits.append(f'<span>모델 {_esc(pb.get("model_id"))}</span>')
    conf = (pb.get("data_confidence") or "").lower()
    if conf in _CONF_LABEL:
        meta_bits.append(f'<span>근거 신뢰도 {_esc(_CONF_LABEL[conf])}</span>')

    header = (
        '<header class="doc">'
        '<div class="eyebrow">Experiential Playbook</div>'
        f'<h1>{_esc(title)} — 경험 기반 처방</h1>'
        + (f'<div class="meta">{"".join(meta_bits)}</div>' if meta_bits else "")
        + '</header>'
        '<div class="disclaimer">우리 회사가 같은 시설유형에서 쌓아온 과거 당선·낙선 데이터를 읽어, '
        '이 지침서에 어떻게 적용할지 제안하는 <b>경험 기반 가설</b>입니다. 다른 공모의 교훈을 옮긴 것이라 '
        '이 지침서의 요구 사실과는 구분되며, 실제 심사 결과를 예측·보장하지 않습니다.</div>'
    )

    # 축적 데이터 없음 — 안내 카드만.
    if not pb.get("has_accumulated_data", True):
        cav = [str(c).strip() for c in (pb.get("caveats") or []) if str(c).strip()]
        msg = cav[0] if cav else "축적된 과거 데이터가 없습니다."
        inner = (
            header
            + '<div class="empty"><div class="big">축적된 과거 데이터가 없습니다</div>'
            + f'<div>{_esc(msg)}</div></div>'
        )
        return _doc(title, inner)

    summary = (pb.get("summary") or "").strip()
    summary_html = (
        _section("과거가 말해주는 것", "", "", "",
                 f'<div class="summ">{_esc(summary)}</div>')
        if summary else ""
    )

    body = (
        _basis_band(pb)
        + _legend()
        + summary_html
        + _section("과거 당선 교훈", "past", "과거·사실",
                   "같은 시설유형 당선작들에서 공통으로 관찰된 것.",
                   _lesson_cards(pb.get("winning_lessons") or [], "win"))
        + _section("과거 낙선 함정", "past", "과거·사실",
                   "떨어진 안들이 공통으로 빠진 함정.",
                   _lesson_cards(pb.get("losing_pitfalls") or [], "lose"))
        + _section("이 지침서 적용", "interp", "AI 해석",
                   "과거 교훈을 이 지침서의 배점·강조·대지에 걸어 처방으로 바꾼 것. "
                   "각 항목은 과거 교훈과 이 지침서 근거에 동시에 앵커됩니다.",
                   _application_cards(pb.get("applications") or []))
        + _section("당락을 가른 축", "past", "과거·사실",
                   "과거 공모에서 당선·낙선을 실제로 갈랐던 평가축 — 이 지침서에서 주목할 지점.",
                   _watch_cards(pb.get("watch_axes") or []))
    )

    caveats = [str(c).strip() for c in (pb.get("caveats") or []) if str(c).strip()]
    caveat_html = (
        _section("한계", "", "", "",
                 '<ul class="list">' + "".join(f"<li>{_esc(c)}</li>" for c in caveats) + '</ul>')
        if caveats else ""
    )

    return _doc(title, header + body + caveat_html)
