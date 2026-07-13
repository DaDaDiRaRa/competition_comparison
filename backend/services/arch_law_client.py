"""arch-law-diagnose(건축법 자동진단) 연동 클라이언트 — 배치의 '법적 골격'을 되받는다.

teoilgi_client 패턴. 우리가 이미 내보내는 feasibility_export.sites[] 를 건축법 진단 앱
(POST /api/diagnose)에 보내 **정북 일조사선·가로구역 최고높이·건폐/용적 한도·심의여부**를
숫자로 되받아 placement_strategy(대지 근거 배치)의 근거로 쓴다.

모드 A — 용량(envelope) 검토: 지침서(brief)는 "허용 한도"(site_area·건폐율%·용적률%·
최고높이)만 주고 건축면적·연면적·층수 같은 설계 산출물은 없다. 그래서 허용 한도로 **최대 매스**를
역산해 진단에 넘기고(건폐율 한도=최대 건축면적, 용적률 한도=최대 연면적, 층수=height/4 추정),
되돌아온 정북 후퇴·가로구역 높이·한도를 "이 땅이 규정하는 매스 골격"으로 삼는다.
⚠ floors_above 는 brief 미제공 추정값 → 층수 의존 판정은 참고만.

경계·안전:
- 게이팅: ARCH_LAW_API_URL env 가 **명시 설정**될 때만 동작(_enabled). 기본값 없음 →
  Cloud Run(service.yaml 미설정)에서는 자동 off, 자기호출 오작동 원천 차단. .env 로 로컬 dev 만 on.
- graceful: to_request None(필수값 결측)·응답 실패·타임아웃 → 그 부지 조용히 skip, 본 파이프라인 무중단.
- ⚠ timeout 120s — 진단 1건 65~110초(국가유산청·Claude 포함). 짧으면 정상 진단이 timeout.
- Phase 3(graph 조문 원문)는 이번 범위 아님 — diagnose 숫자 골격만.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# 진단 서버 주소. 기본값 없음(명시 설정 게이트) — teoilgi 와 달리 배포 URL 미상이라 자동호출 금지.
_DEFAULT_DIAG_URL = "http://localhost:8000"

# 신뢰도 저하 신호 — source 에 이 토큰이 있으면 low_confidence (VWorld 자동조회·추정 폴백).
# '시행령'은 정상 법정값이라 제외 — 넣으면 전국 대부분이 저신뢰로 오탐(진단앱 피드백).
_LOW_CONF_TOKENS = ("미확인", "추정")


def diag_url() -> str:
    return (os.environ.get("ARCH_LAW_API_URL") or _DEFAULT_DIAG_URL).rstrip("/")


def is_enabled() -> bool:
    """ARCH_LAW_API_URL 이 명시 설정됐을 때만 진단 호출을 켠다 (자기호출·prod 오작동 방지)."""
    return bool(os.environ.get("ARCH_LAW_API_URL"))


def to_request(site: dict) -> dict | None:
    """feasibility_export.sites[i] → DiagnoseRequest (A: 용량 검토 모드).

    허용 한도(건폐율%·용적률%·최고높이)로 최대 매스를 역산해 넘긴다. 필수값(주소·대지면적·
    건폐율·용적률·높이) 하나라도 없으면 None → 그 부지 진단 skip.
    """
    site_area = site.get("site_area_sqm")
    bcr, far  = site.get("building_coverage_pct"), site.get("floor_area_ratio_pct")
    height, address = site.get("max_height_m"), site.get("address")
    if not (address and site_area and bcr and far and height):
        return None                                   # 필수값 없으면 진단 skip
    uses = site.get("building_law_uses") or []
    return {
        "address": address,
        "building_use": uses[0] if uses else (site.get("zone_use_raw") or "미상"),
        "site_area": site_area,
        "building_area": round(site_area * bcr / 100, 2),    # 건폐율 한도 = 최대 건축면적
        "floor_area_above": round(site_area * far / 100, 2),  # 용적률 한도 = 최대 연면적
        "floors_above": max(1, round(height / 4.0)),          # ⚠ 추정(층고 4m)
        "height": height,
        "zone_use_override": site.get("zone_use"),            # 표준 용도지역명 → VWorld 우회
    }


async def diagnose(payload: dict, timeout: float = 120.0) -> dict | None:
    """DiagnoseRequest → 진단 응답(dict) 또는 None(graceful).

    ⚠ 진단 65~110초 → timeout 120s 여유 필수. 5xx·타임아웃·네트워크 전부 None 으로 degrade.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{diag_url()}/api/diagnose", json=payload)
        if r.status_code != 200:
            logger.warning("건축법 진단 실패: %s %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception as e:  # noqa: BLE001 — 미배포·네트워크·타임아웃 전부 graceful
        logger.warning("건축법 진단 호출 오류 (비치명): %s", e)
        return None


def digest_diagnosis(diag: dict, site: dict | None = None) -> dict | None:
    """진단 응답 → 배치 근거용 최소 다이제스트 (null 가드 + 신뢰도 캡처).

    매스·단면을 규정하는 필드만 추림: envelope(건폐/용적 한도) · 정북 일조사선 후퇴 ·
    가로구역 최고높이 · 심의(REQUIRED) 여부. pass:null / source '미확인·추정·시행령' 은
    low_confidence 로 표시(불변식 2: degrade 신호를 신뢰도로 캡처). site 를 주면 brief 의
    건폐/용적 한도와 진단 limit_pct 를 대조해 불일치(재확인 신호)를 붙인다.
    """
    if not isinstance(diag, dict):
        return None
    results = diag.get("results")
    if not isinstance(results, dict):
        results = {}

    def _r(key: str) -> dict:
        r = results.get(key)
        return r if isinstance(r, dict) else {}

    bcr, far, hs = _r("건폐율"), _r("용적률"), _r("높이_일조")

    envelope = {
        "bcr_limit_pct": bcr.get("limit_pct"),
        "far_limit_pct": far.get("limit_pct"),
    }
    height_solar = {
        "north_setback_m":      hs.get("north_setback_m"),      # 정북 실이격
        "shadow_applies":       hs.get("shadow_applies"),
        "shadow_setback_rule":  hs.get("shadow_setback_rule"),  # 일조사선 규칙
        "shadow_min_setback_m": hs.get("shadow_min_setback_m"),
        "road_height_limit_m":  hs.get("road_height_limit_m"),  # 가로구역 최고높이 = 최고 N층
        "parcel_north_depth_m": hs.get("parcel_north_depth_m"),
    }

    # 심의 vs 법정 — REQUIRED 만 (CONDITIONAL/NONE 제외)
    reviews_required = [
        {"name": rv.get("name"), "law_ref": rv.get("law_ref"),
         "reasons": [str(x) for x in (rv.get("triggered_reasons") or [])]}
        for rv in (diag.get("applicable_reviews") or [])
        if isinstance(rv, dict) and rv.get("severity") == "REQUIRED"
    ]

    # 신뢰도 — pass:null 또는 source 에 미확인/추정/시행령 = degrade 신호
    low_conf = False
    source_notes: dict[str, str] = {}
    for k, r in results.items():
        if not isinstance(r, dict):
            continue
        src = r.get("source")
        if isinstance(src, str) and src.strip():
            source_notes[k] = src.strip()
            if any(t in src for t in _LOW_CONF_TOKENS):
                low_conf = True
        if r.get("pass") is None:
            low_conf = True

    # brief 건폐/용적 한도 vs 진단 limit_pct 대조 (다르면 brief 수치 재확인 신호)
    limit_mismatch: list[dict] = []
    if isinstance(site, dict):
        for label, brief_key, lim in (
            ("건폐율", "building_coverage_pct", envelope["bcr_limit_pct"]),
            ("용적률", "floor_area_ratio_pct", envelope["far_limit_pct"]),
        ):
            bv = site.get(brief_key)
            if isinstance(bv, (int, float)) and isinstance(lim, (int, float)) and abs(bv - lim) > 0.5:
                limit_mismatch.append({"field": label, "brief_pct": bv, "diagnose_limit_pct": lim})

    return {
        "signal": diag.get("signal"),
        "overall_score": diag.get("overall_score"),
        "envelope": envelope,
        "height_solar": height_solar,
        "reviews_required": reviews_required,
        "has_required_review": bool(reviews_required),
        "low_confidence": low_conf,
        "source_notes": source_notes,
        "limit_mismatch": limit_mismatch,
    }
