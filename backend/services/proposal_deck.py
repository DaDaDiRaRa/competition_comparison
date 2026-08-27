"""수주 제안서 → **A3 편집가능 PPTX 장표 내용** (`deck_render/1.0`).

## 우리는 그리지 않는다

내용은 우리가 만들고 **그리는 것은 터읽기**(arch-site-context `POST /deck/render`)다.
그쪽 `app/deck/style.py` 의 A3 네이티브 편집가능 조각(`kpi_card`·`table`·`caption_band`)은
다시 만들 물건이 아니다 — deck-builder 가 접힌 교훈은 「렌더러를 복제해라」가 아니라
「조립을 레포 건너 나누지 마라」였다.

계약의 낱말은 **다섯뿐**(`cover`·`kpi`·`cards`·`table`·`text`)이고 전부 이미 그쪽 어휘다.
여기에 '제안서' 전용 낱말을 늘려 달라고 하면 그 앱이 우리 도메인을 알기 시작한다.

## 장 순서 = 임원 발표 순서

**사실 → 배점 → 방향 5안 → 권장** (당면 TODO 의 기준 레퍼런스). 결정 요약만 맨 앞에
둔다 — 덱은 결론 먼저다(메모리 `project_byeonsu_conversational_steering`).

## 장표에도 근거가 따라간다

HTML 은 `data-ev` 를 달 수 있지만 PPTX 는 못 단다. 슬라이드마다 `sources` 에 제안서의
`basis`(p.N·항목명)를 모아 보내면 터읽기가 **캡션 밴드에 찍는다** — 장표만 들고 가도
「그 숫자 어디서 났습니까」에 답할 수 있어야 한다.

## 없는 장은 없다고 말한다

만들 수 없던 장은 `missing` 에 **이름을 대고** 적는다. 회의에서 「대안은 왜 없죠」가 나올 때
*안 만들었습니다* 와 *만들 수 없었습니다* 는 다른 말이다.
(터읽기 `RenderRequest` 는 이 필드를 안 읽는다 — 우리 API 응답용이다.)

## LLM 0 · 새 숫자 0

이미 만들어진 `_proposal`·`feasibility_export`·`_bid_structure` 를 재배치할 뿐이다.
판단(권장 종합안·결정 요약)은 **HTML 덱과 같은 함수**를 불러 쓴다 — 두 렌더러가 각자
뽑으면 같은 제안서가 화면과 장표에서 다른 결론을 말한다.
"""

from __future__ import annotations

from typing import Any

from services.brief_proposal_report_generator import (
    _FACT_FIELDS,
    _FACT_TOPLEVEL,
    _dir_name,
    _recommend,
    _zreq,
    COCKPIT_MIN_CELLS,
    cockpit_cells,
)

SCHEMA_VERSION = "deck_render/1.0"

#: 터읽기 `render_slides.py` 의 한 장 상한. 넘겨도 그쪽이 자르고 캡션에 「⚠ N칸은 자리가
#: 없어 뺐습니다」를 찍지만, **우리가 먼저 나눠 보내는 편이 낫다** — 잘린 안은 회의에서
#: 없는 것으로 읽힌다.
MAX_KPI = 4
MAX_CARDS = 4
MAX_ROWS = 12

#: 한 장에 카드 3개. 넷까지 되지만 셋이면 카드가 넓어져 본문(narrative)이 읽힌다.
CARDS_PER_SLIDE = 3

#: 표지 하단 고정 고지 — 창작·제안층이 실린 장표라는 것을 문서가 스스로 밝힌다.
DISCLAIMER = "수주 전략 가설 · 실제 심사 결과를 보장하지 않음 · 최종 판단은 설계팀"

_SEV_LABEL = {"high": "높음", "medium": "보통", "low": "낮음"}
_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


# ── 잔손질 ──────────────────────────────────────────────────────────────────


def _s(v: Any, n: int = 0) -> str:
    """PPTX 한 칸에 들어갈 한 줄. 개행·중복 공백을 눌러 붙이고 길면 자른다."""
    t = "" if v is None else str(v)
    t = " ".join(t.split())
    if n and len(t) > n:
        t = t[:n].rstrip(" ,·-—") + "…"
    return t


