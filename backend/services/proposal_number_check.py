"""
proposal_number_check.py — 제안서 prose 의 '근거 없는 수치' 검산 (LLM 0 · 숫자 수정 0).

`quant_validator` 의 제안서판. `_proposal` 의 **LLM 작성 서술**에 등장하는 수치를
지침서 추출 데이터(brief_data 전체 + 결정론 scoring_focus)와 대조해, 원천에 없는
숫자를 flag 로만 표시한다 — 첨부물식 분양가·ROI 같은 일반지식/발명 수치가 사실처럼
새는 것을 잡는다.

원칙:
- **숫자는 절대 수정하지 않는다** (플래그만, quant_validator 와 동일).
- 코퍼스(허용 출처) = brief_data 전체(특별조건·면적표·_site_context 포함) + scoring_focus.
  → 지침서/대지에 실재하는 수치는 통과, 어디에도 없는 수치만 flag.
- `basis`(근거 인용 — 페이지/항목 포인터)·메타 필드는 검사 제외 (사실 주장이 아님).
- 한 자리 구조 숫자(1순위·3면·5안)는 검사 제외 — 발명 위험은 2자리 이상에 몰려 있음.

회귀: `tests/test_proposal_number_check.py`.
"""
from __future__ import annotations

import json
import re

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(tok: str) -> str:
    """'1,440'→'1440', '30.0'→'30', '18.3'→'18.3' 로 정규화."""
    t = tok.replace(",", "").rstrip(".")
    try:
        f = float(t)
        return str(int(f)) if f == int(f) else str(f)
    except ValueError:
        return t


def _num_set(text: str) -> set:
    return {_norm(m) for m in _NUM.findall(text or "")}


def _iter_prose(proposal: dict):
    """검사 대상 (field, text) — LLM 작성 서술만. basis·메타·결정론 필드 제외."""
    yield ("executive_summary", proposal.get("executive_summary"))
    for t in proposal.get("win_themes") or []:
        if isinstance(t, dict):
            for k in ("theme", "rationale", "scoring_link"):
                yield (f"win_themes.{k}", t.get(k))
    for d in proposal.get("design_directions") or []:
        if isinstance(d, dict):
            for k in ("direction", "narrative", "addresses",
                      "scoring_play", "tradeoffs", "site_rationale"):
                yield (f"design_directions.{k}", d.get(k))
    for sec in ("program_directions", "massing_strategy", "phasing"):
        for it in proposal.get(sec) or []:
            if isinstance(it, dict):
                for k in ("claim", "detail"):
                    yield (f"{sec}.{k}", it.get(k))
    for p in proposal.get("priorities") or []:
        if isinstance(p, dict):
            for k in ("focus", "why", "scoring_weight"):
                yield (f"priorities.{k}", p.get(k))
    for r in proposal.get("risks") or []:
        if isinstance(r, dict):
            for k in ("risk", "mitigation"):
                yield (f"risks.{k}", r.get(k))
    for k in ("kickoff_checklist", "open_questions", "caveats"):
        for s in proposal.get(k) or []:
            yield (k, s)


def check_proposal_numbers(proposal: dict, brief_data: dict, min_digits: int = 2) -> list:
    """근거 없는 수치 flag 리스트. 각 flag: {value, field, context}.

    value=원문 표기(예 '1,100'), field=발견 위치, context=주변 문맥(사람 확인용).
    숫자는 수정하지 않음 — 호출측이 경고로만 노출.
    """
    proposal = proposal or {}

    # 허용 코퍼스: 지침서 전체 + 결정론 scoring_focus 수치
    corpus = _num_set(json.dumps(brief_data or {}, ensure_ascii=False))
    for f in proposal.get("scoring_focus") or []:
        if isinstance(f, dict):
            for k in ("points", "weight_pct"):
                v = f.get(k)
                if isinstance(v, (int, float)):
                    corpus.add(_norm(str(v)))

    flags, seen = [], set()
    for field, text in _iter_prose(proposal):
        if not isinstance(text, str) or not text:
            continue
        for m in _NUM.finditer(text):
            raw = m.group()
            if len(re.sub(r"\D", "", raw)) < min_digits:
                continue  # 한 자리 구조 숫자 제외
            val = _norm(raw)
            if val in corpus:
                continue
            key = (field, val)
            if key in seen:
                continue
            seen.add(key)
            i = m.start()
            ctx = text[max(0, i - 18): i + len(raw) + 12].strip()
            flags.append({"value": raw, "field": field, "context": ctx})
    return flags
