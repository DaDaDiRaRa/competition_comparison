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


def _collect(data: dict, key: str, *list_keys: str) -> dict[str, list]:
    """다중 페이지 타입에서 list_key별 값을 모든 페이지에서 집계.

    Returns {list_key: [aggregated items]} — 한 페이지뿐이어도 동일하게 동작.
    """
    raw = data.get(key) or []
    if isinstance(raw, dict):
        raw = [raw]
    result: dict[str, list] = {lk: [] for lk in list_keys}
    for page in raw:
        if isinstance(page, dict):
            for lk in list_keys:
                result[lk].extend(page.get(lk) or [])
    return result


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


def _cell_safe(val: Any) -> Any:
    """openpyxl이 허용하는 스칼라로 변환. dict/list → 문자열 (숫자 dict는 합계)."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, dict):
        values = list(val.values())
        if values and all(isinstance(v, (int, float)) for v in values):
            return sum(values)
        return ", ".join(f"{k}: {v}" for k, v in val.items())
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _fmt_num(val: Any, unit: str = "") -> str:
    """숫자를 천 단위 구분 포맷으로 변환. None이면 빈 문자열."""
    if val is None:
        return ""
    if isinstance(val, dict):
        values = list(val.values())
        if values and all(isinstance(v, (int, float)) for v in values):
            val = sum(values)
        else:
            return ", ".join(f"{k}: {v}" for k, v in val.items())
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
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
    dg    = _first(brief_data, "brief_design_guide")   # 기타/폴백
    dm    = _first(brief_data, "brief_design_massing")
    dfa   = _first(brief_data, "brief_design_facade")
    ds    = _first(brief_data, "brief_design_sustain")
    bpi   = _first(brief_data, "brief_project_info")
    # BRIEF_DESIGN_* 다중 페이지 집계 — _first는 스칼라 전용, 리스트는 _collect 사용
    _dsp = _collect(brief_data, "brief_design_special",
                    "security_requirements", "accessibility_requirements",
                    "safety_requirements", "special_technical_requirements")
    _dm  = _collect(brief_data, "brief_design_massing",
                    "open_space_requirements", "parking_requirements",
                    "pedestrian_requirements", "connection_requirements",
                    "massing_guidelines")
    _dfa = _collect(brief_data, "brief_design_facade",
                    "primary_materials", "prohibited_materials",
                    "color_requirements", "facade_guidelines", "landscape_requirements")
    _ds  = _collect(brief_data, "brief_design_sustain",
                    "required_certifications", "energy_guidelines", "sustainability_requirements")
    quant = brief_data.get("_quantitative") or {}
    reqs  = brief_data.get("_requirements") or {}

    # ── Section 1: 면적·프로그램 ─────────────────────────────────────────────
    # sites 배열: 새 스키마(복수 부지 지원). 구 데이터는 빈 배열.
    sites = _as_list(bp, "sites")
    s0 = sites[0] if sites and isinstance(sites[0], dict) else {}

    total_fa = (
        bp.get("total_required_floor_area_sqm")
        or at.get("total_required_area_sqm")
        or quant.get("total_floor_area_sqm")
    )
    # 단일값: 구 top-level → sites[0] → area_table → quant 순
    site_area = (
        bp.get("site_area_sqm")
        or s0.get("site_area_sqm")
        or at.get("site_area_sqm")
        or quant.get("site_area_sqm")
    )
    bcr = (
        bp.get("building_coverage_limit_pct")
        or s0.get("building_coverage_limit_pct")
        or br.get("building_coverage_ratio_limit_pct")
        or at.get("building_coverage_limit_pct")
        or quant.get("building_coverage_ratio_pct")
    )
    far = (
        bp.get("floor_area_ratio_limit_pct")
        or s0.get("floor_area_ratio_limit_pct")
        or br.get("floor_area_ratio_limit_pct")
        or at.get("floor_area_ratio_limit_pct")
        or quant.get("floor_area_ratio_pct")
    )
    height       = br.get("height_limit_m") or s0.get("max_height_m") or dg.get("height_limit_m")
    floors_above = bp.get("max_floors_above") or quant.get("floors_above")
    floors_below = bp.get("max_floors_below") or quant.get("floors_below")
    parking      = (
        bp.get("required_parking")
        or at.get("parking_required")
        or quant.get("parking_count")
    )

    # 계층 면적표 — ALL brief_program 페이지의 area_table 합산
    # (BRIEF_PROGRAM이 여러 페이지면 각 페이지의 group이 다를 수 있어 concat)
    _bp_all = brief_data.get("brief_program") or []
    if isinstance(_bp_all, dict):
        _bp_all = [_bp_all]
    area_table: list = []
    shared_areas: list = []
    for _bpp in _bp_all:
        if isinstance(_bpp, dict):
            area_table.extend(_bpp.get("area_table") or [])
            shared_areas.extend(_bpp.get("shared_areas") or [])

    # 개략공사비 내역서 등 공사비 그룹 제거 (면적표와 무관)
    _COST_KW = {"공사비", "내역서", "공종", "원가", "견적"}
    area_table = [g for g in area_table
                  if not any(kw in (g.get("group_name") or "") for kw in _COST_KW)]

    # 구 경로 폴백: rooms / zones (area_table 없는 기존 데이터 호환)
    rooms = _as_list(bp, "rooms") or _as_list(at, "room_program")
    zones = _as_list(bp, "zones") or _as_list(at, "zone_summary")

    # 사업비·기간 — project-wide (병합 셀로 두 부지 공통)
    construction_cost = bp.get("estimated_construction_cost") or ""
    design_fee        = bp.get("estimated_design_fee") or ""
    design_period     = bp.get("design_period") or ""

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
    # 기타/폴백 BRIEF_DESIGN_GUIDE (구 데이터 하위호환)
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
            "parking": parking,
            "area_table": area_table, "shared_areas": shared_areas,  # 새 계층 구조
            "rooms": rooms, "zones": zones,                           # 구 경로 폴백
            "sites": sites,  # 복수 부지 raw 배열 (단일 부지면 len==1 or [])
            "construction_cost": construction_cost,
            "design_fee": design_fee,
            "design_period": design_period,
        },
        "eval": {
            "rows": eval_rows, "total_points": total_points,
            "eval_method": eval_method, "jury": jury, "disqualify": disqualify,
        },
        "reqs": {
            "requirements": requirements, "special_reqs": special_reqs,
            # 새 typed 설계 지침
            "massing": {
                "setback_m":    dm.get("building_setback_m"),
                "open_space":   _dm["open_space_requirements"],
                "parking":      _dm["parking_requirements"],
                "pedestrian":   _dm["pedestrian_requirements"],
                "connection":   _dm["connection_requirements"],
                "height_strategy": dm.get("height_strategy") or "",
                "guidelines":   _dm["massing_guidelines"],
            },
            "facade": {
                "primary_materials":   _dfa["primary_materials"],
                "prohibited_materials": _dfa["prohibited_materials"],
                "color":               _dfa["color_requirements"],
                "facade_guidelines":   _dfa["facade_guidelines"],
                "landscape":           _dfa["landscape_requirements"],
            },
            "sustain": {
                "certifications":    _ds["required_certifications"],
                "renewable_pct":     ds.get("renewable_energy_min_pct"),
                "energy_guidelines": _ds["energy_guidelines"],
                "sustainability_reqs": _ds["sustainability_requirements"],
            },
            "special": {
                "security":      _dsp["security_requirements"],
                "accessibility": _dsp["accessibility_requirements"],
                "safety":        _dsp["safety_requirements"],
                "special_tech":  _dsp["special_technical_requirements"],
            },
            # 기타/폴백 (구 BRIEF_DESIGN_GUIDE 하위호환)
            "design_reqs": design_reqs, "setbacks": setbacks,
            "materials": materials, "sustainability": sustainability,
            "prohibited": prohibited, "concept": concept,
            "special_guide": special_guide,
        },
        "project_info": {
            "sites": _as_list(bpi, "sites"),
            "competition_name": bpi.get("competition_name") or "",
            "organizer": bpi.get("organizer") or "",
            "competition_type": bpi.get("competition_type") or "",
            "construction_cost_100m_won": bpi.get("construction_cost_100m_won"),
            "design_cost_100m_won": bpi.get("design_cost_100m_won"),
            "construction_period_months": bpi.get("construction_period_months"),
            "budget_notes": _as_list(bpi, "budget_notes"),
            "special_conditions": _as_list(bpi, "special_conditions"),
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
    pi = s["project_info"]
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

    # ── 사업 개요 (BRIEF_PROJECT_INFO) ─────────────────────────────────────────
    bpi_sites_md = [st for st in pi["sites"] if isinstance(st, dict)]
    has_bpi_md = bool(bpi_sites_md or pi["competition_name"] or pi["construction_cost_100m_won"] is not None)
    if has_bpi_md:
        lines.append("### 사업 개요\n")
        info_rows_md = []
        if pi["competition_name"]:
            info_rows_md.append(["공모명", pi["competition_name"]])
        if pi["organizer"]:
            info_rows_md.append(["발주처", pi["organizer"]])
        if pi["competition_type"]:
            info_rows_md.append(["공모유형", pi["competition_type"]])
        if info_rows_md:
            lines.append(_md_table(["항목", "내용"], info_rows_md))
            lines.append("")
        if bpi_sites_md:
            lines.append("#### 부지별 건축개요\n")
            bpi_site_rows_md = [
                [
                    st.get("site_id") or f"부지{i+1}",
                    st.get("address") or "",
                    st.get("zoning") or "",
                    st.get("scope") or "",
                    ", ".join(st.get("facilities") or []) or "",
                    _fmt_num(st.get("site_area_sqm"), " ㎡"),
                    _fmt_num(st.get("floor_area_sqm"), " ㎡"),
                    _fmt_num(st.get("building_coverage_pct"), "%"),
                    _fmt_num(st.get("floor_area_ratio_pct"), "%"),
                    _fmt_num(st.get("max_height_m"), " m"),
                    _fmt_num(st.get("open_space_sqm"), " ㎡"),
                    st.get("open_space_notes") or "",
                ]
                for i, st in enumerate(bpi_sites_md)
            ]
            lines.append(_md_table(
                ["부지ID", "위치", "용도지역/지구", "공모범위", "도입시설",
                 "대지면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)", "최고높이(m)",
                 "공개공지(㎡)", "공개공지 조건"],
                bpi_site_rows_md,
            ))
            lines.append("")
        cost_rows_md = []
        if pi["construction_cost_100m_won"] is not None:
            cost_rows_md.append(["예정 공사비", _fmt_num(pi["construction_cost_100m_won"], " 억원")])
        if pi["design_cost_100m_won"] is not None:
            cost_rows_md.append(["예정 설계비", _fmt_num(pi["design_cost_100m_won"], " 억원")])
        if pi["construction_period_months"] is not None:
            cost_rows_md.append(["공사 기간", _fmt_num(pi["construction_period_months"], " 개월")])
        if cost_rows_md:
            lines.append("#### 사업비·기간\n")
            lines.append(_md_table(["항목", "내용"], cost_rows_md))
            lines.append("")
        if pi["budget_notes"]:
            lines.append("**예산 산정 기준:**")
            for note in pi["budget_notes"]:
                lines.append(f"- {_str_item(note)}")
            lines.append("")
        if pi["special_conditions"]:
            lines.append("**특기사항:**")
            for cond in pi["special_conditions"]:
                lines.append(f"- {_str_item(cond)}")
            lines.append("")

    lines.append("### 전체 규모 한도\n")

    multi_sites = [s for s in a["sites"] if isinstance(s, dict)] if len(a["sites"]) > 1 else []
    if multi_sites:
        # 복수 부지: 부지별 상세 테이블 (지역지구·시설·공개공지 포함)
        lines.append("#### 부지별 건축개요\n")
        site_rows = [
            [
                st.get("site_id") or f"부지{i+1}",
                st.get("address") or "",
                ", ".join(st.get("zoning") or []) or "",
                st.get("construction_type") or "",
                st.get("building_use") or "",
                ", ".join(st.get("facilities") or []) or "",
                _fmt_num(st.get("site_area_sqm"), " ㎡"),
                _fmt_num(st.get("floor_area_sqm"), " ㎡"),
                _fmt_num(st.get("building_coverage_limit_pct"), "%"),
                _fmt_num(st.get("floor_area_ratio_limit_pct"), "%"),
                _fmt_num(st.get("max_height_m"), " m"),
                _fmt_num(st.get("public_open_space_sqm"), " ㎡"),
                st.get("public_open_space_notes") or "",
            ]
            for i, st in enumerate(multi_sites)
        ]
        lines.append(_md_table(
            ["부지ID", "위치", "지역지구", "건축구분", "건축용도", "도입시설",
             "대지면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)", "높이(m)",
             "공개공지(㎡)", "공개공지 조건"],
            site_rows,
        ))
        lines.append("")
        lines.append("#### 공통 규모\n")
        scale_rows = [
            ["요구 총 연면적", _fmt_num(a["total_fa"], " ㎡")],
            ["지상 층수",      _fmt_num(a["floors_above"], " 층")],
            ["지하 층수",      ("B" + _fmt_num(a["floors_below"])) if a["floors_below"] else ""],
            ["주차 대수",      _fmt_num(a["parking"], " 대")],
            ["예정 공사비",    a["construction_cost"] or ""],
            ["예정 설계비",    a["design_fee"] or ""],
            ["설계 기간",      a["design_period"] or ""],
        ]
        lines.append(_md_table(["항목", "내용"], scale_rows))
    else:
        scale_rows = [
            ["대지면적",    _fmt_num(a["site_area"], " ㎡")],
            ["요구 연면적", _fmt_num(a["total_fa"], " ㎡")],
            ["건폐율 한도", _fmt_num(a["bcr"], "%")],
            ["용적률 한도", _fmt_num(a["far"], "%")],
            ["높이 한도",   _fmt_num(a["height"], " m")],
            ["지상 층수",   _fmt_num(a["floors_above"], " 층")],
            ["지하 층수",   ("B" + _fmt_num(a["floors_below"])) if a["floors_below"] else ""],
            ["주차 대수",   _fmt_num(a["parking"], " 대")],
            ["예정 공사비", a["construction_cost"] or ""],
            ["예정 설계비", a["design_fee"] or ""],
            ["설계 기간",   a["design_period"] or ""],
        ]
        lines.append(_md_table(["항목", "내용"], scale_rows))
    lines.append("")

    _AREA_HDR = ["구분", "기준면적(A)", "계획면적(B)", "비고"]

    if a["area_table"]:
        lines.append("### 실별 면적 프로그램\n")
        at_rows = []
        for grp in a["area_table"]:
            if not isinstance(grp, dict):
                continue
            gname = grp.get("group_name") or ""
            gtotal = _fmt_num(grp.get("total_area_sqm"), " ㎡")
            at_rows.append([f"**{gname}**" if gname else "", gtotal, "", ""])
            for item in (grp.get("items") or []):
                if not isinstance(item, dict):
                    continue
                at_rows.append([
                    f"　{item.get('name') or ''}",
                    _fmt_num(item.get("area_sqm"), " ㎡"), "",
                    item.get("notes") or "",
                ])
                for sub in (item.get("sub_items") or []):
                    if not isinstance(sub, dict):
                        continue
                    at_rows.append([
                        f"　　{sub.get('name') or ''}",
                        _fmt_num(sub.get("area_sqm"), " ㎡"), "",
                        sub.get("notes") or "",
                    ])
        if at_rows:
            lines.append(_md_table(_AREA_HDR, at_rows))
            lines.append("")
        if a["shared_areas"]:
            lines.append("#### 공용·공동 면적\n")
            sa_rows = [
                [sa.get("name") or "", _fmt_num(sa.get("area_sqm"), " ㎡"), "", sa.get("notes") or ""]
                for sa in a["shared_areas"] if isinstance(sa, dict)
            ]
            if sa_rows:
                lines.append(_md_table(_AREA_HDR, sa_rows))
                lines.append("")
    elif a["rooms"]:
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

    if not a["area_table"] and a["zones"]:
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

    # ── 배치·동선 지침 ────────────────────────────────────────────────────────
    m = r["massing"]
    _massing_items = []
    if m["setback_m"] is not None:
        _massing_items.append(f"이격거리: {m['setback_m']} m")
    if m["height_strategy"]:
        _massing_items.append(f"높이 전략: {m['height_strategy']}")
    for _lst in (m["open_space"], m["parking"], m["pedestrian"],
                 m["connection"], m["guidelines"]):
        _massing_items.extend(_str_item(x) for x in _lst)
    if _massing_items:
        lines.append("### 배치·동선 지침\n")
        for item in _massing_items:
            lines.append(f"- {item}")
        lines.append("")

    # ── 입면·재료 지침 ────────────────────────────────────────────────────────
    f = r["facade"]
    _facade_items = []
    if f["primary_materials"]:
        lines.append("### 입면·재료 지침\n")
        _fa_secs = [
            ("지정 재료",     f["primary_materials"]),
            ("금지 재료",     f["prohibited_materials"]),
            ("색채 계획",     f["color"]),
            ("입면 지침",     f["facade_guidelines"]),
            ("조경·경관",     f["landscape"]),
        ]
        for lbl, lst in _fa_secs:
            if lst:
                lines.append(f"**{lbl}:**")
                for item in lst:
                    lines.append(f"- {_str_item(item)}")
        lines.append("")
    elif any(f[k] for k in ("prohibited_materials", "color", "facade_guidelines", "landscape")):
        lines.append("### 입면·재료 지침\n")
        for lbl, lst in [
            ("금지 재료",   f["prohibited_materials"]),
            ("색채 계획",   f["color"]),
            ("입면 지침",   f["facade_guidelines"]),
            ("조경·경관",   f["landscape"]),
        ]:
            for item in lst:
                lines.append(f"- {_str_item(item)}")
        lines.append("")

    # ── 친환경·인증 요구사항 ─────────────────────────────────────────────────
    sv = r["sustain"]
    _has_sustain = bool(
        sv["certifications"] or sv["renewable_pct"] is not None
        or sv["energy_guidelines"] or sv["sustainability_reqs"]
    )
    if _has_sustain:
        lines.append("### 친환경·인증 요구사항\n")
        if sv["certifications"]:
            cert_rows = [
                [_str_item(c.get("name") if isinstance(c, dict) else c),
                 _str_item(c.get("required_grade", "") if isinstance(c, dict) else "")]
                for c in sv["certifications"]
            ]
            lines.append(_md_table(["인증명", "요구 등급"], cert_rows))
            lines.append("")
        if sv["renewable_pct"] is not None:
            lines.append(f"**신재생에너지 최소 비율:** {sv['renewable_pct']}%\n")
        for item in sv["energy_guidelines"] + sv["sustainability_reqs"]:
            lines.append(f"- {_str_item(item)}")
        lines.append("")

    # ── 특수·보안 지침 ────────────────────────────────────────────────────────
    sp = r["special"]
    _special_items = []
    for lst in (sp["security"], sp["accessibility"], sp["safety"], sp["special_tech"]):
        _special_items.extend(_str_item(x) for x in lst)
    if _special_items:
        lines.append("### 특수·보안 지침\n")
        for item in _special_items:
            lines.append(f"- {item}")
        lines.append("")

    # ── 기타 설계 지침 (폴백 / 구 데이터) ───────────────────────────────────
    list_sections = [
        ("특수 요구사항", r["special_reqs"]),
        ("기타 설계 지침", r["design_reqs"]),
        ("후퇴선 요건",   r["setbacks"]),
        ("재료 요건",     r["materials"]),
        ("친환경 요건",   r["sustainability"]),
        ("금지 사항",     r["prohibited"]),
        ("특별 지침",     r["special_guide"]),
    ]
    for lbl, items in list_sections:
        if items:
            lines.append(f"### {lbl}\n")
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
    pi = s["project_info"]
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
    _grp_fill  = PatternFill("solid", fgColor="DCDCF0")   # area_table 그룹 행 배경
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
        ws.cell(row=row, column=2, value=_cell_safe(val))
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

    _SITE_COLS = ["부지ID", "위치", "지역지구", "건축구분", "건축용도", "도입시설",
                  "대지면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)", "높이(m)",
                  "공개공지(㎡)", "공개공지 조건"]
    _BPI_SITE_COLS = ["부지ID", "위치", "용도지역/지구", "공모범위", "도입시설",
                      "대지면적(㎡)", "연면적(㎡)", "건폐율(%)", "용적률(%)", "최고높이(m)",
                      "공개공지(㎡)", "공개공지 조건"]
    multi_sites = [s for s in a["sites"] if isinstance(s, dict)] if len(a["sites"]) > 1 else []
    bpi_sites_xl = [st for st in pi["sites"] if isinstance(st, dict)]
    has_bpi_xl = bool(bpi_sites_xl or pi["competition_name"] or pi["construction_cost_100m_won"] is not None)

    _span1 = max(
        len(_SITE_COLS) if multi_sites else 0,
        len(_BPI_SITE_COLS) if bpi_sites_xl else 0,
        5,
    )
    row = _write_section_title(ws1, "1. 면적·프로그램 요구", 1, span=_span1)
    row += 1

    # ── 사업 개요 (BRIEF_PROJECT_INFO) ────────────────────────────────────────
    if has_bpi_xl:
        row = _write_subsection(ws1, "사업 개요", row, span=_span1)
        for label, val in [
            ("공모명",   pi["competition_name"] or None),
            ("발주처",   pi["organizer"] or None),
            ("공모유형", pi["competition_type"] or None),
        ]:
            if val:
                row = _write_kv(ws1, label, val, row)
        if bpi_sites_xl:
            row = _write_header(ws1, _BPI_SITE_COLS, row)
            for i, st in enumerate(bpi_sites_xl):
                vals = [
                    st.get("site_id") or f"부지{i+1}",
                    st.get("address") or "",
                    st.get("zoning") or "",
                    st.get("scope") or "",
                    ", ".join(st.get("facilities") or []) or "",
                    _cell_safe(st.get("site_area_sqm")),
                    _cell_safe(st.get("floor_area_sqm")),
                    _cell_safe(st.get("building_coverage_pct")),
                    _cell_safe(st.get("floor_area_ratio_pct")),
                    _cell_safe(st.get("max_height_m")),
                    _cell_safe(st.get("open_space_sqm")),
                    st.get("open_space_notes") or "",
                ]
                for ci, v in enumerate(vals, 1):
                    c = ws1.cell(row=row, column=ci, value=v)
                    c.alignment = _wrap_top
                row += 1
        for label, val in [
            ("예정 공사비 (억원)", pi["construction_cost_100m_won"]),
            ("예정 설계비 (억원)", pi["design_cost_100m_won"]),
            ("공사 기간 (개월)",  pi["construction_period_months"]),
        ]:
            if val is not None:
                row = _write_kv(ws1, label, val, row)
        for title, items in [
            ("예산 산정 기준", pi["budget_notes"]),
            ("특기사항",       pi["special_conditions"]),
        ]:
            if items:
                row = _write_subsection(ws1, title, row, span=2)
                for item in items:
                    c = ws1.cell(row=row, column=1, value=f"• {_str_item(item)}")
                    c.alignment = _wrap_top
                    ws1.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
                    row += 1
        row += 1

    # ── 전체 규모 한도 / 부지별 건축개요 ─────────────────────────────────────
    if multi_sites:
        # 복수 부지: 부지별 상세 테이블
        row = _write_subsection(ws1, "부지별 건축개요", row, span=len(_SITE_COLS))
        row = _write_header(ws1, _SITE_COLS, row)
        for i, st in enumerate(multi_sites):
            zoning_str = ", ".join(st.get("zoning") or []) or ""
            fac_str    = ", ".join(st.get("facilities") or []) or ""
            vals = [
                st.get("site_id") or f"부지{i+1}",
                st.get("address") or "",
                zoning_str,
                st.get("construction_type") or "",
                st.get("building_use") or "",
                fac_str,
                _cell_safe(st.get("site_area_sqm")),
                _cell_safe(st.get("floor_area_sqm")),
                _cell_safe(st.get("building_coverage_limit_pct")),
                _cell_safe(st.get("floor_area_ratio_limit_pct")),
                _cell_safe(st.get("max_height_m")),
                _cell_safe(st.get("public_open_space_sqm")),
                st.get("public_open_space_notes") or "",
            ]
            for ci, v in enumerate(vals, 1):
                c = ws1.cell(row=row, column=ci, value=v)
                c.alignment = _wrap_top
            row += 1
        row += 1
        row = _write_subsection(ws1, "공통 규모", row, span=2)
        for label, val in [
            ("요구 총 연면적 (㎡)", a["total_fa"]),
            ("지상 층수",           a["floors_above"]),
            ("지하 층수",           a["floors_below"]),
            ("주차 대수 (대)",      a["parking"]),
            ("예정 공사비",         a["construction_cost"] or None),
            ("예정 설계비",         a["design_fee"] or None),
            ("설계 기간",           a["design_period"] or None),
        ]:
            row = _write_kv(ws1, label, val, row)
    else:
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
            ("예정 공사비",      a["construction_cost"] or None),
            ("예정 설계비",      a["design_fee"] or None),
            ("설계 기간",        a["design_period"] or None),
        ]:
            row = _write_kv(ws1, label, val, row)
    row += 1

    _AT_COLS = ["구분", "기준면적(A)", "계획면적(B)", "비고"]

    if a["area_table"]:
        row = _write_subsection(ws1, "실별 면적 프로그램", row, span=4)
        row = _write_header(ws1, _AT_COLS, row)
        for grp in a["area_table"]:
            if not isinstance(grp, dict):
                continue
            # 그룹 행: 굵게 + _grp_fill
            c = ws1.cell(row=row, column=1, value=grp.get("group_name") or "")
            c.font = _bold; c.fill = _grp_fill
            c2 = ws1.cell(row=row, column=2, value=grp.get("total_area_sqm"))
            c2.font = _bold; c2.fill = _grp_fill
            for ci in (3, 4):
                ws1.cell(row=row, column=ci).fill = _grp_fill
            row += 1
            for item in (grp.get("items") or []):
                if not isinstance(item, dict):
                    continue
                c = ws1.cell(row=row, column=1, value=item.get("name") or "")
                c.alignment = Alignment(indent=2, vertical="top")
                ws1.cell(row=row, column=2, value=item.get("area_sqm"))
                # column 3 = 계획면적(B) — 빈칸 (설계자 입력용)
                ws1.cell(row=row, column=4, value=item.get("notes") or "")
                row += 1
                for sub in (item.get("sub_items") or []):
                    if not isinstance(sub, dict):
                        continue
                    c = ws1.cell(row=row, column=1, value=sub.get("name") or "")
                    c.alignment = Alignment(indent=4, vertical="top")
                    ws1.cell(row=row, column=2, value=sub.get("area_sqm"))
                    ws1.cell(row=row, column=4, value=sub.get("notes") or "")
                    row += 1
        row += 1
        if a["shared_areas"]:
            row = _write_subsection(ws1, "공용·공동 면적", row, span=4)
            row = _write_header(ws1, _AT_COLS, row)
            for sa in a["shared_areas"]:
                if not isinstance(sa, dict):
                    continue
                ws1.cell(row=row, column=1, value=sa.get("name") or "")
                ws1.cell(row=row, column=2, value=sa.get("area_sqm"))
                ws1.cell(row=row, column=4, value=sa.get("notes") or "")
                row += 1
            row += 1
    elif a["rooms"]:
        # 구 경로 폴백
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

    if not a["area_table"] and a["zones"]:
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
        ws3.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 2

    def _ws3_bullets(items: list, span: int = 3) -> None:
        nonlocal row
        for item in items:
            c = ws3.cell(row=row, column=1, value=f"• {_str_item(item)}")
            c.alignment = _wrap_top
            if span > 1:
                ws3.merge_cells(start_row=row, start_column=1,
                                end_row=row, end_column=span)
            row += 1

    # ── 배치·동선 지침 ────────────────────────────────────────────────────────
    m = r["massing"]
    _m_all = []
    if m["setback_m"] is not None:
        _m_all.append(f"이격거리: {m['setback_m']} m")
    if m["height_strategy"]:
        _m_all.append(f"높이 전략: {m['height_strategy']}")
    for _lst in (m["open_space"], m["parking"], m["pedestrian"],
                 m["connection"], m["guidelines"]):
        _m_all.extend(_str_item(x) for x in _lst)
    if _m_all:
        row = _write_subsection(ws3, "배치·동선 지침", row, span=3)
        _ws3_bullets(_m_all)
        row += 1

    # ── 입면·재료 지침 ────────────────────────────────────────────────────────
    f = r["facade"]
    _f_all = [
        *f["primary_materials"], *f["prohibited_materials"],
        *f["color"], *f["facade_guidelines"], *f["landscape"],
    ]
    if _f_all:
        row = _write_subsection(ws3, "입면·재료 지침", row, span=3)
        _ws3_bullets(_f_all)
        row += 1

    # ── 친환경·인증 요구사항 ─────────────────────────────────────────────────
    sv = r["sustain"]
    _has_sv = bool(
        sv["certifications"] or sv["renewable_pct"] is not None
        or sv["energy_guidelines"] or sv["sustainability_reqs"]
    )
    if _has_sv:
        row = _write_subsection(ws3, "친환경·인증 요구사항", row, span=3)
        if sv["certifications"]:
            row = _write_header(ws3, ["인증명", "요구 등급", ""], row)
            for cert in sv["certifications"]:
                if isinstance(cert, dict):
                    ws3.cell(row=row, column=1, value=cert.get("name") or "")
                    ws3.cell(row=row, column=2, value=cert.get("required_grade") or "")
                else:
                    ws3.cell(row=row, column=1, value=_str_item(cert))
                row += 1
        if sv["renewable_pct"] is not None:
            row = _write_kv(ws3, "신재생에너지 최소 비율 (%)", sv["renewable_pct"], row)
        _ws3_bullets(sv["energy_guidelines"] + sv["sustainability_reqs"])
        row += 1

    # ── 특수·보안 지침 ────────────────────────────────────────────────────────
    sp = r["special"]
    _sp_all = [
        *sp["security"], *sp["accessibility"],
        *sp["safety"], *sp["special_tech"],
    ]
    if _sp_all:
        row = _write_subsection(ws3, "특수·보안 지침", row, span=3)
        _ws3_bullets(_sp_all)
        row += 1

    # ── 기타 설계 지침 (폴백 / 구 데이터) ───────────────────────────────────
    list_sections = [
        ("특수 요구사항", r["special_reqs"]),
        ("기타 설계 지침", r["design_reqs"]),
        ("후퇴선 요건",   r["setbacks"]),
        ("재료 요건",     r["materials"]),
        ("친환경 요건",   r["sustainability"]),
        ("금지 사항",     r["prohibited"]),
        ("특별 지침",     r["special_guide"]),
    ]
    for lbl, items in list_sections:
        if not items:
            continue
        row = _write_subsection(ws3, lbl, row, span=3)
        _ws3_bullets(items)
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
