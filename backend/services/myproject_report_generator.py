"""MyProjectMode 심층 분석 HTML 리포트 생성기.

LLM 호출 없음. myproject_analyzer.py가 생성한 _deep.json + 기본 submission_doc +
meta를 받아 HTML 문자열을 반환한다. 화이트 테마 + 건원 RED 액센트(#e60012)
일관성 유지.
"""
from __future__ import annotations

import html

from config import facility_label as _facility_label, axes_for as _axes_for


from services.grade_helpers import GRADE_COLORS as _GRADE_COLOR
from services.citation_check import flags_band_html as citation_flags_band
from services.quant_validator import flags_band_html as quant_flags_band

_RESULT_BADGE = {
    "win":        ('<span style="background:#dcfce7;color:#15803d;font-size:13px;'
                   'padding:4px 12px;border-radius:20px;font-weight:700;'
                   'border:1px solid #86efac">★ 당선</span>'),
    "contracted": ('<span style="background:#cffafe;color:#0e7490;font-size:13px;'
                   'padding:4px 12px;border-radius:20px;font-weight:700;'
                   'border:1px solid #67e8f9">◆ 수의계약</span>'),
    "lose":       ('<span style="background:#f1f5f9;color:#475569;font-size:13px;'
                   'padding:4px 12px;border-radius:20px;font-weight:700;'
                   'border:1px solid #cbd5e1">참여 (낙선)</span>'),
}

_PROCUREMENT_LABEL = {
    "competition": "경쟁공모",
    "negotiated":  "수의계약",
    "invited":     "지명공모",
    "turnkey":     "턴키/기술제안",
    "private":     "민간발주",
    "other":       "기타",
}

_PHASE_LABEL = {
    "planning":         "기획",
    "concept":          "계획설계",
    "basic_design":     "기본설계",
    "detailed_design":  "실시설계",
    "cm":               "CM/감리",
}

_ROLE_LABEL = {
    "lead":          "주관사",
    "consortium":    "컨소시엄",
    "subcontractor": "협력사",
}


