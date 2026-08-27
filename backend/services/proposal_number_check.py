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

# 발명 위험이 높고 정당 변형이 적은 단위 — 이 단위에 붙은 수치는 (숫자,단위) **쌍**으로
# 코퍼스 대조(자릿수 무관). '공실률 12%·30억·1,100만원·480세대' 류를 정조준.
# 점/㎡/평/m/년/개월은 제외(배점은 결정론·면적/기간은 정당 변형이 잦아 오탐 위험).
_RISKY_UNITS = ("만원", "억", "원", "%", "세대", "가구", "호")
_PAIR = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(" + "|".join(_RISKY_UNITS) + r")")
_RISKY_HEAD = re.compile(r"^\s*(" + "|".join(_RISKY_UNITS) + r")")


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

    corpus_text = json.dumps(brief_data or {}, ensure_ascii=False)
    # 허용 bare 수치: 지침서 전체 + 결정론 scoring_focus 점수
    corpus = _num_set(corpus_text)
    # 허용 (숫자,단위) 쌍: 지침서 전체 + scoring_focus weight_pct → "N%"
    pairs = {(_norm(n), u) for n, u in _PAIR.findall(corpus_text)}
    for f in proposal.get("scoring_focus") or []:
        if isinstance(f, dict):
            pts, wt = f.get("points"), f.get("weight_pct")
            if isinstance(pts, (int, float)):
                corpus.add(_norm(str(pts)))
            if isinstance(wt, (int, float)):
                corpus.add(_norm(str(wt)))
                pairs.add((_norm(str(wt)), "%"))   # 배점 비중 'N%' 정당

    flags, seen = [], set()
    for field, text in _iter_prose(proposal):
        if not isinstance(text, str) or not text:
            continue

        # Pass 1 — 위험 단위 쌍 (자릿수 무관, (숫자,단위) 가 지침서에 없으면 flag)
        for m in _PAIR.finditer(text):
            num, unit = m.group(1), m.group(2)
            if (_norm(num), unit) in pairs:
                continue
            key = (field, "pair", _norm(num), unit)
            if key in seen:
                continue
            seen.add(key)
            ctx = text[max(0, m.start() - 18): m.end() + 12].strip()
            flags.append({"value": f"{num}{unit}", "field": field, "context": ctx})

        # Pass 2 — bare 다자리 수치 (위험 단위가 뒤따르면 Pass 1 담당이라 제외)
        for m in _NUM.finditer(text):
            if _RISKY_HEAD.match(text[m.end(): m.end() + 5]):
                continue
            raw = m.group()
            if len(re.sub(r"\D", "", raw)) < min_digits:
                continue  # 한 자리 구조 숫자 제외
            val = _norm(raw)
            if val in corpus:
                continue
            key = (field, "bare", val)
            if key in seen:
                continue
            seen.add(key)
            i = m.start()
            ctx = text[max(0, i - 18): i + len(raw) + 12].strip()
            flags.append({"value": raw, "field": field, "context": ctx})
    return flags


# ── 구조 검사: 근거를 안 밝힌 수치 주장 ─────────────────────────────────────
#
# 위 코퍼스 검사(`check_proposal_numbers`)와 **잡는 것이 다르다**:
#   · 코퍼스 = 그 숫자가 지침서 어디에도 없다        → 지어냈다
#   · 구조   = 숫자는 지침서에 있는데 이 주장이 출처를 안 밝혔다 → 읽는 사람이 확인 못 한다
# 임원이 「그 숫자 어디서 났습니까」라고 묻는 자리는 후자다. 둘 다 필요하다.
#
# concept-studio `render/numbers.py` 의 원리를 우리 데이터 모델에 옮긴 것 —
# 그쪽은 "사람이 읽는 글에 숫자가 있으면 `data-ev` 를 단 조상 안에 있어야 한다"를
# HTML 구조로 강제한다. 우리는 `basis` 앵커가 계약에 이미 있으므로 데이터에서 본다.
#
# ⚠ **빌드를 세우지 않는다.** concept-studio 는 모든 수치가 레지스터 소속이라 그럴 수
#    있지만, 우리 제안서는 지침서 수치를 산문에 그대로 인용하는 자리가 정당하게 많다.
#    렌더를 막으면 정당한 산출물이 안 나온다 → flag 로만.

#: `basis` 앵커가 **계약상 필수**인 블록만 본다. executive_summary·kickoff_checklist·
#: caveats 는 basis 칸 자체가 없어(스키마 참조) 검사 대상이 아니다 — 없는 칸을 비었다고
#: 나무라면 헛경고다.
_ANCHORED_SECTIONS = {
    "win_themes":         ("theme", "rationale", "scoring_link"),
    "design_directions":  ("direction", "narrative", "addresses",
                           "scoring_play", "tradeoffs", "site_rationale"),
    "program_directions": ("claim", "detail"),
    "massing_strategy":   ("claim", "detail"),
    "phasing":            ("claim", "detail"),
}


def _has_basis(item: dict) -> bool:
    """`basis` 가 실제로 채워졌는가. ⚠ `risks[].basis` 만 문자열이다(나머지는 리스트)."""
    b = item.get("basis")
    if isinstance(b, str):
        return bool(b.strip())
    if isinstance(b, list):
        return any(str(x).strip() for x in b)
    return False


def check_unanchored_claims(proposal: dict, min_digits: int = 2) -> list:
    """근거를 안 밝힌 수치 주장 flag. 각 flag: {value, field, context}.

    숫자가 **맞는지**는 안 본다(그건 코퍼스 검사 몫) — 이 주장이 어디서 왔는지
    문서가 말할 수 있는지만 본다. 숫자·텍스트 수정 0.
    """
    flags: list[dict] = []
    if not isinstance(proposal, dict):
        return flags

    def _scan(text, field):
        t = str(text or "").strip()
        if not t:
            return
        for m in _NUM.finditer(t):
            tok = m.group(0)
            digits = tok.replace(",", "").replace(".", "")
            unit_follows = _RISKY_HEAD.match(t[m.end():])
            if len(digits) < min_digits and not unit_follows:
                continue           # 한 자리 구조 숫자(1순위·5안)는 위험이 낮다
            lo, hi = max(0, m.start() - 18), min(len(t), m.end() + 18)
            flags.append({"value": tok, "field": field, "context": t[lo:hi]})
            return                 # 항목당 하나면 충분하다 — 목록이 길면 아무도 안 읽는다

    for sec, keys in _ANCHORED_SECTIONS.items():
        for i, item in enumerate(proposal.get(sec) or []):
            if not isinstance(item, dict) or _has_basis(item):
                continue
            for k in keys:
                _scan(item.get(k), f"{sec}[{i}].{k}")

    # 배치 존 — 지침서가 위치를 명시한 required 존은 사실이라 basis 가 더 중요하다.
    ps = proposal.get("placement_strategy")
    if isinstance(ps, dict):
        for i, z in enumerate(ps.get("zones") or []):
            if isinstance(z, dict) and not _has_basis(z):
                _scan(z.get("why"), f"placement_strategy.zones[{i}].why")

    for i, r in enumerate(proposal.get("risks") or []):
        if isinstance(r, dict) and not _has_basis(r):
            for k in ("risk", "mitigation"):
                _scan(r.get(k), f"risks[{i}].{k}")
    return flags