def _first_sentence(t: Any) -> str:
    t = _s(t)
    for sep in (" — ", ". ", "—"):
        if sep in t:
            return t.split(sep)[0].strip().rstrip(".")
    return t


def _dicts(d: dict, key: str) -> list[dict]:
    return [x for x in (d.get(key) or []) if isinstance(x, dict)]


def _strs(d: dict, key: str) -> list[str]:
    return [_s(x) for x in (d.get(key) or []) if _s(x)]


def _basis(item: Any) -> list[str]:
    """항목의 근거 목록. ⚠ `risks[].basis` 만 **문자열**이다(나머지는 리스트)."""
    if not isinstance(item, dict):
        return []
    b = item.get("basis")
    if isinstance(b, str):
        b = [b]
    return [_s(x, 40) for x in (b or []) if _s(x)]


def _sources(items: list, cap: int = 24) -> list[str]:
    """여러 항목의 근거를 순서 보존 dedup. 터읽기가 캡션에 14개까지 찍고 나머지는 센다."""
    out: list[str] = []
    for it in items:
        for b in _basis(it):
            if b not in out:
                out.append(b)
            if len(out) >= cap:
                return out
    return out


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _slide(kind: str, title: str, **kw) -> dict:
    s: dict[str, Any] = {"kind": kind, "title": title}
    for k, v in kw.items():
        if v:
            s[k] = v
    return s


# ── 장 하나씩 ───────────────────────────────────────────────────────────────


def _cover(proposal: dict, brief_name: str, facility: str, missing: list) -> dict:
    hook = proposal.get("concept_hook")
    hook = hook if isinstance(hook, dict) else {}
    axes = [a for a in (hook.get("axes") or []) if isinstance(a, dict)]
    keyword = _s(hook.get("keyword"), 28)

    body = []
    if axes:
        body.append(" · ".join(
            f'{_s(a.get("term"), 12)} {_s(a.get("ko"), 26)}'.strip() for a in axes[:3]
        ))
    body.append(DISCLAIMER)

    if not keyword:
        missing.append(
            "컨셉 표지 — `concept_hook` 이 없다. 근거가 모자라 생략됐거나 입찰(bid) 지침서다"
        )

    return _slide(
        "cover",
        title=keyword or _s(brief_name, 38),
        subtitle=f"{_s(brief_name, 44)} · {facility}" if keyword else facility,
        lead=_s(hook.get("tagline"), 58) or _first_sentence(proposal.get("executive_summary"))[:78],
        body=body,
        sources=_sources(axes),
    )


def _cockpit(proposal: dict, bid_structure: dict | None, missing: list) -> dict | None:
    """결정 요약 — HTML 덱과 **같은 셀**(`cockpit_cells`)을 표로."""
    cells = cockpit_cells(proposal, bid_structure)
    if len(cells) < COCKPIT_MIN_CELLS:
        missing.append(
            f"결정 요약 — 채울 수 있는 칸이 {len(cells)}개뿐이다"
            f"(최소 {COCKPIT_MIN_CELLS}). 제안서가 얇다는 뜻이다"
        )
        return None
    return _slide(
        "table",
        title="결정 요약",
        subtitle="DECISION BRIEF",
        lead="지침서를 읽고 판단한 결론 — 근거는 뒤 장에.",
        headers=["항목", "판단", "어떻게 나왔나"],
        rows=[[_s(c[0]), _s(c[1], 52), _s(c[2], 32)] for c in cells[:MAX_ROWS]],
        ratios=[0.18, 0.52, 0.30],
        caption="최종 결정은 설계팀",
    )


