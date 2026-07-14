"""
brief_playbook.py — 지침서 "경험 기반 처방" (experiential playbook, LLM 종합).

`brief_advisor`(해설가: 사실 triage) · `brief_proposal`(전략가: 이 지침서 자체에서 나온
수주 전략) 에 이은 **세 번째 산출물**.

차이:
  - advisor/proposal 은 reference_cases(같은 시설유형 다른 공모의 축적 데이터) 를
    **배경 참고로만** 쓰고, 이 지침서 판단의 근거로는 쓰지 못하게 가드가 걸려 있다.
  - playbook 은 그 관계를 **뒤집는다** — reference_cases 가 *주연료*다. 우리 회사가
    같은 시설유형에서 쌓아온 당선/낙선 경험을 읽어, "과거엔 이래서 됐고 이래서
    떨어졌으니, 이 지침서에서는 이걸 이렇게 하라"는 **경험 기반 처방**을 만든다.

오염 방지(핵심 설계):
  - winning_lessons/losing_pitfalls/watch_axes = **과거 다른 공모의 사실**. 근거(source)
    는 reference_cases(과거 공모명·집계). 이 지침서의 요구로 위장 금지.
  - applications = **과거 교훈 × 이 지침서**(AI 해석 확장층). 각 항목은 과거 교훈
    (rooted_in)과 이 지침서의 실제 사실(basis = 배점 항목/강조/대지, p.N 또는 항목명)에
    **동시에** 앵커. 둘 중 하나라도 못 달면 항목을 뺀다.
  - 당락 예측·보장 없음. 과거 N 이 얕으면(win_n ≤ 2) 단정 말고 tentative.

전제조건: reference_cases 가 비면(축적 데이터 0) LLM 을 아예 호출하지 않고
`has_accumulated_data=False` sentinel 을 반환한다 (연료 없는데 과금 방지 — 무료 게이트).
"""
from __future__ import annotations

import asyncio
import json

from config import settings
from services.llm_client import call_messages
from services.utils import parse_json_response
from services.brief_advisor import _build_advisor_payload, compute_scoring_focus
from services.reference_cases import collect_reference_context


SCHEMA_VERSION = 1   # _playbook 스키마 버전


_PLAYBOOK_SYSTEM = (
    "당신은 건축 설계공모를 준비하는 설계팀의 수석 전략 자문이다.\n"
    "역할은 **우리 회사가 같은 시설유형에서 쌓아온 과거 당선·낙선 경험을 읽고, 그\n"
    "교훈을 지금 이 지침서에 어떻게 적용할지 처방**하는 것이다. 설계팀이 '전에\n"
    "이래서 됐고 이래서 떨어졌으니, 이번엔 이걸 이렇게 하자'를 바로 잡을 수 있어야 한다.\n"
    "\n"
    "당신 앞에는 두 종류의 재료가 있다. 절대 섞지 마라:\n"
    "  · [과거·사실] reference_cases — 같은 시설유형 **다른 공모**의 축적 데이터\n"
    "    (당선/낙선 집계 통계·과거 당선작 컨셉·과거 비교분석). 여기서 교훈을 길어낸다.\n"
    "  · [현재·사실] scoring_focus·emphasis_signals·sites 등 — **이 지침서**가 실제로\n"
    "    요구·강조·배점하는 것. 교훈을 적용할 대상이다.\n"
    "\n"
    "절대 규칙 (위반 시 결과 폐기):\n"
    "1. [출처 분리] 과거 교훈(winning_lessons/losing_pitfalls/watch_axes)의 근거(source)\n"
    "   는 reference_cases 안의 것(과거 공모명 또는 '당선 N건 집계')만 쓴다. 이걸 이\n"
    "   지침서의 요구/배점인 것처럼 쓰지 마라.\n"
    "2. [현재 근거 한정] 이 지침서가 무엇을 요구/배점한다는 *현재 사실 주장*은 제공된\n"
    "   지침서 데이터(scoring_focus/emphasis/sites 등) 안의 것만 쓰고, 근거 위치를 단다\n"
    "   (_page/eval_page 있으면 p.N, 없으면 배점 항목명/카테고리명). 페이지 번호를\n"
    "   추측해 지어내지 않는다. 과거 공모의 수치·요구를 이 지침서 사실로 옮기지 마라.\n"
    "3. [교차 앵커] applications(적용) 의 각 항목은 반드시 **과거 교훈(rooted_in)** 과\n"
    "   **이 지침서의 실제 사실(basis)** 둘 다에 앵커한다. 어느 한쪽이라도 못 달면 그\n"
    "   항목을 빼라. 이 지침서에 걸 데가 없는 일반론은 넣지 않는다.\n"
    "4. [예측·보장 금지] '당선된다/반드시 이긴다' 같은 확정 표현 금지. 과거 경향은\n"
    "   가설이지 예측이 아니다. 과거 표본이 얕으면(win_n ≤ 2, 발췌 1~2건) 단정하지 말고\n"
    "   confidence='tentative' 로, 그렇다고 말한다.\n"
    "5. [새 숫자 금지] 분양가·ROI·세대수·절감액 같은 수치를 지어내 사실로 만들지 않는다.\n"
    "   인용 가능한 숫자는 지침서(현재) 또는 reference_cases(과거)에 실재하는 것만.\n"
    "\n"
    "모든 출력은 한국어 평어체. 반드시 지정된 JSON 형식만 출력한다."
)


