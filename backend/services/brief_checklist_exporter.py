"""
brief_checklist_exporter.py — 지침서 체크리스트 내보내기 (LLM 호출 없음, 렌더만)

공개 API:
  to_markdown(brief_data, validation) -> str   — Markdown 텍스트
  to_xlsx(brief_data, validation) -> bytes     — Excel 파일 (openpyxl)

인수:
  brief_data  : _brief.json dict
                (merge_extracted_data + _requirements + validation 머지 완료 상태)
  validation  : brief_data.get("validation", {})
                {"flags": [...], "summary": {high,medium,low}, "checked_rules": [...]}

4개 섹션/시트:
  1) 면적·프로그램 요구 — room_program/zones + 면적·비율·층수 한도
  2) 심사기준 — evaluation_categories 배점표
  3) 요구사항·필수조건 — requirements 축별 + special_requirements + design_guide
  4) 검증 경고 — validation.flags (severity 정렬 + xlsx 색 강조)

데이터 경로:
  새 BRIEF taxonomy  : brief_program / brief_regulations / brief_evaluation / brief_design_guide
  구 AREA_TABLE 경로 : area_table (room_program, zone_summary)
  _requirements      : extract_brief_requirements() 결과
  _quantitative      : merge_extracted_data() 자동 집계
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _first(data: dict, key: str) -> dict:
    """dict에서 키를 꺼내 리스트면 첫 요소 반환, 없으면 {}."""
    v = data.get(key) or {}
    if isinstance(v, list):
        v = v[0] if v else {}
    return v if isinstance(v, dict) else {}


def _as_list(data: dict, key: str) -> list:
    """dict에서 키를 꺼내 항상 list로 반환. None/빈값이면 []."""
    v = data.get(key) or []
    return v if isinstance(v, list) else ([v] if v else [])


def _str_item(item: Any) -> str:
    """리스트 항목을 문자열로 변환. dict면 공통 텍스트 키 탐색."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for k in ("description", "text", "name", "requirement", "guideline", "item"):
            if item.get(k):
                return str(item[k])
        return str(item)
    return str(item) if item is not None else ""


def _fmt_num(val: Any, unit: str = "") -> str:
    """숫자를 천 단위 구분 포맷으로 변환. None이면 빈 문자열."""
    if val is None:
        return ""
    try:
        fval = float(val)
        formatted = f"{int(fval):,}" if fval == int(fval) else f"{fval:,.1f}"
    except (TypeError, ValueError):
        return str(val)
    return f"{formatted}{unit}" if unit else formatted


_SEVERITY_LABEL = {"high": "높음", "medium": "보통", "low": "낮음"}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ── 섹션 데이터 추출 ──────────────────────────────────────────────────────────

