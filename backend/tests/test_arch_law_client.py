"""arch-law-diagnose 연동 클라이언트 테스트 — 네트워크 없이 결정적.

feasibility_export.sites[] → DiagnoseRequest 매핑(용량 모드 역산), 진단 응답 → 배치 골격
다이제스트(null 가드·신뢰도·심의·불일치), diagnose graceful(실패·비200→None), 게이트 검증.
"""

import asyncio
import json

import services.arch_law_client as alc


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        if self._exc:
            raise self._exc
        return self._resp


# ── to_request: 용량(envelope) 모드 역산 ──────────────────────────────────────

_SITE = {
    "site_id": "부지1",
    "address": "서울 영등포구 여의대로 24",
    "site_area_sqm": 10000,
    "building_coverage_pct": 60,
    "floor_area_ratio_pct": 460,
    "max_height_m": 80,
    "building_law_uses": ["업무시설"],
    "zone_use": "일반상업지역",
    "zone_use_raw": None,
}


def test_to_request_capacity_backcalc():
    req = alc.to_request(_SITE)
    assert req is not None
    assert req["address"] == "서울 영등포구 여의대로 24"
    assert req["building_use"] == "업무시설"
    assert req["site_area"] == 10000
    assert req["building_area"] == 6000.0        # 10000 × 60% = 건폐 한도
    assert req["floor_area_above"] == 46000.0     # 10000 × 460% = 용적 한도
    assert req["floors_above"] == 20              # round(80/4) 추정
    assert req["height"] == 80
    assert req["zone_use_override"] == "일반상업지역"


def test_to_request_use_fallback_to_zone_raw():
    s = dict(_SITE, building_law_uses=[], zone_use_raw="준공업지역(추정)")
    assert alc.to_request(s)["building_use"] == "준공업지역(추정)"
    s2 = dict(_SITE, building_law_uses=[], zone_use_raw=None)
    assert alc.to_request(s2)["building_use"] == "미상"


def test_to_request_none_on_missing_required():
    for missing in ("address", "site_area_sqm", "building_coverage_pct",
                    "floor_area_ratio_pct", "max_height_m"):
        s = dict(_SITE)
        s[missing] = None
        assert alc.to_request(s) is None, f"{missing} 결측이면 None 이어야"


def test_to_request_floors_min_one():
    s = dict(_SITE, max_height_m=2)   # round(2/4)=0 → max(1,…)=1
    assert alc.to_request(s)["floors_above"] == 1


# ── digest_diagnosis: 배치 골격 추림 + 가드 ──────────────────────────────────

def _full_diag():
    return {
        "signal": "GREEN",
        "overall_score": 8.3,
        # 실제 구조: dict + items[], severity 는 REQUIRED/MAYBE/NONE
        "applicable_reviews": {
            "items": [
                {"name": "건축위원회 심의", "severity": "REQUIRED",
                 "triggered_reasons": ["규모"], "law_ref": "건축법 §4"},
                {"name": "경관심의", "severity": "MAYBE"},
                {"name": "교통영향평가", "severity": "NONE"},
            ],
            "required_count": 1, "maybe_count": 1,
        },
        "results": {
            "건폐율": {"limit_pct": 60.0, "actual_pct": 60.0, "pass": True, "source": "🏛 조례",
                     "law_refs": [{"name": "건축법 제55조 (건폐율)", "url": "https://law/55"}]},
            "용적률": {"limit_pct": 460.0, "actual_pct": 460.0, "pass": True, "source": "🏛 조례",
                     "law_refs": [{"name": "건축법 제56조 (용적률)", "url": "https://law/56"}]},
            # envelope 모드 현실 반영: 높이_일조.pass 는 None
            "높이_일조": {"north_setback_m": None, "shadow_applies": True,
                        "shadow_setback_rule": "정북 h/2", "shadow_min_setback_m": 1.5,
                        "road_height_limit_m": 90.0, "parcel_north_depth_m": 40.0,
                        "pass": None,
                        "law_refs": [{"name": "건축법 제61조 (일조 등의 확보를 위한 높이 제한)",
                                      "url": "https://law/61"}]},
            # 정보성 카드도 pass:None — low_confidence 오탐 유발 여부 회귀
            "설비_소방": {"pass": None, "source": "AI 정성판단"},
        },
    }


