"""
feasibility_export.py — _brief.json 의 feasibility_export 정규화 블록 빌더 (1차)

별도 앱(arch-law-diagnose, 건축법규 자동진단)이 이 _brief.json 을 읽어 사전 사업성
검토를 자동으로 채운다. 필요한 값이 brief_project_info.sites[] / brief_site[] /
brief_design_sustain 등에 흩어져 있어, 이미 추출된 값을 "재배치/정규화"만 해서
feasibility_export 블록으로 묶는다.

원칙 (1차):
- 새로 추출하지 않는다 (vision 프롬프트 무관). 기존 추출값 재구성만.
- 기존 키는 절대 수정하지 않는다. feasibility_export 블록만 추가.
- schema_version 으로 소비 앱과 호환 관리.

블록 항목:
  A. sites[].site_id  — brief_project_info.sites[] 와 brief_site[] 조인키 통일 ("부지1"…)
  B. sites[].address  — brief_site[].address 의 "(부지N)" 표기 분해 + 시·구 접두 상속
  C. certifications   — required_certifications 자유문장을 코드값으로
  D. sites[].building_law_uses — facilities 괄호표기에서 건축법 용도 추출
  E. construction_cost_100m_won / design_cost_100m_won / construction_period_months — 최상위 노출
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# "<주소>(부지N…" 직전 주소 텍스트 + 부지 번호 (쉼표/괄호 전까지가 주소 청크)
_SITE_MARKER_RE = re.compile(r"([^,(]+?)\s*\(\s*부지\s*(\d+)")
# 행정 접두 토큰: …특별시/광역시/도/시/군/구 로 끝남
_ADMIN_TOKEN_RE = re.compile(r"(시|도|군|구)$")
# 괄호 안 내용 (건축법 용도 후보)
_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _as_dict(v: Any) -> dict:
    """list 면 첫 dict, dict 면 그대로, 그 외 {}."""
    if isinstance(v, dict):
        return v
    if isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                return x
    return {}


def _as_dict_list(v: Any) -> list[dict]:
    if isinstance(v, dict):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def _building_law_uses(facilities: Any) -> list[str]:
    """facilities 괄호표기에서 건축법 용도만 추출. 복합용도면 배열.

    예: ["어린이집(노유자시설)", "구청"] → ["노유자시설"]
    괄호 내용 중 '시설' 로 끝나거나 '주택' 을 포함하는 것만 (오추출 방어).
    """
    uses: list[str] = []
    for f in facilities or []:
        if not isinstance(f, str):
            continue
        for inner in _PAREN_RE.findall(f):
            t = inner.strip()
            if not t:
                continue
            if (t.endswith("시설") or "주택" in t) and t not in uses:
                uses.append(t)
    return uses


def _parse_site_addresses(brief_site: list[dict]) -> dict[str, str]:
    """brief_site[].address 의 "(부지N)" 표기를 부지별 주소로 분해.

    - 한 address 문자열에 여러 "(부지N)" 마커가 있을 수 있음 (쉼표 구분).
    - 뒤 부지에 시·도·구 접두가 생략되면 앞 부지 접두를 이어붙임 (상속).
    - site_id 별 최초 파싱값 유지 (이후 항목이 덮어쓰지 않음).
    """
    result: dict[str, str] = {}
    for bs in brief_site:
        addr = (bs.get("address") or "").strip()
        if "부지" not in addr:
            continue
        last_prefix = ""
        for m in _SITE_MARKER_RE.finditer(addr):
            text = m.group(1).strip().strip(",").strip()
            sid = f"부지{m.group(2)}"
            toks = text.split()
            pref: list[str] = []
            i = 0
            while i < len(toks) and _ADMIN_TOKEN_RE.search(toks[i]):
                pref.append(toks[i])
                i += 1
            if pref:                       # 자체 접두 보유 → 갱신
                last_prefix = " ".join(pref)
                full = text
            elif last_prefix:              # 접두 생략 → 상속
                full = f"{last_prefix} {text}".strip()
            else:
                full = text
            if sid not in result and full:
                result[sid] = full
    return result


def _code_certifications(sustain: dict) -> dict:
    """required_certifications 자유문장 + renewable_energy_min_pct → 코드값.

    { green_building: "최우수"|"우수"|null, zeb_grade: 1~5|null,
      renewable_pct: int|null, bf_grade: "최우수"|"우수"|null }
    """
    green = zeb = bf = None
    for c in sustain.get("required_certifications") or []:
        if not isinstance(c, dict):
            continue
        text = f"{c.get('name') or ''} {c.get('required_grade') or ''}"
        up = text.upper()
        if "녹색건축" in text:
            if "최우수" in text:
                green = "최우수"
            elif "우수" in text:
                green = "우수"
        if "ZEB" in up or "제로에너지" in text or "제로 에너지" in text:
            mz = re.search(r"([1-5])\s*등급", text)
            if mz:
                zeb = int(mz.group(1))
        if "BF" in up or "장애물 없는" in text or "장애물없는" in text \
                or "배리어" in text or "무장애" in text:
            if "최우수" in text:
                bf = "최우수"
            elif "우수" in text:
                bf = "우수"
    renewable = sustain.get("renewable_energy_min_pct")
    if not isinstance(renewable, (int, float)):
        renewable = None
    return {
        "green_building": green,
        "zeb_grade": zeb,
        "renewable_pct": renewable,
        "bf_grade": bf,
    }


def build_feasibility_export(brief_data: dict) -> dict:
    """이미 추출된 brief_data 에서 feasibility_export 정규화 블록을 생성.

    새 추출 없음. 기존 키 수정 없음 (읽기 전용). 실패해도 호출부에서 무시 가능.
    """
    bpi = _as_dict(brief_data.get("brief_project_info"))
    bpi_sites = _as_dict_list(bpi.get("sites"))
    brief_site = _as_dict_list(brief_data.get("brief_site"))
    parsed_addr = _parse_site_addresses(brief_site)

    # A: 표준 부지 리스트 = brief_project_info.sites[] (site_id 보유). 없으면 마커에서 생성.
    canonical = bpi_sites
    if not canonical and parsed_addr:
        canonical = [{"site_id": sid} for sid in sorted(parsed_addr)]

    sites_out: list[dict] = []
    for i, st in enumerate(canonical):
        sid = st.get("site_id") or f"부지{i + 1}"
        # B: 주소 — 기존 sites[].address 우선, 없으면 brief_site "(부지N)" 분해값
        address = (st.get("address") or "").strip() or parsed_addr.get(sid) or None
        sites_out.append({
            "site_id": sid,
            "address": address,
            # D: 건축법 용도 (괄호표기)
            "building_law_uses": _building_law_uses(st.get("facilities")),
            # 사업성 검토 핵심 수치 재배치 (이미 추출된 값)
            "site_area_sqm": st.get("site_area_sqm"),
            "floor_area_ratio_pct": st.get("floor_area_ratio_pct"),
            "building_coverage_pct": st.get("building_coverage_pct"),
            "max_height_m": st.get("max_height_m"),
        })

    # C: 인증 코드화
    certifications = _code_certifications(_as_dict(brief_data.get("brief_design_sustain")))

    return {
        "schema_version": SCHEMA_VERSION,
        "sites": sites_out,
        "certifications": certifications,
        # E: 사업 규모 최상위 노출
        "construction_cost_100m_won": bpi.get("construction_cost_100m_won"),
        "design_cost_100m_won": bpi.get("design_cost_100m_won"),
        "construction_period_months": bpi.get("construction_period_months"),
    }
