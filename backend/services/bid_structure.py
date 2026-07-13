"""
bid_structure.py — 설계자 선정 입찰(bid) 지침서의 **2층 배점 구조** 정규화 (LLM 0).

설계공모는 "합계 100점 심사기준표 1개"지만, 입찰은 2층이다:
  · 상위(top_layer): 종합평점 = 사업수행능력평가(PQ) × w% + 가격평가 × (100-w)%.
    w 는 보통 **연면적 규모별로 차등**(예: 8만㎡ 미만 20%, 8~24만 30%, 24만 이상 40%).
  · 하위(pq_detail): 사업수행능력 100점 세부표(참여기술자·유사용역실적·신용도).

이 모듈은 **새 추출 없음** — 이미 추출된 `_requirements.evaluation_criteria`(상위 밴드
서술) + `brief_evaluation`(하위 100점표)를 재배치·파싱만 한다(feasibility_export 패턴).
genre=="bid" 일 때만 `merge_extracted_data` 가 `_bid_structure` 로 부착.

정직성 규칙: 밴드 기준은 대개 **연면적**인데 그 값이 미추출이면 적용 밴드를 단정하지
않는다(대지면적으로 대체 추정 금지 — 21만㎡ 대지 ≠ 연면적). 밴드는 제시하되
applicable 은 기준값 확보 시에만 채운다.
"""
from __future__ import annotations

import re

SCHEMA_VERSION = 1

# "N만" → N*10000. (㎡ 단위, 한국 지침서 관용 표기)
_MAN = 10000


def _man_to_sqm(n: str) -> int:
    return int(n) * _MAN


def _parse_bands(text: str) -> list[dict]:
    """축 서술에서 연면적 밴드 추출.

    입력 예: "사업수행능력평가 (8만㎡ 미만: 20%, 8만~24만㎡: 30%, 24만㎡ 이상: 40%)"
    반환: [{label, min_sqm, max_sqm, weight_pct}] (min/max None 가능).
    각 clause 를 콤마로 쪼개 미만/이상/범위(~)를 판별.
    """
    # 괄호 안이 있으면 그 안을, 없으면 전체를 스캔
    m = re.search(r"[（(](.+?)[)）]", text)
    body = m.group(1) if m else text
    bands: list[dict] = []
    for clause in re.split(r"[,，]", body):
        c = clause.strip()
        wm = re.search(r"(\d+(?:\.\d+)?)\s*%", c)
        if not wm:
            continue
        weight = float(wm.group(1))
        nums = re.findall(r"(\d+)\s*만", c)          # "8만", "24만"
        if "~" in c or "∼" in c or "－" in c:         # 범위: N1만~N2만
            if len(nums) >= 2:
                lo, hi = _man_to_sqm(nums[0]), _man_to_sqm(nums[1])
                bands.append({"label": c, "min_sqm": lo, "max_sqm": hi, "weight_pct": weight})
                continue
        if "미만" in c and nums:
            bands.append({"label": c, "min_sqm": None, "max_sqm": _man_to_sqm(nums[0]), "weight_pct": weight})
        elif "이상" in c and nums:
            bands.append({"label": c, "min_sqm": _man_to_sqm(nums[0]), "max_sqm": None, "weight_pct": weight})
        elif nums:
            # 경계어 없이 단일 수치 — 참고로만 (min=max 아님, label 로 보존)
            bands.append({"label": c, "min_sqm": None, "max_sqm": None, "weight_pct": weight})
    return bands


def _parse_bands_from_method(text: str) -> dict:
    """상위층 페이지의 evaluation_method 서술에서 축별 밴드 추출 (가장 안정적 소스).

    형식: "…: 8만㎡미만(사업수행능력평가 20%, 가격평가 80%), 8만㎡이상~24만㎡미만(…30%, …70%),
           24만㎡이상(…40%, …60%)" — 구간(area)별로 두 축의 %가 괄호 안에 함께.
    반환: {axis_name: [{label, min_sqm, max_sqm, weight_pct}]}. 못 찾으면 {}.
    이 서술은 배점표 method 로 추출돼 evaluation_criteria(LLM run 편차)보다 안정적.
    """
    result: dict[str, list] = {}
    if not text:
        return result
    for m in re.finditer(r"([^,()（）]*?(?:미만|이상|~)[^,()（）]*?)\s*[（(]([^)）]*)[)）]", text):
        area_raw, inner = m.group(1).strip(), m.group(2)
        # area_raw 는 콤마가 없으면 접두문("전체연면적…: 8만㎡미만")까지 먹으므로
        # 면적 토큰(첫 'N만' ~ 마지막 미만/이상)만 잘라 라벨·경계 계산에 쓴다.
        am = re.search(r"\d+\s*만[^,()（）]*(?:미만|이상)", area_raw)
        area_expr = am.group(0).strip() if am else area_raw
        nums = re.findall(r"(\d+)\s*만", area_expr)
        lo = hi = None
        if ("~" in area_expr or "∼" in area_expr) and len(nums) >= 2:
            lo, hi = _man_to_sqm(nums[0]), _man_to_sqm(nums[1])
        elif "미만" in area_expr and nums:
            hi = _man_to_sqm(nums[0])
        elif "이상" in area_expr and nums:
            lo = _man_to_sqm(nums[0])
        for am in re.finditer(r"([가-힣]+평가|[가-힣]{3,})\s*(\d+(?:\.\d+)?)\s*%", inner):
            axis = am.group(1).strip()
            result.setdefault(axis, []).append(
                {"label": area_expr, "min_sqm": lo, "max_sqm": hi, "weight_pct": float(am.group(2))}
            )
    return result


