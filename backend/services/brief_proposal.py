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
    "- brief_genre: 이 지침서의 장르(결정론 판별). \"bid\"=설계자 선정 입찰이면 수주는 **설계\n"
    "  컨셉이 아니라 자격·실적·가격 경쟁력**으로 갈린다 — design_directions(설계 5안)를 억지로\n"
    "  펼치지 말고, win_themes·priorities·kickoff 를 '유사용역 실적 확보·참여기술자 구성·가격\n"
    "  전략·적격 통과'로 재편하라(배점이 실제로 그것에 쏠려 있으므로). \"competition\"이면 설계안\n"
    "  전략 그대로. \"unknown\"이면 배점이 가리키는 대로.\n"
    "- scoring_focus: 배점표를 결정론으로 계산한 결과(카테고리·배점·비중·랭킹). 신뢰 가능.\n"
    "- evaluation_detail: 배점 항목별 세부(sub_items)·실격조건·총점·출처 페이지(eval_page).\n"
    "- emphasis_signals: 강조어휘 문장 + 지침서 자체 분류별 분량(강조 신호). 단,\n"
    "  \"일반사항\"·\"(미분류)\"는 잡동사니 버킷이므로 테마 신호로 쓰지 말 것.\n"
    "- design_overview / sites / special_conditions / validation_flags: 보조 근거.\n"
    "- prior_insight: (있으면) 앞서 생성된 사실 triage 해설 — 제안의 토대로 삼되 그대로\n"
    "  복붙하지 말고 '그래서 어떻게 할지'로 발전시킨다.\n"
    "- placement_requirements: (있으면) 지침서가 **명시한 위치·층 요구 문장**들. placement_strategy\n"
    "  에서 이 요구는 사실·필수 제약이니 반드시 그대로 반영(required=true)하고 override 하지 마라.\n"
    "- reference_cases: (있으면) 동일 시설유형 **다른 공모**의 참고자료 — 세 서브키:\n"
    "  · pattern_summary: 당선·낙선 집계 통계(키워드·정성패턴). 경향 힌트로만.\n"
    "  · case_excerpts: 과거 당선작의 실제 컨셉 서술(main_strategy 등).\n"
    "  · concept_comparison_excerpts: 과거 비교분석의 축별 컨셉 비교 서술.\n"
    "  규칙: (a) 전략·제안(win_themes/design_directions 등)을 구체화하는 아이디어 영감·경향\n"
    "  힌트로만 활용. (b) 이 공모의 사실 주장(지침서가 요구·배점하는 것)으로 인용 절대 금지 —\n"
    "  다른 공모·다른 지침서의 자료임. 각 항목의 basis 에는 절대 넣지 말 것(이 지침서 basis 는\n"
    "  반드시 이 지침서 내부 근거만). (c) win_n ≤ 2 또는 발췌가 1~2건뿐이면 신호가 약하니\n"
    "  단정 말고 '경향이 있다' 수준으로. (d) 참고자료와 이 지침서 요구가 충돌하면 지침서가 우선.\n"
    "- site_context: (있으면) VWorld 위성·지적도 이미지를 Claude vision으로 판독한 실제 대지 맥락.\n"
    "  analysis 하위 키: orientation(방위·형상) / road_access(접도) / surrounding_uses(주변용도) /\n"
    "  natural_assets(자연자산) / special_context(특이사항) / overall_summary(대지요약).\n"
    "  규칙: (a) 대지 맥락을 설계 방향에 연결할 때 반드시 이 데이터를 우선 참고.\n"
    "  (b) design_directions 5안에 대지 형상·접도·조망 조건을 직접 반영 (이 부지라서 가능한 안).\n"
    "  (c) 불확실(confidence=low)이면 '위성 분석 기준, 현장 확인 필요' 단서를 붙여라.\n"
    "  site_context.measured (있으면): 터읽기 형제앱의 **실측** 대지 맥락 — 하위 키:\n"
    "    region(기준 지역) / key_facts(인구통계: 각 index=전국100 지수·index_band 상회|비슷|하회·proximity 근접도·source 출처) /\n"
    "    design_drivers(★지배 설계 드라이버 2~3개: name·response(설계 검토신호)·strength·evidence(근거·근접도)) /\n"
    "    cross_implications(도메인 횡단 참고 시사점) / hazards(홍수·산사태 영향범위·폭염 이력) / coverage.\n"
    "  measured 규칙: (1) **정량·사실은 measured 를 우선**(출처 있는 실측) — vision(analysis)은 형상·접도·조망 등 시각 판독 보완용.\n"
    "    (2) measured.design_drivers 를 design_directions·site_rationale 에 직접 연결하라 (이 대지가 설계에 요구하는 것).\n"
    "    (3) basis 에 measured.key_facts.<항목> / measured.design_drivers.<이름> / measured.hazards 를 근거로 표기 가능.\n"
    "    (4) measured 수치는 인용 OK(실측·출처 있음), 단 measured 에 **없는** 새 숫자는 여전히 금지. proximity 가 '시군구'면 '구 평균(대지 고유값 아님)'임을 밝혀라.\n"
    "  site_context.law_diagnosis (있으면): 건축법 자동진단(arch-law-diagnose)이 되돌린 **이 대지의\n"
    "    법적 매스 골격** — 부지별 배열, 각 항목 하위 키:\n"
    "    envelope(bcr_limit_pct 건폐율 한도·far_limit_pct 용적률 한도) /\n"
    "    height_solar(shadow_applies 정북일조 적용여부·shadow_min_setback_m 정북 필요이격·shadow_setback_rule 규칙·\n"
    "      north_setback_m 정북 실이격(용량모드는 실형상 없어 대개 null)·road_height_limit_m 가로구역 최고높이·parcel_north_depth_m) /\n"
    "    reviews_required(심의 REQUIRED 항목) / has_required_review / low_confidence / limit_mismatch(brief 한도 vs 진단 한도 불일치).\n"
    "  law_diagnosis 규칙: (1) **정북 일조·가로구역 최고높이·용적/건폐 한도는 brief 에 없던 법적 사실**이니\n"
    "    massing_strategy·placement_strategy 의 매스·층대·방위 근거로 **직접** 써라. 정북 신호는 순서대로:\n"
    "    north_setback_m(실이격) 있으면 그걸, 없으면 shadow_min_setback_m(필요이격)·shadow_applies=true 를 근거로\n"
    "    '북측 저층·상부 후퇴'를 유도하라(용량모드라 north_setback_m 은 대개 null — shadow_* 가 실신호). road_height_limit_m\n"
    "    있으면 최고 층대 상한. basis 에 'law:정북일조 필요이격 65m' / 'law:가로구역 50m' 처럼 표기 가능(진단값이면 인용 OK).\n"
    "    (2) has_required_review=true 면 그 심의를 risks 로 노출하고\n"
    "    한도를 법정으로 단정하지 마라. (3) **low_confidence=true 거나 값이 null 이면 단정 말고 '한도 안에서'\n"
    "    수준까지만** 쓰고 confidence 를 낮춰라(진단이 VWorld 자동조회·추정으로 채운 값). (4) limit_mismatch 가\n"
    "    있으면 open_questions/risks 에 'brief 건폐/용적 수치 재확인' 을 넣어라. (5) 진단에 **없는** 새 숫자(정밀\n"
    "    일조사선 각도·층수 확정 등) 발명 금지 — floors_above 는 애초에 추정 입력이라 층수 판정은 참고만.\n"
    "  site_context.sites (다부지, 있으면): **부지별** vision analysis·measured 배열(site_id·address).\n"
    "    다부지면 placement 의 각 zone 은 그 zone.site 부지에 해당하는 sites[] 항목의 향·접도·조망·\n"
    "    measured 를 근거로 써라 — 대표(첫 부지) analysis 로 **다른 부지의 방위·조망을 판단하지 마라**\n"
    "    (부지마다 접도·향이 다름). sites 없으면(단일부지) 상위 analysis/measured 사용.\n"
    "\n"
    "[출력 JSON — 정확히 이 키만, 다른 키 추가 금지]\n"
    "{\n"
    '  "executive_summary": "첫 문장은 \'발주처가 명시 요구 너머로 진짜 원하는 것\'을 배점·강조 분포로 읽어 한 줄로 박아라(예: 배점이 시민개방에 쏠리면 진짜 주제는 사무소가 아니라 열린 청사). 이어서 무게중심과 권장 전략 방향을 2~4문장. 제안형.",\n'
    '  "concept_hook": {\n'
    '    "keyword": "이 프로젝트 가치를 한 단어(또는 짧은 합성어)로 압축한 파르티 — 제안·시안. 배점 무게중심·win_themes·대지에서 도출(예: TRANSIT, WEAVE, 열린마당). 억지 조어·근거 없는 슬로건 금지, 못 만들면 concept_hook 전체 생략.",\n'
    '    "tagline": "keyword 를 푸는 3축 슬로건 한 줄 — axes 의 term 을 이어붙인 것 (예: \'되살림 · 잇기 · 지속\').",\n'
    '    "axes": [\n'
    '      { "term": "축 이름(한 단어, 예: 되살림)", "ko": "이 축이 이 지침서에서 뜻하는 것 한 줄", "en": "영문 병기(선택, 예: Urban Regeneration)",\n'
    '        "basis": ["이 축이 나온 근거 — 배점 항목명/강조/대지(site_context.키)/p.N. 최소 1개 필수"] }\n'
    '    ] },\n'
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
    '  "placement_strategy": {\n'
    '    "synthesis": "여러 근거(배점 × 대지 × 법적 envelope × 프로그램 성격)를 엮은 배치 논지 2~3문장. 뻔한 전략어가 아니라 \'이 땅의 이 조건들이 겹쳐서 이렇게 풀린다\'로.",\n'
    '    "zones": [\n'
    '      { "site": "부지N — 이 존이 속한 부지(sites/law_diagnosis 의 site_id). 단일 부지면 생략/빈값.",\n'
    '        "program": "프로그램/기능 (예: 시민개방 저층부·업무동·보건소·구의회·코어)",\n'
    '        "plan": "N|S|E|W|NE|NW|SE|SW|C 중 하나 — 평면상 대략 위치(대지 방위·접도 기준). 다이어그램용 enum.",\n'
    '        "level": "지하|저층|중층|상층 중 하나 — 단면상 층대. 정확한 층수 아님(원리).",\n'
    '        "required": "true|false — 지침서가 이 프로그램의 위치/층을 **명시적으로 요구**했으면 true(사실·필수), AI 가 추론한 배치면 false(제안).",\n'
    '        "why": "왜 여기인가 — 대지사실·법·프로그램·배점이 교차하는 근거 1~2문장",\n'
    '        "draws_on": ["대지:남측 20m도로", "법:정북일조/용적460%", "프로그램:감염동선", "배점:배치40"],\n'
    '        "basis": ["site_context.road_access", "배치계획", "p.20"] }\n'
    "    ],\n"
    '    "section_note": "단면 원리 한 줄 (예: 저층 시민개방 · 중상층 업무 · 코어 북측 · 지하 부지연계)",\n'
    '    "alternatives": [\n'
    '      { "label": "A|B|C — 짧은 이름",\n'
    '        "based_on": "이 대안이 구현하는 design_directions 중 한 direction (그 설계안의 공간판)",\n'
    '        "premise": "이 조닝을 가르는 전제 한 줄 (예: 조망 우선 / 가로 활성 / 효율 집약) — 왜 이렇게 다르게 배치하나",\n'
    '        "zones": [ { "program": "...", "plan": "N|S|E|W|NE|NW|SE|SW|C", "level": "지하|저층|중층|상층", "required": true } ] }\n'
    "    ]\n"
    "  },\n"
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
    "- concept_hook (표지 파르티 — 제안 시안): keyword 는 한 단어 압축, axes 는 **정확히 3축**\n"
    "  으로 이 지침서의 배점 무게중심(scoring_focus 상위)·win_themes·대지 조건에서 도출하라. 각\n"
    "  축은 **반드시 basis 로 어떤 사실에서 나왔는지 앵커**(못 달면 그 축을 빼고, 3축 못 채우면\n"
    "  concept_hook 전체를 생략). 아무 프로젝트에나 붙는 뻔한 슬로건(예: '혁신·소통·미래')은\n"
    "  금지 — 이 지침서 고유의 배점·대지에서만 나온 것이어야 한다. 팀이 갈아끼울 출발점 시안이지\n"
    "  확정 컨셉이 아니다(사실 아님, 근거 위 추론).\n"
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
    "- program_directions·massing_strategy·phasing 은 **해석 확장층** — 1층 사실\n"
    "  (배점·강조·대지) 위에서 추론한 제안이다. 각 claim 은 **반드시 basis 로 어떤 사실에서\n"
    "  나왔는지 앵커**하라(앵커 못 달면 그 항목은 빼라). 신호가 얕으면 항목 수를 줄여라.\n"
    "  사실로 위장하지 말 것 — 이 셋은 '제안'으로 읽히게 쓴다.\n"
    "- **placement_strategy (CRITICAL — 뻔함 탈출 엔진):** 이 필드가 '동선 분리하라' 같은\n"
    "  뻔한 전략어를 **구체적·대지 특정 배치**로 바꾸는 곳이다. 핵심 규칙:\n"
    "  ① **교차 합성 강제** — 각 zone.draws_on 은 **서로 다른 소스 유형 2개 이상**을 엮어야\n"
    "     한다(대지·법·프로그램·배점 중 2+). 한 소스만으로 나온 배치(=배점만 보고 '분리')는\n"
    "     뻔하니 넣지 마라. 여러 사실이 겹치는 지점에서 나온 배치만 가치 있다.\n"
    "  ② **법적 envelope 활용** — sites 의 zone_use(용도지역)·floor_area_ratio_pct·\n"
    "     building_coverage_pct·max_height·limits_determined_by 를 매스·층대 근거로 써라\n"
    "     (예: 용도지역/높이한도 안에서 상층 업무, 정북 방향이면 북측 후퇴). **site_context.law_diagnosis\n"
    "     가 있으면 그 진단 실측값(north_setback_m 정북 후퇴·road_height_limit_m 가로구역 최고높이·\n"
    "     envelope 한도)을 우선 근거로 draws_on 에 'law:…' 로 앵커하라** — 이게 brief 에 없던 골격이다.\n"
    "     단 정밀 일조사선 각도는 없으니 '한도/후퇴 안에서' 수준까지, low_confidence·null 이거나\n"
    "     limits_determined_by=심의/has_required_review=true 면 그 수치를 법정 한계로 단정 말 것.\n"
    "  ③ **대지 사실 우선** — plan(방위) 은 site_context(향·접도·주변·조망) 근거로 정하라.\n"
    "     site_context 없으면 배점·프로그램·envelope 로만 정하고 confidence 를 낮춰라.\n"
    "  ④ plan 은 8방위+C enum, level 은 지하/저층/중층/상층 enum(정확한 층수 발명 금지).\n"
    "  ⑤ **명시 요구 절대 준수 (CRITICAL) — 지침서가 특정 프로그램의 위치/층을 명시하면\n"
    "     (예: '보건소 1층 필수', '어린이집 저층 옥외 접함', '민원실 주출입 인접') 그건 사실이자\n"
    "     필수 제약이다. 반드시 그대로 반영하고 required=true + basis 에 그 요구 위치를 앵커하라.\n"
    "     추론으로 그 위치를 덮거나 무시하지 마라.** 지침서가 위치를 안 정한 것만 우리가\n"
    "     추론(required=false)해 배치한다. 명시 요구와 추론이 충돌하면 명시 요구가 이긴다.\n"
    "  ⑥ synthesis 는 '이 땅의 이 조건들이 겹쳐서 이렇게'로 — 일반론 금지. zones 5~8개 권장.\n"
    "  ⑦ **다부지면 각 zone 에 site(부지N) 필수** — sites/law_diagnosis 에 부지가 2개 이상이면\n"
    "     모든 zone 에 소속 부지를 site 로 표기하라(방위 N/S/E/W 가 부지마다 다르므로 섞이면 안 됨).\n"
    "     각 부지의 plan(방위)은 그 부지 고유의 접도·조망·형상 기준으로 정하라. 단일 부지면 site 생략.\n"
    "  ⑧ **alternatives (조닝 ALT — 최대 3안):** 위 zones(권장안)와 별개로, design_directions\n"
    "     상위 2~3안을 **공간 배치로 표현한 대안**을 준다. (a) 각 대안은 based_on 으로\n"
    "     design_directions 의 한 direction 에 연결(그 전략의 공간판). (b) **required=true(지침서\n"
    "     명시 위치)인 존은 모든 대안에서 위치·층이 동일**해야 한다 — 사실은 변주 대상이 아니다.\n"
    "     대안 간 차이는 required=false(추론) 배치에서만 나온다. (c) 대안 zones 는 compact\n"
    "     (program/plan/level/required 만; why/draws_on/basis 는 권장안에만). (d) 전제(premise)가\n"
    "     실제로 갈리게 — 무엇을 상층에 올리고 무엇을 저층 개방하느냐가 달라지게. 신호 얕으면 2안,\n"
    "     더 얕으면 alternatives 를 빈 배열로 두라(억지 변주 금지).\n"
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