def _facts(feasibility: dict | None, missing: list) -> list[dict]:
    """사업 규모 — 지침서에서 **실제로 뽑은** 숫자만. HTML 팩트 밴드와 같은 필드.

    부지 제원(면적·용적·건폐·높이)과 사업비·기간은 성격이 달라 **장을 나눈다**.
    한 장에 몰면 상한(4)에 걸려 공사비가 잘리는데, 임원 덱에서 사업비가 빠지면
    그건 '자리가 없었다' 가 아니라 '안 봤다' 로 읽힌다.
    """
    fe = feasibility if isinstance(feasibility, dict) else {}
    sites = [s for s in (fe.get("sites") or []) if isinstance(s, dict)]
    s0 = sites[0] if sites else {}

    site_kpis = [{"label": label, "value": f"{fmt(s0[key])}{unit}"}
                 for key, unit, label, fmt in _FACT_FIELDS if _num(s0.get(key))]
    cost_kpis = [{"label": label, "value": f"{fmt(fe[key])}{unit}"}
                 for key, unit, label, fmt in _FACT_TOPLEVEL if _num(fe.get(key))]

    if not site_kpis and not cost_kpis:
        missing.append(
            "사업 규모 — `feasibility_export` 에 정량이 없다. 지침서에서 면적·한도가 "
            "안 잡혔거나 그 블록이 붙기 전에 분석된 건이다"
        )
        return []

    cap = "지침서 추출 사실 — 지어낸 수치 없음"
    if len(sites) > 1:
        cap += f" · 부지 {len(sites)}곳 중 대표(1번지) 기준"

    out = []
    for sub, kpis in (("FACTS · 부지 제원", site_kpis), ("FACTS · 사업비 · 기간", cost_kpis)):
        for i in range(0, len(kpis), MAX_KPI):
            out.append(_slide(
                "kpi", title="사업 규모", subtitle=sub,
                kpis=kpis[i:i + MAX_KPI], caption=cap,
            ))
    return out


def _scoring(proposal: dict, missing: list) -> dict | None:
    """배점 무게중심 — 결정론(`compute_scoring_focus`). LLM 환각을 덮어쓴 값이다."""
    focus = _dicts(proposal, "scoring_focus")
    if not focus:
        missing.append("배점 무게중심 — 지침서에서 심사 배점표가 안 잡혔다")
        return None

    ranked = sorted(focus, key=lambda f: f.get("rank") if _num(f.get("rank")) else 99)
    rows = []
    for f in ranked[:MAX_ROWS]:
        name = _s(f.get("category"), 34)
        if f.get("shared_with"):
            name += " ·공유"
        rows.append([
            _s(f.get("rank")) or "-",
            name,
            f'{f["points"]:g}' if _num(f.get("points")) else "정성",
            f'{f["weight_pct"]:g}%' if _num(f.get("weight_pct")) else "-",
        ])
    dropped = max(len(ranked) - MAX_ROWS, 0)
    return _slide(
        "table", title="배점 무게중심", subtitle="SCORING",
        lead="이 배점이 제안의 우선순위를 정한다.",
        headers=["순위", "심사 항목", "배점", "비중"],
        rows=rows, ratios=[0.10, 0.56, 0.17, 0.17],
        caption="결정론 산출 — 지침서 배점표 그대로"
                + (f" · {dropped}줄 생략" if dropped else ""),
    )


def _bid(bid_structure: dict | None) -> dict | None:
    """입찰 2층 배점 — 공모의 5안 자리에 들어간다(장르가 다르다)."""
    bs = bid_structure if isinstance(bid_structure, dict) else {}
    top = bs.get("top_layer") if isinstance(bs.get("top_layer"), dict) else {}
    axes = [a for a in (top.get("axes") or []) if isinstance(a, dict)]
    if not axes:
        return None

    rows = []
    for a in axes:
        bands = [b for b in (a.get("bands") or []) if isinstance(b, dict)]
        if bands:
            span = " / ".join(
                f'{_s(b.get("label"), 16)} {b["weight_pct"]:g}%'
                for b in bands if _num(b.get("weight_pct"))
            )
        elif isinstance(a.get("weight_range"), list) and len(a["weight_range"]) == 2:
            span = f'{a["weight_range"][0]:g}~{a["weight_range"][1]:g}% (범위만 확보)'
        else:
            span = "확인 필요"
        rows.append([_s(a.get("name"), 24), _s(span, 60)])

    applicable = top.get("applicable") if isinstance(top.get("applicable"), dict) else {}
    note = _s(applicable.get("note"), 70)
    basis_dim = _s(top.get("basis_dimension"))
    return _slide(
        "table", title="배점 구조", subtitle="2층 · 사업수행능력 vs 가격",
        lead=f"밴드 기준 = {basis_dim}" if basis_dim else "",
        headers=["축", "규모별 비중"], rows=rows[:MAX_ROWS], ratios=[0.28, 0.72],
        caption=note or "연면적 규모에 따라 비중이 달라진다",
    )