_CSS = """
<style>
:root {
  --accent: #e60012;
  --accent-soft: rgba(230,0,18,0.06);
  --accent-border: rgba(230,0,18,0.25);
  --text: #212529;
  --text-muted: #6c757d;
  --text-faint: #adb5bd;
  --bg: #f8f9fa;
  --surface: #ffffff;
  --surface-alt: #f1f3f5;
  --border: #dee2e6;
  --success: #16a34a;
  --danger:  #dc2626;
  --info:    #0891b2;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
       background: var(--bg); color: var(--text); padding: 24px;
       font-size: 14px; line-height: 1.6; }
.wrap { max-width: 1100px; margin: 0 auto; }

.hdr { background: var(--surface); border-radius: 12px;
       padding: 24px 28px; margin-bottom: 20px;
       border-left: 4px solid var(--accent); }
.hdr-top { display: flex; align-items: center; gap: 10px;
           margin-bottom: 10px; flex-wrap: wrap; }
.hdr-title { font-size: 22px; font-weight: 700; color: var(--text); }
.hdr-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.hdr-meta { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px;
            color: var(--text-muted); }
.hdr-meta span strong { color: var(--text); font-weight: 600; }
.facility-badge { background: var(--accent-soft); color: var(--accent);
                  font-size: 12px; padding: 3px 10px; border-radius: 20px;
                  font-weight: 600; border: 1px solid var(--accent-border); }

.sec { background: var(--surface); border-radius: 10px;
       padding: 22px 26px; margin-bottom: 16px; }
.sec-title { font-size: 11px; font-weight: 700; color: var(--accent);
             margin-bottom: 14px; padding-bottom: 8px;
             border-bottom: 1px solid var(--border);
             text-transform: uppercase; letter-spacing: 1px; }

.narrative { font-size: 15px; line-height: 1.8; color: var(--text);
             padding: 16px 20px; background: var(--surface-alt);
             border-radius: 8px; white-space: pre-wrap; }
.intent { font-size: 14px; color: var(--text-muted); font-style: italic;
          margin-top: 10px; padding-left: 12px;
          border-left: 3px solid var(--accent-border); }

.kw-row { display: flex; flex-wrap: wrap; gap: 6px; }
.kw { background: var(--accent-soft); color: var(--accent);
      font-size: 12px; padding: 4px 12px; border-radius: 14px;
      border: 1px solid var(--accent-border); font-weight: 500; }

.usertag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.usertag { background: var(--surface-alt); color: var(--text-muted);
           font-size: 12px; padding: 3px 10px; border-radius: 12px;
           border: 1px solid var(--border); }

.memo { font-size: 13px; color: var(--text); line-height: 1.7;
        padding: 14px 16px; background: var(--surface-alt);
        border: 1px solid var(--border); border-radius: 8px;
        white-space: pre-wrap; }

.bullet-list { list-style: none; padding: 0; }
.bullet-list li { padding: 8px 0; border-bottom: 1px solid var(--border);
                  line-height: 1.6; color: var(--text); font-size: 14px; }
.bullet-list li:last-child { border-bottom: none; }
.bullet-list li::before { content: "·"; color: var(--accent);
                          font-weight: 700; margin-right: 8px; }

.axis-card { background: var(--surface); border: 1px solid var(--border);
             border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; }
.axis-head { display: flex; align-items: center; gap: 10px;
             padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.axis-name { font-size: 15px; font-weight: 700; color: var(--text); flex: 1; }
.grade-pill { min-width: 36px; text-align: center;
              padding: 3px 10px; border-radius: 14px;
              font-weight: 700; font-size: 13px; letter-spacing: 1px; }
.grade-justify { font-size: 11px; color: var(--text-muted);
                 background: var(--surface-alt); padding: 6px 10px;
                 border-radius: 4px; margin: 8px 0;
                 border-left: 2px solid var(--accent-border);
                 font-family: 'Consolas', 'Malgun Gothic', monospace;
                 line-height: 1.5; }

.evidence-block { margin-top: 12px; }
.evidence-label { font-size: 10px; font-weight: 700;
                  text-transform: uppercase; letter-spacing: 1px;
                  margin-bottom: 8px; }
.evidence-label.s { color: var(--success); }
.evidence-label.w { color: var(--danger); }
.evidence-list { list-style: none; padding-left: 14px; }
.evidence-list li { font-size: 13px; line-height: 1.6;
                    color: var(--text); padding: 4px 0;
                    position: relative; }
.evidence-list li::before { content: "▸"; color: var(--text-faint);
                            position: absolute; left: -14px; }

.diff-row, .imp-row { display: grid; gap: 8px; }
.diff-card { background: var(--accent-soft); border-left: 3px solid var(--accent);
             padding: 10px 14px; border-radius: 6px;
             font-size: 14px; color: var(--text); }
.imp-card { background: var(--surface-alt); border-left: 3px solid var(--info);
            padding: 10px 14px; border-radius: 6px;
            font-size: 14px; color: var(--text); }

.empty { color: var(--text-faint); font-style: italic; font-size: 13px; }

@media print {
  body { background: white; padding: 0; font-size: 12px; }
  .sec, .hdr { box-shadow: none; page-break-inside: avoid; }
  .axis-card { page-break-inside: avoid; }
}
</style>
"""


def _esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _grade_badge(grade: str | None) -> str:
    if not grade or grade not in _GRADE_COLOR:
        return ('<span style="color:#adb5bd;font-size:13px">—</span>')
    fg, bg = _GRADE_COLOR[grade]
    return (f'<span class="grade-pill" style="color:{fg};background:{bg}">'
            f'{_esc(grade)}</span>')


def _bullet_list(items, css_class: str = "bullet-list") -> str:
    if not items:
        return '<div class="empty">—</div>'
    rows = "".join(f"<li>{_esc(x)}</li>" for x in items if x)
    if not rows:
        return '<div class="empty">—</div>'
    return f'<ul class="{css_class}">{rows}</ul>'


