# -*- coding: utf-8 -*-
"""개념 매스 다이어그램 — 부지별 (1) 적층(층별 프로그램) + (2) 용량 핏(용적 봉투 vs 프로그램).

LLM 0 · 결정론 (Report Generation Rule). 새 추출 없음 — feasibility_export 부지
지오메트리(대지·건폐·용적·높이한도)와 이미 추출된 면적표 시설 프로그램을 재배치.
제안서 덱(brief_proposal_report_generator)과 체크리스트가 쓰는 `program_stack_html`
과 같은 '한 문서화' 계열 공용 헬퍼.

용량 모델(결정론):
  footprint      = 대지 × 건폐율
  봉투 층수      = min(용적률/건폐율, 높이한도/층고)          # 층고 4.3m 가정
  용적 봉투(cap) = min(대지 × 용적률, footprint × 높이한도층)  # 지상 허용 연면적
  지상 추정      = 시설 연면적 합 − '지하' 표기 시설 합

⚠ 지상/지하 한계(정직성): 시설 소계(예 '구청')는 지상·지하층을 한 값에 섞어 담아
분리 불가. 지하는 **이름에 '지하' 표기된 시설만** 제외하므로 지상 추정은 과대 가능
(캡션에 고지). 따라서 '초과'는 단정이 아니라 "지하 배분·효율 재검토" 신호로 표기.
정북 일조·가로구역 계단컷은 봉투 층수에 미반영(향후) — 캡션 고지.

회귀: tests/test_brief_massing.py.
"""

from __future__ import annotations

import html
import re

from services.brief_checklist_exporter import (
    _extract_sections,
    _to_area_float,
    _norm_prog_name,
    _is_subtotal_name,
)
from services.report_theme import CATEGORY_COLORS

_SANS = "var(--sans)"
_FLOOR_H = 4.3            # 층고 가정 (m) — 공공청사 기준
_UNDER_RE = re.compile(r"지\s*하")


def _is_under(name: str) -> bool:
    """이름에 '지하' 표기가 있으면 지하 시설 (용적률 산정 제외 근사)."""
    return bool(_UNDER_RE.search(name or ""))


def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _site_geometry(brief_data: dict) -> list[dict]:
    """feasibility_export.sites[] → 부지 지오메트리 리스트 (문서 순서 보존)."""
    fe = brief_data.get("feasibility_export") or {}
    out = []
    for s in fe.get("sites") or []:
        if not isinstance(s, dict):
            continue
        area = _num(s.get("site_area_sqm"))
        bcr = _num(s.get("building_coverage_pct"))
        far = _num(s.get("floor_area_ratio_pct"))
        if not (area and bcr and far):
            continue                       # 봉투 계산 불가 → 부지 제외
        out.append({
            "site_id": (s.get("site_id") or "").strip() or f"부지{len(out) + 1}",
            "area": area, "bcr": bcr, "far": far,
            "h_limit": _num(s.get("max_height_m")),
        })
    return out