def test_digest_extracts_skeleton():
    d = alc.digest_diagnosis(_full_diag())
    assert d["signal"] == "GREEN" and d["overall_score"] == 8.3
    assert d["envelope"] == {"bcr_limit_pct": 60.0, "far_limit_pct": 460.0}
    assert d["height_solar"]["north_setback_m"] is None       # envelope 모드 현실
    assert d["height_solar"]["shadow_min_setback_m"] == 1.5
    assert d["height_solar"]["road_height_limit_m"] == 90.0
    # 패치 1 회귀 가드: applicable_reviews dict items[] 에서 REQUIRED 만 뽑아야 함
    assert d["has_required_review"] is True
    assert [r["name"] for r in d["reviews_required"]] == ["건축위원회 심의"]  # REQUIRED 만 (MAYBE/NONE 제외)
    # 패치 2 회귀 가드: 높이_일조·설비_소방 pass:None 이 있어도 건폐/용적 pass:True 라 저신뢰 아님
    assert d["low_confidence"] is False


def test_digest_info_card_null_pass_not_low_conf():
    """정보성 카드(설비_소방 등) pass:None 만으로는 low_confidence 를 켜면 안 됨 (패치 2 회귀).

    건폐율·용적률 pass 가 True 이고 source 에 미확인/추정 토큰이 없으면 나머지 카테고리가
    전부 pass:None 이어도 저신뢰가 아니다 — envelope 모드에서 상시 True 로 켜지던 버그 방지.
    """
    diag = _full_diag()  # 높이_일조·설비_소방 pass=None, 건폐/용적 pass=True
    assert alc.digest_diagnosis(diag)["low_confidence"] is False


def test_digest_low_confidence_on_null_pass_and_source_token():
    diag = _full_diag()
    diag["results"]["건폐율"]["pass"] = None            # pass:null → degrade
    diag["results"]["용적률"]["source"] = "지자체 미확인"  # 토큰 → degrade
    d = alc.digest_diagnosis(diag)
    assert d["low_confidence"] is True
    assert d["source_notes"]["용적률"] == "지자체 미확인"


def test_digest_ordinance_source_not_low_confidence():
    """'시행령'은 정상 법정값 — 저신뢰 오탐 방지(진단앱 피드백). 미확인·추정만 degrade."""
    diag = _full_diag()
    diag["results"]["건폐율"]["source"] = "건축법 시행령 제84조"
    diag["results"]["용적률"]["source"] = "서울시 도시계획 조례"
    d = alc.digest_diagnosis(diag)
    assert d["low_confidence"] is False


def test_digest_limit_mismatch_flags_brief_recheck():
    diag = _full_diag()
    diag["results"]["건폐율"]["limit_pct"] = 80.0   # brief 60 ↔ 진단 80
    d = alc.digest_diagnosis(diag, site=_SITE)
    assert any(m["field"] == "건폐율" and m["brief_pct"] == 60 and m["diagnose_limit_pct"] == 80.0
               for m in d["limit_mismatch"])


def test_digest_no_mismatch_within_tolerance():
    d = alc.digest_diagnosis(_full_diag(), site=_SITE)   # 60/460 일치
    assert d["limit_mismatch"] == []


def test_digest_graceful_on_missing_results():
    d = alc.digest_diagnosis({"signal": "YELLOW"})
    assert d["envelope"] == {"bcr_limit_pct": None, "far_limit_pct": None}
    assert d["reviews_required"] == []
    assert alc.digest_diagnosis("not a dict") is None
    assert alc.digest_diagnosis(None) is None


# ── diagnose: graceful HTTP ──────────────────────────────────────────────────