def _evidence_list(items, kind: str) -> str:
    """kind: 's' (strengths) | 'w' (weaknesses)"""
    label_kr = "강점" if kind == "s" else "약점"
    if not items:
        return ""
    rows = "".join(f"<li>{_esc(x)}</li>" for x in items if x)
    if not rows:
        return ""
    return (f'<div class="evidence-block">'
            f'<div class="evidence-label {kind}">{label_kr}</div>'
            f'<ul class="evidence-list">{rows}</ul></div>')


def _axes_section(facility_type: str, axes_evidence: dict) -> str:
    if not axes_evidence:
        return '<div class="empty">평가축 분석 데이터 없음</div>'
    axes_meta = _axes_for(facility_type)
    parts = []
    # axes_meta 순서대로 정렬, 누락된 축은 뒤에
    keys_ordered = list(axes_meta.keys()) + [
        k for k in axes_evidence.keys() if k not in axes_meta
    ]
    for axis_key in keys_ordered:
        if axis_key not in axes_evidence:
            continue
        ev = axes_evidence[axis_key] or {}
        axis_label = axes_meta.get(axis_key, axis_key)
        grade = ev.get("grade")
        justification = ev.get("grade_justification") or ""
        strengths = ev.get("strengths") or []
        weaknesses = ev.get("weaknesses") or []
        justify_html = (f'<div class="grade-justify">▣ {_esc(justification)}</div>'
                        if justification else "")
        parts.append(
            '<div class="axis-card">'
            '  <div class="axis-head">'
            f'    <div class="axis-name">{_esc(axis_label)}</div>'
            f'    {_grade_badge(grade)}'
            '  </div>'
            f'  {justify_html}'
            f'  {_evidence_list(strengths, "s")}'
            f'  {_evidence_list(weaknesses, "w")}'
            '</div>'
        )
    return "".join(parts)


def _meta_row(meta: dict) -> str:
    """헤더 메타 한 줄 — 발주처/대지위치/수주형태/사업단계/역할."""
    items = []
    if meta.get("client"):
        items.append(f'<span>발주처 <strong>{_esc(meta["client"])}</strong></span>')
    if meta.get("location"):
        items.append(f'<span>위치 <strong>{_esc(meta["location"])}</strong></span>')
    proc = _PROCUREMENT_LABEL.get(meta.get("procurement_type"))
    if proc:
        items.append(f'<span>수주 <strong>{_esc(proc)}</strong></span>')
    phase = _PHASE_LABEL.get(meta.get("project_phase"))
    if phase:
        items.append(f'<span>단계 <strong>{_esc(phase)}</strong></span>')
    role = _ROLE_LABEL.get(meta.get("role"))
    if role:
        items.append(f'<span>역할 <strong>{_esc(role)}</strong></span>')
    if meta.get("partners"):
        items.append(f'<span>컨소시엄 <strong>{_esc(meta["partners"])}</strong></span>')
    if meta.get("gross_floor_area"):
        items.append(f'<span>연면적 <strong>{_esc(meta["gross_floor_area"])}</strong></span>')
    if meta.get("floors"):
        items.append(f'<span>층수 <strong>{_esc(meta["floors"])}</strong></span>')
    if meta.get("units"):
        items.append(f'<span>세대수 <strong>{_esc(meta["units"])}</strong></span>')
    if not items:
        return ""
    return f'<div class="hdr-meta">{"".join(items)}</div>'


