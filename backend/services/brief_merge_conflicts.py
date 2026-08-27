"""멀티파일 병합 충돌 탐지 — **조용히 이기는 것을 막는다** (LLM 0 · 값 수정 0).

## 무엇이 문제였나

`analyze` 는 지침서 + 과업지시서 등 **복수 파일 동시 분석**을 지원한다. 병합은
`first_wins` — 먼저 올린 파일이 이긴다. 그 자체는 규칙으로 정해도 되는 일이지만,
**진 값이 어디에도 안 남는 게** 문제다. 두 문서가 대지면적을 다르게 적어도 화면엔
하나만 뜨고, 그 하나가 `feasibility_export` → `arch_law_client` 진단 → **법적 골격**까지
흘러간다. 사람은 두 문서가 다르게 말했다는 사실 자체를 모른다.

## 왜 자동 해소를 안 하나 (concept-studio 와 다른 선택)

concept-studio 는 출처 등급으로 자동 해소한다(`gazette > guideline > press > …`).
그건 **권위 서열이 실재하는** 문서군이라 가능하다 — 고시가 보도자료를 이긴다.

우리는 다르다. 지침서·과업지시서·설계지침은 **전부 같은 발주처가 낸 공식 문서**고,
어느 쪽이 이겨야 하는지는 공모마다 다르다(과업지시서가 지침서를 정정하기도 하고,
지침서 본문이 별첨을 이긴다고 명시하기도 한다). **코드가 정할 일이 아니다.**

그래서 이 모듈은 `quant_validator`·`citation_check` 와 같은 자리에 선다:
**값을 안 고치고 flag 만.** 해소(first_wins)는 그대로 두되 **말은 한다.**
우리 CLAUDE.md 가 시퀀스 C 잔여로 적어 둔 개선 방향 그대로다 —
「충돌을 숨기지 말고 `_quantitative_flags` 처럼 경고로 노출해 사람이 판단」.

## 파일 이름의 날짜는 힌트지 판정이 아니다

나중 날짜 파일이 다르게 말하면 **정정일 가능성이 높다**(concept-studio 가 실측으로
얻은 규칙). 하지만 그것도 단정하지 않고 flag 에 `later_differs` 로 표시만 한다 —
파일 이름은 사람이 붙인 것이고, 내용과 무관하게 다시 저장되는 일도 있다.
"""

from __future__ import annotations

import re
from typing import Any

#: 부지별로 대조할 정량 필드 — `feasibility_export` 의 입력이라 틀리면 법적 골격까지 간다.
_SITE_NUM_FIELDS = (
    "site_area_sqm", "floor_area_sqm", "building_coverage_pct",
    "floor_area_ratio_pct", "max_height_m", "open_space_sqm",
)

#: 최상위 키 중 병합에서 **특별 취급**되는 것 — 블록 유실 통지 대상이 아니다.
_SPECIAL_KEYS = {
    "_by_type", "design_guidelines_grouped", "page_map", "total_pages",
    "_quantitative", "_brief_genre", "_brief_meta",
}

#: 파일 이름 앞머리의 `YYMMDD` / `YYYYMMDD`.
_DATE_RE = re.compile(r"(?<!\d)(\d{6}|\d{8})(?!\d)")


def _label(names: list[str] | None, i: int) -> str:
    if names and i < len(names) and str(names[i]).strip():
        return str(names[i]).strip()
    return f"파일{i + 1}"


def _file_date(name: str) -> str:
    """파일 이름의 날짜(YYYYMMDD 정규화). 없으면 ''. **판정이 아니라 힌트다.**"""
    m = _DATE_RE.search(name or "")
    if not m:
        return ""
    d = m.group(1)
    return f"20{d}" if len(d) == 6 else d


