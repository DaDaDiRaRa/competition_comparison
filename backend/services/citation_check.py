"""
citation_check.py — LLM 서술의 (p.N) 인용 사후검증 (LLM 0 · 텍스트 수정 0).

`quant_validator`(정량 정합)·`proposal_number_check`(근거 없는 수치)의 인용판.
compare/diagnose/myproject 프롬프트는 모든 strengths/weaknesses/notes에 `(p.N)`을
강제하지만, 지금까지 **프롬프트로만 강제**할 뿐 N이 실재 페이지인지 코드가 검증하지
않았다. 이 모듈이 그 검증을 코드로 승격한다 — 환각된 페이지 번호(예: 12쪽 제출물에
'(p.47)')를 flag 로만 표시.

원칙 (프로젝트 관대 정책 — false positive 회피):
- **텍스트는 절대 수정하지 않는다** (플래그만).
- 유효 상한 = 제출물 `total_pages`(문서 실제 쪽수). 없으면 관측된 `_page` 최대값.
  둘 다 없으면 **검증 스킵**(bound=None) — 근거 없이 flag 하지 않는다.
- `1 <= N <= bound` 밖의 인용만 flag. 문서 안 페이지는 태깅 안 된 쪽이라도 정당 인용으로 인정.
- `(p.?)`(쪽 미상)는 프롬프트가 허용한 표기라 flag 하지 않는다.

flag: {value:"p.47", field:<위치>, page:47, bound:12, context:<주변문맥>, [company]}

회귀: `tests/test_citation_check.py`.
"""
from __future__ import annotations

import html
import re

from services.report_theme import warning_band

# (p.12) · (p.12,13) · (p. 12) · (p.?) — 쉼표·공백·물음표 허용
_CITE = re.compile(r"\(p\.\s*([0-9][0-9,\s]*|\?)\s*\)", re.IGNORECASE)


def collect_page_bound(source: dict | list | None) -> int | None:
    """유효 페이지 상한. total_pages 우선, 없으면 관측 _page 최대값, 둘 다 없으면 None."""
    if isinstance(source, dict):
        tp = source.get("total_pages")
        if isinstance(tp, (int, float)) and tp > 0:
            return int(tp)
    pages = _collect_pages(source)
    return max(pages) if pages else None


def _collect_pages(obj) -> list[int]:
    """중첩 dict/list 를 재귀 순회해 모든 _page 정수를 수집."""
    out: list[int] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "_page" and isinstance(v, (int, float)):
                out.append(int(v))
            else:
                out.extend(_collect_pages(v))
    elif isinstance(obj, list):
        for it in obj:
            out.extend(_collect_pages(it))
    return out


def check_text(text: str, bound: int | None, field: str = "",
               company: str | None = None) -> list[dict]:
    """text 안 (p.N) 중 1..bound 밖 인용을 flag. bound=None 이면 검증 스킵."""
    if bound is None or not isinstance(text, str) or not text:
        return []
    flags: list[dict] = []
    for m in _CITE.finditer(text):
        group = m.group(1)
        if "?" in group:
            continue  # (p.?) 는 허용 표기
        for tok in group.split(","):
            tok = tok.strip()
            if not tok:
                continue
            n = int(tok)
            if 1 <= n <= bound:
                continue
            ctx = text[max(0, m.start() - 20): m.end() + 8].strip()
            flag = {"value": f"p.{n}", "field": field, "page": n,
                    "bound": bound, "context": ctx}
            if company is not None:
                flag["company"] = company
            flags.append(flag)
    return flags


def _scan(pairs, bound: int | None, company: str | None = None) -> list[dict]:
    """(field, text) 반복자를 훑어 flag 누적. text 가 리스트면 항목별 검사."""
    flags: list[dict] = []
    for field, text in pairs:
        if isinstance(text, list):
            for item in text:
                if isinstance(item, str):
                    flags.extend(check_text(item, bound, field, company))
        elif isinstance(text, str):
            flags.extend(check_text(text, bound, field, company))
    return flags


# ── 소비처별 헬퍼 (순수 함수, LLM 무관) ─────────────────────────────────────────