def generate_myproject_report(
    *,
    deep: dict,
    sub_doc: dict,
    meta: dict,
) -> str:
    """심층 분석 HTML 리포트.

    Args:
        deep: myproject_analyzer.deep_analyze() 결과
        sub_doc: 기본 submission JSON (company, result, facility_type, competition_id, total_pages 등)
        meta: _meta.json (procurement_type, project_phase, location 등 + competition_name)
    """
    facility_type = sub_doc.get("facility_type", "")
    competition_name = meta.get("competition_name") or sub_doc.get("competition_id", "")
    company = sub_doc.get("company", "—")
    result = sub_doc.get("result", "")
    total_pages = sub_doc.get("total_pages", 0)

    facility_kr = _facility_label(facility_type) if facility_type else ""
    result_badge = _RESULT_BADGE.get(result, "")
    facility_badge = (f'<span class="facility-badge">{_esc(facility_kr)}</span>'
                      if facility_kr else "")

    narrative = deep.get("concept_narrative", "")
    intent = deep.get("design_intent", "")
    differentiators = deep.get("key_differentiators") or []
    axes_evidence = deep.get("axes_evidence") or {}
    improvement = deep.get("improvement_points") or []
    keywords = deep.get("search_keywords") or []

    user_tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    memo = meta.get("memo") or ""

    # 인용 사후검증 밴드 (문서 쪽수 벗어난 (p.N) 노출, 없으면 '')
    citation_band = citation_flags_band(deep.get("_citation_flags"))
    # 정량 정합성 밴드 (추출 수치 모순, quant_validator, 없으면 '')
    quant_band = quant_flags_band((sub_doc.get("extracted_data") or {}).get("_quantitative_flags"))

    diff_cards = "".join(f'<div class="diff-card">{_esc(d)}</div>'
                         for d in differentiators if d) or '<div class="empty">—</div>'
    imp_cards = "".join(f'<div class="imp-card">{_esc(i)}</div>'
                        for i in improvement if i) or '<div class="empty">—</div>'
    kw_html = "".join(f'<span class="kw">{_esc(k)}</span>' for k in keywords if k) \
        or '<div class="empty">—</div>'
    user_tag_html = ("".join(f'<span class="usertag">#{_esc(t)}</span>'
                             for t in user_tags if t)) if user_tags else ""

    # 컨셉 narrative 섹션 (intent 포함)
    narrative_block = ""
    if narrative or intent:
        narrative_block = '<div class="sec"><div class="sec-title">컨셉 NARRATIVE</div>'
        if narrative:
            narrative_block += f'<div class="narrative">{_esc(narrative)}</div>'
        if intent:
            narrative_block += f'<div class="intent">{_esc(intent)}</div>'
        narrative_block += '</div>'

    # 사용자 메모 + 태그 섹션 (있을 때만)
    user_block = ""
    if memo or user_tag_html:
        user_block = '<div class="sec"><div class="sec-title">등록자 메모 · 태그</div>'
        if memo:
            user_block += f'<div class="memo">{_esc(memo)}</div>'
        if user_tag_html:
            user_block += f'<div class="usertag-row">{user_tag_html}</div>'
        user_block += '</div>'

    html_out = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<title>{_esc(competition_name)} — {_esc(company)} 심층 분석</title>
{_CSS}
</head><body><div class="wrap">

<div class="hdr">
  <div class="hdr-top">
    <div class="hdr-title">{_esc(competition_name)}</div>
    {facility_badge}
    {result_badge}
  </div>
  <div class="hdr-sub">{_esc(company)} · 총 {total_pages}페이지 분석</div>
  {_meta_row(meta)}
</div>

{narrative_block}

{user_block}

<div class="sec">
  <div class="sec-title">핵심 차별화 ({len(differentiators)})</div>
  <div class="diff-row">{diff_cards}</div>
</div>

<div class="sec">
  <div class="sec-title">평가축별 심층 분석</div>
  {_axes_section(facility_type, axes_evidence)}
</div>

<div class="sec">
  <div class="sec-title">보강 · 강조 포인트 ({len(improvement)})</div>
  <div class="imp-row">{imp_cards}</div>
</div>

<div class="sec">
  <div class="sec-title">아카이브 검색 키워드 ({len(keywords)})</div>
  <div class="kw-row">{kw_html}</div>
</div>
{quant_band}
{citation_band}

</div></body></html>
"""
    return html_out
