"""
brief_genre.py — 지침서 장르 판별 (LLM 0, 결정론).

파이프라인 전체는 "설계공모(design competition) = 합계 100점 심사기준표 1개 +
설계축(배치·공간·기술계획 등)"을 가정한다. 그러나 실무 문서에는 두 장르가 있다:

  · competition — 설계공모. 평가축이 **설계 품질**(배치/공간/기술/경관/창의성).
  · bid         — 설계자 선정 **입찰**(적격심사/협상). 평가가 **자격·실적·가격**
                  (사업수행능력평가=참여기술자·유사용역실적·신용도 + 가격평가).
                  2층 구조(연면적별 PQ% vs 가격%)이며 배점표가 여러 표에 분산.

장르를 오인하면 다운스트림(해설·제안서·처방·검증)이 입찰의 PQ 표를 설계축으로
착각한다(대치미도: 참여기술자(50)를 '설계 강조'로 읽음). 이 모듈은 이미 추출된
brief_data 에서 **결정론 신호**로 장르를 판별해 `_brief_genre` 로 부착한다.

최강 판별자 = **평가 카테고리명 자체**(사업수행능력/참여기술자 vs 배치계획/공간계획).
보조 = 본문 텍스트 마커(적격심사·낙찰 vs 심사위원·당선작). bare "공모"/"입찰"은
양쪽에 섞여 나오므로(재건축 공모 맥락) 약신호로만 취급.
"""
from __future__ import annotations

import json

SCHEMA_VERSION = 1

# ── 마커 사전 (가중치) ────────────────────────────────────────────────────────
# 평가 카테고리명에 나타나는 축 이름 — 장르를 가장 강하게 가른다 (가중 3).
_BID_AXIS = (
    "사업수행능력", "참여기술자", "유사용역", "유사 용역", "신용도",
    "가격평가", "가격 평가", "실적세대", "실적건수", "회사실적", "경영상태",
)
_COMP_AXIS = (
    "배치계획", "배치 계획", "공간계획", "공간 계획", "기술계획", "기술 계획",
    "설계개념", "설계 개념", "경관", "창의성", "계획설계", "디자인", "동선계획",
    "조경계획", "단위세대", "특화계획",
)
# 본문 텍스트 마커 (가중 2) — 장르 고유 어휘.
_BID_TEXT = (
    "적격심사", "낙찰", "용역업자", "협상에 의한 계약", "협상에의한계약",
    "입찰참가자격", "입찰참여", "종합평점", "적격통과", "추정가격", "예정가격",
)
_COMP_TEXT = (
    "심사위원", "당선작", "출품작", "응모작", "응모자격", "작품설명",
    "설계공모", "설계 공모", "공모지침", "심사기준표", "당선자",
)

_W_AXIS = 3
_W_TEXT = 2


def _collect_texts(brief_data: dict) -> tuple[list[str], str]:
    """(평가 카테고리명 리스트, 본문 텍스트 blob) 반환."""
    be = brief_data.get("brief_evaluation")
    if isinstance(be, dict):
        be = [be]
    eval_names = [
        (c.get("name") or "")
        for pg in (be or [])
        if isinstance(pg, dict)
        for c in (pg.get("evaluation_categories") or [])
        if isinstance(c, dict)
    ]
    # 본문: admin/overview/requirements/design_guide 를 JSON 직렬화해 통째로 스캔
    parts = []
    for k in ("brief_admin", "brief_overview", "brief_project_info",
              "_requirements", "brief_design_guide", "design_guidelines_grouped"):
        v = brief_data.get(k)
        if v:
            parts.append(json.dumps(v, ensure_ascii=False))
    return eval_names, "\n".join(parts)


def _count_hits(markers, eval_names: list[str], text: str) -> list[str]:
    """마커 중 평가명 또는 본문에 등장한 것 (중복 제거, 공백 무시 매칭)."""
    hit = []
    names_joined = " ".join(eval_names).replace(" ", "")
    text_c = text.replace(" ", "")
    for m in markers:
        mc = m.replace(" ", "")
        if mc and (mc in names_joined or mc in text_c):
            hit.append(m)
    return hit


def detect_brief_genre(brief_data: dict) -> dict:
    """지침서 장르 판별. 반환 dict (schema_version 1):

    {
      schema_version, genre: "competition"|"bid"|"unknown",
      confidence: "high|medium|low",
      bid_score, competition_score,
      signals: {bid_axis, bid_text, competition_axis, competition_text}  # 히트 마커
    }

    결정론·LLM 0. 판별 불가(양쪽 약함)면 genre="unknown". 실패해도 예외 없이 unknown 반환.
    """
    try:
        eval_names, text = _collect_texts(brief_data)

        bid_axis  = _count_hits(_BID_AXIS,  eval_names, text)
        bid_text  = _count_hits(_BID_TEXT,  eval_names, text)
        comp_axis = _count_hits(_COMP_AXIS, eval_names, text)
        comp_text = _count_hits(_COMP_TEXT, eval_names, text)

        bid_score  = len(bid_axis)  * _W_AXIS + len(bid_text)  * _W_TEXT
        comp_score = len(comp_axis) * _W_AXIS + len(comp_text) * _W_TEXT

        # 판정: 절대 임계 + 상대 마진.
        top = max(bid_score, comp_score)
        margin = abs(bid_score - comp_score)
        if top < _W_AXIS:                       # 어느 쪽도 축 신호 하나 못 넘김
            genre, confidence = "unknown", "low"
        elif margin < _W_TEXT:                   # 팽팽 — 혼재/모호
            genre, confidence = ("bid" if bid_score >= comp_score else "competition"), "low"
        else:
            genre = "bid" if bid_score > comp_score else "competition"
            confidence = "high" if (top >= 6 and margin >= 4) else "medium"

        return {
            "schema_version": SCHEMA_VERSION,
            "genre": genre,
            "confidence": confidence,
            "bid_score": bid_score,
            "competition_score": comp_score,
            "signals": {
                "bid_axis": bid_axis,
                "bid_text": bid_text,
                "competition_axis": comp_axis,
                "competition_text": comp_text,
            },
        }
    except Exception:
        return {
            "schema_version": SCHEMA_VERSION,
            "genre": "unknown", "confidence": "low",
            "bid_score": 0, "competition_score": 0,
            "signals": {"bid_axis": [], "bid_text": [], "competition_axis": [], "competition_text": []},
        }


# 사람이 읽는 라벨 (exporter·프론트 공유).
GENRE_LABEL = {
    "competition": "설계공모",
    "bid": "설계자 선정 입찰",
    "unknown": "장르 미확정",
}
