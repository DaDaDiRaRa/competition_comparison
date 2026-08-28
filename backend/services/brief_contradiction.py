"""지침서 **내부 모순** 탐지 — 같은 양을 여러 곳이 다르게 말한다 (LLM 0 · 값 수정 0).

## 왜 필요한가 (실제 사고)

영등포 지침서의 `_quantitative.site_area_sqm` 이 대지면적이 아니라 **부지1의 연면적
합계**(56,189.72)를 들고 있었다. 체크리스트 핵심수치 카드의 대지면적 폴백 사슬 끝이
그 값이었고 앞 후보가 전부 비어서, **5.4배 틀린 대지면적**(실제 10,438㎡)이 리포트
첫 화면에 떴다 — prod 21건 중 **7건**, 2026-06 부터.

같은 지침서 안에 옳은 값도 있었다(`feasibility_export.sites[]` 7,498 + 2,940).
**두 소스가 같은 것을 다르게 말하는데 아무도 안 물었다.**

## 왜 「함의 용적률」이 아니라 「소스 불일치」인가

처음엔 연면적÷대지면적 이 명시 용적률과 맞는지 보려 했다. 두 이유로 접었다:
  · 연면적은 **지하를 포함**해 명시 용적률보다 크게 나오는 게 정상이라 문턱이 필요한데,
    prod 표본이 사실상 **한 공모**(영등포 11회)뿐이라 보정할 데이터가 없다.
  · **다부지면 명시 용적률이 단일 숫자가 아니다**(「부지1: 460% / 부지2: 400%」) — 비교 대상이 없다.

반면 「같은 양에 대한 소스 불일치」는 **문턱 보정이 필요 없다.** 지침서가 스스로
두 번 말했는데 값이 다르면, 어느 쪽이 맞든 **사람이 봐야 하는 상태**다.
어제 만든 `brief_merge_conflicts`(파일 **간** 충돌)의 파일 **내부**판이다.

## 무엇을 안 하는가

- **값을 안 고친다** (`quant_validator`·`citation_check` 와 같은 자리). flag 만.
- **어느 쪽이 맞는지 안 정한다.** 소스마다 신뢰도가 다르지만(정규화된 `feasibility_export`
  가 대개 낫다) 그건 사람이 원문을 봐야 아는 일이다. 값과 출처를 나란히 보여줄 뿐이다.
- **면적만 본다.** 건폐율·용적률은 다부지에서 부지별로 **정당하게 다르므로** 단일값과
  대조하면 헛경고가 난다. 필요해지면 부지별로 짝지어 보는 게 맞다.
"""

from __future__ import annotations

from typing import Any

#: 상대 오차 허용. 추출은 반올림 표기를 섞어 온다(56,189.7 vs 56,190).
TOLERANCE = 0.01
#: 절대 하한 — 작은 값에서 상대 오차가 과민해지는 것 방지.
ABS_FLOOR = 1.0


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _sum_sites(sites: Any, field: str) -> float | None:
    """부지별 값의 합. 하나도 없으면 None (0 과 구분 — 0 은 「없음」이 아니다)."""
    if not isinstance(sites, list):
        return None
    vals = [_num(s.get(field)) for s in sites if isinstance(s, dict)]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _sources_site_area(brief_data: dict) -> list[tuple[str, float]]:
    """총 대지면적을 말하는 자리들. 다부지면 **합**이 총 대지면적이다."""
    out: list[tuple[str, float]] = []
    fe = brief_data.get("feasibility_export")
    if isinstance(fe, dict):
        v = _sum_sites(fe.get("sites"), "site_area_sqm")
        if v is not None:
            out.append(("feasibility_export.sites 합", v))
    bpi = brief_data.get("brief_project_info")
    if isinstance(bpi, dict):
        v = _sum_sites(bpi.get("sites"), "site_area_sqm")
        if v is not None:
            out.append(("brief_project_info.sites 합", v))
    q = brief_data.get("_quantitative")
    if isinstance(q, dict):
        v = _num(q.get("site_area_sqm"))
        if v is not None:
            out.append(("_quantitative.site_area_sqm", v))
    return out


