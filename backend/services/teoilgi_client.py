"""터읽기(arch-site-context) 연동 클라이언트 — 수주 제안서 대지분석을 '실측'으로.

형제앱 터읽기의 `POST /board {brief:true}` 를 호출해 그 대지의 **실측 인문·생활맥락**
(전국=100 인구지수·근접도, 수급진단, 재해위험, ★지배 설계 드라이버)을 받아온다.
기존 VWorld vision 판독(형상·조망 등 시각 추론)을 **대체하지 않고 보강** — 정량·사실은 실측을
우선, vision 은 시각 판독 보완. graceful: 실패/미배포 시 None → 제안서는 vision 만으로 진행.

계약: board_brief/1.0 (터읽기 INTEGRATION.md §4). synthesize=false 로 호출 →
터읽기 ②AI판단(의견)은 받지 않는다(이중 AI 의견·출처 흐림 방지, 경계). 우리는 사실+드라이버까지만.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# 터읽기 /board 주소 (배포 URL). 로컬 개발은 TEOILGI_BOARD_URL=http://127.0.0.1:8000 로 override.
_DEFAULT_BOARD_URL = "https://arch-site-context-30350777436.asia-northeast3.run.app"

# competition FACILITY_TYPES → 터읽기 matrix use_type(주거·상업·의료만 존재, 그 외 주거 기본).
FACILITY_TO_USE_TYPE = {
    "residential": "주거", "public": "주거", "education": "주거", "masterplan": "주거",
    "transport": "주거", "industrial": "주거", "mixed_use": "주거",
    "reconstruction": "주거", "alternative": "주거",
    "commercial": "상업", "office": "상업", "hospitality": "상업", "cultural": "상업",
    "medical": "의료",
}


def board_url() -> str:
    return os.environ.get("TEOILGI_BOARD_URL", _DEFAULT_BOARD_URL).rstrip("/")


def use_type_for(facility_type: str) -> str:
    return FACILITY_TO_USE_TYPE.get(facility_type, "주거")


async def fetch_board_context(
    address: str, use_type: str = "주거", radius: int = 1000, timeout: float = 30.0,
) -> dict | None:
    """주소 → 터읽기 board_brief(실측 대지 맥락) 또는 None(graceful).

    synthesize=false·brief=true — 사실·수급·재해·설계 드라이버만(터읽기 ②AI판단 제외).
    """
    body = {
        "address": address, "use_type": use_type, "radius": radius,
        "resolution": "시군구", "synthesize": False, "brief": True,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{board_url()}/board", json=body)
        if r.status_code != 200:
            logger.warning("터읽기 /board 실패: %s %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        if not isinstance(data, dict) or data.get("error"):
            logger.warning("터읽기 /board 응답 이상: %s", str(data)[:200])
            return None
        return data
    except Exception as e:  # noqa: BLE001 — 형제앱 미배포·네트워크·타임아웃 전부 graceful
        logger.warning("터읽기 /board 호출 오류 (비치명): %s", e)
        return None
