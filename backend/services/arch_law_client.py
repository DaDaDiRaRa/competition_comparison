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
- 기본 ON: teoilgi 패턴 — 공개 배포된 진단 엔진(_DEFAULT_DIAG_URL)을 기본값으로 두고 항상 시도.
  배포본·로컬 모두 별도 설정 없이 동작. 로컬 진단 엔진을 쓰려면 ARCH_LAW_API_URL 로 override.
  끄려면 ARCH_LAW_DISABLE=1 (오프라인·비용 절감). 기본값이 공개 URL 이라 localhost 자기호출 없음.
- graceful: to_request None(필수값 결측)·응답 실패·타임아웃 → 그 부지 조용히 skip, 본 파이프라인 무중단.
- ⚠ timeout 120s — 진단 1건 65~110초(국가유산청·Claude 포함). 짧으면 정상 진단이 timeout.
- Phase 3(graph 조문 원문)는 이번 범위 아님 — diagnose 숫자 골격만.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 진단 서버 주소 기본값 = 공개 배포된 arch-law-diagnose (형제앱, teoilgi 와 동일 패턴).
# 로컬 진단 엔진을 쓰려면 ARCH_LAW_API_URL 로 override (예: http://localhost:8010).
_DEFAULT_DIAG_URL = "https://arch-law-diagnose-30350777436.asia-northeast3.run.app"

# arch-law-graph (Phase 3 조문 원문). GRAPH_API_URL 로 override. graph 죽어도 진단 골격은 유효.
_DEFAULT_GRAPH_URL = "https://arch-law-graph-30350777436.asia-northeast3.run.app"

# 신뢰도 저하 신호 — source 에 이 토큰이 있으면 low_confidence (VWorld 자동조회·추정 폴백).
# '시행령'은 정상 법정값이라 제외 — 넣으면 전국 대부분이 저신뢰로 오탐(진단앱 피드백).
_LOW_CONF_TOKENS = ("미확인", "추정")


def diag_url() -> str:
    return (os.environ.get("ARCH_LAW_API_URL") or _DEFAULT_DIAG_URL).rstrip("/")


def is_enabled() -> bool:
    """기본 ON — 공개 진단 엔진을 항상 시도. ARCH_LAW_DISABLE=1 이면 끔(오프라인·비용 절감).

    graceful 이므로 엔진이 없어도 무해(조용히 skip). 자기호출 문제는 기본값이 공개 URL 이라 없음.
    """
    return os.environ.get("ARCH_LAW_DISABLE", "").strip().lower() not in ("1", "true", "yes")


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


def graph_url() -> str:
    return (os.environ.get("GRAPH_API_URL") or _DEFAULT_GRAPH_URL).rstrip("/")


def effective_label(tx: dict | None) -> str:
    """조문 원문 → 시행일 표기. 값이 없으면 '' (graph `doc/API.md` §ef_yd 규칙 그대로).

    두 필드는 **의미가 다르므로 섞지 않는다**:
      · `ef_yd`     = 그 **조문**이 시행된 날. 중앙법령 조문에만 값이 있다.
      · `law_ef_yd` = 그 조문이 속한 **법규 판본** 전체가 시행된 날. 법제처가 자치법규·
                      행정규칙엔 조문시행일자를 안 주므로(조례 88개 조문 전부 null)
                      조례·고시·별표는 이쪽에만 값이 있다.

    그래서 조문 시행일이 없을 땐 **법규임을 라벨에 밝힌다**("법규 시행 2026-07-13") —
    graph 웹앱(`data.js efInfo`)과 같은 규칙이라 두 화면이 같은 말을 한다.
    판례·해석례는 시행일 개념이 없어 `law_ef_yd: null` 이고, 그때는 아무것도 안 쓴다.
    """
    if not isinstance(tx, dict):
        return ""
    art = _fmt_ef(tx.get("ef_yd"))
    if art:
        return f"시행 {art}"
    law = _fmt_ef(tx.get("law_ef_yd"))
    return f"법규 시행 {law}" if law else ""


def _fmt_ef(raw: Any) -> str:
    """raw `YYYYMMDD` → `YYYY-MM-DD`. 빈 값·모양이 다르면 '' (추측하지 않는다).

    graph 는 **키를 항상 준다** — `""`(그 조문은 시행일 미보유)와 키 없음(API 가 안 줌)은
    소비자에게 다른 정보지만, 화면에 쓸 수 있는 게 없다는 점에선 같아서 둘 다 ''.
    """
    s = str(raw or "").strip()
    if len(s) != 8 or not s.isdigit():
        return ""
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