def _clean_facilities(raw: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """(name, area) → 장식기호 제거·소계 제외·양수만. 동일 라벨은 합산하지 않음
    (매스는 부지별 개별 시설을 보여야 하므로 program_stack 의 dedup 과 다름)."""
    out = []
    for name, area in raw:
        if not area or area <= 0:
            continue
        n = _norm_prog_name(name)
        if _is_subtotal_name(n):
            continue
        out.append((n, float(area)))
    return out


def _per_site_programs(a: dict) -> list[list[tuple[str, float]]]:
    """면적표 area_rows → 부지별 시설 프로그램 버킷 리스트 (문서 순서).

    다부지('부지N' site_total 존재): 각 부지 요약 시설만 채택, 선언 subtotal 도달 시
    닫음(재집계·상세 dump 배제 — program_stack 과 동일 로직, 단 부지별로 분리 보존).
    단일부지: 최상위 시설 subtotal 을 하나의 버킷으로.
    """
    rows = [r for r in (a.get("area_rows") or []) if isinstance(r, dict)]
    multi_site = any((r.get("row_type") or "") == "site_total" and "부지" in (r.get("name") or "")
                     for r in rows)

    buckets: list[list[tuple[str, float]]] = []
    if multi_site:
        cur = None
        site_target = None
        site_sum = 0.0
        for r in rows:
            rt = r.get("row_type") or "space"
            if rt == "site_total":
                if "부지" in (r.get("name") or ""):
                    cur = []
                    buckets.append(cur)
                    site_target = _to_area_float(r.get("subtotal_area")) or _to_area_float(r.get("area"))
                    site_sum = 0.0
                else:
                    cur = None            # 총합계·재집계 헤더 → 섹션 아님
                continue
            if rt == "facility":
                if cur is None:
                    continue
                area = _to_area_float(r.get("subtotal_area")) or _to_area_float(r.get("area"))
                if area:
                    cur.append(((r.get("name") or "").strip() or "시설", area))
                    site_sum += area
                    if site_target and site_sum >= site_target * 0.995:
                        cur = None        # 이 부지 요약 완료
            else:
                cur = None                # 상세 시작 → 요약 종료
        return [_clean_facilities(b) for b in buckets if b]

    # 단일부지 — 최상위 시설 subtotal 수집
    single: list[tuple[str, float]] = []
    for r in rows:
        rt = r.get("row_type") or "space"
        if rt == "facility":
            area = _to_area_float(r.get("subtotal_area")) or _to_area_float(r.get("area"))
            if area:
                single.append(((r.get("name") or "").strip() or "시설", area))
    single = _clean_facilities(single)
    return [single] if single else []


def build_massing_sites(brief_data: dict) -> list[dict]:
    """부지 지오메트리 × 부지별 프로그램 → 매스 계산 결과 리스트 (결정론, 테스트용).

    지오메트리와 프로그램 버킷을 문서 순서로 zip. 프로그램이 없는 부지는 제외.
    """
    geoms = _site_geometry(brief_data)
    if not geoms:
        return []
    try:
        a = _extract_sections(brief_data)["area"]
    except Exception:
        return []
    buckets = _per_site_programs(a)
    if not buckets:
        return []

    sites = []
    for i, g in enumerate(geoms):
        if i >= len(buckets):
            break
        progs = buckets[i]
        if len(progs) < 1:
            continue
        fp = g["area"] * g["bcr"] / 100.0
        fl_far = g["far"] / g["bcr"]
        fl_h = (g["h_limit"] / _FLOOR_H) if g["h_limit"] else None
        fl_env = min(fl_far, fl_h) if fl_h else fl_far
        binding = "용적률" if (fl_h is None or fl_far <= fl_h) else "높이한도"
        cap = fp * fl_env                                   # 지상 용적 봉투 연면적

        ground = [(n, ar) for n, ar in progs if not _is_under(n)]
        under = [(n, ar) for n, ar in progs if _is_under(n)]
        g_est = sum(ar for _, ar in ground)
        u_sum = sum(ar for _, ar in under)
        over = max(g_est - cap, 0.0)
        fill = (g_est / cap) if cap else 0.0

        sites.append({
            **g, "footprint": fp, "fl_env": fl_env, "binding": binding, "cap": cap,
            "ground": ground, "under": under,
            "ground_est": g_est, "under_sum": u_sum, "over": over, "fill": fill,
        })
    return sites


# ─────────────────────────── 렌더 (SVG, LLM 0) ───────────────────────────

def _esc(s):
    return html.escape(str(s), quote=True)


def _m2(v):
    return f"{v:,.0f}㎡"


def _color(i):
    return CATEGORY_COLORS[i % len(CATEGORY_COLORS)]


_VW = 690           # SVG viewBox 폭 (풀와이드)
_X0 = 6             # 바 시작 x
_BARW = 512        # 최대 바 폭 (끝 숫자 라벨 여백 확보)
_BAR_H = 18


def _fit_svg(site: dict) -> str:
    """가로 용량 핏 — 봉투(허용, 회색) / 지상 프로그램(소요, 색+초과 빨강) / 지하(빗금) 3개
    가로 바 + 용적 상한 세로 점선. 세로 타워 대신 폭을 꽉 채워 오른쪽 여백 제거."""
    cap, g_est, over, u_sum = site["cap"], site["ground_est"], site["over"], site["under_sum"]
    ground, under = site["ground"], site["under"]
    maxA = max(cap, g_est, u_sum) * 1.04 or 1.0

    def w_of(v):
        return v / maxA * _BARW

    parts = []

    def bar_row(y, label, endnum, note=""):
        parts.append(f'<text x="{_X0}" y="{y - 5:.0f}" font-size="10.5" font-weight="700" '
                     f'font-family="{_SANS}" fill="#141414">{label}</text>')
        if endnum:
            parts.append(f'<text x="{_X0 + _BARW + 8:.0f}" y="{y + _BAR_H - 5:.0f}" font-size="10.5" '
                         f'font-weight="700" font-family="{_SANS}" fill="#3a3a3a">{endnum}</text>')
        if note:
            parts.append(f'<text x="{_X0}" y="{y + _BAR_H + 13:.0f}" font-size="9.5" '
                         f'font-family="{_SANS}" fill="var(--muted)">{note}</text>')

    # 1) 용적 봉투(허용) — 회색 track
    y1 = 20
    bar_row(y1, "용적 봉투(허용)", f"{_m2(cap)} · {site['fl_env']:.1f}층")
    parts.append(f'<rect x="{_X0}" y="{y1}" width="{w_of(cap):.1f}" height="{_BAR_H}" '
                 f'fill="#6f6b66" fill-opacity="0.26" rx="1.5"/>')

    # 2) 지상 프로그램(소요) — 시설 색 세그먼트 + 초과 빨강
    y2 = 62
    soyo_note = (f"채움 {site['fill'] * 100:.0f}%" + (f" · 빨강 = 초과 {over:,.0f}㎡" if over > 1 else "")
                 + f" · footprint {site['footprint']:,.0f}㎡ × {site['fl_env']:.1f}층")
    bar_row(y2, "지상 프로그램(소요)", _m2(g_est), soyo_note)
    x = float(_X0)
    for i, (name, area) in enumerate(ground):
        px = w_of(area)
        parts.append(f'<rect x="{x:.1f}" y="{y2}" width="{px:.1f}" height="{_BAR_H}" '
                     f'fill="{_color(i)}" stroke="#fff" stroke-width="0.7"/>')
        if px >= 46:            # 넓은 세그먼트만 이름 인라인 (좁은 건 아래 범례)
            parts.append(f'<text x="{x + px / 2:.1f}" y="{y2 + _BAR_H / 2 + 4:.0f}" text-anchor="middle" '
                         f'font-size="9.5" font-weight="700" font-family="{_SANS}" fill="#fff">'
                         f'{_esc(name if len(name) <= 6 else name[:5] + "…")}</text>')
        x += px
    if over > 1:               # 초과분 — 용적 상한 너머 빨강
        parts.append(f'<rect x="{x:.1f}" y="{y2}" width="{w_of(over):.1f}" height="{_BAR_H}" '
                     f'fill="var(--accent)"/>')

    # 용적 상한 세로 점선 (봉투 폭 = 지상 허용 한계) — 두 바 관통
    xe = _X0 + w_of(cap)
    parts.append(f'<line x1="{xe:.1f}" y1="{y1 - 8}" x2="{xe:.1f}" y2="{y2 + _BAR_H + 4}" '
                 f'stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="5 3"/>')
    anchor = "end" if xe > _VW - 90 else "middle"
    parts.append(f'<text x="{xe:.1f}" y="{y1 - 11}" text-anchor="{anchor}" font-size="9.5" '
                 f'font-weight="700" font-family="{_SANS}" fill="var(--accent)">용적 상한</text>')

    svg_h = y2 + _BAR_H + 20
    # 3) 지하(용적 제외) — 빗금 (있을 때만)
    if u_sum > 0:
        y3 = svg_h + 8
        bar_row(y3, "지하 (용적 제외)", _m2(u_sum))
        parts.append(f'<rect x="{_X0}" y="{y3}" width="{w_of(u_sum):.1f}" height="{_BAR_H}" '
                     f'fill="#6a6a6a" fill-opacity="0.28" stroke="#6a6a6a" stroke-width="0.8" '
                     f'stroke-dasharray="3 2" rx="1.5"/>')
        svg_h = y3 + _BAR_H + 8

    return (f'<svg viewBox="0 0 {_VW} {svg_h:.0f}" width="100%" style="display:block" '
            f'role="img" aria-label="{_esc(site["site_id"])} 용량 핏">' + "".join(parts) + '</svg>')


def _legend_html(site: dict) -> str:
    """시설 범례 — 색·이름·㎡·(지상 대비 %). 인라인 라벨 못 단 좁은 세그먼트 커버."""
    g_est = site["ground_est"] or 1.0
    chips = []
    for i, (name, area) in enumerate(site["ground"]):
        pct = area / g_est * 100
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;'
            f'color:var(--muted);font-family:{_SANS}">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{_color(i)};'
            f'display:inline-block"></span>{_esc(name)} {_m2(area)} · {pct:.0f}%</span>')
    for name, area in site["under"]:
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;'
            f'color:var(--muted);font-family:{_SANS}">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:#6a6a6a;opacity:0.4;'
            f'display:inline-block"></span>{_esc(name)} {_m2(area)} · 지하</span>')
    if not chips:
        return ""
    return ('<div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px">'
            + "".join(chips) + '</div>')