def _num(v: Any) -> float | None:
    """숫자로 볼 수 있으면 float. 12345 와 12345.0 을 같게 보려고."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _differs(a: Any, b: Any) -> bool:
    """값이 실질적으로 다른가. 숫자는 수치로, 나머지는 공백 정리 후 문자열로."""
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) > 1e-9
    return " ".join(str(a).split()) != " ".join(str(b).split())


def _sites(d: dict) -> dict[str, dict]:
    """`brief_project_info.sites[]` → {site_id: site}. site_id 없으면 순번으로."""
    pinfo = d.get("brief_project_info")
    out: dict[str, dict] = {}
    if isinstance(pinfo, dict):
        for i, s in enumerate(pinfo.get("sites") or []):
            if isinstance(s, dict):
                out[str(s.get("site_id") or f"#{i + 1}")] = s
    return out


def detect_conflicts(data_list: list[dict], source_names: list[str] | None = None) -> list[dict]:
    """파일별 brief_data 목록 → 충돌 flag 리스트. 값은 **안 고친다**.

    각 flag: `{kind, key, chosen, chosen_from, others: [{value, from}], later_differs}`
      · kind = "quantitative" | "site" | "block"
      · chosen = first_wins 로 실제 채택된 값 · others = 진 값들(어느 파일이 뭐라 했는지)
      · later_differs = 나중 날짜 파일이 다르게 말했다(정정 가능성 — **단정 아님**)

    파일이 1개면 빈 리스트(충돌이 있을 수 없다).
    """
    if not isinstance(data_list, list) or len(data_list) < 2:
        return []
    data_list = [d for d in data_list if isinstance(d, dict)]
    if len(data_list) < 2:
        return []

    names = [_label(source_names, i) for i in range(len(data_list))]
    dates = [_file_date(n) for n in names]
    flags: list[dict] = []

    def _add(kind: str, key: str, picks: list[tuple[int, Any]]) -> None:
        """picks = [(파일index, 값)] — 첫 항목이 first_wins 승자."""
        if len(picks) < 2:
            return
        wi, wv = picks[0]
        others = [{"value": v, "from": names[i]} for i, v in picks[1:] if _differs(wv, v)]
        if not others:
            return
        later = any(dates[i] and dates[wi] and dates[i] > dates[wi]
                    for i, v in picks[1:] if _differs(wv, v))
        flags.append({
            "kind": kind, "key": key, "chosen": wv, "chosen_from": names[wi],
            "others": others, "later_differs": later,
        })

    # ── _quantitative: 필드별 first non-null wins ────────────────────────────
    qkeys: list[str] = []
    for d in data_list:
        for k in (d.get("_quantitative") or {}):
            if k not in qkeys:
                qkeys.append(k)
    for k in qkeys:
        picks = [(i, (d.get("_quantitative") or {}).get(k))
                 for i, d in enumerate(data_list)
                 if (d.get("_quantitative") or {}).get(k) is not None]
        _add("quantitative", k, picks)

    # ── brief_project_info.sites[]: 부지별 정량 ──────────────────────────────
    per_file_sites = [_sites(d) for d in data_list]
    site_ids: list[str] = []
    for sm in per_file_sites:
        for sid in sm:
            if sid not in site_ids:
                site_ids.append(sid)
    for sid in site_ids:
        for f in _SITE_NUM_FIELDS:
            picks = [(i, sm[sid].get(f)) for i, sm in enumerate(per_file_sites)
                     if sid in sm and sm[sid].get(f) is not None]
            _add("site", f"{sid}.{f}", picks)

    # ── 최상위 블록: 뒤 파일 것이 통째로 버려졌는가 ───────────────────────────
    # 필드별 병합이 아니라 first_wins 라, base 가 비어 있지 않으면 뒤 파일 블록은
    # **통째로** 사라진다. 어느 필드가 어긋났는지까진 못 말하지만 **사라졌다는 사실**은 말한다.
    #
    # ⚠ 위에서 **정밀하게** 짚은 블록은 여기서 다시 말하지 않는다 — 같은 사실을 두 번
    #   말하면 목록이 부풀고, 정확한 줄(「부지1.site_area_sqm 12,345 ↔ 12,500」) 옆에
    #   뭉뚱그린 줄(「brief_project_info 내용 다름」)이 붙어 오히려 덜 읽힌다.
    precise_blocks = {"brief_project_info"} if any(f["kind"] == "site" for f in flags) else set()

    base = data_list[0]
    for i, d in enumerate(data_list[1:], start=1):
        for key, val in d.items():
            if key in _SPECIAL_KEYS or key in precise_blocks or key.startswith("_"):
                continue
            if not val or not isinstance(val, (dict, list)):
                continue
            bv = base.get(key)
            if bv and _differs(str(bv)[:400], str(val)[:400]):
                flags.append({
                    "kind": "block", "key": key,
                    "chosen": f"{names[0]} 의 값", "chosen_from": names[0],
                    "others": [{"value": "(내용 다름 — 병합 안 됨)", "from": names[i]}],
                    "later_differs": bool(dates[i] and dates[0] and dates[i] > dates[0]),
                })
    return flags


# ── 렌더 (LLM 0) ────────────────────────────────────────────────────────────


_KIND_KO = {"quantitative": "정량", "site": "부지", "block": "블록"}


def _fmt(v: Any) -> str:
    n = _num(v)
    if n is not None:
        return f"{n:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def summary_line(flags: list | None) -> str:
    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return ""
    later = sum(1 for f in flags if f.get("later_differs"))
    tail = f" · 그중 {later}건은 나중 날짜 파일이 다르게 말함" if later else ""
    return f"파일 간 충돌 {len(flags)}건{tail}"


def band_html(flags: list | None) -> str:
    """충돌 경고 밴드. 없으면 '' (파일 1개거나 충돌 0건)."""
    import html

    from services.report_theme import warning_band

    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return ""
    rows = ""
    for f in flags[:14]:
        kind = _KIND_KO.get(f.get("kind"), "")
        others = " · ".join(
            f'{html.escape(_fmt(o.get("value")))} <span style="color:#888">'
            f'({html.escape(str(o.get("from")))})</span>'
            for o in (f.get("others") or [])[:3])
        mark = ' <b style="color:#c0392b">나중 문서가 다름</b>' if f.get("later_differs") else ""
        rows += (f'<li><b>{html.escape(str(f.get("key")))}</b>'
                 f' <span style="color:#888">[{kind}]</span> — 채택 '
                 f'{html.escape(_fmt(f.get("chosen")))} '
                 f'<span style="color:#888">({html.escape(str(f.get("chosen_from")))})</span>'
                 f' ↔ {others}{mark}</li>')
    if len(flags) > 14:
        rows += f'<li style="color:#888">외 {len(flags) - 14}건</li>'
    title = html.escape(
        f"파일 간 값이 어긋납니다 {len(flags)}건 — 먼저 올린 파일 값을 썼습니다(자동 판정 아님)")
    return warning_band(title, rows)


def md_lines(flags: list | None) -> list[str]:
    """md·HWPX 용 — 같은 사실이 문서 종류를 안 가리고 따라가게."""
    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return []
    L = ["## 0.4 파일 간 충돌", "",
         f"> 복수 파일 분석에서 값이 어긋난 항목 {len(flags)}건. "
         "**먼저 올린 파일 값을 채택**했으며 자동 판정이 아닙니다 — 원문 확인이 필요합니다.", ""]
    for f in flags[:20]:
        others = " · ".join(f'{_fmt(o.get("value"))}({o.get("from")})'
                            for o in (f.get("others") or [])[:3])
        mark = "  ⚠ 나중 날짜 파일이 다름" if f.get("later_differs") else ""
        L.append(f"- **{f.get('key')}** — 채택 {_fmt(f.get('chosen'))}"
                 f"({f.get('chosen_from')}) ↔ {others}{mark}")
    L.append("")
    return L
