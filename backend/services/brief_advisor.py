"""
brief_advisor.py — 지침서 "종합 해설" 백본.

Unit 1 (이 파일의 현재 범위) 는 **결정론 함수만** — API 호출 없이 이미 추출된
`_brief.json` 데이터에서, 'AI 종합 해설'이 근거로 쓸 신호를 계산/추출한다.
LLM 종합(`interpret_brief`)은 Unit 2 에서 같은 파일에 추가된다.

공개 API (Unit 1):
  compute_scoring_focus(brief_data) -> list[dict]
      brief_evaluation 배점표 → 카테고리별 배점·비중·랭킹.
      null 점수·shared_with(병합셀) 시맨틱은 brief_validator._check_points_mismatch 와 동일.
  extract_emphasis_signals(brief_data) -> dict
      design_guidelines_grouped 에서 '지침서가 강조하는 것'의 결정론 후보:
        - emphasis_phrases : 강조어휘(특히/반드시/중점/우선/핵심 등)가 붙은 문장
        - category_weights : 지침서 자체 분류(category)별 항목 수 (= 분량 = 강조 신호)
      LLM 은 이 후보 위에서만 서술 → 환각 차단.

설계 원칙:
  - 이 신호들은 "중요"의 *근거 후보*일 뿐, 판단(중요하다는 결론)은 LLM/사람의 몫.
  - 외부 당락 예측 없음. 전부 지침서 본문 내부 신호 (안전한 ②).
  - "확인기 아닌 탐지기": 특정 테마를 찾으러 가지 않고, 본문이 무엇을 강조하는지 중립 집계.
"""
from __future__ import annotations

import asyncio
import json
import re

from config import settings
from services.llm_client import call_messages
from services.utils import parse_json_response, _first, _as_list
from services.reference_cases import collect_reference_context


SCHEMA_VERSION = 1   # _brief_insight 스키마 버전


# 강조어휘 — 지침서가 명시적으로 무게를 싣는 표지. 객관적(정규식) 신호.
_EMPHASIS_MARKERS = (
    "특히", "반드시", "필히", "중점", "우선", "핵심",
    "강조", "유의", "주의", "필수", "엄수",
)
_MARKER_RE = re.compile("|".join(re.escape(m) for m in _EMPHASIS_MARKERS))


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _select_eval_page(brief_data: dict) -> dict:
    """brief_evaluation 다중 페이지 중 실제 배점표 페이지 선택.

    배점(numeric points)이 가장 많은 페이지를 고른다 — 비연속 스태킹 폴백 시
    개별 추출된 여러 페이지 중 진짜 배점표를 집는다 (brief_checklist_exporter
    ._extract_sections 와 동일 로직. CLAUDE.md Critical Rule: `_first` 로 되돌리면
    비연속 케이스 누락).
    """
    pages = brief_data.get("brief_evaluation") or []
    if isinstance(pages, dict):
        pages = [pages]
    pages = [p for p in pages if isinstance(p, dict) and not p.get("_merged")]

    def _eval_pts(p: dict) -> int:
        cats = (p or {}).get("evaluation_categories") or []
        return sum(1 for c in cats if isinstance(c.get("points"), (int, float)))

    return max(pages, key=_eval_pts, default={})