def _directions_matrix(dirs: list[dict]) -> dict:
    rows = [[
        _s(_dir_name(d), 26),
        _s(d.get("scoring_play"), 26),
        _s(d.get("addresses"), 44),
        _s(d.get("tradeoffs"), 44),
    ] for d in dirs[:MAX_ROWS]]
    return _slide(
        "table", title="설계 접근 방향", subtitle=f"{len(dirs)}개 안 · 한눈에",
        lead="변주가 아니라 전제가 서로 다른 안들이다.",
        headers=["안", "득점", "베팅하는 것", "포기하는 것"],
        rows=rows, ratios=[0.20, 0.18, 0.31, 0.31],
        sources=_sources(dirs), caption="제안 — 최종 컨셉 선택은 설계팀",
    )


def _direction_cards(dirs: list[dict]) -> list[dict]:
    """5안 상세. 한 장 3개씩 나눠 담는다 — 넷을 넘기면 터읽기가 자른다."""
    out = []
    total = (len(dirs) + CARDS_PER_SLIDE - 1) // CARDS_PER_SLIDE
    for i in range(0, len(dirs), CARDS_PER_SLIDE):
        chunk = dirs[i:i + CARDS_PER_SLIDE]
        cards = []
        for d in chunk:
            body = _s(d.get("narrative"), 260) or _s(d.get("addresses"), 260)
            tr = _s(d.get("tradeoffs"), 80)
            sr = _s(d.get("site_rationale"), 80)
            if sr:
                body += f"  ▸ 이 부지라서 — {sr}"
            if tr:
                body += f"  ▸ 포기 — {tr}"
            cards.append({
                "head": _s(_dir_name(d), 22),
                "tag": _s(d.get("scoring_play"), 30),
                "body": body,
            })
        n = i // CARDS_PER_SLIDE + 1
        out.append(_slide(
            "cards",
            title="설계 접근 방향",
            subtitle=f"상세 {n}/{total}" if total > 1 else "상세",
            cards=cards[:MAX_CARDS], sources=_sources(chunk),
        ))
    return out


def _recommended(proposal: dict, missing: list) -> dict | None:
    """권장 종합안 — HTML 덱과 **같은 판단**(`_recommend`)."""
    rec = _recommend(proposal)
    if not rec:
        missing.append(
            "권장 종합안 — 설계안이 2개 미만이거나 배점 순위가 없다(입찰 지침서면 정상)"
        )
        return None
    dds = rec["dds"]
    bb = dds[rec["backbone"]]

    cards = [{
        "head": _s(_dir_name(bb), 22),
        "tag": "뼈대 · BACKBONE",
        "body": _s(
            f'배점이 {rec["topcat"]} {rec["toppts"]}점'
            + (f'(전체 {int(rec["topw"])}%)' if _num(rec.get("topw")) else "")
            + "에 쏠려 있어, 이 안이 최대 승부처를 정면으로 가져간다. "
            + _s(bb.get("addresses"), 120), 280),
    }]
    for i in rec["grafts"][:2]:
        cards.append({
            "head": _s(_dir_name(dds[i]), 22),
            "tag": "접목 · 득점축이 달라 양립",
            "body": _s(dds[i].get("addresses"), 200),
        })
    if rec["conditional"]:
        cards.append({
            "head": "조건부 옵션",
            "tag": "심의·부지 여건에 따라",
            "body": " · ".join(_s(_dir_name(dds[i]), 24) for i in rec["conditional"]),
        })

    return _slide(
        "cards", title="권장 종합안", subtitle="RECOMMENDED",
        lead="상충하는 전제는 뭉치지 않았다.",
        cards=cards[:MAX_CARDS], sources=_basis(bb),
        caption="5개 안을 비교한 결과의 권장 조합 — 최종 컨셉 선택은 설계팀",
    )