def _measured_digest(brief) -> dict | None:
    """터읽기 board_brief → 프롬프트용 압축 다이제스트 (실측 사실·설계 드라이버만).

    synthesize=false 로 받았으므로 ②AI판단은 애초에 없음(경계). 원시 seed·notes 도 제외해 경량화.
    """
    if not isinstance(brief, dict):
        return None
    drivers = [
        {"rank": d.get("rank"), "name": d.get("name"), "response": d.get("response"),
         "strength": d.get("strength"),
         "evidence": [{"key": e.get("key"), "detail": e.get("detail"), "proximity": e.get("proximity")}
                      for e in (d.get("evidence") or [])]}
        for d in (brief.get("design_drivers") or [])
    ]
    key_facts = [
        {"item": f.get("item"), "value": f.get("value"), "unit": f.get("unit"),
         "national_avg": f.get("national_avg"), "index": f.get("index"),
         "index_band": f.get("index_band"), "proximity": f.get("proximity"),
         "source": f.get("source"), "year": f.get("year")}
        for f in (brief.get("key_facts") or [])
    ]
    return {
        "source": "터읽기(arch-site-context) /board — 실측 board_brief",
        "region": brief.get("region"),
        "use_type": brief.get("use_type"),
        "radius_m": brief.get("radius"),
        "coverage": brief.get("coverage"),
        "design_drivers": drivers,
        "cross_implications": [
            {"name": c.get("name"), "text": c.get("text"), "domains": c.get("domains")}
            for c in (brief.get("cross_implications") or [])
        ],
        "key_facts": key_facts,
        "hazards": brief.get("hazards"),
        "land_price": brief.get("land_price"),
        "building": brief.get("building"),
        "base_date": brief.get("base_date"),
    }


