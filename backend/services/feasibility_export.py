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

SCHEMA_VERSION = 2

# 표준 용도지역명 (국토계획법 시행령 별표) — 매칭은 substring 후 최장 우선
_ZONE_USES = [
    "제1종전용주거지역", "제2종전용주거지역",
    "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역", "준주거지역",
    "중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역",
    "전용공업지역", "일반공업지역", "준공업지역",
    "보전녹지지역", "생산녹지지역", "자연녹지지역",
]

# 주차 — 요구 문장의 "N대" 추출 + 요구/운영 구분 키워드
_PARK_COUNT_RE = re.compile(r"([\d,]{1,7})\s*대")
_BUJI_RE = re.compile(r"부지\s*(\d+)")
_PARK_REQ_KW = ("확보", "이상", "계획", "설치", "조성")          # 요구 문장 신호
_PARK_OPER_KW = ("운영", "기존", "현 ", "개방", "공유", "인근",  # 현황/운영 문장 (요구 아님)
                 "광장", "유수지", "마트")
# 심의 결정 — 한도가 법정이 아니라 심의로 정해지는 신호
_SIMUI_KW = ("심의",)
_LIMIT_KW = ("건폐율", "용적률", "높이")

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


# ── C: 주차대수 구조화 ────────────────────────────────────────────────────────

