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

.winner-box { background: rgba(246,216,96,0.05); border: 1px solid rgba(246,216,96,0.2);
              border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.winner-box-title { font-size: 15px; font-weight: 700; color: #f6d860; margin-bottom: 12px; }
.w-axis { margin-bottom: 12px; }
.w-axis-label { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 4px; }

.footer { text-align: center; color: #4a5568; font-size: 12px; margin-top: 30px; padding: 12px; }
</style>
"""


def generate_comparison_report(
    meta: dict,
    submissions: list[dict],
    comparison: dict,
) -> str:
    comp_name    = meta.get("competition_name", "")
    facility_type = meta.get("facility_type", "")
    year         = meta.get("year", "")
    client       = meta.get("client", "")
    location     = meta.get("location", "")
    facility_label = FACILITY_TYPES.get(facility_type, facility_type)

    comp_subs  = comparison.get("submissions", {})
    ranking    = comparison.get("ranking", [])
    key_diff   = comparison.get("key_differentiators", [])
    winners    = [s["company"] for s in submissions if s.get("result") == "win"]

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

    # ── 참여 제안서 카드 ──────────────────────────────────
    cards = ""
    for s in submissions:
        company = s["company"]
        is_win  = s.get("result") == "win"
        pages   = s.get("total_pages", 0)
        badge   = '<span class="badge-win">★ 당선</span>' if is_win else '<span class="badge-lose">낙선</span>'
        wcls    = " winner" if is_win else ""
        cards  += f'<div class="sub-card{wcls}">{badge}<div class="sub-company">{company}</div><div class="sub-pages">{pages}페이지</div></div>'

    sub_section = f'<div class="sec"><div class="sec-title">참여 제안서</div><div class="sub-cards">{cards}</div></div>'

    # ── 비교 테이블 ───────────────────────────────────────
    company_list = list(comp_subs.keys())
    th_cols = "".join(
        f'<th style="{"background:#2d3748;color:#f6d860;" if c in winners else ""}min-width:200px">{c}{"  ★" if c in winners else ""}</th>'
        for c in company_list
    )

    rows = ""
    for axis in AXES:
        label = AXIS_LABELS_KO.get(axis, axis)
        cells = ""
        for company in company_list:
            ax = comp_subs.get(company, {}).get(axis, {})
            score      = ax.get("score")
            strengths  = ax.get("strengths", [])
            weaknesses = ax.get("weaknesses", [])
            compliance = ax.get("brief_compliance", "unclear")
            notes      = ax.get("notes", "")

            s_tags = "".join(f'<span class="tag tag-strength">{t}</span>' for t in strengths)
            w_tags = "".join(f'<span class="tag tag-weakness">{t}</span>' for t in weaknesses)
            cell_bg = "rgba(246,216,96,0.03)" if company in winners else ""

            cells += (
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
    rank_cls = {0: "r1", 1: "r2", 2: "r3"}
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
    diff_items = "".join(f'<div class="diff-item">{d}</div>' for d in key_diff)
    diff_section = (
        f'<div class="sec"><div class="sec-title">주요 차별화 요소</div><div class="diff-list">{diff_items}</div></div>'
        if key_diff else ""
    )

    # ── 당선작 강점 분석 ──────────────────────────────────
    winner_boxes = ""
    for winner in winners:
        wd = comp_subs.get(winner, {})
        axis_items = ""
        for axis in AXES:
            ax = wd.get(axis, {})
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
{sub_section}
{table_section}
{ranking_section}
{diff_section}
{winner_section}
<div class="footer">Competition Analyzer — 자동 생성 비교 리포트 · {comp_name}</div>
</div>
</body>
</html>"""
