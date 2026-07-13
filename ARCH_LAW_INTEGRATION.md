# arch-law-diagnose + arch-law-graph 연동 사양 (technical handoff)

> competition_comparison ↔ 건축법 진단(arch-law-diagnose) + 법령 그래프(arch-law-graph) 연동 사양.
> 두 앱 다 REST. MCP 아님. 콜백 없음, 동기 request/response. 인증 없음(사내).
> **Phase 2 = diagnose(숫자 골격), Phase 3 = graph(조문 원문).** 둘을 잇는 열쇠는 `law_refs` — 문자열 그대로 넘기면 매핑 작업 없음.

```
competition_comparison
  ├─ [Phase 2] POST diagnose /api/diagnose  → 숫자·판정 + law_refs[] 포인터   (배치 골격)
  └─ [Phase 3] POST graph    /api/lookup    → law_refs 의 조문 원문           (정확한 근거)
```

---

## Phase 2 — diagnose (매스·단면 법적 골격)

**Endpoint** `POST /api/diagnose` — `http://localhost:8000`(dev) | `:8080`(docker). Swagger `GET /docs`.

### Request (`DiagnoseRequest`)

```python
# required (검증: gt=0 / ge=1) — 없으면 422
address: str
building_use: str            # 주 용도 분류
site_area: float             # 대지면적 ㎡
building_area: float         # 건축면적 ㎡
floor_area_above: float      # 지상 연면적 ㎡ (주차 포함)
floors_above: int            # 지상 층수
height: float                # 높이 m

# 골격 정밀화에 특히 유효한 optional (미입력 시 VWorld 자동조회/추정 → 정직도↓)
road_width: float|None                 # 전면도로 폭 — 넣는 게 좋음
zone_use_override: str|None            # 용도지역 직접지정
zone_district: str|None                # 지역지구
floor_area_below: float|None           # 지하 연면적 (용적률서 제외)
floor_area_parking_above: float|None   # 지상주차 부속 (용적률서 제외)
north_setback_m: float|None            # 정북 실이격 → §86① 자동판정
adjacent_zone_north: str|None          # 정북 인접 용도지역 (비주거면 일조완화)
road_20m_adjacent: bool|None           # 20m↑도로 접함 → §86②1 제외
street_block_max_height_m: float|None  # 가로구역 최고높이 고시값 주입
units: int|None
far_limit_manual_override: float|None  # 심의/지구단위 확정 용적률
```

### Response 200 — 파싱 대상

```jsonc
{
  "signal": "GREEN|YELLOW|RED",
  "overall_score": 8.3,                       // float 0~10
  "land_info": { "zone_use": str, "zone_district": str, "district_unit_plan": {...} },

  "applicable_reviews": [                      // 심의 vs 법정 판별
    { "name": "건축위원회 심의", "severity": "REQUIRED|CONDITIONAL|NONE",
      "triggered_reasons": [str], "law_ref": str, "law_ref_url": str }
  ],

  "results": {                                 // 값 미확인 시 pass=null, confidence=1
    "건폐율":   { "limit_pct": float|null, "actual_pct": float, "pass": bool|null,
                 "source": str, "law_refs": [{"name":str,"url":str}] },
    "용적률":   { "limit_pct": float|null, "actual_pct": float, "pass": bool|null,
                 "source": str, "law_refs": [...] },
    "높이_일조": { "actual_height_m": float, "floors_above": int, "road_width_m": float,
                 "north_setback_m": float|null,          // 정북 이격
                 "shadow_applies": bool, "shadow_min_setback_m": float|null,
                 "shadow_setback_rule": str|null,        // 일조사선 규칙
                 "road_height_limit_m": float|null,      // 가로구역 최고높이 = 최고 N층
                 "parcel_north_depth_m": float|null,
                 "pass": bool|null, "law_refs": [...] },
    "주차": {...}, "조경": {...}, "설비_소방": {...}, "도시계획시설": {...}, "행위제한": {...}
  },

  "data_quality": { "ordinance_used_bcr": bool, "ordinance_used_far": bool,
                    "road_width_source": str, "land_cache_stale": bool },
  "warnings": [str], "risks": [str]
}
```

### 매스·단면을 규정하는 필드 (배치 근거 층)

- envelope: `results.건폐율.limit_pct`, `results.용적률.limit_pct`
- 정북 후퇴: `높이_일조.north_setback_m` + `shadow_setback_rule` + `shadow_min_setback_m`
- 높이 cap: `높이_일조.road_height_limit_m`(가로구역), `parcel_north_depth_m`
- 심의 여부: `applicable_reviews[].severity == "REQUIRED"` → limits_determined_by="심의"

### 에러 시맨틱

- `503` 엔진 부팅 전 → 재시도
- `422` required 누락·gt·ge 위반 → **재시도 금지**(매핑 버그)
- `400` ValueError / `500` 예외
- 5xx·503만 지수백오프

### 불변식

1. 결정론 계산 엔진 → **숫자·판정·law_refs 포인터만** 반환. **조문 본문·해석 산문 없음**(→ Phase 3 graph). 배치 근거 문장은 소비측이 이 수치로 생성.
2. `pass:null` / `confidence:1` / `source`에 "미확인|추정|시행령" = degrade 신호 → **null 가드 + source·data_quality를 신뢰도로 캡처**.

---

## Phase 3 — graph (조문 원문, "정확한 근거"가 필요할 때만)