def _extract_sections(brief_data: dict) -> dict:
    """brief_data에서 4개 섹션용 정규화 데이터를 추출."""
    bp    = _first(brief_data, "brief_program")
    br    = _first(brief_data, "brief_regulations")
    at    = _first(brief_data, "area_table")
    be    = _first(brief_data, "brief_evaluation")
    dg    = _first(brief_data, "brief_design_guide")
    quant = brief_data.get("_quantitative") or {}
    reqs  = brief_data.get("_requirements") or {}

    # ── Section 1: 면적·프로그램 ─────────────────────────────────────────────
    total_fa = (
        bp.get("total_required_floor_area_sqm")
        or at.get("total_required_area_sqm")
        or quant.get("total_floor_area_sqm")
    )
    site_area = (
        bp.get("site_area_sqm")
        or at.get("site_area_sqm")
        or quant.get("site_area_sqm")
    )
    bcr = (
        bp.get("building_coverage_limit_pct")
        or br.get("building_coverage_ratio_limit_pct")
        or at.get("building_coverage_limit_pct")
        or quant.get("building_coverage_ratio_pct")
    )
    far = (
        bp.get("floor_area_ratio_limit_pct")
        or br.get("floor_area_ratio_limit_pct")
        or at.get("floor_area_ratio_limit_pct")
        or quant.get("floor_area_ratio_pct")
    )
    height       = br.get("height_limit_m") or dg.get("height_limit_m")
    floors_above = bp.get("max_floors_above") or quant.get("floors_above")
    floors_below = bp.get("max_floors_below") or quant.get("floors_below")
    parking      = (
        bp.get("required_parking")
        or at.get("parking_required")
        or quant.get("parking_count")
    )

    # 실별 면적 — 새 taxonomy: rooms[{name,required_area_sqm,required_count,floor,notes}]
    #            구 경로:      room_program[{name,area_sqm,count,notes}]
    rooms = _as_list(bp, "rooms") or _as_list(at, "room_program")

    # 존 구성 — 새: zones[{name,area_sqm}], 구: zone_summary[{zone,area_sqm}]
    zones = _as_list(bp, "zones") or _as_list(at, "zone_summary")

    # ── Section 2: 심사기준 ───────────────────────────────────────────────────
    categories   = _as_list(be, "evaluation_categories")
    legacy_crit  = _as_list(reqs, "evaluation_criteria")
    eval_rows    = categories if categories else [
        {"name": c.get("item", ""), "points": c.get("points"), "description": ""}
        for c in legacy_crit
    ]
    total_points = be.get("total_points")
    eval_method  = be.get("evaluation_method") or ""
    jury         = be.get("jury_composition") or ""
    disqualify   = _as_list(be, "disqualification_criteria")

    # ── Section 3: 요구사항 ───────────────────────────────────────────────────
    requirements   = _as_list(reqs, "requirements")
    special_reqs   = _as_list(reqs, "special_requirements")
    design_reqs    = _as_list(dg, "design_requirements")
    setbacks       = _as_list(dg, "setback_requirements")
    materials      = _as_list(dg, "materials_required")
    sustainability = _as_list(dg, "sustainability_requirements")
    prohibited     = _as_list(dg, "prohibited_items")
    concept        = dg.get("concept_direction") or ""
    special_guide  = _as_list(dg, "special_guidelines")

    return {
        "area": {
            "total_fa": total_fa, "site_area": site_area,
            "bcr": bcr, "far": far, "height": height,
            "floors_above": floors_above, "floors_below": floors_below,
            "parking": parking, "rooms": rooms, "zones": zones,
        },
        "eval": {
            "rows": eval_rows, "total_points": total_points,
            "eval_method": eval_method, "jury": jury, "disqualify": disqualify,
        },
        "reqs": {
            "requirements": requirements, "special_reqs": special_reqs,
            "design_reqs": design_reqs, "setbacks": setbacks,
            "materials": materials, "sustainability": sustainability,
            "prohibited": prohibited, "concept": concept,
            "special_guide": special_guide,
        },
    }


# ── Markdown ───────────────────────────────────────────────────────────────────

def _md_row(cells: list[str], widths: list[int]) -> str:
    return "| " + " | ".join(
        c.ljust(widths[i]) for i, c in enumerate(cells)
    ) + " |"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    n = len(headers)
    widths = [
        max(len(headers[i]), *(len(r[i]) if i < len(r) else 0 for r in rows), 3)
        for i in range(n)
    ]
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [_md_row(headers, widths), sep]
    for row in rows:
        padded = [row[i] if i < len(row) else "" for i in range(n)]
        lines.append(_md_row(padded, widths))
    return "\n".join(lines)