def _placement(proposal: dict, missing: list) -> dict | None:
    """대지 근거 배치 — 지침서 명시(사실)와 추론(제안)을 한 칸에서 가른다."""
    ps = proposal.get("placement_strategy")
    ps = ps if isinstance(ps, dict) else {}
    zones = [z for z in (ps.get("zones") or []) if isinstance(z, dict)]
    if not zones:
        missing.append("배치 전략 — `placement_strategy.zones` 가 없다(대지 정보가 없으면 생략된다)")
        return None

    rows = []
    for z in zones[:MAX_ROWS]:
        where = " · ".join(x for x in (_s(z.get("plan")), _s(z.get("level"))) if x)
        rows.append([
            _s(z.get("program"), 26),
            where or "-",
            "필수" if _zreq(z) else "제안",
            _s(z.get("why"), 52),
        ])
    dropped = max(len(zones) - MAX_ROWS, 0)
    cap = "「필수」=지침서가 위치를 명시한 것 · 「제안」=추론"
    if dropped:
        cap += f" · {dropped}줄 생략"
    return _slide(
        "table", title="배치 전략", subtitle="PLACEMENT",
        lead=_s(ps.get("synthesis"), 110),
        headers=["프로그램", "위치", "구분", "왜 여기인가"],
        rows=rows, ratios=[0.22, 0.16, 0.10, 0.52],
        sources=_sources(zones), caption=cap,
    )


def _priorities(proposal: dict) -> dict | None:
    pr = _dicts(proposal, "priorities")
    if not pr:
        return None
    pr = sorted(pr, key=lambda p: p.get("rank") if _num(p.get("rank")) else 99)
    rows = [[
        _s(p.get("rank")) or "-",
        _s(p.get("focus"), 34),
        _s(p.get("why"), 54),
        _s(p.get("scoring_weight"), 12) or "-",
    ] for p in pr[:MAX_ROWS]]
    return _slide(
        "table", title="착수 우선순위", subtitle="PRIORITIES",
        headers=["순위", "착수 영역", "왜", "비중"],
        rows=rows, ratios=[0.09, 0.30, 0.48, 0.13],
    )


def _risks(proposal: dict) -> dict | None:
    rk = _dicts(proposal, "risks")
    if not rk:
        return None
    rk = sorted(rk, key=lambda r: _SEV_ORDER.get(r.get("severity"), 3))
    rows = [[
        _SEV_LABEL.get(r.get("severity"), "-"),
        _s(r.get("risk"), 46),
        _s(r.get("mitigation"), 54),
    ] for r in rk[:MAX_ROWS]]
    dropped = max(len(rk) - MAX_ROWS, 0)
    return _slide(
        "table", title="리스크 · 대응", subtitle="RISKS",
        headers=["심각도", "리스크", "대응"], rows=rows, ratios=[0.11, 0.42, 0.47],
        sources=_sources(rk),
        caption=(f"{dropped}줄 생략" if dropped else ""),
    )


def _kickoff(proposal: dict) -> dict | None:
    todo = _strs(proposal, "kickoff_checklist")
    ask = _strs(proposal, "open_questions")
    if not todo and not ask:
        return None
    body = [f"□ {_s(t, 92)}" for t in todo[:9]]
    if ask:
        body.append("")
        body.append("발주처 확인 필요")
        body += [f"? {_s(q, 92)}" for q in ask[:5]]
    return _slide("text", title="착수 체크리스트", subtitle="KICKOFF", body=body)


def _caveats(proposal: dict) -> dict | None:
    cav = _strs(proposal, "caveats")
    flags = [f for f in (proposal.get("_number_flags") or []) if isinstance(f, dict)]
    if not cav and not flags:
        return None
    body = [f"· {_s(c, 96)}" for c in cav[:8]]
    if flags:
        body.append("")
        body.append(
            f"근거 미확인 수치 {len(flags)}건 — 지침서 원문에서 확인되지 않은 숫자가 "
            "본문에 있다. 발표 전 대조 필요."
        )
        body += [f"  · {_s(f.get('value'))} ({_s(f.get('field'), 40)})" for f in flags[:5]]
    conf = _s(proposal.get("data_confidence"))
    return _slide(
        "text", title="한계 · 전제", subtitle="CAVEATS", body=body,
        caption=(f"근거 신뢰도 {_SEV_LABEL.get(conf, conf)}" if conf else ""),
    )