def _find_eval_pages(brief_data: dict) -> tuple[dict, dict]:
    """brief_evaluation 다중 페이지에서 (상위층 페이지, PQ상세 페이지) 식별.

    - top_page: 카테고리에 사업수행능력평가 + 가격평가 둘 다 있는 페이지(상위 2축).
    - pq_page : 배점 numeric 최다 페이지(참여기술자·유사용역실적·신용도 100점표).
    없으면 각 {}.
    """
    be = brief_data.get("brief_evaluation")
    if isinstance(be, dict):
        be = [be]
    pages = [p for p in (be or []) if isinstance(p, dict) and not p.get("_merged")]

    def _names(p):
        return " ".join((c.get("name") or "") for c in (p.get("evaluation_categories") or [])).replace(" ", "")

    top = next((p for p in pages
                if "사업수행능력평가" in _names(p) and "가격평가" in _names(p)), {})

    def _numpts(p):
        return sum(1 for c in (p.get("evaluation_categories") or [])
                   if isinstance(c.get("points"), (int, float)))
    pq = max(pages, key=_numpts, default={})
    return top, pq


def _parse_range(text: str) -> list[float] | None:
    """정확한 밴드 없이 범위만 있는 서술에서 [lo, hi] 추출.

    입력 예: "가격평가 비중: 연면적 규모에 따라 60~80% 차등 적용" → [60.0, 80.0].
    LLM 추출이 밴드 상세(8만/24만㎡)를 떨궈도 이 범위는 requirements 에 안정적으로 남는다.
    """
    m = re.search(r"(\d+(?:\.\d+)?)\s*[~∼－-]\s*(\d+(?:\.\d+)?)\s*%", text)
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    return [min(lo, hi), max(lo, hi)]


def _axis_role(text: str) -> str:
    if "가격" in text:
        return "price"
    if "수행능력" in text or "PQ" in text or "적격" in text:
        return "pq"
    return "other"


def _basis_dimension(text_all: str) -> str:
    """밴드 기준 차원 판별 — 연면적/대지면적/unknown. (대개 연면적)"""
    if "연면적" in text_all:
        return "연면적"
    if "대지면적" in text_all or "부지면적" in text_all:
        return "대지면적"
    return "unknown"


def _pq_detail(page: dict) -> dict:
    """하위 사업수행능력 100점표 — 식별된 PQ 페이지의 카테고리를 상위 항목으로 집계.

    page = _find_eval_pages 가 고른 배점 최다 페이지 (참여기술자·유사용역실적·신용도).
    """
    page = page or {}
    # 반복 병합행을 상위 카테고리로 집계 (참여기술자(50)/유사용역실적(40)/신용도(10))
    agg: dict[str, float] = {}
    order: list[str] = []
    for c in page.get("evaluation_categories", []):
        if not isinstance(c, dict):
            continue
        nm = (c.get("name") or "").strip()
        if not nm:
            continue
        if nm not in agg:
            agg[nm] = 0.0
            order.append(nm)
        if isinstance(c.get("points"), (int, float)):
            agg[nm] += c["points"]
    cats = [{"name": n, "points": agg[n]} for n in order]
    return {
        "total_points": page.get("total_points"),
        "categories": cats,
        "source": "brief_evaluation",
    }