def check_comparison(comparison: dict, submissions: list[dict]) -> list[dict]:
    """비교 결과의 축별 strengths/weaknesses/notes + concept_comparison 인용 검증.

    제출물별 bound 로 각자 판정(교차비교는 제출물마다 쪽수가 다름).
    concept_comparison 문단은 여러 회사를 인용하므로 전 제출물 상한의 합집합(max)으로 판정.
    """
    comparison = comparison or {}
    bounds = {s.get("company"): collect_page_bound(s) for s in submissions or []}
    union_bound = max([b for b in bounds.values() if b], default=None)

    flags: list[dict] = []
    subs = comparison.get("submissions")
    if isinstance(subs, dict):
        for company, axes in subs.items():
            bound = bounds.get(company, union_bound)
            if not isinstance(axes, dict):
                continue
            for axis, cell in axes.items():
                if not isinstance(cell, dict):
                    continue
                flags.extend(_scan((
                    (f"submissions.{company}.{axis}.strengths", cell.get("strengths")),
                    (f"submissions.{company}.{axis}.weaknesses", cell.get("weaknesses")),
                    (f"submissions.{company}.{axis}.notes", cell.get("notes")),
                ), bound, company))

    concept = comparison.get("concept_comparison")
    if isinstance(concept, dict):
        flags.extend(_scan(
            ((f"concept_comparison.{axis}", para) for axis, para in concept.items()),
            union_bound,
        ))
    return flags


def check_diagnosis(diagnosis: dict, submission: dict) -> list[dict]:
    """진단 결과(단일 제출물)의 축별·전역 strengths/weaknesses/recommendations/evidence 인용 검증."""
    diagnosis = diagnosis or {}
    bound = collect_page_bound(submission)

    flags: list[dict] = []
    axes = diagnosis.get("axes")
    if isinstance(axes, dict):
        for axis, cell in axes.items():
            if not isinstance(cell, dict):
                continue
            flags.extend(_scan((
                (f"axes.{axis}.strengths", cell.get("strengths")),
                (f"axes.{axis}.weaknesses", cell.get("weaknesses")),
                (f"axes.{axis}.recommendations", cell.get("recommendations")),
                (f"axes.{axis}.evidence", cell.get("evidence")),
            ), bound))

    flags.extend(_scan((
        ("strengths", diagnosis.get("strengths")),
        ("weaknesses", diagnosis.get("weaknesses")),
        ("recommendations", diagnosis.get("recommendations")),
    ), bound))

    rm = diagnosis.get("requirement_mapping")
    if isinstance(rm, list):
        for i, item in enumerate(rm):
            if isinstance(item, dict):
                flags.extend(check_text(item.get("evidence", ""), bound,
                                        f"requirement_mapping[{i}].evidence"))
    return flags


def check_myproject(deep: dict, sub_doc: dict) -> list[dict]:
    """MyProject deep 분석의 축별 evidence·개선점·차별화 인용 검증."""
    deep = deep or {}
    bound = collect_page_bound(sub_doc)

    flags: list[dict] = []
    axes = deep.get("axes_evidence")
    if isinstance(axes, dict):
        for axis, cell in axes.items():
            if not isinstance(cell, dict):
                continue
            flags.extend(_scan((
                (f"axes_evidence.{axis}.strengths", cell.get("strengths")),
                (f"axes_evidence.{axis}.weaknesses", cell.get("weaknesses")),
                (f"axes_evidence.{axis}.evidence", cell.get("evidence")),
            ), bound))

    flags.extend(_scan((
        ("key_differentiators", deep.get("key_differentiators")),
        ("improvement_points", deep.get("improvement_points")),
    ), bound))
    return flags


# ── 렌더 헬퍼 (LLM 0 · 인라인 스타일 자체완결 — 3개 리포트 generator 공유) ──────

def flags_band_html(flags: list[dict], limit: int = 20) -> str:
    """`_citation_flags` 를 경고 밴드로. 없으면 ''. 자체완결 인라인 스타일(CSS 무의존).

    문서 실제 쪽수를 벗어난 (p.N) 인용을 투명하게 노출 — 환각 쪽번호일 수 있으니
    원문 확인 필요 신호 (텍스트 수정 0, 플래그만). report_generator·
    diagnosis_report_generator·myproject_report_generator 공용.
    """
    flags = [f for f in (flags or []) if isinstance(f, dict)]
    if not flags:
        return ""
    rows = []
    for f in flags[:limit]:
        val = html.escape(str(f.get("value") or ""))
        bound = f.get("bound")
        loc = html.escape(str(f.get("field") or ""))
        ctx = html.escape(str(f.get("context") or "").strip())
        bound_txt = f" (문서 {bound}쪽)" if isinstance(bound, int) else ""
        ctx_txt = f' · <span style="color:#888">…{ctx}…</span>' if ctx else ""
        rows.append(
            f'<li style="margin:3px 0"><b>{val}</b>{html.escape(bound_txt)} · '
            f'<span style="color:#666;font-size:12px">{loc}</span>{ctx_txt}</li>'
        )
    return warning_band(
        '⚠ 근거 미확인 인용 — 아래 (p.N)은 문서 실제 쪽수를 벗어납니다 '
        '(환각 쪽번호일 수 있으니 원문 확인 필요)',
        "".join(rows),
    )