def _text_of(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("text") or x.get("description") or x.get("requirement") or ""
    return ""


def _collect_parking_statements(brief_data: dict) -> list[str]:
    """주차 요구가 서술된 필드들을 모음 (이미 추출된 brief_design_massing 등)."""
    out: list[str] = []
    for m in _as_dict_list(brief_data.get("brief_design_massing")):
        for key in ("parking_requirements", "massing_guidelines"):
            for x in m.get(key) or []:
                s = _text_of(x).strip()
                if s:
                    out.append(s)
    return out


def _parse_parking(statements: list[str]) -> tuple[dict[str, tuple[int, str]], str | None]:
    """요구 문장에서 per-site 주차대수 + 프로젝트 전체 요구 문장(generic) 추출.

    - 요구 문장: "N대" + 요구키워드(확보/이상/계획…) 포함, 운영/현황 문장 제외.
    - per-site: 'N대' 직전 가장 가까운 "부지N" 마커에 귀속 (예: "'부지1…' 부설주차장으로 430대").
    - 부지 마커 없는 "총 N대" 문장은 generic 으로 1건만 보관.
    """
    per_site: dict[str, tuple[int, str]] = {}
    generic: str | None = None
    for s in statements:
        if any(op in s for op in _PARK_OPER_KW):
            continue
        m = _PARK_COUNT_RE.search(s)
        if not m or not any(kw in s for kw in _PARK_REQ_KW):
            continue
        count = int(m.group(1).replace(",", ""))
        sid = None
        for bm in _BUJI_RE.finditer(s[:m.start()]):   # count 직전 마지막 부지N
            sid = f"부지{bm.group(1)}"
        if sid:
            per_site.setdefault(sid, (count, s))
        elif generic is None and "총" in s:
            generic = s
    return per_site, generic


# ── D: 용도지역 정규화 ────────────────────────────────────────────────────────

def _normalize_zone_use(zoning: Any) -> tuple[str | None, str | None]:
    """zoning 서술에서 표준 용도지역명 추출. 불확실하면 (None, 원문).

    Returns (zone_use, zone_use_raw). 매칭 성공 시 raw=None, 실패 시 zone_use=None.
    """
    if isinstance(zoning, list):
        text = ", ".join(str(z) for z in zoning if z)
    else:
        text = str(zoning or "")
    if not text.strip():
        return None, None
    matches = [z for z in _ZONE_USES if z in text]
    if len(matches) == 1:
        return matches[0], None
    # 2개 이상 = **판단 보류**. 원문을 그대로 넘긴다(설계 원칙: 「불확실 시 raw」).
    #
    # 옛 코드는 `max(matches, key=len)` 였다. 주석이 근거로 든 「제2종일반주거지역 >
    # 일반주거지역」은 **일어날 수 없는 케이스**다 — `_ZONE_USES` 16개에 포함관계가
    # 하나도 없다(bare '일반주거지역'은 목록에 없다). 그래서 그 max 는 길이 동점에서
    # **리스트 앞 항목을 고르는 것**밖에 안 했고, 조용히 틀렸다:
    #   · '제3종일반주거지역 (제2종일반주거지역에서 종상향)' → 종상향 **前** 값을 채택
    #   · '제1종일반주거지역, 제2종일반주거지역'(다중 용도지역) → 임의로 제1종
    # 250% vs 300% 짜리 오선택이고 예외도 안 난다. 이 값은 `arch_law_client.to_request`
    # 의 `zone_use_override` 로 가서 **건폐/용적 한도를 통째로 좌우한다** — 비워 두면
    # 진단 엔진이 주소로 직접 조회하므로, 틀린 값을 주입하는 것보다 낫다.
    # (형제앱 arch-law-diagnose 의 `zone_use_normalizer` 도 다중 매칭은 None 으로 떨어진다.)
    return None, text


# ── E: 심의 결정 플래그 ───────────────────────────────────────────────────────

def _limits_determined_by(special_conditions: list) -> str:
    """건폐율·용적률·높이가 도시계획위원회 '심의'로 결정되면 '심의', 아니면 '법정'."""
    for x in special_conditions or []:
        s = _text_of(x)
        if any(k in s for k in _SIMUI_KW) and any(k in s for k in _LIMIT_KW):
            return "심의"
    return "법정"


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

    # 2차 — 서술 파싱 (프로젝트 단위로 1회): 주차 / 심의 플래그
    park_per_site, park_generic = _parse_parking(_collect_parking_statements(brief_data))
    limits_by = _limits_determined_by(bpi.get("special_conditions") or [])

    sites_out: list[dict] = []
    for i, st in enumerate(canonical):
        sid = st.get("site_id") or f"부지{i + 1}"
        # B: 주소 — 기존 sites[].address 우선, 없으면 brief_site "(부지N)" 분해값
        address = (st.get("address") or "").strip() or parsed_addr.get(sid) or None
        # 2차 C: 주차 — site-specific 우선, 없으면 count=null + 전체 요구 문구를 note 로
        pc, pnote = park_per_site.get(sid, (None, None))
        if pc is None and pnote is None:
            pnote = park_generic
        # 2차 D: 용도지역 정규화
        zone_use, zone_use_raw = _normalize_zone_use(st.get("zoning"))
        sites_out.append({
            "site_id": sid,
            "address": address,
            # 1차 D: 건축법 용도 (괄호표기)
            "building_law_uses": _building_law_uses(st.get("facilities")),
            # 2차 C: 주차대수 구조화
            "required_parking_count": pc,
            "parking_note": pnote,
            # 2차 D: 용도지역
            "zone_use": zone_use,
            "zone_use_raw": zone_use_raw,
            # 2차 E: 한도 결정 주체 (소비 앱이 60%/460% 를 법정으로 오인 방지)
            "limits_determined_by": limits_by,
            # 사업성 검토 핵심 수치 재배치 (이미 추출된 값)
            "site_area_sqm": st.get("site_area_sqm"),
            "floor_area_ratio_pct": st.get("floor_area_ratio_pct"),
            "building_coverage_pct": st.get("building_coverage_pct"),
            "max_height_m": st.get("max_height_m"),
            # 목표 연면적·공개공지 (2026-08-27 추가, arch-law-diagnose 요청).
            # `brief_project_info.sites` 에 **이미 있던 값**인데 이 블록에만 안 실려 있어,
            # 소비 앱이 그것 때문에 자기 파서를 못 지우고 있었다. 재배치라 새 추출 0.
            # ⚠ schema_version 은 2 그대로 — 추가만이라 하위호환이고, 소비 측 게이트가
            #   `>=2` 라 올리면 **옛 판본을 읽던 코드가 갈라진다**. 판본 구분이 필요해지면
            #   그때 두 앱이 같이 정한다.
            "floor_area_sqm": st.get("floor_area_sqm"),
            "open_space_sqm": st.get("open_space_sqm"),
            "open_space_notes": st.get("open_space_notes"),
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