def _sources_total_fa(brief_data: dict) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    q = brief_data.get("_quantitative")
    if isinstance(q, dict):
        v = _num(q.get("total_floor_area_sqm"))
        if v is not None:
            out.append(("_quantitative.total_floor_area_sqm", v))
    for bp in (brief_data.get("brief_program") or []):
        if isinstance(bp, dict):
            v = _num(bp.get("total_required_floor_area_sqm"))
            if v is not None:
                out.append(("brief_program.total_required_floor_area_sqm", v))
                break        # 페이지마다 반복되므로 첫 값만 (같은 표의 사본이다)
    return out


_QUANTITIES = (
    ("site_area_sqm", "총 대지면적", _sources_site_area),
    ("total_floor_area_sqm", "총 연면적", _sources_total_fa),
)


def _disagrees(vals: list[float]) -> bool:
    lo, hi = min(vals), max(vals)
    return (hi - lo) > max(ABS_FLOOR, hi * TOLERANCE)


def detect_contradictions(brief_data: Any) -> list[dict]:
    """지침서 내부 모순 flag. 각 flag:

        {quantity, label, sources: [{where, value}], spread_ratio}

    `spread_ratio` = 최대÷최소 — 「5.4배 다르다」가 「56,189 vs 10,438」보다 빨리 읽힌다.
    값은 **안 고친다**. 어느 쪽이 맞는지도 **안 정한다**.
    """
    if not isinstance(brief_data, dict):
        return []
    flags: list[dict] = []
    for key, label, collect in _QUANTITIES:
        try:
            srcs = collect(brief_data)
        except Exception:      # noqa: BLE001 — 감사가 본 파이프라인을 막지 않는다
            continue
        vals = [v for _, v in srcs]
        if len(vals) < 2 or not _disagrees(vals):
            continue
        lo, hi = min(vals), max(vals)
        flags.append({
            "quantity": key,
            "label": label,
            "sources": [{"where": w, "value": v} for w, v in srcs],
            "spread_ratio": round(hi / lo, 2) if lo else None,
        })
    return flags


# ── 렌더 (LLM 0) ────────────────────────────────────────────────────────────


def _fmt(v: float) -> str:
    return f"{v:,.1f}".rstrip("0").rstrip(".")


def summary_line(flags: list | None) -> str:
    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return ""
    return "지침서 내부 모순 " + " · ".join(
        f'{f["label"]} {f["spread_ratio"]}배' if f.get("spread_ratio") else str(f["label"])
        for f in flags[:3])


def band_html(flags: list | None) -> str:
    """모순 경고 밴드. 없으면 ''."""
    import html

    from services.report_theme import warning_band

    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return ""
    rows = ""
    for f in flags:
        srcs = " ↔ ".join(
            f'{html.escape(_fmt(s["value"]))} <span style="color:#888">'
            f'({html.escape(str(s["where"]))})</span>'
            for s in (f.get("sources") or []))
        ratio = f' <b style="color:#c0392b">{f["spread_ratio"]}배</b>' if f.get("spread_ratio") else ""
        rows += f'<li><b>{html.escape(str(f["label"]))}</b>{ratio} — {srcs}</li>'
    return warning_band(
        html.escape("지침서 안에서 같은 값이 다르게 적혀 있습니다 "
                    "— 어느 쪽이 맞는지는 원문 확인이 필요합니다(자동 판정 안 함)"),
        rows)


def md_lines(flags: list | None) -> list[str]:
    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return []
    L = ["## 0.3 지침서 내부 모순", "",
         "> 같은 값을 지침서가 여러 곳에서 다르게 말합니다. "
         "**자동 판정하지 않았으며** 원문 확인이 필요합니다.", ""]
    for f in flags:
        srcs = " ↔ ".join(f'{_fmt(s["value"])}({s["where"]})' for s in (f.get("sources") or []))
        ratio = f' — {f["spread_ratio"]}배' if f.get("spread_ratio") else ""
        L.append(f"- **{f['label']}**{ratio}: {srcs}")
    L.append("")
    return L
