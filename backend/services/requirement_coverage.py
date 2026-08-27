"""지침서 요구 **완결성 감사** — 진단이 답하지 않고 지나간 요구를 찾는다.

## 왜 필요한가

진단은 이미 요구사항 매트릭스를 낸다(`requirement_mapping`: 요구·축·충족여부·근거).
그런데 그 목록을 **LLM 이 고른다.** 분모(`_requirements.requirements`, 지침서에서 뽑은
요구 전체)의 어느 항목이 매트릭스에 안 나타나도 아무도 모른다 — 표는 멀쩡해 보이고
없는 줄은 눈에 안 띈다.

**실무에서 탈락은 누락에서 난다.** 그러니 "답한 것"만 보여주는 표는 절반이다.
이 모듈은 분모와 분자를 대조해 **N개 중 M개**를 세고, 빠진 것을 이름 대고 말한다.

`quant_validator`(정량 정합)·`citation_check`(인용 실재)와 **같은 자리**다:
**LLM 0 · 텍스트 수정 0 · flag 만.** 매트릭스를 고쳐 쓰지 않는다.

## 매칭은 관대하게

LLM 의 `requirement` 는 30자 요약이고 지침서 `description` 은 그보다 길다. 길이가
비대칭이라 Jaccard 는 같은 항목도 낮게 나온다 → **포함 계수**(overlap coefficient,
교집합 ÷ 짧은 쪽)를 쓴다. 요약이 원문의 압축이면 요약 쪽 bigram 은 대개 원문에 있다.

문턱은 **낮게** 잡는다. 헛경고 하나가 진짜 누락 열 개의 신뢰를 깎는다(영등포 교훈) —
"확실히 아무것도 안 걸린 것"만 누락으로 세운다.
"""

from __future__ import annotations

import re
from typing import Any

#: 확신 매칭 — 요약 bigram 의 절반 이상이 원문에 있으면 같은 요구로 본다.
MATCH_MIN = 0.50

#: 같은 평가축이면 문턱을 낮춘다. 축이 같은데 겹침도 있으면 다른 요구일 확률이 낮다.
AXIS_MATCH_MIN = 0.30

_STATUSES = ("yes", "partial", "no", "unclear")
_PUNCT = re.compile(r"[\s·、,，.。\-–—/()\[\]{}「」『』\"':;!?~%]+")


def _norm(t: Any) -> str:
    """공백·구두점을 지우고 라틴은 소문자로. 표기 흔들림을 흡수한다."""
    return _PUNCT.sub("", str(t or "")).lower()


def _bigrams(t: str) -> set[str]:
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _overlap(a: str, b: str) -> float:
    """포함 계수 — 교집합 ÷ 짧은 쪽. 길이 비대칭에 강하다."""
    ba, bb = _bigrams(_norm(a)), _bigrams(_norm(b))
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / min(len(ba), len(bb))


def _req_text(r: dict) -> str:
    return str(r.get("description") or "").strip()


def _map_text(m: dict) -> str:
    return str(m.get("requirement") or "").strip()