# 작업 지시 + 출력 스키마 (정적, cache_control ephemeral 대상).
# .format() 안 씀 — JSON 중괄호 충돌 회피 (comparator/advisor/proposal 과 동일 원칙).
_PLAYBOOK_INSTRUCTION = (
    "[작업] 아래 데이터로 '경험 기반 처방(experiential playbook)' JSON 한 개를 생성하라.\n"
    "우리 회사 과거 당선·낙선 경험을, 지금 이 지침서에 적용하는 것이 목표다.\n"
    "\n"
    "[입력 설명]\n"
    "- reference_cases: **과거·사실 (주연료)** — 같은 시설유형 다른 공모 축적 데이터. 세 서브키:\n"
    "  · pattern_summary: 당선 win_n·낙선 lose_n 집계 + winner_patterns/loser_patterns/\n"
    "    key_differentiators(정성 패턴) + 당선/낙선 키워드. 교훈·함정·당락축의 근거.\n"
    "  · case_excerpts: 과거 당선작의 실제 컨셉 서술(main_strategy 등) + 공모명.\n"
    "  · concept_comparison_excerpts: 과거 비교분석의 축별 컨셉 비교 서술 + 공모명.\n"
    "- brief_genre: 이 지침서의 장르(결정론 판별). \"bid\"=설계자 선정 입찰이면 평가는 설계안이\n"
    "  아니라 자격·실적·가격이다 — 과거 교훈을 이 지침서에 적용할 때 '실적·참여기술자·가격\n"
    "  경쟁력'축으로 걸어라(설계 컨셉축이 아니라). \"competition\"이면 설계축 그대로.\n"
    "- scoring_focus / evaluation_detail / emphasis_signals / sites / special_conditions:\n"
    "  **현재·사실** — 이 지침서가 요구·강조·배점하는 것. 교훈을 적용할 대상.\n"
    "- data_basis: 과거 표본 규모(win_n·lose_n·발췌 수). 신뢰도 판단에 쓴다.\n"
    "\n"
    "[출력 JSON — 정확히 이 키만, 다른 키 추가 금지]\n"
    "{\n"
    '  "summary": "과거 경험이 이 지침서에 주는 핵심을 2~3문장. \'과거엔 X가 당락을 갈랐고, 이 지침서는 Y를 무겁게 보니 Z에 유의\' 식으로 과거와 현재를 엮어라.",\n'
    '  "winning_lessons": [\n'
    '    { "lesson": "과거 당선작에서 배우는 교훈 (한 줄)",\n'
    '      "evidence": "reference_cases 근거 — 어떤 패턴/컨셉/축에서 나왔는지",\n'
    '      "source": "과거 공모명 또는 \'당선 N건 집계\'",\n'
    '      "confidence": "strong|tentative" }\n'
    "  ],\n"
    '  "losing_pitfalls": [\n'
    '    { "pitfall": "과거 낙선작 공통 함정 (한 줄)",\n'
    '      "evidence": "reference_cases 근거", "source": "과거 공모명 또는 \'낙선 N건 집계\'",\n'
    '      "confidence": "strong|tentative" }\n'
    "  ],\n"
    '  "applications": [\n'
    '    { "guidance": "이 지침서에서 구체적으로 뭘 어떻게 할지 (처방, 2~3문장)",\n'
    '      "rooted_in": "이 처방이 근거한 과거 교훈/함정 (winning_lessons·losing_pitfalls 중 어느 것)",\n'
    '      "brief_anchor": "이 지침서의 어떤 사실에 적용되는가 (배점 항목·강조·대지 조건)",\n'
    '      "basis": ["이 지침서 근거 위치 — 배점 항목명 또는 p.N"],\n'
    '      "confidence": "strong|tentative" }\n'
    "  ],\n"
    '  "watch_axes": [\n'
    '    { "axis": "과거 당락을 가른 축 (key_differentiators 기반)",\n'
    '      "why": "이 축이 왜 갈랐는지 + 이 지침서에서 주목할 이유",\n'
    '      "source": "과거 공모명 또는 집계" }\n'
    "  ],\n"
    '  "data_confidence": "high|medium|low",\n'
    '  "caveats": ["한계 — 과거 표본 규모/편향 + 실제 심사 결과는 보장 못 함 고지"]\n'
    "}\n"
    "\n"
    "[필드 규칙]\n"
    "- winning_lessons/losing_pitfalls: reference_cases 가 실제로 가리키는 것만. 집계 N 이\n"
    "  작으면(win_n/lose_n ≤ 2) confidence='tentative'. 없는 함정을 지어내지 말 것.\n"
    "- applications 가 이 산출물의 핵심이다 — 과거 교훈을 이 지침서 사실에 걸어 처방으로\n"
    "  바꾼다. 각 항목은 rooted_in(과거)과 basis(현재) 둘 다 필수. 이 지침서에 걸 곳이\n"
    "  없으면 아무리 좋은 과거 교훈이어도 넣지 마라 (일반 조언 금지).\n"
    "- watch_axes: pattern_summary.key_differentiators 우선. 없으면 winner/loser 패턴 대비에서.\n"
    "- data_confidence: win_n ≤ 2 이거나 발췌가 거의 없으면 low. 표본이 충분하고 패턴이\n"
    "  뚜렷하면 medium~high. 솔직하게.\n"
    "- caveats 에 반드시 '다른 공모의 경험을 이 지침서에 적용한 가설이며 실제 심사 결과는\n"
    "  보장할 수 없다' 취지의 문장을 한 줄 포함.\n"
    "- 억지로 개수 채우지 말 것 (강한 신호 위주 triage). 신호 없는 항목은 지어내지 말 것.\n"
    "\n"
    "[교차 앵커 예시 — applications 한 항목]\n"
    '✅ {"guidance":"저층부를 시민에게 개방하는 안을 전면에 세워라. 과거 당선작들이 공통으로\n'
    '   저층 개방을 택했고, 이 지침서는 시민개방 항목에 배점이 쏠려 있어 부합도가 높다.",\n'
    '   "rooted_in":"당선작 공통 저층 개방형 채택","brief_anchor":"시민개방 배점 1순위",\n'
    '   "basis":["시민개방","p.12"],"confidence":"strong"}\n'
    "  과거 교훈(rooted_in)과 이 지침서 사실(basis) 둘 다에 걸려 있다."
)


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _data_basis(ref_ctx: dict) -> dict:
    """reference_cases → 결정론 표본 규모 (LLM 이 못 바꾸게 덮어쓸 값)."""
    ps = (ref_ctx.get("pattern_summary") or {}) if isinstance(ref_ctx, dict) else {}
    return {
        "win_n":            int(ps.get("win_n") or 0),
        "lose_n":           int(ps.get("lose_n") or 0),
        "case_count":       len(ref_ctx.get("case_excerpts") or []) if isinstance(ref_ctx, dict) else 0,
        "comparison_count": len(ref_ctx.get("concept_comparison_excerpts") or []) if isinstance(ref_ctx, dict) else 0,
    }


