"""
brief_proposal.py — 지침서 기반 "프로젝트 수주 제안서" (LLM 종합).

`brief_advisor.py` 가 "해설가"(사실 triage, 예측·처방 금지)라면, 이 모듈은
"전략가" — 같은 결정론 백본 신호(배점·강조·부지·제약) 위에서 **앞을 보는 제안**을
한다: 수주 핵심 테마, 설계 접근 방향 후보, 배점 기반 우선순위, 리스크/대응,
착수 체크리스트. 사용자가 명시적으로 요청한 "프로젝트 시작 제안" 산출물.

설계 원칙 (advisor 와의 차이):
  - advisor: "지침서가 X를 강조한다(근거)"까지만. 예측·처방 금지.
  - proposal: "X가 핵심이니 이렇게 접근하라"까지 허용 (수주 전략 처방).
  - 단, **사실 주장(지침서가 무엇을 요구/강조하는가)에는 근거 인용 유지** — 환각 차단.
    전략·판단은 '제안'으로 명시하고, 실제 당락은 보장 못 함을 caveats 에 고지.
  - 새 추출 없음. brief_advisor._build_advisor_payload 가 만든 신호 + 기존 _insight 를
    재료로만 사용 (LLM 1콜). 추출 산출물 회귀 없음.
"""
from __future__ import annotations

import asyncio
import json
import logging

from config import settings
from services.llm_client import call_messages
from services.utils import parse_json_response
from services.brief_advisor import _build_advisor_payload, compute_scoring_focus
from services.db_manager import load_pattern


logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1   # _proposal 스키마 버전


_PROPOSAL_SYSTEM = (
    "당신은 건축 설계공모를 준비하는 설계팀의 수주 전략 자문이다.\n"
    "역할은 **이미 추출된 지침서 데이터를 바탕으로, 이 공모에 어떻게 착수하고\n"
    "무엇으로 차별화할지 실행 가능한 제안**을 만드는 것이다. 설계팀이 제안서를\n"
    "읽고 곧바로 작업 우선순위를 잡을 수 있어야 한다.\n"
    "\n"
    "당신은 \"전략가\"다 — 무엇이 핵심이고 어디에 집중해야 하는지 처방한다.\n"
    "그러나 처방은 반드시 **지침서 근거 위에서만** 한다. 다음 두 층을 명확히 구분하라:\n"
    "  · [사실] 지침서가 무엇을 요구/강조/배점하는가 → 반드시 근거(basis) 인용.\n"
    "  · [제안] 그 사실에 비춘 전략·접근 방향·우선순위 → 당신의 판단. 처방 허용.\n"
    "\n"
    "절대 규칙 (위반 시 결과 폐기):\n"
    "1. [사실 근거 한정] 지침서가 요구/강조한다는 *사실 주장*은 제공된 데이터 안의\n"
    "   내용만 사용하고 근거 위치를 단다. 데이터에 없는 요구·수치·배점을 지어내지\n"
    "   않는다. 외부 사례·심사위원 성향 같은 미확인 통념을 끌어오지 않는다.\n"
    "2. [인용 형식] 근거는 데이터에 _page/eval_page 가 있으면 (p.N), 없으면\n"
    "   섹션명/카테고리명/배점항목명. **페이지 번호를 추측해 지어내지 않는다.**\n"
    "3. [당선 보장 금지] \"당선된다\", \"반드시 이긴다\" 같은 확정 표현 금지. 전략은\n"
    "   \"~하면 강조점에 부합한다\", \"배점상 ~에 집중할 가치가 크다\" 같은 제안형으로.\n"
    "   실제 심사 결과는 보장할 수 없음을 caveats 에 명시한다.\n"
    "4. [근거 약하면 약하다고] 신호가 빈약하면 억지로 채우지 말고 그렇게 말한다.\n"
    "   data_confidence 로 전체 신뢰도를 솔직히 표기한다.\n"
    "\n"
    "모든 출력은 한국어 평어체. 반드시 지정된 JSON 형식만 출력한다."
)