def to_markdown(brief_data: dict, validation: dict) -> str:
    """지침서 체크리스트를 Markdown 문자열로 반환."""
    s    = _extract_sections(brief_data)
    a, e, r = s["area"], s["eval"], s["reqs"]
    flags = sorted(
        validation.get("flags") or [],
        key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 2),
    )
    summary = validation.get("summary") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = [
        "# 지침서 체크리스트",
        f"\n생성: {now}\n",
    ]

    # ── 1. 면적·프로그램 ──────────────────────────────────────────────────────
    lines.append("## 1. 면적·프로그램 요구\n")
    lines.append("### 전체 규모 한도\n")
    scale_rows = [
        ["대지면적",    _fmt_num(a["site_area"], " ㎡")],
        ["요구 연면적", _fmt_num(a["total_fa"], " ㎡")],
        ["건폐율 한도", _fmt_num(a["bcr"], "%")],
        ["용적률 한도", _fmt_num(a["far"], "%")],
        ["높이 한도",   _fmt_num(a["height"], " m")],
        ["지상 층수",   _fmt_num(a["floors_above"], " 층")],
        ["지하 층수",   ("B" + _fmt_num(a["floors_below"])) if a["floors_below"] else ""],
        ["주차 대수",   _fmt_num(a["parking"], " 대")],
    ]
    lines.append(_md_table(["항목", "수치"], scale_rows))
    lines.append("")

    if a["rooms"]:
        lines.append("### 실별 면적 프로그램\n")
        room_rows = [
            [
                rm.get("name") or "",
                _fmt_num(rm.get("required_area_sqm") or rm.get("area_sqm"), " ㎡"),
                str(rm.get("required_count") or rm.get("count") or 1),
                rm.get("floor") or "",
                rm.get("notes") or "",
            ]
            for rm in a["rooms"]
        ]
        lines.append(_md_table(["실명", "요구면적(㎡)", "개수", "위치/층", "비고"], room_rows))
        lines.append("")

    if a["zones"]:
        lines.append("### 존 구성\n")
        zone_rows = [
            [z.get("name") or z.get("zone") or "", _fmt_num(z.get("area_sqm"), " ㎡")]
            for z in a["zones"]
        ]
        lines.append(_md_table(["존명", "면적(㎡)"], zone_rows))
        lines.append("")

    # ── 2. 심사기준 ───────────────────────────────────────────────────────────
    lines.append("## 2. 심사기준 (배점표)\n")
    if e["total_points"] is not None:
        lines.append(f"**총 배점:** {_fmt_num(e['total_points'])} 점  ")
    if e["eval_method"]:
        lines.append(f"**평가 방법:** {e['eval_method']}  ")
    if e["jury"]:
        lines.append(f"**심사단 구성:** {e['jury']}  ")
    lines.append("")

    if e["rows"]:
        eval_tbl_rows = [
            [
                row.get("name") or "",
                _fmt_num(row.get("points")),
                row.get("description") or "",
            ]
            for row in e["rows"]
        ]
        lines.append(_md_table(["항목명", "배점", "설명"], eval_tbl_rows))
        lines.append("")

    if e["disqualify"]:
        lines.append("### 실격 요건\n")
        for d in e["disqualify"]:
            lines.append(f"- {_str_item(d)}")
        lines.append("")

    # ── 3. 요구사항·필수조건 ──────────────────────────────────────────────────
    lines.append("## 3. 요구사항·필수조건\n")

    if r["requirements"]:
        lines.append("### 평가축별 요구사항\n")
        req_rows = [
            [
                req.get("axis") or "",
                req.get("description") or "",
                _fmt_num(req.get("weight_pct"), "%"),
            ]
            for req in r["requirements"]
        ]
        lines.append(_md_table(["평가축", "설명", "배점비중(%)"], req_rows))
        lines.append("")

    if r["concept"]:
        lines.append(f"**설계 방향:** {r['concept']}\n")

    list_sections = [
        ("특수 요구사항", r["special_reqs"]),
        ("설계 지침",     r["design_reqs"]),
        ("후퇴선 요건",   r["setbacks"]),
        ("재료 요건",     r["materials"]),
        ("친환경 요건",   r["sustainability"]),
        ("금지 사항",     r["prohibited"]),
        ("특별 지침",     r["special_guide"]),
    ]
    for label, items in list_sections:
        if items:
            lines.append(f"### {label}\n")
            for item in items:
                lines.append(f"- {_str_item(item)}")
            lines.append("")

    # ── 4. 검증 경고 ──────────────────────────────────────────────────────────
    lines.append("## 4. 검증 경고\n")
    high_n   = summary.get("high", 0)
    medium_n = summary.get("medium", 0)
    low_n    = summary.get("low", 0)
    lines.append(f"**요약:** 높음 {high_n}건, 보통 {medium_n}건, 낮음 {low_n}건\n")

    if flags:
        flag_rows = [
            [
                _SEVERITY_LABEL.get(f.get("severity", ""), f.get("severity", "")),
                f.get("type") or "",
                f.get("message") or "",
                f.get("location") or "",
            ]
            for f in flags
        ]
        lines.append(_md_table(["심각도", "유형", "메시지", "위치"], flag_rows))
    else:
        lines.append("_검출된 경고 없음_")
    lines.append("")

    return "\n".join(lines)