def _empty_playbook(facility_type: str, brief_id: str = "") -> dict:
    """축적 데이터가 없을 때의 graceful sentinel (LLM 미호출)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "brief_id": brief_id,
        "facility_type": facility_type,
        "model_id": "",
        "has_accumulated_data": False,
        "data_basis": {"win_n": 0, "lose_n": 0, "case_count": 0, "comparison_count": 0},
        "summary": "",
        "winning_lessons": [],
        "losing_pitfalls": [],
        "applications": [],
        "watch_axes": [],
        "data_confidence": "none",
        "caveats": [
            "이 시설유형에 축적된 과거 당선·낙선 데이터가 없어 경험 기반 처방을 생성할 수 없습니다. "
            "'경쟁 공모 등록' 탭에서 같은 시설유형의 과거 공모(당락 라벨 포함)를 등록하고 비교분석을 "
            "실행해 데이터를 쌓으면 사용할 수 있습니다.",
        ],
    }


def _playbook_sync(brief_data: dict, facility_type: str) -> dict:
    # advisor 와 동일한 결정론 백본 신호 재사용 — reference_cases 도 여기서 채워진다.
    payload = _build_advisor_payload(brief_data, facility_type)
    ref_ctx = payload.get("reference_cases") or {}
    brief_id = (brief_data.get("_brief_meta") or {}).get("brief_id", "")

    # 전제조건 게이트 — 과거 데이터 없으면 과금 없이 sentinel (무료 게이트).
    if not ref_ctx:
        return _empty_playbook(facility_type, brief_id)

    payload["data_basis"] = _data_basis(ref_ctx)

    dynamic = (
        "데이터 — reference_cases 는 과거·사실(주연료), 나머지는 이 지침서의 현재·사실:\n"
        + _compact(payload)
    )
    raw = call_messages(
        model=settings.model_id_advisor,   # 처방 전용 모델(기본 Opus). 추출은 그대로 Sonnet.
        max_tokens=24000,   # 잘림 여유 (16k 초과 방지)
        temperature=0,     # Opus 4.7/4.8 은 call_messages 가 temperature 를 자동 생략 (400 회피)
        system=_PLAYBOOK_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PLAYBOOK_INSTRUCTION, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    try:
        result = parse_json_response(raw)
    except Exception as e:
        raise ValueError(f"경험 기반 처방 JSON 파싱 실패: {e}\n원문(앞 200자): {raw[:200]}")
    if not isinstance(result, dict):
        raise ValueError(f"경험 기반 처방 응답이 dict 아님: {type(result).__name__}")

    # 결정론 값으로 덮어씀 — LLM 이 표본 규모/시설유형을 바꾸지 못하게 (환각 차단).
    result["has_accumulated_data"] = True
    result["data_basis"] = payload["data_basis"]
    result["scoring_focus"] = compute_scoring_focus(brief_data)   # 렌더러가 배점 무게중심 참조
    result["schema_version"] = SCHEMA_VERSION
    result["model_id"] = settings.model_id_advisor
    result["facility_type"] = facility_type
    result["brief_id"] = brief_id
    # 렌더러가 재조회 없이 근거 사례를 그릴 수 있게 원본 보존.
    result["_reference_cases"] = ref_ctx
    return result


async def build_playbook(brief_data: dict, facility_type: str = "") -> dict:
    """지침서 경험 기반 처방 생성 (LLM 최대 1콜). 저장된 _brief.json 재해석, 추가 추출 없음.

    같은 시설유형의 과거 당선·낙선 축적 데이터(reference_cases)가 있어야 의미가 있다.
    없으면 `has_accumulated_data=False` sentinel 을 **LLM 호출 없이** 반환한다.

    반환은 _playbook 스키마 dict (summary / winning_lessons / losing_pitfalls /
    applications(과거×이 지침서 교차 앵커) / watch_axes / data_basis(결정론) /
    data_confidence / caveats + 메타).
    """
    return await asyncio.to_thread(_playbook_sync, brief_data, facility_type)