def _item_text(item) -> str:
    """design_guidelines_grouped 의 항목 → 텍스트. {label, text} 또는 문자열."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text") or "").strip()
    return ""


def _iter_guideline_texts(brief_data: dict):
    """design_guidelines_grouped 의 모든 (category, section, text) 튜플 산출.

    그룹은 flat `items` 또는 중첩 `items_by_sub` 중 하나로 텍스트를 담는다 — 둘 다 순회.
    """
    groups = brief_data.get("design_guidelines_grouped")
    if not isinstance(groups, list):
        return
    for g in groups:
        if not isinstance(g, dict):
            continue
        category = (g.get("category") or "").strip() or "(미분류)"
        base_section = (g.get("section_path") or "").strip()
        for it in (g.get("items") or []):
            t = _item_text(it)
            if t:
                yield category, base_section, t
        for sub in (g.get("items_by_sub") or []):
            if not isinstance(sub, dict):
                continue
            section = (sub.get("sub_path") or base_section).strip()
            for it in (sub.get("items") or []):
                t = _item_text(it)
                if t:
                    yield category, section, t


# ── 공개 API ──────────────────────────────────────────────────────────────────

def compute_scoring_focus(brief_data: dict) -> list[dict]:
    """배점표 → 카테고리별 배점·비중·랭킹 (결정론, LLM 없음).

    Returns [{category, points, weight_pct, shared_with, sub_items_count,
              is_qualitative, rank}] — 추출 순서 유지.
      points        : 명시 배점 (int|float) 또는 None
      weight_pct    : points / 만점 × 100 (총점 우선, 없으면 numeric 합). None 가능.
      shared_with   : 병합셀 공유 카테고리 (정상, 경고 아님)
      is_qualitative: points None + shared_with 없음 → 정성평가 항목
      rank          : 명시 배점 기준 내림차순 순위 (1=최고). None 점수는 rank None.
    """
    be = _select_eval_page(brief_data)
    cats = [c for c in be.get("evaluation_categories", []) if isinstance(c, dict)]
    if not cats:
        return []

    total = be.get("total_points")
    numeric = [c["points"] for c in cats if isinstance(c.get("points"), (int, float))]
    if isinstance(total, (int, float)) and total > 0:
        denom: float | None = float(total)
    elif numeric:
        denom = float(sum(numeric))
    else:
        denom = None

    focus: list[dict] = []
    for i, c in enumerate(cats):
        pts = c.get("points")
        pts = pts if isinstance(pts, (int, float)) else None
        shared = [s for s in (c.get("shared_with") or []) if s]
        weight = round(pts / denom * 100, 1) if (pts is not None and denom) else None
        focus.append({
            "category": c.get("name") or f"항목{i + 1}",
            "points": pts,
            "weight_pct": weight,
            "shared_with": shared,
            "sub_items_count": len(c.get("sub_items") or []),
            "is_qualitative": pts is None and not shared,
            "rank": None,
        })

    ranked = sorted(
        [f for f in focus if f["points"] is not None],
        key=lambda f: f["points"], reverse=True,
    )
    for r, f in enumerate(ranked, start=1):
        f["rank"] = r

    return focus


def extract_emphasis_signals(brief_data: dict) -> dict:
    """design_guidelines_grouped 에서 '강조' 결정론 후보 추출 (LLM 없음).

    Returns {
      "emphasis_phrases": [{text, marker, category, section}],  # 강조어휘 붙은 문장
      "category_weights": [{category, item_count, sections}],   # 분류별 분량 (강조 신호)
    }
    둘 다 지침서 본문 내부 신호 — 외부 예측 없음. '중요하다'는 판단은 소비자(LLM/사람) 몫.
    """
    phrases: list[dict] = []
    seen_phrases: set[str] = set()   # 정규화 데이터가 같은 지침을 여러 그룹에 담는 중복 차단
    cat_counts: dict[str, dict] = {}

    for category, section, text in _iter_guideline_texts(brief_data):
        slot = cat_counts.setdefault(
            category, {"category": category, "item_count": 0, "sections": []}
        )
        slot["item_count"] += 1
        if section and section not in slot["sections"]:
            slot["sections"].append(section)

        m = _MARKER_RE.search(text)
        if m and text not in seen_phrases:
            seen_phrases.add(text)
            phrases.append({
                "text": text,
                "marker": m.group(0),
                "category": category,
                "section": section,
            })

    category_weights = sorted(
        cat_counts.values(), key=lambda d: d["item_count"], reverse=True,
    )
    return {
        "emphasis_phrases": phrases,
        "category_weights": category_weights,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Unit 2 — LLM 종합 해설 (interpret_brief)
#
# 결정론 백본(위)이 만든 신호 위에서 LLM 이 '종합·번역'만 수행. 외부 당락 예측 없음.
# 가드: ① 근거 한정 ② 인용 필수(페이지 추측 금지) ③ 예측 금지 ④ 중립 탐지.
# comparator 패턴(call_messages + cache_control ephemeral + parse_json_response) 재사용.
# ═══════════════════════════════════════════════════════════════════════════════

_ADVISOR_SYSTEM = (
    "당신은 건축 설계공모 지침서를 읽고 핵심을 짚어주는 분석가다.\n"
    "역할은 **이미 추출된 지침서 데이터를 종합·번역**해서, 설계팀이 이 지침서를\n"
    "빠르고 정확하게 이해하도록 돕는 것이다.\n"
    "\n"
    "당신은 \"해설가\"이지 \"전략가\"가 아니다. 무엇이 당선되는지 예측하거나, 어떻게\n"
    "하면 이긴다고 처방하지 않는다. 오직 **이 지침서가 무엇을 요구하고 무엇을\n"
    "강조하는지**를 근거와 함께 정리한다. 판단과 결정은 사람의 몫이다.\n"
    "\n"
    "절대 규칙 (위반 시 결과 폐기):\n"
    "1. [근거 한정] 제공된 지침서 데이터 안의 내용만 사용한다. 데이터에 없는\n"
    "   사실·수치·요구를 지어내지 않는다. 외부 지식(다른 공모 사례, 심사위원\n"
    "   성향, 업계 통념)을 끌어오지 않는다.\n"
    "2. [인용 필수] 모든 \"중요하다/강조된다\" 주장에 근거 위치를 단다. 데이터에\n"
    "   _page 또는 eval_page 가 있으면 (p.N), 없으면 섹션명/카테고리명/배점항목명.\n"
    "   **페이지 번호를 추측해 지어내지 않는다.**\n"
    "3. [예측 금지] \"이기려면\", \"당선 가능성\", \"유리하다\", \"차별화하려면\" 같은\n"
    "   표현 금지. \"지침서가 X를 강조한다 (근거)\"까지만 말한다.\n"
    "4. [중립 탐지] 미리 정한 테마를 찾으러 가지 않는다. 제공된 신호(배점·강조\n"
    "   문장·분량)가 실제로 가리키는 것만 보고한다. 근거가 약하면 약하다고 말하고,\n"
    "   신호가 없으면 넣지 않는다 — 빈약함 자체가 정보다.\n"
    "\n"
    "모든 출력은 한국어 평어체. 반드시 지정된 JSON 형식만 출력한다."
)


# 작업 지시 + 출력 스키마 (정적, cache_control ephemeral 대상).
# .format() 안 씀 — JSON 중괄호 충돌 회피 (comparator 와 동일 원칙). 치환 토큰 없음.
_ADVISOR_INSTRUCTION = (
    "[작업] 아래 지침서 데이터를 종합해 JSON 한 개를 생성하라.\n"
    "\n"
    "[입력 설명]\n"
    "- brief_genre: 이 지침서의 장르(결정론 판별). \"bid\"=설계자 선정 입찰(적격심사/협상)이면\n"
    "  평가축은 **설계안이 아니라 자격·실적·가격**(사업수행능력=참여기술자·유사용역실적·신용도\n"
    "  + 가격)이다. 이 경우 배치/공간계획 같은 '설계 강조'로 오해하지 말고 '어떤 자격·실적이\n"
    "  얼마나 배점되는지'로 해설하라. \"competition\"이면 설계축 그대로. \"unknown\"이면 데이터가\n"
    "  가리키는 대로.\n"
    "- bid_structure: (입찰일 때만) 2층 배점 구조 — top_layer.axes(사업수행능력% vs 가격%,\n"
    "  연면적 규모별 밴드) + pq_detail(하위 100점표). applicable.weights 가 있으면 그 값으로,\n"
    "  없으면(연면적 미확보) '연면적에 따라 사업수행능력 20~40% / 가격 60~80%로 갈린다'처럼\n"
    "  밴드로 서술하고 적용은 확인 필요라고 명시하라. 값을 지어내지 말 것.\n"
    "- scoring_focus: 배점표를 결정론으로 계산한 결과(카테고리·배점·비중·랭킹). 신뢰 가능.\n"
    "- evaluation_detail: 배점 항목별 세부(sub_items)·실격조건·총점·출처 페이지(eval_page).\n"
    "- emphasis_signals.emphasis_phrases: 강조어휘(특히/반드시/중점 등)가 붙은 본문 문장.\n"
    "- emphasis_signals.category_weights: 지침서 자체 분류별 항목 수(분량). 단,\n"
    "  \"일반사항\"·\"(미분류)\"는 분류 안 된 잡동사니 버킷이므로 테마 신호로 쓰지 말 것.\n"
    "- design_overview / sites / special_conditions / validation_flags: 보조 근거.\n"
    "- reference_cases: (있으면) 동일 시설유형 **다른 공모**의 참고자료(집계 통계 +\n"
    "  과거 당선작 컨셉 발췌 + 과거 비교분석 서술). 반드시 이렇게만 사용: reading_guide 의\n"
    "  배경 참고로만 활용 가능. key_emphases/must_not_miss/hidden_constraints/\n"
    "  scoring_focus/data_confidence 등 **이 지침서에 대한 판단·근거로는 절대 사용 금지**\n"
    "  (이 지침서 판단은 반드시 이 지침서 내부 신호만으로). basis 에도 절대 넣지 말 것.\n"
    "\n"
    "[출력 JSON — 정확히 이 키만, 다른 키 추가 금지]\n"
    "{\n"
    '  "synthesis_summary": "핵심을 2~4문장 평어 압축. 배점 무게중심과 발주 의도를 엮되 처방 금지.",\n'
    '  "key_emphases": [\n'
    '    { "topic": "지침서가 강조하는 주제",\n'
    '      "signal_strength": "strong|medium|weak",\n'
    '      "signals": ["배점 40점(배치계획)","동선계획 14항목","\'특히 감염동선 분리\'"],\n'
    '      "basis": ["배치계획","p.18"],\n'
    '      "note": "무엇을 어떻게 강조하는지 한 줄. 처방 아님." }\n'
    "  ],\n"
    '  "must_not_miss": [ {"item":"놓치면 실격/감점","basis":"p.N 또는 항목명"} ],\n'
    '  "hidden_constraints": [ {"issue":"심의로 정해지는 한계·상충·제약","basis":"...","note":"..."} ],\n'
    '  "reading_guide": ["검토 시 주의점 (본문 근거 기반)"],\n'
    '  "data_confidence": "high|medium|low",\n'
    '  "caveats": ["분석의 한계 (예: 배점표 추출 불완전)"]\n'
    "}\n"
    "\n"
    "[필드 규칙]\n"
    "- key_emphases: 다중 신호(배점+강조어휘+분량)가 겹치면 strong, 단일 신호면 medium/weak.\n"
    "  신호 없으면 항목을 만들지 말 것. 억지로 개수 채우지 말 것 (강한 것 위주 triage).\n"
    "- must_not_miss: disqualification_criteria + high severity validation flag +\n"
    "  정량으로 못박힌 하한(면적/대수) 우선.\n"
    "- data_confidence: scoring_focus 가 비었거나 항목 2개 이하면 low. high severity flag 있으면 한 단계 ↓.\n"
    "\n"
    "[예시 — key_emphases 한 항목]\n"
    '❌ 나쁨: {"topic":"동선","note":"동선에 집중하면 좋은 평가를 받을 수 있다"}\n'
    '✅ 좋음: {"topic":"동선 분리","signal_strength":"strong",\n'
    '         "signals":["배치계획 배점 1순위","동선계획 14항목","\'특히 감염동선 분리\'(p.20)"],\n'
    '         "basis":["p.20","배치계획"],"note":"감염·보안·소방 동선 분리를 반복 요구"}\n'
    "차이: 좋음은 '지침서가 무엇을 강조하는가'를 근거와 함께 말하고, 나쁨은 결과를 예측한다."
)


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _build_advisor_payload(brief_data: dict, facility_type: str) -> dict:
    """LLM 에 넘길 동적 데이터 조립 — 이미 추출된 값만, 새 추출 없음.

    배점표/강조신호는 결정론 함수 결과를 그대로 싣고, 텍스트 근거(sub_items·강조문장·
    실격조건·심의제약)를 함께 넣어 LLM 이 인용·종합할 재료를 준다. 전체 본문 덤프는
    하지 않는다(토큰 + 환각 면적 최소화) — LLM 은 받은 신호 위에서만 서술한다.
    """
    be = _select_eval_page(brief_data)
    eval_cats = [
        {
            "name": c.get("name"),
            "points": c.get("points") if isinstance(c.get("points"), (int, float)) else None,
            "shared_with": [s for s in (c.get("shared_with") or []) if s],
            "sub_items": c.get("sub_items") or [],
        }
        for c in be.get("evaluation_categories", []) if isinstance(c, dict)
    ]

    dg = _first(brief_data, "brief_design_guide")
    feas = brief_data.get("feasibility_export") or {}
    feas_sites = feas.get("sites") if isinstance(feas, dict) else None
    # sites: feasibility_export 우선 (limits_determined_by 등 심의/법정 제약 신호 보유)
    sites = feas_sites or (
        _as_list(_first(brief_data, "brief_program"), "sites")
        or _as_list(_first(brief_data, "brief_project_info"), "sites")
    )
    special = (
        brief_data.get("special_conditions")
        or _first(brief_data, "brief_project_info").get("special_conditions")
        or []
    )
    flags = [
        {"severity": f.get("severity"), "message": f.get("message"), "location": f.get("location")}
        for f in ((brief_data.get("validation") or {}).get("flags") or [])
        if isinstance(f, dict)
    ]

    payload = {
        "facility_type": facility_type,
        "brief_genre": (brief_data.get("_brief_genre") or {}).get("genre", "unknown"),
        "scoring_focus": compute_scoring_focus(brief_data),
        "evaluation_detail": {
            "total_points": be.get("total_points"),
            "eval_page": be.get("_page"),
            "categories": eval_cats,
            "disqualification_criteria": be.get("disqualification_criteria") or [],
            "evaluation_method": be.get("evaluation_method") or "",
        },
        "emphasis_signals": extract_emphasis_signals(brief_data),
        "design_overview": {
            "concept_direction": dg.get("concept_direction") or "",
            "special_guidelines": dg.get("special_guidelines") or [],
            "prohibited_items": dg.get("prohibited_items") or [],
        },
        "sites": sites or [],
        "special_conditions": special,
        "validation_flags": flags,
    }
    # 시설유형 기존 사례 참고자료 (집계 통계 + 실제 사례 발췌). brief_proposal 도 이 payload 를
    # 재사용하므로 단일 소스 — 있을 때만 추가, 없으면 조용히 skip.
    ref_ctx = collect_reference_context(facility_type)
    if ref_ctx:
        payload["reference_cases"] = ref_ctx

    # 입찰(bid) 2층 배점 구조 — 있으면 상위 밴드·적용 가중치를 그대로 실어 LLM 이
    # "사업수행능력 30% vs 가격 70%" 처럼 구체적으로 짚게 한다 (결정론 값, 환각 방지).
    bid_struct = brief_data.get("_bid_structure")
    if isinstance(bid_struct, dict):
        payload["bid_structure"] = bid_struct
    return payload


def _interpret_sync(brief_data: dict, facility_type: str) -> dict:
    payload = _build_advisor_payload(brief_data, facility_type)
    dynamic = "지침서 데이터 (이 안의 내용만 사용):\n" + _compact(payload)
    raw = call_messages(
        model=settings.model_id_advisor,   # 해설 전용 모델(기본 Opus). 추출은 그대로 Sonnet.
        max_tokens=24000,  # 긴 한국어 출력 + Opus thinking 생략 시 본문 추론 + 잘림 여유(16k 초과 방지)
        temperature=0,     # Opus 4.7/4.8 은 call_messages 가 temperature 를 자동 생략 (400 회피)
        system=_ADVISOR_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _ADVISOR_INSTRUCTION, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic, "cache_control": {"type": "ephemeral"}},
            ],
        }],
    )
    try:
        result = parse_json_response(raw)
    except Exception as e:
        raise ValueError(f"종합 해설 JSON 파싱 실패: {e}\n원문(앞 200자): {raw[:200]}")
    if not isinstance(result, dict):
        raise ValueError(f"종합 해설 응답이 dict 아님: {type(result).__name__}")

    # 결정론 값으로 덮어씀 — LLM 이 배점 숫자/랭킹을 바꾸지 못하게 (환각 차단).
    result["scoring_focus"] = payload["scoring_focus"]
    result["schema_version"] = SCHEMA_VERSION
    result["model_id"] = settings.model_id_advisor
    result["facility_type"] = facility_type
    # 렌더러가 재조회 없이 "참고 사례" 섹션을 그릴 수 있게 원본 보존 (없으면 {} — graceful skip)
    result["_reference_cases"] = payload.get("reference_cases", {})
    return result


async def interpret_brief(brief_data: dict, facility_type: str = "") -> dict:
    """지침서 종합 해설 (LLM 1콜). 저장된 _brief.json 데이터를 재해석, 추가 추출 없음.

    반환은 _brief_insight 스키마 dict (synthesis_summary / key_emphases / must_not_miss /
    hidden_constraints / reading_guide / scoring_focus / data_confidence / caveats + 메타).
    scoring_focus 는 결정론 값으로 강제 — LLM 환각 차단.
    """
    return await asyncio.to_thread(_interpret_sync, brief_data, facility_type)