Phase 2의 `law_refs[].name`을 **그대로** 넘기면 원문이 온다. 매핑 불필요.

**Endpoint** `POST /api/lookup` — graph 서버(env `GRAPH_API_URL`).

### Request

```jsonc
{ "queries": ["건축법 제61조 (일조 등의 확보를 위한 높이 제한)", ...] }   // 최대 50
```

원소 = diagnose `law_refs[].name` 문자열, 또는 graph 노드 id(`"건축법/제61조"`).

### Response

```jsonc
{ "results": [
  { "query": "건축법 제61조 (...)", "found": true,
    "id": "건축법/제61조", "law_nm": "건축법", "article_no": "제61조",
    "title": "일조 등의 확보를 위한 높이 제한",
    "content": "① 전용주거지역과 일반주거지역 안에서 ...",   // ← 인용할 원문
    "source_url": "https://www.law.go.kr/..." },
  { "query": "...", "found": false }                        // graph 미보유 → 인용 금지
]}
```

### 인용 가드레일 (환각 차단 — 필수)

1. `found:false`면 원문 없음 → 인용하지 말고 `law_refs.url`(법제처 링크)만 표시. graph는 **검색 추정을 일부러 안 함**(틀린 조문 주입 = 환각보다 위험).
2. **`content`에 있는 문장만 인용.** 소비측 LLM이 조문 지어내면 안 됨.
3. graph 죽어도 diagnose 골격은 유효 → 원문만 생략되게 try/except degrade.

---

## client stub (`arch_law_client.py`, teoilgi 패턴)

```python
import os, httpx

DIAG_URL  = os.getenv("ARCH_LAW_API_URL", "http://localhost:8000")
GRAPH_URL = os.getenv("GRAPH_API_URL",   "http://localhost:8100")

async def diagnose(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=120) as c:   # ⚠ 진단 65~110s, timeout 여유 필수
        r = await c.post(f"{DIAG_URL}/api/diagnose", json=payload)
        r.raise_for_status()
        return r.json()

async def fetch_law_texts(diag: dict) -> dict[str, dict]:
    """진단 응답의 모든 law_refs 원문 배치 조회. graph 실패 시 {} (골격은 유지)."""
    names = {ref["name"]
             for cat in diag["results"].values()
             for ref in cat.get("law_refs", [])}
    if not names:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{GRAPH_URL}/api/lookup", json={"queries": list(names)})
            r.raise_for_status()
        return {x["query"]: x for x in r.json()["results"] if x.get("found")}
    except Exception:
        return {}   # graph 없어도 diagnose 골격은 살아있음

def to_request(fx: dict) -> dict:
    """feasibility_export → DiagnoseRequest 매핑 (필드명 확정 후 채움)"""
    return {
        "address": fx["address"], "building_use": fx["use"],
        "site_area": fx["site_area"], "building_area": fx["building_area"],
        "floor_area_above": fx["gfa_above"], "floors_above": fx["floors"],
        "height": fx["height_m"],
        # optional: road_width, zone_use_override, units ... 있으면 정직도↑
    }
```

> ⚠ **diagnose timeout 120s** — 진단 1건 65~110초(국가유산청·Claude 포함). 짧으면 정상 진단이 timeout.

### 결과 조립 예 (숫자 + 원문 = 근거)

```python
diag  = await diagnose(to_request(fx))
texts = await fetch_law_texts(diag)          # {} 여도 아래 골격은 동작

h = diag["results"]["높이_일조"]
ref = h["law_refs"][0]["name"]               # "건축법 제61조 (...)"
법근거 = texts.get(ref, {}).get("content")    # 원문 or None

# → "북측 정북 일조사선(건축법 제61조)으로 {h['north_setback_m']}m 후퇴,
#    가로구역 최고높이 {h['road_height_limit_m']}m 제한 → 업무 매스 남측 고층 / 개방부 북측 저층"
#    (법근거 있으면 각주로 원문 첨부, 없으면 law_refs.url 링크만)
```

---

## 진행 순서

1. **Phase 2 먼저** — `/api/diagnose` 되받기. 여기까지가 "매스·단면 골격" 전부(풍부함 급상승의 실질).
2. **Phase 3는 "정확한 원문 근거"가 필요할 때** — `law_refs` 문자열을 graph `/api/lookup`에 그대로. 매핑 불필요, degrade 안전.
3. **남은 조각**: `feasibility_export` 실제 필드명을 arch-law-diagnose 쪽에 넘기면 `to_request()` 매핑표 확정.

---

## 참고 — 왜 graph를 굳이 지금 안 붙여도 되나

- competition_comparison이 필요한 **배치 근거(매스·단면 골격)는 diagnose 숫자에 전부 있음** → graph 없이 충족.
- graph가 더 주는 건 **조문 원문 인용문**(각주). 설계 드라이버가 아니라 마감.
- `law_refs` 포인터만 캡처해두면 원문은 **나중에 무손실 추가 가능** → Phase 3는 "정확한 근거가 필요할 때" 착수.
- diagnose가 내부적으로 graph를 쓰는 건 diagnose 자체 QueryBox(자연어 질의) 그라운딩 한정 — `/api/diagnose` 응답엔 graph 원문이 안 실려 나온다(포인터만). 그래서 원문이 필요하면 competition_comparison이 직접 graph를 호출해야 함.