# ── Excel (openpyxl) ──────────────────────────────────────────────────────────

def to_xlsx(brief_data: dict, validation: dict) -> bytes:
    """지침서 체크리스트를 Excel(.xlsx) bytes로 반환. 4개 시트."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl 패키지가 설치되지 않았습니다. "
            "'pip install openpyxl' 후 재시작하세요."
        ) from exc

    s    = _extract_sections(brief_data)
    a, e, r = s["area"], s["eval"], s["reqs"]
    flags = sorted(
        validation.get("flags") or [],
        key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 2),
    )
    summary = validation.get("summary") or {}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # 기본 Sheet 제거

    # ── 공통 스타일 ───────────────────────────────────────────────────────────
    _bold      = Font(bold=True)
    _hdr_font  = Font(bold=True, color="FFFFFF")
    _hdr_fill  = PatternFill("solid", fgColor="3D3D6B")   # 남색 헤더
    _sec_fill  = PatternFill("solid", fgColor="E4E4F0")   # 섹션 제목 배경
    _sub_fill  = PatternFill("solid", fgColor="F2F2FA")   # 소제목 배경
    _center    = Alignment(horizontal="center", vertical="center")
    _wrap_top  = Alignment(wrap_text=True, vertical="top")

    _SEVERITY_FILL = {
        "high":   PatternFill("solid", fgColor="FFCCCC"),
        "medium": PatternFill("solid", fgColor="FFF3CD"),
        "low":    PatternFill("solid", fgColor="D9EDF7"),
    }

    def _write_section_title(ws, title: str, row: int, span: int = 4) -> int:
        c = ws.cell(row=row, column=1, value=title)
        c.font = Font(bold=True, size=13, color="1A1A4E")
        c.fill = _sec_fill
        c.alignment = _center
        if span > 1:
            ws.merge_cells(
                start_row=row, start_column=1,
                end_row=row, end_column=span,
            )
        ws.row_dimensions[row].height = 22
        return row + 1

    def _write_subsection(ws, title: str, row: int, span: int = 4) -> int:
        c = ws.cell(row=row, column=1, value=title)
        c.font = _bold
        c.fill = _sub_fill
        if span > 1:
            ws.merge_cells(
                start_row=row, start_column=1,
                end_row=row, end_column=span,
            )
        return row + 1

    def _write_header(ws, cols: list[str], row: int) -> int:
        for ci, label in enumerate(cols, 1):
            c = ws.cell(row=row, column=ci, value=label)
            c.font = _hdr_font
            c.fill = _hdr_fill
            c.alignment = _center
        return row + 1

    def _write_kv(ws, label: str, val: Any, row: int) -> int:
        ws.cell(row=row, column=1, value=label).font = _bold
        ws.cell(row=row, column=2, value=val)
        return row + 1

    def _auto_width(ws) -> None:
        """셀 최대 길이 기준 열 너비 자동 조정 (최소 10, 최대 60)."""
        for col in ws.columns:
            max_len = max(
                (len(str(cell.value)) for cell in col if cell.value is not None),
                default=6,
            )
            ws.column_dimensions[
                get_column_letter(col[0].column)
            ].width = max(min(max_len + 4, 60), 10)

    # ── Sheet 1: 면적·프로그램 ────────────────────────────────────────────────
    ws1 = wb.create_sheet("1.면적·프로그램")
    row = _write_section_title(ws1, "1. 면적·프로그램 요구", 1, span=5)
    row += 1  # 여백

    row = _write_subsection(ws1, "전체 규모 한도", row, span=2)
    for label, val in [
        ("대지면적 (㎡)",    a["site_area"]),
        ("요구 연면적 (㎡)", a["total_fa"]),
        ("건폐율 한도 (%)",  a["bcr"]),
        ("용적률 한도 (%)",  a["far"]),
        ("높이 한도 (m)",    a["height"]),
        ("지상 층수",        a["floors_above"]),
        ("지하 층수",        a["floors_below"]),
        ("주차 대수 (대)",   a["parking"]),
    ]:
        row = _write_kv(ws1, label, val, row)
    row += 1

    if a["rooms"]:
        row = _write_subsection(ws1, "실별 면적 프로그램", row, span=5)
        row = _write_header(ws1, ["실명", "요구면적(㎡)", "개수", "위치/층", "비고"], row)
        for rm in a["rooms"]:
            if not isinstance(rm, dict):
                ws1.cell(row=row, column=1, value=_str_item(rm))
                row += 1
                continue
            ws1.cell(row=row, column=1, value=rm.get("name") or "")
            area = rm.get("required_area_sqm") or rm.get("area_sqm")
            ws1.cell(row=row, column=2, value=area)
            ws1.cell(row=row, column=3, value=rm.get("required_count") or rm.get("count") or 1)
            ws1.cell(row=row, column=4, value=rm.get("floor") or "")
            ws1.cell(row=row, column=5, value=rm.get("notes") or "")
            row += 1
        row += 1

    if a["zones"]:
        row = _write_subsection(ws1, "존 구성", row, span=2)
        row = _write_header(ws1, ["존명", "면적(㎡)"], row)
        for z in a["zones"]:
            ws1.cell(row=row, column=1, value=z.get("name") or z.get("zone") or "")
            ws1.cell(row=row, column=2, value=z.get("area_sqm"))
            row += 1

    _auto_width(ws1)

    # ── Sheet 2: 심사기준 ─────────────────────────────────────────────────────
    ws2 = wb.create_sheet("2.심사기준")
    row = _write_section_title(ws2, "2. 심사기준 (배점표)", 1, span=3)
    row += 1

    for label, val in [
        ("총 배점",    e["total_points"]),
        ("평가 방법",  e["eval_method"] or None),
        ("심사단 구성", e["jury"] or None),
    ]:
        row = _write_kv(ws2, label, val, row)
    row += 1

    if e["rows"]:
        row = _write_header(ws2, ["항목명", "배점", "설명"], row)
        running_total: float = 0.0
        for ev in e["rows"]:
            if not isinstance(ev, dict):
                ws2.cell(row=row, column=1, value=_str_item(ev))
                row += 1
                continue
            ws2.cell(row=row, column=1, value=ev.get("name") or "")
            pts = ev.get("points")
            ws2.cell(row=row, column=2, value=pts)
            desc_cell = ws2.cell(row=row, column=3, value=ev.get("description") or "")
            desc_cell.alignment = _wrap_top
            if isinstance(pts, (int, float)):
                running_total += pts
            row += 1
        # 합계 행
        ws2.cell(row=row, column=1, value="합계").font = _bold
        ws2.cell(row=row, column=2, value=running_total if running_total else None).font = _bold
        row += 2

    if e["disqualify"]:
        row = _write_subsection(ws2, "실격 요건", row, span=3)
        for d in e["disqualify"]:
            c = ws2.cell(row=row, column=1, value=_str_item(d))
            c.alignment = _wrap_top
            ws2.merge_cells(
                start_row=row, start_column=1, end_row=row, end_column=3,
            )
            row += 1

    _auto_width(ws2)

    # ── Sheet 3: 요구사항·필수조건 ────────────────────────────────────────────
    ws3 = wb.create_sheet("3.요구사항")
    row = _write_section_title(ws3, "3. 요구사항·필수조건", 1, span=3)
    row += 1

    if r["requirements"]:
        row = _write_subsection(ws3, "평가축별 요구사항", row, span=3)
        row = _write_header(ws3, ["평가축", "설명", "배점비중(%)"], row)
        for req in r["requirements"]:
            if not isinstance(req, dict):
                ws3.cell(row=row, column=1, value=_str_item(req))
                row += 1
                continue
            ws3.cell(row=row, column=1, value=req.get("axis") or "")
            d_cell = ws3.cell(row=row, column=2, value=req.get("description") or "")
            d_cell.alignment = _wrap_top
            wt = req.get("weight_pct")
            ws3.cell(row=row, column=3, value=wt)
            row += 1
        row += 1

    if r["concept"]:
        ws3.cell(row=row, column=1, value="설계 방향").font = _bold
        c = ws3.cell(row=row, column=2, value=r["concept"])
        c.alignment = _wrap_top
        ws3.merge_cells(
            start_row=row, start_column=2, end_row=row, end_column=3,
        )
        row += 2

    list_sections = [
        ("특수 요구사항", r["special_reqs"]),
        ("설계 지침",     r["design_reqs"]),
        ("후퇴선 요건",   r["setbacks"]),
        ("재료 요건",     r["materials"]),
        ("친환경 요건",   r["sustainability"]),
        ("금지 사항",     r["prohibited"]),
        ("특별 지침",     r["special_guide"]),
    ]
    for label, items in list_sections:
        if not items:
            continue
        row = _write_subsection(ws3, label, row, span=3)
        for item in items:
            c = ws3.cell(row=row, column=1, value=f"• {_str_item(item)}")
            c.alignment = _wrap_top
            ws3.merge_cells(
                start_row=row, start_column=1, end_row=row, end_column=3,
            )
            row += 1
        row += 1

    _auto_width(ws3)

    # ── Sheet 4: 검증 경고 ────────────────────────────────────────────────────
    ws4 = wb.create_sheet("4.검증경고")
    row = _write_section_title(ws4, "4. 검증 경고", 1, span=4)
    row += 1

    high_n, med_n, low_n = (
        summary.get("high", 0),
        summary.get("medium", 0),
        summary.get("low", 0),
    )
    summary_cell = ws4.cell(
        row=row, column=1,
        value=f"요약: 높음 {high_n}건 / 보통 {med_n}건 / 낮음 {low_n}건",
    )
    summary_cell.font = _bold
    ws4.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 2

    row = _write_header(ws4, ["심각도", "유형", "메시지", "위치"], row)

    if flags:
        for flag in flags:
            sev  = flag.get("severity", "low")
            fill = _SEVERITY_FILL.get(sev, _SEVERITY_FILL["low"])
            vals = [
                _SEVERITY_LABEL.get(sev, sev),
                flag.get("type") or "",
                flag.get("message") or "",
                flag.get("location") or "",
            ]
            for ci, val in enumerate(vals, 1):
                c = ws4.cell(row=row, column=ci, value=val)
                c.fill = fill
                c.alignment = _wrap_top
            row += 1
    else:
        c = ws4.cell(row=row, column=1, value="검출된 경고 없음")
        ws4.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

    _auto_width(ws4)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
