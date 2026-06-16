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


# ── Markdown (구조화 데이터 덤프) ─────────────────────────────────────────────
# 테이블 포맷 없음 — key: value + 중첩 리스트로 데이터 밀도 최대화.
# null 필드도 "(없음)" 명시 → downstream 프로그램이 "누락"과 "미존재"를 구별 가능.

def _v(val: Any, unit: str = "") -> str:
    """값을 문자열로. None/빈값이면 '(없음)'."""
    if val is None or val == "" or val == []:
        return "(없음)"
    if isinstance(val, list):
        return ", ".join(str(x) for x in val) or "(없음)"
    s = str(val)
    return (s + unit) if unit and s != "(없음)" else s


def to_markdown(brief_data: dict, validation: dict) -> str:
    """지침서 추출 데이터를 구조화 텍스트 덤프로 반환.

    가독성보다 데이터 밀도·분류 우선 — LLM/프로그램 연동용.
    """
    s  = _extract_sections(brief_data)
    a, e, r = s["area"], s["eval"], s["reqs"]
    pi = s["project_info"]
    flags = sorted(
        validation.get("flags") or [],
        key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 2),
    )
    summary = validation.get("summary") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    L: list[str] = [f"# 지침서 추출 데이터", f"생성: {now}", ""]

    # ══════════════════════════════════════════════════════════════════════════
    # 1. 사업 개요
    # ══════════════════════════════════════════════════════════════════════════
    L.append("## 1. 사업 개요")
    L.append(f"공모명: {_v(pi['competition_name'])}")
    L.append(f"발주처: {_v(pi['organizer'])}")
    L.append(f"공모유형: {_v(pi['competition_type'])}")
    L.append(f"예정공사비: {_v(pi['construction_cost_100m_won'], ' 억원')}")
    L.append(f"예정설계비: {_v(pi['design_cost_100m_won'], ' 억원')}")
    L.append(f"공사기간: {_v(pi['construction_period_months'], ' 개월')}")

    if pi["budget_notes"]:
        L.append("예산산정기준:")
        for n in pi["budget_notes"]:
            L.append(f"- {_str_item(n)}")

    if pi["special_conditions"]:
        L.append("특기사항:")
        for c in pi["special_conditions"]:
            L.append(f"- {_str_item(c)}")

    # ── BRIEF_PROJECT_INFO 부지별 ─────────────────────────────────────────────
    for i, st in enumerate([x for x in pi["sites"] if isinstance(x, dict)]):
        sid = st.get("site_id") or f"부지{i+1}"
        L.append(f"\n### 부지개요: {sid}")
        L.append(f"위치: {_v(st.get('address'))}")
        L.append(f"용도지역지구: {_v(st.get('zoning'))}")
        L.append(f"공모범위: {_v(st.get('scope'))}")
        fac = st.get("facilities") or []
        L.append(f"도입시설: {', '.join(fac) if fac else '(없음)'}")
        L.append(f"대지면적: {_v(st.get('site_area_sqm'), ' ㎡')}")
        L.append(f"연면적: {_v(st.get('floor_area_sqm'), ' ㎡')}")
        L.append(f"건폐율: {_v(st.get('building_coverage_pct'), '%')}")
        L.append(f"용적률: {_v(st.get('floor_area_ratio_pct'), '%')}")
        L.append(f"최고높이: {_v(st.get('max_height_m'), ' m')}")
        L.append(f"공개공지: {_v(st.get('open_space_sqm'), ' ㎡')}")
        L.append(f"공개공지조건: {_v(st.get('open_space_notes'))}")

    # ── BRIEF_PROGRAM 부지별 ──────────────────────────────────────────────────
    bp_sites = [x for x in a["sites"] if isinstance(x, dict)]
    for i, st in enumerate(bp_sites):
        sid = st.get("site_id") or f"부지{i+1}"
        L.append(f"\n### 건축개요: {sid}")
        L.append(f"위치: {_v(st.get('address'))}")
        zoning = st.get("zoning") or []
        L.append(f"지역지구: {', '.join(zoning) if isinstance(zoning, list) else _v(zoning)}")
        L.append(f"건축구분: {_v(st.get('construction_type'))}")
        L.append(f"건축용도: {_v(st.get('building_use'))}")
        fac = st.get("facilities") or []
        L.append(f"도입시설: {', '.join(fac) if fac else '(없음)'}")
        L.append(f"대지면적: {_v(st.get('site_area_sqm'), ' ㎡')}")
        L.append(f"연면적: {_v(st.get('floor_area_sqm'), ' ㎡')}")
        L.append(f"건폐율한도: {_v(st.get('building_coverage_limit_pct'), '%')}")
        L.append(f"용적률한도: {_v(st.get('floor_area_ratio_limit_pct'), '%')}")
        L.append(f"최고높이: {_v(st.get('max_height_m'), ' m')}")
        L.append(f"공개공지: {_v(st.get('public_open_space_sqm'), ' ㎡')}")
        L.append(f"공개공지조건: {_v(st.get('public_open_space_notes'))}")

    L.append("\n### 전체 규모 한도")
    L.append(f"요구연면적: {_v(a['total_fa'], ' ㎡')}")
    L.append(f"대지면적: {_v(a['site_area'], ' ㎡')}")
    L.append(f"건폐율한도: {_v(a['bcr'], '%')}")
    L.append(f"용적률한도: {_v(a['far'], '%')}")
    L.append(f"높이한도: {_v(a['height'], ' m')}")
    L.append(f"지상층수: {_v(a['floors_above'], ' 층')}")
    L.append(f"지하층수: {_v(a['floors_below'], ' 층')}")
    L.append(f"주차대수: {_v(a['parking'], ' 대')}")
    L.append(f"예정공사비: {_v(a['construction_cost'])}")
    L.append(f"예정설계비: {_v(a['design_fee'])}")
    L.append(f"설계기간: {_v(a['design_period'])}")

    # ══════════════════════════════════════════════════════════════════════════
    # 2. 면적 프로그램
    # ══════════════════════════════════════════════════════════════════════════
    L.append("\n## 2. 면적 프로그램")

    if a["area_table"]:
        for grp in a["area_table"]:
            if not isinstance(grp, dict):
                continue
            gname  = grp.get("group_name") or "(무제)"
            gtotal = _v(grp.get("total_area_sqm"), " ㎡")
            gsite  = grp.get("site_id") or "-"
            L.append(f"\n### {gname}")
            L.append(f"부지: {gsite}")
            L.append(f"합계면적: {gtotal}")
            items = grp.get("items") or []
            if items:
                L.append("항목:")
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    iname = it.get("name") or ""
                    iarea = _v(it.get("area_sqm"), " ㎡")
                    inote = it.get("notes") or ""
                    L.append(f"- {iname}: {iarea}" + (f"  # {inote}" if inote else ""))
                    for sub in (it.get("sub_items") or []):
                        if not isinstance(sub, dict):
                            continue
                        sname = sub.get("name") or ""
                        sarea = _v(sub.get("area_sqm"), " ㎡")
                        snote = sub.get("notes") or ""
                        L.append(f"  - {sname}: {sarea}" + (f"  # {snote}" if snote else ""))

        if a["shared_areas"]:
            L.append("\n### 공용·공동 면적")
            for sa in a["shared_areas"]:
                if not isinstance(sa, dict):
                    continue
                L.append(f"- {sa.get('name') or ''}: {_v(sa.get('area_sqm'), ' ㎡')}"
                         + (f"  # {sa.get('notes')}" if sa.get("notes") else ""))

    elif a["rooms"]:
        L.append("\n### 실별 면적 프로그램")
        for rm in a["rooms"]:
            if not isinstance(rm, dict):
                continue
            area = rm.get("required_area_sqm") or rm.get("area_sqm")
            L.append(f"- {rm.get('name') or ''}: {_v(area, ' ㎡')}"
                     f"  수량:{rm.get('required_count') or rm.get('count') or 1}"
                     + (f"  위치:{rm.get('floor')}" if rm.get("floor") else "")
                     + (f"  # {rm.get('notes')}" if rm.get("notes") else ""))

    if not a["area_table"] and a["zones"]:
        L.append("\n### 존 구성")
        for z in a["zones"]:
            L.append(f"- {z.get('name') or z.get('zone') or ''}: {_v(z.get('area_sqm'), ' ㎡')}")

    # ══════════════════════════════════════════════════════════════════════════
    # 3. 심사기준
    # ══════════════════════════════════════════════════════════════════════════
    L.append("\n## 3. 심사기준")
    L.append(f"총배점: {_v(e['total_points'], ' 점')}")
    L.append(f"평가방법: {_v(e['eval_method'])}")
    L.append(f"심사단구성: {_v(e['jury'])}")

    running = 0.0
    for ev in e["rows"]:
        if not isinstance(ev, dict):
            continue
        name      = ev.get("name") or "(항목명 없음)"
        pts       = ev.get("points")
        shared    = ev.get("shared_with") or []
        sub_items = ev.get("sub_items") or []
        desc      = ev.get("description") or ""
        L.append(f"\n### {name}")
        L.append(f"배점: {_v(pts, ' 점')}")
        L.append(f"공유배점: {', '.join(shared) if shared else '(없음)'}")
        if desc:
            L.append(f"설명: {desc}")
        if sub_items:
            L.append("세부기준:")
            for sub in sub_items:
                L.append(f"- {_str_item(sub)}")
        if isinstance(pts, (int, float)):
            running += pts

    L.append(f"\n배점합계: {running if running else '(없음)'}")

    if e["disqualify"]:
        L.append("\n### 실격 요건")
        for d in e["disqualify"]:
            L.append(f"- {_str_item(d)}")

    # ══════════════════════════════════════════════════════════════════════════
    # 4. 요구사항·설계 지침
    # ══════════════════════════════════════════════════════════════════════════
    L.append("\n## 4. 요구사항·설계 지침")

    if r["requirements"]:
        L.append("\n### 평가축별 요구사항")
        for req in r["requirements"]:
            if not isinstance(req, dict):
                continue
            L.append(f"- 축: {req.get('axis') or ''}  "
                     f"배점비중: {_v(req.get('weight_pct'), '%')}  "
                     f"설명: {req.get('description') or ''}")

    if r["concept"]:
        L.append(f"\n설계방향: {r['concept']}")

    # ── 배치·동선 ────────────────────────────────────────────────────────────
    m = r["massing"]
    _m_has = any([
        m["setback_m"] is not None, m["height_strategy"],
        m["open_space"], m["parking"], m["pedestrian"],
        m["connection"], m["guidelines"],
    ])
    L.append("\n### 배치·동선 지침")
    L.append(f"이격거리: {_v(m['setback_m'], ' m')}")
    L.append(f"높이전략: {_v(m['height_strategy'])}")
    for lbl, lst in [
        ("공개공지", m["open_space"]),
        ("주차계획", m["parking"]),
        ("동선계획", m["pedestrian"]),
        ("연결부",   m["connection"]),
        ("배치지침", m["guidelines"]),
    ]:
        if lst:
            L.append(f"{lbl}:")
            for x in lst:
                L.append(f"- {_str_item(x)}")
        else:
            L.append(f"{lbl}: (없음)")

    # ── 입면·재료 ────────────────────────────────────────────────────────────
    f = r["facade"]
    L.append("\n### 입면·재료 지침")
    for lbl, lst in [
        ("지정재료",   f["primary_materials"]),
        ("금지재료",   f["prohibited_materials"]),
        ("색채계획",   f["color"]),
        ("입면지침",   f["facade_guidelines"]),
        ("조경경관",   f["landscape"]),
    ]:
        if lst:
            L.append(f"{lbl}:")
            for x in lst:
                L.append(f"- {_str_item(x)}")
        else:
            L.append(f"{lbl}: (없음)")

    # ── 친환경·인증 ──────────────────────────────────────────────────────────
    sv = r["sustain"]
    L.append("\n### 친환경·인증 요구사항")
    if sv["certifications"]:
        L.append("의무인증:")
        for c in sv["certifications"]:
            if isinstance(c, dict):
                L.append(f"- {c.get('name') or ''}  요구등급: {_v(c.get('required_grade'))}")
            else:
                L.append(f"- {_str_item(c)}")
    else:
        L.append("의무인증: (없음)")
    L.append(f"신재생에너지비율: {_v(sv['renewable_pct'], '%')}")
    for lbl, lst in [
        ("에너지지침",  sv["energy_guidelines"]),
        ("지속가능성",  sv["sustainability_reqs"]),
    ]:
        if lst:
            L.append(f"{lbl}:")
            for x in lst:
                L.append(f"- {_str_item(x)}")
        else:
            L.append(f"{lbl}: (없음)")

    # ── 특수·보안 ────────────────────────────────────────────────────────────
    sp = r["special"]
    L.append("\n### 특수·보안 지침")
    for lbl, lst in [
        ("보안요건",     sp["security"]),
        ("장애인접근성", sp["accessibility"]),
        ("안전요건",     sp["safety"]),
        ("특수기술",     sp["special_tech"]),
    ]:
        if lst:
            L.append(f"{lbl}:")
            for x in lst:
                L.append(f"- {_str_item(x)}")
        else:
            L.append(f"{lbl}: (없음)")

    # ── 기타 설계 지침 (구 데이터 폴백) ─────────────────────────────────────
    _misc = [
        ("특수요구사항", r["special_reqs"]),
        ("기타설계지침", r["design_reqs"]),
        ("후퇴선요건",   r["setbacks"]),
        ("재료요건",     r["materials"]),
        ("친환경요건",   r["sustainability"]),
        ("금지사항",     r["prohibited"]),
        ("특별지침",     r["special_guide"]),
    ]
    has_misc = any(v for _, v in _misc)
    if has_misc:
        L.append("\n### 기타 설계 지침")
        for lbl, lst in _misc:
            if lst:
                L.append(f"{lbl}:")
                for x in lst:
                    L.append(f"- {_str_item(x)}")

    # ══════════════════════════════════════════════════════════════════════════
    # 5. 검증 경고
    # ══════════════════════════════════════════════════════════════════════════
    high_n   = summary.get("high", 0)
    medium_n = summary.get("medium", 0)
    low_n    = summary.get("low", 0)
    L.append(f"\n## 5. 검증 경고")
    L.append(f"높음: {high_n}건 / 보통: {medium_n}건 / 낮음: {low_n}건")

    if flags:
        for flag in flags:
            sev = _SEVERITY_LABEL.get(flag.get("severity", ""), flag.get("severity", ""))
            L.append(f"[{sev}] {flag.get('type') or ''}: {flag.get('message') or ''}"
                     + (f"  | 위치: {flag.get('location')}" if flag.get("location") else ""))
    else:
        L.append("경고없음")

    return "\n".join(L)


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

    def _write_kv(ws, label: str, val: Any, row: int, val_end_col: int = 2) -> int:
        ws.cell(row=row, column=1, value=label).font = _bold
        c = ws.cell(row=row, column=2, value=_cell_safe(val))
        c.alignment = _wrap_top
        if val_end_col > 2:
            ws.merge_cells(start_row=row, start_column=2,
                           end_row=row, end_column=val_end_col)
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
    ws1.freeze_panes = "A3"

    if has_bpi_xl:
        row = _write_subsection(ws1, "사업 개요", row, span=_span1)
        for label, val in [
            ("공모명",   pi["competition_name"] or None),
            ("발주처",   pi["organizer"] or None),
            ("공모유형", pi["competition_type"] or None),
        ]:
            if val:
                row = _write_kv(ws1, label, val, row, val_end_col=4)
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
                row = _write_kv(ws1, label, val, row, val_end_col=4)
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
        row = _write_subsection(ws1, "공통 규모", row, span=4)
        for label, val in [
            ("요구 총 연면적 (㎡)", a["total_fa"]),
            ("지상 층수",           a["floors_above"]),
            ("지하 층수",           a["floors_below"]),
            ("주차 대수 (대)",      a["parking"]),
            ("예정 공사비",         a["construction_cost"] or None),
            ("예정 설계비",         a["design_fee"] or None),
            ("설계 기간",           a["design_period"] or None),
        ]:
            row = _write_kv(ws1, label, val, row, val_end_col=4)
    else:
        row = _write_subsection(ws1, "전체 규모 한도", row, span=4)
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
            row = _write_kv(ws1, label, val, row, val_end_col=4)
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
    _S2_SPAN = 4  # 항목명 | 배점 | 공유 | 세부기준
    row = _write_section_title(ws2, "2. 심사기준 (배점표)", 1, span=_S2_SPAN)
    row += 1
    ws2.freeze_panes = "A3"

    for label, val in [
        ("총 배점",    e["total_points"]),
        ("평가 방법",  e["eval_method"] or None),
        ("심사단 구성", e["jury"] or None),
    ]:
        row = _write_kv(ws2, label, val, row, val_end_col=_S2_SPAN)
    row += 1

    if e["rows"]:
        row = _write_header(ws2, ["항목명", "배점", "공유 배점", "세부 기준"], row)
        running_total: float = 0.0
        for ev in e["rows"]:
            if not isinstance(ev, dict):
                c = ws2.cell(row=row, column=1, value=_str_item(ev))
                ws2.merge_cells(start_row=row, start_column=1,
                                end_row=row, end_column=_S2_SPAN)
                row += 1
                continue

            name      = ev.get("name") or ""
            pts       = ev.get("points")
            shared    = ev.get("shared_with") or []
            sub_items = ev.get("sub_items") or []
            desc      = ev.get("description") or ""

            # ── 카테고리 행 ────────────────────────────────────────────────
            has_pts = pts is not None
            c1 = ws2.cell(row=row, column=1, value=name)
            if has_pts:
                c1.font = _bold
                c1.fill = _grp_fill
            c2 = ws2.cell(row=row, column=2, value=pts)
            if has_pts:
                c2.font = _bold
                c2.fill = _grp_fill
                c2.alignment = _center

            shared_text = ("↳ " + ", ".join(shared) + "와 배점 공유") if shared else ""
            ws2.cell(row=row, column=3, value=shared_text)

            # 첫 sub_item 또는 description을 col 4에
            first_sub = (f"• {_str_item(sub_items[0])}" if sub_items
                         else (desc or ""))
            c4 = ws2.cell(row=row, column=4, value=first_sub)
            c4.alignment = _wrap_top

            if isinstance(pts, (int, float)):
                running_total += pts
            row += 1

            # ── 나머지 sub_items: col 4에 계속 ────────────────────────────
            for sub in sub_items[1:]:
                c = ws2.cell(row=row, column=4, value=f"• {_str_item(sub)}")
                c.alignment = _wrap_top
                row += 1

        # 합계 행
        ws2.cell(row=row, column=1, value="합  계").font = _bold
        c_sum = ws2.cell(row=row, column=2,
                         value=running_total if running_total else None)
        c_sum.font = _bold
        c_sum.fill = _grp_fill
        c_sum.alignment = _center
        row += 2

    if e["disqualify"]:
        row = _write_subsection(ws2, "실격 요건", row, span=_S2_SPAN)
        for d in e["disqualify"]:
            c = ws2.cell(row=row, column=1, value=_str_item(d))
            c.alignment = _wrap_top
            ws2.merge_cells(start_row=row, start_column=1,
                            end_row=row, end_column=_S2_SPAN)
            row += 1

    ws2.column_dimensions["A"].width = 28
    ws2.column_dimensions["B"].width = 8
    ws2.column_dimensions["C"].width = 22
    ws2.column_dimensions["D"].width = 55
    _auto_width(ws2)

    # ── Sheet 3: 요구사항·필수조건 ────────────────────────────────────────────
    ws3 = wb.create_sheet("3.요구사항")
    _S3_SPAN = 3  # 소항목 레이블 | 내용(col2-3 병합)
    row = _write_section_title(ws3, "3. 요구사항·필수조건", 1, span=_S3_SPAN)
    row += 1
    ws3.freeze_panes = "A3"

    if r["requirements"]:
        row = _write_subsection(ws3, "평가축별 요구사항", row, span=_S3_SPAN)
        row = _write_header(ws3, ["평가축", "설명", "배점비중(%)"], row)
        for req in r["requirements"]:
            if not isinstance(req, dict):
                ws3.cell(row=row, column=1, value=_str_item(req))
                row += 1
                continue
            ws3.cell(row=row, column=1, value=req.get("axis") or "")
            d_cell = ws3.cell(row=row, column=2, value=req.get("description") or "")
            d_cell.alignment = _wrap_top
            ws3.cell(row=row, column=3, value=req.get("weight_pct"))
            row += 1
        row += 1

    if r["concept"]:
        ws3.cell(row=row, column=1, value="설계 방향").font = _bold
        c = ws3.cell(row=row, column=2, value=r["concept"])
        c.alignment = _wrap_top
        ws3.merge_cells(start_row=row, start_column=2,
                        end_row=row, end_column=_S3_SPAN)
        row += 2

    def _ws3_labeled(lbl: str, items: list) -> None:
        """소항목 레이블(col 1) + 내용 불릿(col 2-3 병합) 형태로 출력."""
        nonlocal row
        if not items:
            return
        for i, item in enumerate(items):
            if i == 0:
                c_lbl = ws3.cell(row=row, column=1, value=lbl)
                c_lbl.font = Font(bold=True, size=9)
            text = _str_item(item)
            if not text.startswith("•"):
                text = f"• {text}"
            c = ws3.cell(row=row, column=2, value=text)
            c.alignment = _wrap_top
            ws3.merge_cells(start_row=row, start_column=2,
                            end_row=row, end_column=_S3_SPAN)
            row += 1

    def _ws3_kv(lbl: str, val: Any) -> None:
        """소항목 레이블(col 1) + 단일 값(col 2-3 병합) 형태로 출력."""
        nonlocal row
        if val is None or val == "":
            return
        c_lbl = ws3.cell(row=row, column=1, value=lbl)
        c_lbl.font = Font(bold=True, size=9)
        c = ws3.cell(row=row, column=2, value=_cell_safe(val))
        c.alignment = _wrap_top
        ws3.merge_cells(start_row=row, start_column=2,
                        end_row=row, end_column=_S3_SPAN)
        row += 1

    def _ws3_bullets(items: list) -> None:
        """레이블 없는 평면 불릿 (구 데이터 폴백용)."""
        nonlocal row
        for item in items:
            c = ws3.cell(row=row, column=1, value=f"• {_str_item(item)}")
            c.alignment = _wrap_top
            ws3.merge_cells(start_row=row, start_column=1,
                            end_row=row, end_column=_S3_SPAN)
            row += 1

    # ── 배치·동선 지침 ────────────────────────────────────────────────────────
    m = r["massing"]
    _MASSING_SUBS = [
        ("이격거리",  [f"{m['setback_m']} m"] if m["setback_m"] is not None else []),
        ("높이 전략", [m["height_strategy"]] if m["height_strategy"] else []),
        ("공개공지",  m["open_space"]),
        ("주차 계획", m["parking"]),
        ("동선 계획", m["pedestrian"]),
        ("연결부",    m["connection"]),
        ("배치 지침", m["guidelines"]),
    ]
    if any(v for _, v in _MASSING_SUBS):
        row = _write_subsection(ws3, "배치·동선 지침", row, span=_S3_SPAN)
        for lbl, items in _MASSING_SUBS:
            _ws3_labeled(lbl, items)
        row += 1

    # ── 입면·재료 지침 ────────────────────────────────────────────────────────
    f = r["facade"]
    _FACADE_SUBS = [
        ("지정 재료", f["primary_materials"]),
        ("금지 재료", f["prohibited_materials"]),
        ("색채 계획", f["color"]),
        ("입면 지침", f["facade_guidelines"]),
        ("조경·경관", f["landscape"]),
    ]
    if any(v for _, v in _FACADE_SUBS):
        row = _write_subsection(ws3, "입면·재료 지침", row, span=_S3_SPAN)
        for lbl, items in _FACADE_SUBS:
            _ws3_labeled(lbl, items)
        row += 1

    # ── 친환경·인증 요구사항 ─────────────────────────────────────────────────
    sv = r["sustain"]
    _has_sv = bool(
        sv["certifications"] or sv["renewable_pct"] is not None
        or sv["energy_guidelines"] or sv["sustainability_reqs"]
    )
    if _has_sv:
        row = _write_subsection(ws3, "친환경·인증 요구사항", row, span=_S3_SPAN)
        if sv["certifications"]:
            for i, cert in enumerate(sv["certifications"]):
                if i == 0:
                    ws3.cell(row=row, column=1, value="의무 인증").font = Font(bold=True, size=9)
                if isinstance(cert, dict):
                    name  = cert.get("name") or ""
                    grade = cert.get("required_grade") or ""
                    content = f"{name}  {grade}".strip() if grade else name
                else:
                    content = _str_item(cert)
                c = ws3.cell(row=row, column=2, value=content)
                c.alignment = _wrap_top
                ws3.merge_cells(start_row=row, start_column=2,
                                end_row=row, end_column=_S3_SPAN)
                row += 1
        _ws3_kv("신재생에너지 비율", (f"{sv['renewable_pct']}%" if sv["renewable_pct"] is not None else None))
        _ws3_labeled("에너지 지침",  sv["energy_guidelines"])
        _ws3_labeled("지속가능성",   sv["sustainability_reqs"])
        row += 1

    # ── 특수·보안 지침 ────────────────────────────────────────────────────────
    sp = r["special"]
    _SPECIAL_SUBS = [
        ("보안 요건",     sp["security"]),
        ("장애인 접근성", sp["accessibility"]),
        ("안전 요건",     sp["safety"]),
        ("특수 기술",     sp["special_tech"]),
    ]
    if any(v for _, v in _SPECIAL_SUBS):
        row = _write_subsection(ws3, "특수·보안 지침", row, span=_S3_SPAN)
        for lbl, items in _SPECIAL_SUBS:
            _ws3_labeled(lbl, items)
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
        row = _write_subsection(ws3, lbl, row, span=_S3_SPAN)
        _ws3_bullets(items)
        row += 1

    ws3.column_dimensions["A"].width = 16
    ws3.column_dimensions["B"].width = 55
    ws3.column_dimensions["C"].width = 12
    _auto_width(ws3)

    # ── Sheet 4: 검증 경고 ────────────────────────────────────────────────────
    ws4 = wb.create_sheet("4.검증경고")
    row = _write_section_title(ws4, "4. 검증 경고", 1, span=4)
    row += 1
    ws4.freeze_panes = "A3"

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