# 작업 지시 + 출력 스키마 (정적, cache_control ephemeral 대상).
# .format() 안 씀 — JSON 중괄호 충돌 회피 (comparator/advisor 와 동일 원칙).
_PROPOSAL_INSTRUCTION = (
    "[작업] 아래 지침서 데이터를 바탕으로 이 공모 착수를 위한 '프로젝트 수주 제안서'\n"
    "JSON 한 개를 생성하라. 설계팀이 읽고 바로 우선순위를 잡을 수 있게.\n"
    "\n"
    "[입력 설명]\n"
    "- scoring_focus: 배점표를 결정론으로 계산한 결과(카테고리·배점·비중·랭킹). 신뢰 가능.\n"
    "- evaluation_detail: 배점 항목별 세부(sub_items)·실격조건·총점·출처 페이지(eval_page).\n"
    "- emphasis_signals: 강조어휘 문장 + 지침서 자체 분류별 분량(강조 신호). 단,\n"
    "  \"일반사항\"·\"(미분류)\"는 잡동사니 버킷이므로 테마 신호로 쓰지 말 것.\n"
    "- design_overview / sites / special_conditions / validation_flags: 보조 근거.\n"
    "- prior_insight: (있으면) 앞서 생성된 사실 triage 해설 — 제안의 토대로 삼되 그대로\n"
    "  복붙하지 말고 '그래서 어떻게 할지'로 발전시킨다.\n"
    "- pattern_context: (있으면) 동일 시설유형 과거 공모 당선·낙선 분석 경향.\n"
    "  규칙: (a) 전략·제안을 구체화하는 힌트로만 활용. (b) 이 공모의 사실 주장(지침서가\n"
    "  요구·배점하는 것)으로 인용 절대 금지 — 다른 공모·다른 지침서의 통계임.\n"
    "  (c) win_n ≤ 2 이면 신호가 약하니 단정 말고 '경향이 있다' 수준으로.\n"
    "  (d) 패턴과 이 지침서 요구가 충돌하면 지침서가 우선.\n"
    "- site_context: (있으면) VWorld 위성·지적도 이미지를 Claude vision으로 판독한 실제 대지 맥락.\n"
    "  analysis 하위 키: orientation(방위·형상) / road_access(접도) / surrounding_uses(주변용도) /\n"
    "  natural_assets(자연자산) / special_context(특이사항) / overall_summary(대지요약).\n"
    "  규칙: (a) 대지 맥락을 설계 방향에 연결할 때 반드시 이 데이터를 우선 참고.\n"
    "  (b) design_directions 5안에 대지 형상·접도·조망 조건을 직접 반영 (이 부지라서 가능한 안).\n"
    "  (c) 불확실(confidence=low)이면 '위성 분석 기준, 현장 확인 필요' 단서를 붙여라.\n"
    "\n"
    "[출력 JSON — 정확히 이 키만, 다른 키 추가 금지]\n"
    "{\n"
    '  "executive_summary": "첫 문장은 \'발주처가 명시 요구 너머로 진짜 원하는 것\'을 배점·강조 분포로 읽어 한 줄로 박아라(예: 배점이 시민개방에 쏠리면 진짜 주제는 사무소가 아니라 열린 청사). 이어서 무게중심과 권장 전략 방향을 2~4문장. 제안형.",\n'
    '  "win_themes": [\n'
    '    { "theme": "수주를 가르는 핵심 테마(차별화 축)",\n'
    '      "rationale": "왜 이게 핵심인지 — 배점/강조 근거에 비춘 제안",\n'
    '      "scoring_link": "연결되는 배점 항목·비중(있으면)",\n'
    '      "basis": ["배치계획","p.18"] }\n'
    "  ],\n"
    '  "design_directions": [\n'
    '    { "direction": "짧은 컨셉 이름 + 한 줄 (예: \'저층 개방형 — 저층부를 시민에게 내주고 업무동을 상부로\')",\n'
    '      "narrative": "이 컨셉을 2~4문장으로 풀어라 — 어떤 발상이고, 배점·강조·대지의 어떤 사실에서 출발하며, 공간적으로 무엇을 하는가. 근거 있는 추론만, 새 숫자 금지.",\n'
    '      "addresses": "이 컨셉이 베팅하는 것 — 어떤 배점/강조에 거는가 (1~2문장)",\n'
    '      "scoring_play": "이 안이 실제로 따는 점수 — 어떤 배점 항목을 얼마나 가져가는가(예: \'배치 10 + 조망 5\')",\n'
    '      "tradeoffs": "이 컨셉이 포기·감수하는 것 (면적/공사비/운영 등 상충, 1~2문장)",\n'
    '      "site_rationale": "이 부지라서 가능/유리한 이유 — site_context 의 실측 대지 조건에 연결(없으면 생략)",\n'
    '      "basis": ["p.N 또는 항목명"] }\n'
    "  ],\n"
    '  "program_directions": [\n'
    '    { "claim": "프로그램 구성 제안 — 한 줄 제목격 (예: \'저층부에 시민개방형 공유 프로그램 집중\')",\n'
    '      "detail": "2~4문장 — 왜 이게 배점/강조/대지에서 나오는지 + 설계적으로 무엇을 의미하는지(어떤 공간·동선·구성). 근거 있는 추론, 새 숫자·새 사실 금지.",\n'
    '      "basis": ["근거가 된 사실의 위치/항목 — 배점 항목명 또는 p.N 또는 site_context.키"] }\n'
    "  ],\n"
    '  "massing_strategy": [\n'
    '    { "claim": "매스·배치 전략 제안 — 한 줄 제목격 (예: \'남측 조망축으로 판상 펼치고 코어를 북측에\')",\n'
    '      "detail": "2~4문장 — 대지 형상·접도·조망(site_context)과 배점에 비춘 배치 논리와 그 효과. 근거 있는 추론, 새 숫자 금지.",\n'
    '      "basis": ["근거 위치/항목"] }\n'
    "  ],\n"
    '  "phasing": [\n'
    '    { "claim": "착수·전개 단계 제안 — 한 줄 제목격 (설계 진행 순서·의사결정 분기)",\n'
    '      "detail": "2~4문장 — 어떤 사실(실격/한도/배점 무게)이 이 순서를 강제하는지 + 각 단계에서 무엇을 확정하는지. 근거 있는 추론, 새 숫자 금지.",\n'
    '      "basis": ["근거 위치/항목"] }\n'
    "  ],\n"
    '  "priorities": [\n'
    '    { "rank": 1, "focus": "가장 먼저·가장 무겁게 다룰 영역",\n'
    '      "why": "배점/강조 근거", "scoring_weight": "비중%(있으면)" }\n'
    "  ],\n"
    '  "risks": [\n'
    '    { "risk": "수주를 위협하는 리스크·제약(실격조건/심의/정량 하한 등)",\n'
    '      "severity": "high|medium|low", "mitigation": "대응 제안",\n'
    '      "basis": "p.N 또는 항목명" }\n'
    "  ],\n"
    '  "kickoff_checklist": ["착수 즉시 할 일 (제안형, 실행 가능 단위)"],\n'
    '  "open_questions": ["발주처/주최측에 확인이 필요한 사항"],\n'
    '  "data_confidence": "high|medium|low",\n'
    '  "caveats": ["분석의 한계 + 실제 심사 결과는 보장 못 함 고지"]\n'
    "}\n"
    "\n"
    "[필드 규칙]\n"
    "- win_themes: **1~2개로 압축**. 공모는 모든 항목을 고루 잘해서가 아니라 1~2개 큰 수로\n"
    "  갈린다. '여기서 당락이 갈린다'를 날카롭게 좁혀라 — 나열식으로 늘리면 도로 요약이 된다.\n"
    "  배점 무게중심(scoring_focus 상위)과 반복 강조가 겹치는 축을 우선.\n"
    "- design_directions: **서로 배타적인 컨셉을 정확히 5안** 제시. 한 아이디어의 변주 5개가\n"
    "  아니라 출발 전제가 다른 5개여야 한다(배치 전략·공공성 해석·매스 구성 등 축이 갈리게).\n"
    "  각 안은 '무엇에 베팅하고(addresses) 무엇을 포기하는가(tradeoffs)'를 반드시 대비시켜라.\n"
    "  단일 정답을 고르지 말고 팀이 고를 판을 깔아라. (이 필드만 5개 고정 — 아래 triage 예외.)\n"
    "- priorities: 배점 무게중심·반복 강조 순으로 착수 순서. 배점 약하면 caveats 에 명시.\n"
    "- risks 는 두 층: (a) 명시적 — disqualification_criteria + high severity validation flag +\n"
    "  정량 하한(면적/대수/등급) + 심의로 정해지는 한계(limits_determined_by=심의). (b) 추론적 —\n"
    "  지침서가 *유난히 반복·강조*하는 항목은 '과거 응모안들이 자주 놓쳤다'는 신호일 수 있으니\n"
    "  '흔한 감점 함정' 으로 제시하되, 추론임을 note/근거에 드러내고 단정하지 말 것.\n"
    "- win_themes·priorities·risks 는 억지로 개수 채우지 말 것(강한 것 위주 triage). 단\n"
    "  design_directions 는 위 규칙대로 5안을 채운다. 신호 없는 항목은 지어내지 말 것.\n"
    "- program_directions·massing_strategy·phasing 은 **AI 해석 확장층** — 1층 사실\n"
    "  (배점·강조·대지) 위에서 추론한 제안이다. 각 claim 은 **반드시 basis 로 어떤 사실에서\n"
    "  나왔는지 앵커**하라(앵커 못 달면 그 항목은 빼라). 신호가 얕으면 항목 수를 줄여라.\n"
    "  사실로 위장하지 말 것 — 이 셋은 '제안'으로 읽히게 쓴다.\n"
    "- **읽을 만한 깊이 (CRITICAL):** 각 항목은 한 줄 제목(claim/direction)에서 끝내지 말고\n"
    "  detail/narrative 로 **2~4문장 풀어써라** — 설계팀이 읽고 판단할 수 있게. 단 분량을\n"
    "  늘리는 건 'filler(미사여구·동어반복)'가 아니라 **근거 있는 추론의 깊이**다: ① 어떤\n"
    "  사실(배점·강조·대지)에서 출발하는지 ② 공간·동선·구성으로 무엇을 하는지 ③ 그래서\n"
    "  무엇을 얻고 무엇과 상충하는지. 풀어쓰되 **새 사실·새 숫자(분양가·세대수·ROI 등)는\n"
    "  여전히 도입 금지** — 깊이는 '해석의 밀도'에서 나오지 '없는 데이터'에서 나오지 않는다.\n"
    "- **새 숫자를 사실로 만들지 말 것(CRITICAL):** 분양가·ROI·미분양률·세대수·절감액 같은\n"
    "  수치를 지어내 단정하지 마라. 규모·비용 가정이 필요하면 '가정/시나리오'로 명시하거나\n"
    "  open_questions(발주처 확인)로 빼라. 인용 가능한 사실 숫자는 지침서에 실재하는 것만.\n"
    "- data_confidence: scoring_focus 가 비었거나 항목 2개 이하면 low. high severity flag\n"
    "  있으면 한 단계 ↓.\n"
    "- caveats 에는 반드시 '실제 심사 결과는 보장할 수 없으며 본 제안은 지침서 근거 기반\n"
    "  전략 가설' 취지의 문장을 한 줄 포함.\n"
    "\n"
    "[사실/제안 구분 예시 — win_themes 한 항목]\n"
    '✅ {"theme":"감염동선 분리","rationale":"배치계획이 배점 1순위(40점)이고 \'특히\n'
    '   감염동선 분리\'를 반복 요구 — 동선 해법을 전면에 세울 가치가 크다",\n'
    '   "scoring_link":"배치계획 40점(1순위)","basis":["p.20","배치계획"]}\n'
    "  사실(배점 1순위·반복 요구)은 근거 인용, 제안(전면에 세워라)은 판단으로 명시."
)


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _pattern_signals(facility_type: str) -> dict:
    """시설유형 패턴에서 제안서 참고용 신호 추출. 없거나 N=0이면 {} 반환."""
    try:
        pattern = load_pattern(facility_type)
        if not isinstance(pattern, dict):
            return {}
        win_n = pattern.get("win_count") or 0
        if win_n == 0:
            return {}
        qi  = pattern.get("qualitative_insights") or {}
        ls  = pattern.get("loser_stats") or {}
        lqi = ls.get("qualitative_insights") or {}
        lose_n = ls.get("lose_count") or 0
        return {
            "note": (
                f"동일 시설유형 과거 공모 당선 {win_n}건·낙선 {lose_n}건 집계 경향. "
                "직접 인용 금지 — 전략·제안 힌트로만 사용."
            ),
            "win_n": win_n,
            "lose_n": lose_n,
            "winner_keywords":     (pattern.get("concept_keywords") or [])[:8],
            "winner_patterns":     (qi.get("winner_patterns") or [])[:5],
            "loser_patterns":      (qi.get("loser_patterns") or [])[:5],
            "key_differentiators": (qi.get("key_differentiators") or [])[:4],
            "loser_keywords":      (ls.get("concept_keywords") or [])[:8],
        }
    except Exception:
        return {}


