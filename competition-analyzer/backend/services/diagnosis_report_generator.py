"""Diagnosis report generator — no LLM calls, pure HTML rendering."""
from __future__ import annotations

from datetime import datetime

from config import axes_for, facility_label as _facility_label

_COMPLIANCE_COLOR = {
    "yes": "#68d391", "partial": "#f6ad55", "no": "#fc8181", "unclear": "#718096",
}
_COMPLIANCE_KR = {"yes": "충족", "partial": "부분충족", "no": "미충족", "unclear": "불명확"}
_STATUS_COLOR = {
    "yes": "#68d391", "partial": "#f6ad55", "no": "#fc8181", "unclear": "#718096",
}
_STATUS_KR = {"yes": "충족", "partial": "부분충족", "no": "미충족", "unclear": "불명확"}

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif;
       background: #0f1117; color: #e2e8f0; padding: 24px; font-size: 14px; }
.wrap { max-width: 1000px; margin: 0 auto; }

.hdr { background: #1a1f2e; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
       border-left: 5px solid #553c9a; display: flex; align-items: center; gap: 24px; }
.hdr-ring { width: 100px; height: 100px; border-radius: 50%; border-width: 5px;
            border-style: solid; display: flex; flex-direction: column;
            align-items: center; justify-content: center; flex-shrink: 0; }
.hdr-ring-score { font-size: 30px; font-weight: 700; }
.hdr-ring-label { font-size: 11px; color: #718096; }
.hdr-info { flex: 1; }
.hdr-title { font-size: 22px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
.hdr-sub { font-size: 13px; color: #a0aec0; margin-bottom: 10px; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { font-size: 12px; padding: 3px 10px; border-radius: 20px; font-weight: 600; }

.sec { background: #1a1f2e; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }
.sec-title { font-size: 15px; font-weight: 700; color: #90cdf4; margin-bottom: 14px;
             padding-bottom: 8px; border-bottom: 1px solid #2d3748; }

.dist-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.dist-label { font-size: 12px; color: #a0aec0; min-width: 130px; }
.dist-bar-bg { flex: 1; background: #0d1117; border-radius: 3px; height: 14px; overflow: hidden; }
.dist-bar-fill { height: 100%; border-radius: 3px; background: #2c5282; }
.dist-count { font-size: 12px; color: #718096; min-width: 28px; text-align: right; }

.compliance-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.compliance-card { background: #0d1117; border-radius: 6px; padding: 10px 12px; }
.compliance-axis { font-size: 11px; color: #718096; margin-bottom: 4px; }
.compliance-badge { font-size: 12px; padding: 2px 10px; border-radius: 20px; font-weight: 600; display: inline-block; }

table.req-table { width: 100%; border-collapse: collapse; font-size: 12px; }
table.req-table thead tr { color: #718096; border-bottom: 1px solid #2d3748; }
table.req-table th { text-align: left; padding: 5px 8px; }
table.req-table td { padding: 6px 8px; border-bottom: 1px solid #1a2535; vertical-align: top; }

.warn-box { background: #1a1200; border: 1px solid #744210; border-radius: 8px;
            padding: 12px 16px; margin-bottom: 12px; }
.warn-title { font-size: 13px; color: #f6ad55; margin-bottom: 8px; }
.warn-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }
.warn-tag { background: #744210; color: #fef3c7; font-size: 12px; padding: 2px 10px; border-radius: 20px; }
.warn-item { font-size: 12px; color: #e2e8f0; margin-bottom: 4px; }
.warn-item .warn-key { color: #a0aec0; margin-right: 6px; }

.axes-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.axis-card { background: #0d1117; border-radius: 10px; padding: 16px; display: flex; gap: 14px; }
.axis-ring { width: 60px; height: 60px; border-radius: 50%; border-width: 4px; border-style: solid;
             display: flex; flex-direction: column; align-items: center;
             justify-content: center; flex-shrink: 0; }
.axis-ring-score { font-size: 20px; font-weight: 700; }
.axis-ring-sub { font-size: 9px; color: #718096; }
.axis-body { flex: 1; min-width: 0; }
.axis-name { font-size: 14px; font-weight: 700; color: #90cdf4; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.axis-strengths { font-size: 12px; color: #68d391; margin-bottom: 3px; }
.axis-weaknesses { font-size: 12px; color: #fc8181; margin-bottom: 3px; }
.axis-recs { font-size: 12px; color: #f6ad55; margin-bottom: 3px; }
.axis-evidence { font-size: 11px; color: #718096; font-style: italic; margin-top: 3px; }

.rec-list { display: flex; flex-direction: column; gap: 8px; }
.rec-item { display: flex; gap: 10px; align-items: flex-start; }
.rec-num { background: #2b6cb0; color: #fff; border-radius: 50%; width: 22px; height: 22px;
           display: flex; align-items: center; justify-content: center;
           font-size: 11px; font-weight: 700; flex-shrink: 0; }
.rec-text { font-size: 13px; color: #e2e8f0; padding-top: 2px; }

.sw-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.sw-tag { font-size: 12px; padding: 3px 10px; border-radius: 20px; }

.footer { text-align: center; color: #4a5568; font-size: 12px; margin-top: 24px; padding: 12px; }
@media print {
  body { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  @page { size: A4 portrait; margin: 15mm; }
  .sec { page-break-inside: avoid; }
}
</style>
"""


def _ring_color(score) -> str:
    if score is None:
        return "#718096"
    if score >= 7:
        return "#68d391"
    if score >= 5:
        return "#f6ad55"
    return "#fc8181"


def _esc(text) -> str:
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _render_header(diagnosis: dict, facility_type_label: str) -> str:
    score = diagnosis.get("overall_score")
    color = _ring_color(score)
    score_html = (
        f'<div class="hdr-ring" style="border-color:{color}">'
        f'<span class="hdr-ring-score" style="color:{color}">{score:.1f}</span>'
        f'<span class="hdr-ring-label">종합점수</span>'
        f'</div>'
    ) if score is not None else ""

    comp_name = _esc(diagnosis.get("competition_name") or "")
    title = comp_name or "진단 결과"
    sub = f"{facility_type_label} · 총 {diagnosis.get('total_pages', 0)}페이지"

    strengths = diagnosis.get("strengths") or []
    weaknesses = diagnosis.get("weaknesses") or []

    sw_html = ""
    if strengths or weaknesses:
        sw_html = '<div class="sw-row">'
        for s in strengths:
            sw_html += f'<span class="sw-tag" style="background:#1c4a2e;color:#68d391">{_esc(s)}</span>'
        for w in weaknesses:
            sw_html += f'<span class="sw-tag" style="background:#2d1515;color:#fc8181">{_esc(w)}</span>'
        sw_html += "</div>"

    return (
        f'<div class="hdr">'
        f'{score_html}'
        f'<div class="hdr-info">'
        f'<div class="hdr-title">{title} 진단 결과</div>'
        f'<div class="hdr-sub">{sub}</div>'
        f'{sw_html}'
        f'</div>'
        f'</div>'
    )


def _render_page_dist(distribution: dict, total: int) -> str:
    if not distribution:
        return ""
    rows = ""
    for pt, count in sorted(distribution.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total else 0
        rows += (
            f'<div class="dist-row">'
            f'<span class="dist-label">{_esc(pt)}</span>'
            f'<div class="dist-bar-bg"><div class="dist-bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<span class="dist-count">{count}</span>'
            f'</div>'
        )
    return (
        f'<div class="sec">'
        f'<div class="sec-title">페이지 구성</div>'
        f'{rows}'
        f'</div>'
    )


def _render_brief_compliance(brief_compliance: dict, axes_meta: dict) -> str:
    if not brief_compliance:
        return ""
    cards = ""
    for k, v in brief_compliance.items():
        axis_label = axes_meta.get(k, {}).get("label_ko", k) if axes_meta else k
        color = _COMPLIANCE_COLOR.get(v, "#718096")
        kr = _COMPLIANCE_KR.get(v, v)
        cards += (
            f'<div class="compliance-card">'
            f'<div class="compliance-axis">{_esc(axis_label)}</div>'
            f'<span class="compliance-badge" style="background:{color};color:#0d1117">{kr}</span>'
            f'</div>'
        )
    return (
        f'<div class="sec">'
        f'<div class="sec-title">지침서 축별 충족도</div>'
        f'<div class="compliance-grid">{cards}</div>'
        f'</div>'
    )


def _render_requirement_mapping(mapping: list, axes_meta: dict) -> str:
    if not mapping:
        return ""
    rows = ""
    for row in mapping:
        axis_key = row.get("axis", "")
        axis_label = axes_meta.get(axis_key, {}).get("label_ko", axis_key) if axes_meta else axis_key
        status = row.get("status", "unclear")
        color = _STATUS_COLOR.get(status, "#718096")
        kr = _STATUS_KR.get(status, status)
        rows += (
            f'<tr>'
            f'<td style="color:#e2e8f0">{_esc(row.get("requirement", ""))}</td>'
            f'<td style="color:#a0aec0">{_esc(axis_label)}</td>'
            f'<td style="text-align:center"><span class="compliance-badge" style="background:{color};color:#0d1117">{kr}</span></td>'
            f'<td style="color:#718096">{_esc(row.get("evidence", ""))}</td>'
            f'</tr>'
        )
    return (
        f'<div class="sec">'
        f'<div class="sec-title">지침서 요구사항 충족도</div>'
        f'<table class="req-table">'
        f'<thead><tr><th style="width:35%">요구사항</th><th style="width:18%">평가축</th>'
        f'<th style="width:12%;text-align:center">충족여부</th><th>근거</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'</div>'
    )


def _render_pattern_deviation(deviation: dict) -> str:
    if not deviation:
        return ""
    missing = deviation.get("missing_page_types") or []
    gaps = deviation.get("page_distribution_gaps") or []
    quant = deviation.get("quantitative_gaps") or {}

    parts = ""
    if missing:
        tags = "".join(f'<span class="warn-tag">{_esc(t)}</span>' for t in missing)
        parts += (
            f'<div style="margin-bottom:12px">'
            f'<div class="warn-title">⚠ 누락 페이지 유형 (당선작 대비)</div>'
            f'<div class="warn-tags">{tags}</div>'
            f'</div>'
        )
    if gaps:
        items = "".join(f'<div class="warn-item">{_esc(g)}</div>' for g in gaps)
        parts += (
            f'<div style="margin-bottom:12px">'
            f'<div class="warn-title">페이지 배분 편차</div>'
            f'{items}'
            f'</div>'
        )
    if quant:
        items = "".join(
            f'<div class="warn-item"><span class="warn-key">{_esc(k)}:</span>{_esc(v)}</div>'
            for k, v in quant.items()
        )
        parts += (
            f'<div>'
            f'<div class="warn-title">⚠ 정량 지표 편차 (당선·낙선 패턴 대비)</div>'
            f'{items}'
            f'</div>'
        )

    if not parts:
        return ""
    return f'<div class="warn-box">{parts}</div>'


def _render_axes(axes: dict, axes_meta: dict) -> str:
    if not axes:
        return ""
    cards = ""
    for key, data in axes.items():
        score = data.get("score")
        color = _ring_color(score)
        ring = (
            f'<div class="axis-ring" style="border-color:{color}">'
            f'<span class="axis-ring-score" style="color:{color}">{score:.1f}</span>'
            f'<span class="axis-ring-sub">/ 10</span>'
            f'</div>'
        ) if score is not None else ""

        label = axes_meta.get(key, {}).get("label_ko", key) if axes_meta else key
        compliance = data.get("brief_compliance") or data.get("compliance")
        badge = ""
        if compliance:
            bc = _COMPLIANCE_COLOR.get(compliance, "#718096")
            bk = _COMPLIANCE_KR.get(compliance, compliance)
            badge = f'<span class="compliance-badge" style="background:{bc};color:#0d1117;font-size:11px">{bk}</span>'

        strengths = data.get("strengths") or []
        weaknesses = data.get("weaknesses") or []
        recs = data.get("recommendations") or []
        evidence = data.get("evidence") or data.get("notes") or ""

        body = f'<div class="axis-name">{_esc(label)}{badge}</div>'
        if strengths:
            body += f'<div class="axis-strengths">▲ 강점: {_esc(" · ".join(strengths))}</div>'
        if weaknesses:
            body += f'<div class="axis-weaknesses">▼ 약점: {_esc(" · ".join(weaknesses))}</div>'
        if recs:
            body += f'<div class="axis-recs">→ 보강: {_esc(" / ".join(recs))}</div>'
        if evidence:
            body += f'<div class="axis-evidence">근거: {_esc(evidence)}</div>'

        cards += f'<div class="axis-card">{ring}<div class="axis-body">{body}</div></div>'

    return (
        f'<div class="sec">'
        f'<div class="sec-title">평가축별 상세</div>'
        f'<div class="axes-grid">{cards}</div>'
        f'</div>'
    )


def _render_recommendations(recs: list) -> str:
    if not recs:
        return ""
    items = ""
    for i, rec in enumerate(recs, 1):
        items += (
            f'<div class="rec-item">'
            f'<div class="rec-num">{i}</div>'
            f'<div class="rec-text">{_esc(rec)}</div>'
            f'</div>'
        )
    return (
        f'<div class="sec" style="border-left:4px solid #2b6cb0">'
        f'<div class="sec-title">보강 포인트</div>'
        f'<div class="rec-list">{items}</div>'
        f'</div>'
    )


def generate_diagnosis_report(diagnosis: dict) -> str:
    facility_type = diagnosis.get("facility_type", "")
    ft_label = _facility_label(facility_type)
    axes_meta = axes_for(facility_type) if facility_type else {}
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    body = _render_header(diagnosis, ft_label)
    body += _render_page_dist(
        diagnosis.get("page_distribution") or {},
        diagnosis.get("total_pages") or 0,
    )

    deviation = diagnosis.get("pattern_deviation")
    if deviation:
        body += _render_pattern_deviation(deviation)

    body += _render_brief_compliance(diagnosis.get("brief_compliance") or {}, axes_meta)
    body += _render_requirement_mapping(diagnosis.get("requirement_mapping") or [], axes_meta)
    body += _render_axes(diagnosis.get("axes") or {}, axes_meta)
    body += _render_recommendations(diagnosis.get("recommendations") or [])

    comp_name = _esc(diagnosis.get("competition_name") or "")
    footer = f'<div class="footer">Competition Analyzer · {comp_name} · {generated_at}</div>'

    return (
        "<!DOCTYPE html><html lang='ko'><head>"
        "<meta charset='utf-8'>"
        f"<title>{comp_name or ft_label} 진단 결과</title>"
        f"{_CSS}"
        "</head><body>"
        f"<div class='wrap'>{body}{footer}</div>"
        "</body></html>"
    )