def build_bid_structure(brief_data: dict) -> dict | None:
    """genre=="bid" 인 지침서의 2층 배점 구조. bid 아니거나 신호 없으면 None.

    반환 (schema_version 1):
    {
      schema_version, top_layer: {basis_dimension, thresholds_sqm, axes: [{name, role, bands}],
                                  applicable: {basis_value_sqm, band_label, weights, note}},
      pq_detail: {total_points, categories, source}
    }
    결정론·LLM 0. 실패해도 예외 없이 None.
    """
    try:
        genre = (brief_data.get("_brief_genre") or {}).get("genre")
        if genre != "bid":
            return None

        req = brief_data.get("_requirements") or {}
        crit = req.get("evaluation_criteria") or []
        if not isinstance(crit, list):
            crit = []

        # 다중 배점표 병합: 상위층 페이지(사업수행능력+가격 2축)와 PQ상세 페이지를 분리 식별.
        top_page, pq_page = _find_eval_pages(brief_data)

        by_role: dict[str, dict] = {}

        def _slot(role: str, name: str) -> dict:
            return by_role.setdefault(role, {"name": name, "role": role, "bands": [], "weight_range": None})

        # 1순위 소스: 상위층 페이지 evaluation_method 서술 (run 편차 작음).
        method_bands = _parse_bands_from_method((top_page or {}).get("evaluation_method") or "")
        for axis_name, bands in method_bands.items():
            role = _axis_role(axis_name)
            if role == "other" or not bands:
                continue
            s = _slot(role, axis_name)
            if not s["bands"]:
                s["bands"] = bands
                s["name"] = axis_name

        # 2·3순위 소스: evaluation_criteria 항목 + requirements 설명 (정확 밴드/범위 보강).
        cand_texts: list[str] = []
        for it in crit:
            if isinstance(it, dict) and "%" in str(it.get("item") or ""):
                cand_texts.append(str(it["item"]))
        for r in (req.get("requirements") or []):
            if isinstance(r, dict):
                desc = str(r.get("description") or "")
                if "%" in desc and ("가격" in desc or "수행능력" in desc or "비중" in desc or "차등" in desc):
                    cand_texts.append(desc)
        for t in cand_texts:
            role = _axis_role(t)
            if role == "other":
                continue
            bands = _parse_bands(t)
            has_thresh = any(b.get("min_sqm") or b.get("max_sqm") for b in bands)
            name = re.split(r"[（(:：]", t)[0].strip()[:40]
            s = _slot(role, name)
            if has_thresh and not any(bb.get("min_sqm") or bb.get("max_sqm") for bb in s["bands"]):
                s["bands"] = bands
                s["name"] = name
            elif not s["bands"] and s["weight_range"] is None:
                rng = _parse_range(t)
                if rng:
                    s["weight_range"] = rng

        axes = [by_role[r] for r in ("pq", "price") if r in by_role]
        # 상위 배점 신호가 전혀 없어도 PQ 100점표(하위)만으로 구조 노출 가치 있음.
        pq_detail = _pq_detail(pq_page)
        has_pq_table = bool(pq_detail.get("categories")) and (pq_detail.get("total_points") or 0) >= 50
        if not axes and not has_pq_table:
            return None

        basis_dim = _basis_dimension(
            "\n".join(cand_texts) + "\n" + ((top_page or {}).get("evaluation_method") or "")
        )

        # 정확 밴드가 있는 축들의 경계 합집합
        thr = sorted({b[k] for a in axes for b in (a.get("bands") or [])
                      for k in ("min_sqm", "max_sqm") if b.get(k)})

        applicable = _resolve_applicable(brief_data, axes, basis_dim)

        return {
            "schema_version": SCHEMA_VERSION,
            "top_layer": {
                "basis_dimension": basis_dim,
                "thresholds_sqm": thr,
                "axes": axes,
                "applicable": applicable,
            },
            "pq_detail": pq_detail,
        }
    except Exception:
        return None


def _basis_value_sqm(brief_data: dict, basis_dim: str):
    """밴드 기준 차원의 실제 값. 연면적이면 _quantitative.total_floor_area_sqm,
    대지면적이면 site_area_sqm. 미확보면 None (대체 추정 금지)."""
    q = brief_data.get("_quantitative") or {}
    if basis_dim == "연면적":
        return q.get("total_floor_area_sqm")
    if basis_dim == "대지면적":
        v = q.get("site_area_sqm")
        if v is not None:
            return v
        fe = brief_data.get("feasibility_export") or {}
        for s in fe.get("sites", []):
            if isinstance(s, dict) and s.get("site_area_sqm") is not None:
                return s["site_area_sqm"]
    return None


def _band_for(bands: list[dict], value: float) -> dict | None:
    for b in bands:
        lo, hi = b.get("min_sqm"), b.get("max_sqm")
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return b
    return None


def _resolve_applicable(brief_data: dict, axes: list[dict], basis_dim: str) -> dict:
    """기준값 확보 시 적용 밴드·유효 가중치 계산. 미확보면 note 로 사유 명시(단정 금지)."""
    val = _basis_value_sqm(brief_data, basis_dim)
    if val is None:
        note = (
            f"{basis_dim} 값 미확보 — 적용 밴드 판정 보류. "
            "이 값이 상위 배점(사업수행능력% vs 가격%)을 결정하므로 발주처 자료로 확인 필요."
            if basis_dim != "unknown"
            else "밴드 기준 차원(연면적/대지면적)이 서술에서 불명확 — 원문 확인 필요."
        )
        return {"basis_value_sqm": None, "band_label": None, "weights": {}, "note": note}

    weights: dict[str, float] = {}
    label = None
    for a in axes:
        b = _band_for(a["bands"], val)
        if b:
            weights[a["name"]] = b["weight_pct"]
            label = label or b["label"]
    return {
        "basis_value_sqm": val,
        "band_label": label,
        "weights": weights,
        "note": f"{basis_dim} {val:,.0f}㎡ 기준 적용 밴드." if weights else f"{basis_dim} {val:,.0f}㎡ — 매칭 밴드 없음.",
    }