async def fetch_law_texts(names: list[str], timeout: float = 20.0) -> dict[str, dict]:
    """law_ref name 리스트 → {name: {title, content, source_url, law_nm, article_no,
    ef_yd, law_ef_yd}} (graph 원문 + 시행일).

    Phase 3 — arch-law-graph /api/lookup 배치 조회. found=false 는 제외(인용 금지, 링크만).
    graph 죽어도/미보유해도 graceful({} 또는 부분) — 진단 골격은 유효. name dedup·최대 50개.

    시행일 2종은 2026-08-24 graph F-1·F-4 로 추가된 필드다(우리 연동 2026-07-14 이후).
    **키를 그대로 보존**한다 — 빈 문자열과 키 없음의 구분이 소비자 정보이고, 옛 브리프에
    저장된 `law_texts` 엔 이 키가 아예 없다(`effective_label` 이 둘 다 '' 로 흡수).
    """
    names = [n for n in dict.fromkeys(names) if n]   # dedup, 순서 보존
    if not names:
        return {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{graph_url()}/api/lookup", json={"queries": names[:50]})
        if r.status_code != 200:
            logger.warning("법조문 원문 조회 비200: %s", r.status_code)
            return {}
        results = (r.json() or {}).get("results") or []
        return {
            x["query"]: {"title": x.get("title"), "content": x.get("content"),
                         "source_url": x.get("source_url"), "law_nm": x.get("law_nm"),
                         "article_no": x.get("article_no"),
                         "ef_yd": x.get("ef_yd"), "law_ef_yd": x.get("law_ef_yd")}
            for x in results
            if isinstance(x, dict) and x.get("found") and x.get("query") and (x.get("content") or "").strip()
        }
    except Exception as e:  # noqa: BLE001 — graph 미배포·네트워크 전부 graceful
        logger.warning("법조문 원문 조회 실패 (비치명): %s", e)
        return {}


def digest_diagnosis(diag: dict, site: dict | None = None) -> dict | None:
    """진단 응답 → 배치 근거용 최소 다이제스트 (null 가드 + 신뢰도 캡처).

    매스·단면을 규정하는 필드만 추림: envelope(건폐/용적 한도) · 정북 일조사선 후퇴 ·
    가로구역 최고높이 · 심의(REQUIRED) 여부. source 에 '미확인·추정' 토큰이 있거나 건폐율·
    용적률 pass:null(zone 미해결) 이면 low_confidence(불변식 2: degrade 신호를 신뢰도로 캡처).
    site 를 주면 brief 의 건폐/용적 한도와 진단 limit_pct 를 대조해 불일치(재확인 신호)를 붙인다.
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

    # 심의 vs 법정 — REQUIRED 만 (MAYBE/NONE 제외).
    # ⚠ applicable_reviews 는 배열이 아니라 dict {items[], required_count, maybe_count} — items[] 순회.
    _reviews = diag.get("applicable_reviews")
    _items = _reviews.get("items", []) if isinstance(_reviews, dict) else []
    reviews_required = [
        {"name": rv.get("name"), "law_ref": rv.get("law_ref"),
         "reasons": [str(x) for x in (rv.get("triggered_reasons") or [])]}
        for rv in _items
        if isinstance(rv, dict) and rv.get("severity") == "REQUIRED"
    ]

    # 신뢰도 — source 에 미확인/추정 토큰 = degrade 신호 (전체 카테고리)
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
    # pass:null 은 한도 미확인(zone 미해결) 신호로서만 유효 — 건폐율·용적률에 한정.
    # 높이_일조.pass 는 envelope 모드에서 항상 None(실이격 미입력)이고 정보성 카드(설비·조경·
    # 인증 등)도 pass=None 이 정상이라, 전체 카테고리에 걸면 low_confidence 가 상시 True 가 됨.
    if bcr.get("pass") is None or far.get("pass") is None:
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

    # 관련 법조문 포인터 (배치 관련 카테고리만: 높이_일조·건폐율·용적률) — Phase 3 graph 원문 조회용.
    #   results.<cat>.law_refs = [{name, url}]. 이름 dedup(순서 보존). 원문은 소비측이 graph 로 별도 조회.
    law_refs: list[dict] = []
    _seen_ref: set = set()
    for _cat in ("높이_일조", "건폐율", "용적률"):
        for _ref in (_r(_cat).get("law_refs") or []):
            _nm = _ref.get("name") if isinstance(_ref, dict) else None
            if _nm and _nm not in _seen_ref:
                _seen_ref.add(_nm)
                law_refs.append({"name": _nm, "url": _ref.get("url")})

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
        "law_refs": law_refs,
    }