def _prior_insight_digest(brief_data: dict) -> dict:
    """기존 _insight(사실 triage)에서 제안의 토대로 쓸 부분만 요약 전달.

    전체를 싣지 않고 핵심 신호만 — 토큰 절감 + 제안이 사실 triage 를 '복붙'하지 않게.
    """
    ins = brief_data.get("_insight")
    if not isinstance(ins, dict):
        return {}
    return {
        "synthesis_summary": ins.get("synthesis_summary") or "",
        "key_emphases": [
            {"topic": e.get("topic"), "signal_strength": e.get("signal_strength")}
            for e in (ins.get("key_emphases") or []) if isinstance(e, dict)
        ],
        "must_not_miss": [
            m.get("item") for m in (ins.get("must_not_miss") or []) if isinstance(m, dict)
        ],
    }


def _propose_sync(brief_data: dict, facility_type: str) -> dict:
    # advisor 와 동일한 결정론 백본 신호 — 단일 소스 재사용 (드리프트 차단)
    payload = _build_advisor_payload(brief_data, facility_type)
    payload["prior_insight"] = _prior_insight_digest(brief_data)

    # 시설유형 당선·낙선 패턴 (있을 때만, 없으면 조용히 skip)
    ps = _pattern_signals(facility_type)
    if ps:
        payload["pattern_context"] = ps

    # VWorld 대지 맥락 (사전에 site-analyze 엔드포인트가 실행됐을 때만, 없으면 skip)
    sc = brief_data.get("_site_context")
    if sc and isinstance(sc, dict) and sc.get("analysis"):
        payload["site_context"] = {
            "matched_address": sc.get("matched_address", ""),
            "lat":             sc.get("lat"),
            "lng":             sc.get("lng"),
            "radius_m":        sc.get("radius_m", 500),
            "analysis":        sc["analysis"],
        }

    dynamic = "지침서 데이터 (사실 주장은 이 안의 내용만 사용):\n" + _compact(payload)
    raw = call_messages(
        model=settings.model_id_advisor,   # 제안 전용 모델(기본 Opus). 추출은 그대로 Sonnet.
        max_tokens=16000,
        temperature=0,     # Opus 4.7/4.8 은 call_messages 가 temperature 를 자동 생략 (400 회피)
        system=_PROPOSAL_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROPOSAL_INSTRUCTION, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    try:
        result = parse_json_response(raw)
    except Exception as e:
        raise ValueError(f"제안서 JSON 파싱 실패: {e}\n원문(앞 200자): {raw[:200]}")
    if not isinstance(result, dict):
        raise ValueError(f"제안서 응답이 dict 아님: {type(result).__name__}")

    # 배점은 결정론 값을 함께 실어 렌더러가 LLM 환각 없이 무게중심을 그릴 수 있게.
    result["scoring_focus"] = compute_scoring_focus(brief_data)
    result["schema_version"] = SCHEMA_VERSION
    result["model_id"] = settings.model_id_advisor
    result["facility_type"] = facility_type
    result["brief_id"] = (brief_data.get("_brief_meta") or {}).get("brief_id", "")

    # 근거 없는 수치 검산 (LLM 0, 숫자 수정 0). 비치명 — 실패해도 제안서는 유지.
    try:
        from services.proposal_number_check import check_proposal_numbers
        result["_number_flags"] = check_proposal_numbers(result, brief_data)
    except Exception as e:
        logger.warning("제안서 수치 검산 실패 (비치명): %s", e)
        result["_number_flags"] = []
    return result


async def propose_project(brief_data: dict, facility_type: str = "") -> dict:
    """지침서 기반 수주 제안서 생성 (LLM 1콜). 저장된 _brief.json 재해석, 추가 추출 없음.

    반환은 _proposal 스키마 dict (executive_summary / win_themes / design_directions(+
    scoring_play·site_rationale) / program_directions / massing_strategy / phasing /
    priorities / risks / kickoff_checklist / open_questions / scoring_focus(결정론) +
    data_confidence / caveats + 메타).

    program_directions·massing_strategy·phasing 은 시퀀스 E Phase 2 의 'AI 해석 확장층'
    — 1층 사실(배점·강조·대지) 위에서 추론한 제안, 각 항목 basis 앵커 강제. 새 숫자를
    사실로 만들지 않음(가정은 open_questions/caveats 로).
    """
    return await asyncio.to_thread(_propose_sync, brief_data, facility_type)