def _site_block(site: dict) -> str:
    over = site["over"]
    vc = "var(--accent)" if over > 1 else "#4e7d3e"
    if over > 1:
        verdict = (f"지상 추정 {site['ground_est']:,.0f}㎡ / 용적 봉투 {site['cap']:,.0f}㎡ "
                   f"= {site['fill'] * 100:.0f}% — {site['binding']}이 {site['fl_env']:.1f}층에서 막음, "
                   f"지하 배분·효율 재검토 필요")
    else:
        verdict = f"봉투 내 수용 · 채움 {site['fill'] * 100:.0f}%"
    hlim = f" · 높이한도 {site['h_limit']:.0f}m" if site["h_limit"] else ""
    return (
        f'<div style="border:1px solid var(--line);border-radius:12px;padding:16px;background:#fff;margin-bottom:14px">'
        f'<div style="font-family:{_SANS};font-weight:800;font-size:15px;color:#141414">{_esc(site["site_id"])}</div>'
        f'<div style="font-size:11px;color:var(--muted);margin:2px 0 4px">'
        f'대지 {site["area"]:,.0f}㎡ · 건폐 {site["bcr"]:.0f}% · 용적 {site["far"]:.0f}%{hlim}</div>'
        f'<div style="font-size:12px;font-weight:700;color:{vc};margin-bottom:10px">{verdict}</div>'
        f'{_fit_svg(site)}{_legend_html(site)}'
        f'</div>')


def massing_html(brief_data: dict) -> str:
    """부지별 개념 매스 섹션 HTML (LLM 0, 결정론). 데이터 부족·오류 시 "" (graceful).

    제안서 덱과 체크리스트가 공유 가능한 공용 헬퍼. 소비 측은 빈 문자열이면 섹션 생략.
    """
    try:
        sites = build_massing_sites(brief_data)
        if not sites:
            return ""
        blocks = "".join(_site_block(s) for s in sites)
        cap = ("가로 바: 용적 봉투(허용, 회색)=footprint×봉투층 vs 지상 프로그램(소요, 시설 색·초과분 빨강), "
               "빨간 세로 점선=용적률 상한(지상 허용 한계), 빗금 바=지하(용적 제외). "
               "층고 4.3m 가정 · 시설 소계의 지하층은 분리 불가라 지상 추정은 과대 가능 · "
               "정북 일조·가로구역 계단컷 미반영 — 개념 스케일이며 실측/인허가 아님.")
        return (f'<div style="display:flex;flex-direction:column;gap:0">{blocks}</div>'
                f'<div style="font-size:11px;color:var(--muted);margin-top:4px;line-height:1.6;'
                f'font-family:{_SANS}">{cap}</div>')
    except Exception:
        return ""