def test_diagnose_success(monkeypatch):
    monkeypatch.setattr(alc.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(resp=_Resp(200, {"signal": "GREEN"})))
    out = asyncio.run(alc.diagnose({"address": "x"}))
    assert out and out["signal"] == "GREEN"


def test_diagnose_graceful_on_non_200(monkeypatch):
    monkeypatch.setattr(alc.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(resp=_Resp(422, {"detail": "bad"})))
    assert asyncio.run(alc.diagnose({})) is None


def test_diagnose_graceful_on_exception(monkeypatch):
    monkeypatch.setattr(alc.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(exc=RuntimeError("down")))
    assert asyncio.run(alc.diagnose({})) is None


# ── 게이트: 기본 ON(공개 엔진), ARCH_LAW_DISABLE 로만 끔 ──────────────────────

def test_is_enabled_default_on(monkeypatch):
    monkeypatch.delenv("ARCH_LAW_DISABLE", raising=False)
    assert alc.is_enabled() is True                     # 기본 ON
    monkeypatch.setenv("ARCH_LAW_DISABLE", "1")
    assert alc.is_enabled() is False                    # 명시 OFF
    monkeypatch.setenv("ARCH_LAW_DISABLE", "true")
    assert alc.is_enabled() is False


def test_diag_url_default_is_public(monkeypatch):
    monkeypatch.delenv("ARCH_LAW_API_URL", raising=False)
    assert alc.diag_url() == "https://arch-law-diagnose-30350777436.asia-northeast3.run.app"
    monkeypatch.setenv("ARCH_LAW_API_URL", "http://localhost:8010")  # override
    assert alc.diag_url() == "http://localhost:8010"


# ── Phase 3: 조문 원문 (graph) ────────────────────────────────────────────────

def test_digest_captures_placement_law_refs():
    """digest 가 배치 관련 카테고리(높이_일조·건폐율·용적률) law_refs 를 dedup 캡처."""
    d = alc.digest_diagnosis(_full_diag())
    names = [r["name"] for r in d["law_refs"]]
    assert "건축법 제61조 (일조 등의 확보를 위한 높이 제한)" in names   # 정북
    assert "건축법 제55조 (건폐율)" in names and "건축법 제56조 (용적률)" in names
    assert all(r.get("url") for r in d["law_refs"])                     # url 보존


def test_graph_url_default_is_public(monkeypatch):
    monkeypatch.delenv("GRAPH_API_URL", raising=False)
    assert alc.graph_url() == "https://arch-law-graph-30350777436.asia-northeast3.run.app"


def test_fetch_law_texts_found_only(monkeypatch):
    payload = {"results": [
        {"query": "건축법 제61조 (일조 등의 확보를 위한 높이 제한)", "found": True,
         "title": "일조 등의 확보를 위한 높이 제한", "content": "① 전용주거지역과 일반주거지역...",
         "source_url": "https://law/61", "law_nm": "건축법", "article_no": "제61조"},
        {"query": "미보유 조문", "found": False},                              # found=false → 제외
        {"query": "빈 원문", "found": True, "content": "   "},                 # content 빈 → 제외
    ]}
    monkeypatch.setattr(alc.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(resp=_Resp(200, payload)))
    out = asyncio.run(alc.fetch_law_texts(
        ["건축법 제61조 (일조 등의 확보를 위한 높이 제한)", "미보유 조문", "빈 원문", "건축법 제61조 (일조 등의 확보를 위한 높이 제한)"]))
    assert set(out) == {"건축법 제61조 (일조 등의 확보를 위한 높이 제한)"}       # found+content 만, dedup
    assert out["건축법 제61조 (일조 등의 확보를 위한 높이 제한)"]["content"].startswith("①")


def test_fetch_law_texts_graceful(monkeypatch):
    assert asyncio.run(alc.fetch_law_texts([])) == {}
    monkeypatch.setattr(alc.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(exc=RuntimeError("graph down")))
    assert asyncio.run(alc.fetch_law_texts(["x"])) == {}