def check_coverage(requirements: Any, mapping: Any) -> dict:
    """지침서 요구(분모) × 진단 매트릭스(분자) 대조.

    Returns:
        {
          "total": int,            # 지침서 요구 수 — 글이 있는 것만(분모)
          "mapped": int,           # 매트릭스에 나타난 요구 수(분자)
          "coverage_pct": int|None,
          "by_status": {"yes":n,"partial":n,"no":n,"unclear":n},
          "unmapped": [{"axis":str,"description":str}],   # 진단이 답하지 않은 요구
          "unanchored": [str],     # 매트릭스엔 있는데 지침서 요구에 안 붙는 항목
        }

    요구가 없으면(지침서 미첨부·추출 실패) 전부 0 · `coverage_pct: None` —
    **0% 가 아니다.** 잴 것이 없는 것과 못 맞춘 것은 다르다.
    """
    reqs = [r for r in (requirements or []) if isinstance(r, dict)] \
        if isinstance(requirements, list) else []
    maps = [m for m in (mapping or []) if isinstance(m, dict)] \
        if isinstance(mapping, list) else []

    by_status = {s: 0 for s in _STATUSES}
    for m in maps:
        s = str(m.get("status") or "unclear")
        by_status[s if s in by_status else "unclear"] += 1

    scored = [(m, _map_text(m)) for m in maps]
    hit_idx: set[int] = set()
    unmapped: list[dict] = []
    total = 0

    for r in reqs:
        desc = _req_text(r)
        if not desc:
            continue                       # 글이 없으면 대조할 수 없다 — 분모에서 뺀다
        total += 1
        r_axis = str(r.get("axis") or "")
        best, best_i = 0.0, -1
        for i, (m, mtext) in enumerate(scored):
            if not mtext:
                continue
            score = _overlap(desc, mtext)
            floor = AXIS_MATCH_MIN if (r_axis and str(m.get("axis") or "") == r_axis) else MATCH_MIN
            if score >= floor and score > best:
                best, best_i = score, i
        if best_i >= 0:
            hit_idx.add(best_i)
        else:
            unmapped.append({"axis": r_axis, "description": desc})

    # 지침서 어느 요구에도 안 붙는 매트릭스 항목 — 요구를 지어냈거나 우리가 못 뽑은 것.
    # 단정하지 않는다(추출이 요구를 놓쳤을 수도 있다) — 이름만 남긴다.
    unanchored = [t for i, (m, t) in enumerate(scored) if t and i not in hit_idx]

    mapped = total - len(unmapped)
    return {
        "total": total,
        "mapped": mapped,
        "coverage_pct": round(100 * mapped / total) if total else None,
        "by_status": by_status,
        "unmapped": unmapped,
        "unanchored": unanchored,
    }


def check_diagnosis(diagnosis: dict, brief_data: dict) -> dict:
    """진단 결과 + 지침서 → 완결성 요약. 실패해도 빈 요약(비치명)."""
    try:
        reqs = ((brief_data or {}).get("_requirements") or {}).get("requirements")
        return check_coverage(reqs, (diagnosis or {}).get("requirement_mapping"))
    except Exception:  # noqa: BLE001 — 감사가 본 파이프라인을 막지 않는다
        return check_coverage([], [])


# ── 렌더 (LLM 0) ────────────────────────────────────────────────────────────


def summary_line(cov: dict) -> str:
    """표 옆에 붙는 한 줄. 잴 것이 없으면 ''."""
    if not cov or not cov.get("total"):
        return ""
    return f'지침서 요구 {cov["total"]}개 중 {cov["mapped"]}개 응답 ({cov["coverage_pct"]}%)'


def band_html(cov: dict) -> str:
    """누락이 있을 때만 경고 밴드. 없으면 '' (깨끗한 진단엔 아무것도 안 붙는다)."""
    import html

    from services.report_theme import warning_band

    if not cov:
        return ""
    unmapped = cov.get("unmapped") or []
    unanchored = cov.get("unanchored") or []
    if not unmapped and not unanchored:
        return ""

    rows = ""
    for u in unmapped[:12]:
        axis = html.escape(str(u.get("axis") or ""))
        desc = html.escape(str(u.get("description") or "")[:110])
        tail = f' <span style="color:#888">({axis})</span>' if axis else ""
        rows += f"<li>{desc}{tail}</li>"
    if len(unmapped) > 12:
        rows += f'<li style="color:#888">외 {len(unmapped) - 12}건</li>'
    for t in unanchored[:5]:
        rows += (f'<li style="color:#8a6d3b">「{html.escape(str(t)[:80])}」 — '
                 '지침서 요구 목록에 대응이 없다(추출 누락 또는 진단이 만든 항목)</li>')

    title = f'진단이 답하지 않은 지침서 요구 {len(unmapped)}건' if unmapped \
        else '지침서 요구에 대응 없는 매트릭스 항목'
    if unmapped:
        title += ' · 탈락은 누락에서 난다'
    return warning_band(html.escape(title), rows)