_PLACEMENT_KEYS = (
    "층", "저층", "중층", "상층", "지하", "지상", "옥상", "배치", "위치", "인접",
    "접함", "면한", "면하", "주출입", "진출입", "진입", "별동", "독립", "동선 분리",
    "조닝", "남측", "북측", "동측", "서측", "저층부", "상층부", "1층", "2층",
)


def _placement_req_signals(brief_data: dict) -> list[str]:
    """지침서에서 프로그램의 위치·층을 명시한 문장 수집 (placement 준수용).

    design_guidelines_grouped 항목 + _requirements 서술 중 위치/층 키워드 포함 문장만.
    LLM 이 이 요구를 override 하지 않고 required=true 로 반영하게 근거를 준다. dedup·상한.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(t: str):
        t = (t or "").strip()
        if t and len(t) >= 6 and t not in seen and any(k in t for k in _PLACEMENT_KEYS):
            seen.add(t)
            out.append(t[:180])

    for g in (brief_data.get("design_guidelines_grouped") or []):
        if not isinstance(g, dict):
            continue
        for it in (g.get("items") or []):
            _add(it if isinstance(it, str) else (it.get("text") if isinstance(it, dict) else ""))
        for sub in (g.get("items_by_sub") or []):
            if isinstance(sub, dict):
                for it in (sub.get("items") or []):
                    _add(it if isinstance(it, str) else (it.get("text") if isinstance(it, dict) else ""))
    req = brief_data.get("_requirements") or {}
    for r in (req.get("requirements") or []):
        if isinstance(r, dict):
            _add(str(r.get("description") or ""))
    for r in (req.get("special_requirements") or []):
        _add(r if isinstance(r, str) else str(r))
    return out[:14]


def _lock_placement_alternatives(result: dict) -> None:
    """조닝 ALT 정직성 가드 (LLM 0 · 숫자/텍스트 발명 0).

    권장안(placement_strategy.zones)에서 지침서 명시(required=true)인 존의 위치(plan·level)를
    **모든 대안에 동일 고정** — 사실은 대안마다 달라지면 안 된다. 대안에서 빠진 명시 존은 canonical
    로 채우고, malformed 대안은 제거, 최대 3안. alternatives 없거나 비면 no-op(graceful).
    """
    ps = result.get("placement_strategy")
    if not isinstance(ps, dict):
        return
    alts = ps.get("alternatives")
    if not isinstance(alts, list) or not alts:
        return

    def _req(z):
        return z.get("required") in (True, "true", "True", 1)

    canon: dict[str, tuple] = {}   # program → (plan, level)
    order: list[str] = []
    for z in (ps.get("zones") or []):
        if isinstance(z, dict) and _req(z):
            key = (z.get("program") or "").strip()
            if key and key not in canon:
                canon[key] = (z.get("plan"), z.get("level"))
                order.append(key)

    cleaned = []
    for alt in alts:
        if not isinstance(alt, dict):
            continue
        zs = [z for z in (alt.get("zones") or [])
              if isinstance(z, dict) and (z.get("program") or "").strip()]
        if not zs:
            continue
        present = set()
        for z in zs:
            key = (z.get("program") or "").strip()
            if key in canon:                       # 명시 존 → canonical 위치로 덮어씀(사실 락)
                z["plan"], z["level"] = canon[key]
                z["required"] = True
                present.add(key)
        for key in order:                          # 빠진 명시 존은 canonical 로 보강
            if key not in present:
                p, l = canon[key]
                zs.append({"program": key, "plan": p, "level": l, "required": True})
        alt["zones"] = zs
        cleaned.append(alt)
        if len(cleaned) >= 3:
            break
    ps["alternatives"] = cleaned


def _propose_sync(brief_data: dict, facility_type: str) -> dict:
    # advisor 와 동일한 결정론 백본 신호 — 단일 소스 재사용 (드리프트 차단). reference_cases
    # (시설유형 기존 사례 참고자료) 도 _build_advisor_payload 가 이미 채워서 넘겨준다.
    payload = _build_advisor_payload(brief_data, facility_type)
    payload["prior_insight"] = _prior_insight_digest(brief_data)
    # 명시 위치·층 요구 — placement_strategy 가 override 없이 준수하도록 (required=true 근거).
    _preq = _placement_req_signals(brief_data)
    if _preq:
        payload["placement_requirements"] = _preq
    ref_ctx = payload.get("reference_cases", {})

    # 대지 맥락 — vision(VWorld 위성·지적도 판독) + measured(터읽기 실측 board_brief) +
    # law_diagnosis(건축법 진단 골격). 셋 중 하나만 있어도 실음.
    sc = brief_data.get("_site_context")
    if sc and isinstance(sc, dict) and (sc.get("analysis") or sc.get("measured")
                                        or sc.get("law_diagnosis") or sc.get("sites")):
        site_ctx = {
            "matched_address": sc.get("matched_address", ""),
            "lat":             sc.get("lat"),
            "lng":             sc.get("lng"),
            "radius_m":        sc.get("radius_m", 500),
        }
        if sc.get("analysis"):
            site_ctx["analysis"] = sc["analysis"]
        measured = _measured_digest(sc.get("measured"))
        if measured:
            site_ctx["measured"] = measured
        # 건축법 진단 골격(정북 일조사선·가로구역 높이·건폐/용적 한도·심의) — placement 법근거.
        law = [d for d in (sc.get("law_diagnosis") or []) if isinstance(d, dict)]
        if law:
            site_ctx["law_diagnosis"] = law
        # 다부지: 부지별 vision/measured — 대표(첫 부지) analysis 로 다른 부지 판단 금지.
        per_site = [x for x in (sc.get("sites") or []) if isinstance(x, dict)]
        if len(per_site) > 1:
            site_ctx["sites"] = [
                {"site_id": x.get("site_id"), "address": x.get("address"),
                 "analysis": x.get("analysis"), "measured": _measured_digest(x.get("measured"))}
                for x in per_site
            ]
        payload["site_context"] = site_ctx

    dynamic = "지침서 데이터 (사실 주장은 이 안의 내용만 사용):\n" + _compact(payload)
    raw = call_messages(
        model=settings.model_id_advisor,   # 제안 전용 모델(기본 Opus). 추출은 그대로 Sonnet.
        max_tokens=40000,   # 대형 brief(5안+placement+alternatives 3안+program/massing/phasing) 잘림 방지
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
    # 렌더러가 재조회 없이 "참고 사례" 섹션을 그릴 수 있게 원본 보존 (없으면 {} — graceful skip)
    result["_reference_cases"] = ref_ctx

    # 조닝 ALT 사실-락 (LLM 0) — 지침서 명시 배치는 모든 대안에 동일 고정. 비치명.
    try:
        _lock_placement_alternatives(result)
    except Exception as e:
        logger.warning("조닝 ALT 사실-락 실패 (비치명): %s", e)

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

    반환은 _proposal 스키마 dict (executive_summary / concept_hook(표지 파르티 — keyword+
    3축 tagline, 각 축 basis 앵커, 근거 없으면 LLM 이 생략) / win_themes / design_directions(+
    scoring_play·site_rationale) / program_directions / massing_strategy / phasing /
    priorities / risks / kickoff_checklist / open_questions / scoring_focus(결정론) +
    data_confidence / caveats + 메타).

    program_directions·massing_strategy·phasing 은 시퀀스 E Phase 2 의 'AI 해석 확장층'
    — 1층 사실(배점·강조·대지) 위에서 추론한 제안, 각 항목 basis 앵커 강제. 새 숫자를
    사실로 만들지 않음(가정은 open_questions/caveats 로).
    """
    return await asyncio.to_thread(_propose_sync, brief_data, facility_type)