# ── 조립 ────────────────────────────────────────────────────────────────────


def build_deck(
    proposal: dict,
    brief_name: str,
    facility_label_ko: str,
    *,
    feasibility: dict | None = None,
    bid_structure: dict | None = None,
    filename: str = "proposal.pptx",
) -> dict:
    """`_proposal` → `deck_render/1.0` payload.

    ⚠ `filename` 은 **ASCII 여야 한다** — 터읽기 `/deck/render` 가 그 값을 그대로
    `Content-Disposition` 에 넣는데 ASGI 헤더는 latin-1 이라 한글이면 그쪽이 500 을 낸다
    (우리 `utils.html_file_response` 가 RFC 6266 으로 푼 것과 같은 함정). 한글 파일명은
    **우리 응답에서** 붙인다.
    """
    if not isinstance(proposal, dict) or not proposal:
        raise ValueError("제안서(_proposal)가 없습니다. 먼저 수주 제안서를 생성해주세요.")

    missing: list[str] = []
    slides: list[dict] = []

    slides.append(_cover(proposal, brief_name, facility_label_ko, missing))

    cockpit = _cockpit(proposal, bid_structure, missing)
    if cockpit:
        slides.append(cockpit)
    slides.extend(_facts(feasibility, missing))
    for maybe in (_scoring(proposal, missing), _bid(bid_structure)):
        if maybe:
            slides.append(maybe)

    dirs = _dicts(proposal, "design_directions")
    # '해당 없음'류(입찰 등)는 컨셉이 아니라 자리표시다 — 장표로 만들지 않는다.
    if dirs and any(k in _dir_name(dirs[0]) for k in ("해당 없음", "해당없음", "N/A", "없음")):
        dirs = []
    if dirs:
        slides.append(_directions_matrix(dirs))
        slides.extend(_direction_cards(dirs))
    else:
        missing.append("설계 접근 5안 — `design_directions` 가 없다(입찰 지침서면 정상)")

    for maybe in (
        _recommended(proposal, missing),
        _placement(proposal, missing),
        _priorities(proposal),
        _risks(proposal),
        _kickoff(proposal),
        _caveats(proposal),
    ):
        if maybe:
            slides.append(maybe)

    if missing:
        # 못 담은 장은 **장표 안에** 적는다. 헤더는 latin-1 이라 한글을 못 싣고,
        # 무엇보다 파일만 들고 회의에 들어가는 사람에게는 헤더가 없는 것과 같다.
        slides.append(_slide(
            "text", title="못 담은 것", subtitle="MISSING",
            lead="아래는 만들지 않은 게 아니라 만들 수 없었던 장이다.",
            body=[f"· {_s(m, 96)}" for m in missing[:8]],
        ))

    title = _s(brief_name, 44) or "수주 제안서"
    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "subtitle": f"수주 제안서 · {facility_label_ko}",
        "filename": _ascii_filename(filename),
        "slides": slides,
        "missing": missing,
    }


def _ascii_filename(name: str) -> str:
    """터읽기가 헤더에 그대로 박으므로 순수 ASCII 로 좁힌다(위 build_deck 경고 참조).

    지침서 이름은 대개 한글이라(`_slugify` 가 한글을 보존한다) 잘라내면 `__deck.pptx`
    같은 껍데기만 남는다. 알아볼 글자가 안 남으면 **차라리 뜻이 통하는 기본값**을 쓴다 —
    사용자에게 보이는 한글 이름은 우리 응답 헤더(RFC 6266)가 들고 간다.
    """
    import re

    stem = str(name or "")
    if stem.lower().endswith(".pptx"):
        stem = stem[:-5]
    stem = "".join(c for c in stem if 32 <= ord(c) < 127 and c not in '"\\/')
    stem = re.sub(r"[\s_]+", "_", stem).strip("_ .")
    if not re.search(r"[A-Za-z0-9]", stem):
        return "proposal_deck.pptx"
    return f"{stem}.pptx"
