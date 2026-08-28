#!/usr/bin/env python3
"""Competition Analyzer MCP 서버 — 축적 데이터를 **읽기 전용**으로 연다.

사내 5개 앱(arch-law-graph·arch-site-model·터읽기·law-qa·arch-law-diagnose)이 이미 MCP 를
열었는데 우리만 빠져 있었다(C-1). 우리가 가진 것 — **과거 공모 축적**(당선/낙선 제출물·
시설유형 패턴·아카이브 FTS)과 **분석된 지침서** — 은 다른 앱에 없다.

## 노출 도구 (넷 다 읽기 전용 · LLM 0 · API 키 불필요)

- `search_competitions` : 자연어로 과거 공모 검색 (FTS5 BM25)
- `list_briefs`         : 분석된 지침서 목록
- `get_brief`           : 지침서 하나의 핵심 (배점·면적·요구·검증 경고)
- `get_facility_pattern`: 시설유형별 당선 패턴 + 낙선 통계

**쓰기 도구는 없다.** 분석·제안서 생성은 과금·장시간 작업이라 REST 로만 둔다.

## 배선 (kunwon-ops docs/plan-mcp-gateway.md §9 의 검증된 패턴)

`stateless_http=True` · `streamable_http_path="/"` · DNS 리바인딩 방지 끄기 ·
Starlette `Mount` 대신 raw ASGI 프리픽스 래퍼 — 넷 다 형제앱 배포에서 실측으로 얻은 것.
마운트·인증은 `main.py` 에 있다.

⚠ 우리는 `mcp` 를 백엔드 venv 에 **같이** 넣는다(별도 서비스 아님 — 터읽기와 같은 방식).
그래서 **버전이 좁다.** `requirements-server.txt` 의 `fastapi==0.115.12`·`pydantic==2.10.6`
과 같이 살 수 있는 건 `mcp==1.12.4` 뿐이다:
  · mcp>=1.15  → `pydantic>=2.11` 요구 (우리 핀 2.10.6 과 충돌)
  · sse-starlette>=3.4 → `starlette>=0.49.1` **무조건** 요구 (fastapi 0.115 는 <0.47)
arch-law-diagnose 가 이 조합으로 **테스트는 전부 초록인데 앱이 안 뜨는** 사고를 겪었다.
`tests/test_app_boot.py` 가 조건을 지키고, 로컬 venv 도 배포와 같은 버전으로 맞춰 둔다.

## Claude Code 에 연결

    claude mcp add competition --transport http \\
      https://competition-analyzer-30350777436.asia-northeast3.run.app/mcp \\
      --header "Authorization: Bearer $COMPETITION_MCP_KEY"
"""

# ⚠ `from __future__ import annotations` 를 **쓰지 않는다.** 그걸 켜면 모든 애노테이션이
# 문자열이 되는데, 배포에 핀된 `mcp==1.12.4` 의 도구 등록기는 문자열 애노테이션을 해석하지
# 않아 `TypeError: issubclass() arg 1 must be a class` 로 죽는다(최신 mcp 는 해석한다).
# 로컬만 최신 mcp 면 여기서 안 걸리고 **프로덕션에서만** 죽는다 — 그래서 로컬 venv 도
# requirements-server.txt 와 같은 버전으로 맞춰 둔다.
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent      # backend/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

mcp = FastMCP(
    "competition",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

#: 한 번에 돌려줄 최대 건수. MCP 응답은 컨텍스트에 그대로 실리므로 크게 열면 손해다.
MAX_LIMIT = 30


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _err(code: str, message: str) -> str:
    """확인 불가는 정직하게 — 빈 결과와 오류는 다른 정보다."""
    return _json({"error": code, "message": message})


def _clamp(n, default: int) -> int:
    try:
        return max(1, min(int(n), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


@mcp.tool()
def search_competitions(query: str, limit: int = 10) -> str:
    """자연어로 **과거 공모**를 검색한다 (우리 DB 축적분, BM25 관련도순).

    예: "병원 공모 사례", "저층부 개방 당선작", "준공업지역 청사".
    각 결과: 시설유형·공모명·참여사·당선사·컨셉 키워드·평가축 요약.

    ⚠ 2자 미만 토큰은 trigram 이 못 잡는다(「병원」은 되지만 「병」은 안 된다).
    결과가 비면 그 낱말이 우리 DB 에 없는 것이지 검색이 실패한 게 아니다.
    """
    q = (query or "").strip()
    if not q:
        return _err("EMPTY_QUERY", "검색어가 비었습니다.")
    try:
        from services.archive_search import get_index
        rows = get_index().search_natural(q, limit=_clamp(limit, 10))
    except Exception as e:  # noqa: BLE001 — MCP 계약대로 정직한 에러로
        return _err("SEARCH_FAILED", f"확인 불가: {type(e).__name__}")
    return _json({"query": q, "count": len(rows), "results": rows})


@mcp.tool()
def list_briefs(facility_type: str = "", limit: int = 20) -> str:
    """분석된 **지침서 목록** (최신순). facility_type 을 주면 그 시설유형만.

    각 항목: brief_id·공모명·시설유형·장르(공모/입찰)·산출물 보유 여부
    (해설·제안서·경험처방)·방향 지시 이력.
    `brief_id` 를 `get_brief` 에 넘기면 내용을 볼 수 있다.
    """
    try:
        from routers.brief import list_briefs as _list
        items = _list()
    except Exception as e:  # noqa: BLE001
        return _err("LIST_FAILED", f"확인 불가: {type(e).__name__}")
    ft = (facility_type or "").strip()
    if ft:
        items = [b for b in items if (b or {}).get("facility_type") == ft]
    n = _clamp(limit, 20)
    return _json({"count": len(items), "shown": min(len(items), n),
                  "briefs": items[:n]})


@mcp.tool()
def get_brief(brief_id: str) -> str:
    """지침서 하나의 **핵심**: 사업 개요·배점 무게중심·면적·부지 제원·검증 경고.

    전문이 아니라 요약이다 — `_brief.json` 은 1MB 가 넘어 컨텍스트에 통째로 올리면
    손해다. 원문 리포트는 앱의 `/api/brief/exports/{brief_id}.html` 에 있다.

    포함되는 경고(있을 때만): 지침서 **내부 모순**(같은 값을 여러 곳이 다르게 말함) ·
    **파일 간 충돌**(복수 파일 분석) · 검증 flag.
    """
    import json as _j

    from config import settings

    safe = Path(brief_id or "").name
    if not safe or safe != (brief_id or ""):
        return _err("BAD_ID", "잘못된 brief_id 입니다.")
    path = settings.db_path / "_briefs" / f"{safe}.json"
    if not path.exists():
        return _err("NOT_FOUND", f"지침서를 찾을 수 없습니다: {safe}")
    try:
        d = _j.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return _err("READ_FAILED", f"확인 불가: {type(e).__name__}")

    meta = d.get("_brief_meta") or {}
    insight = d.get("_insight") or {}
    out = {
        "brief_id": safe,
        "brief_name": meta.get("brief_name"),
        "facility_type": meta.get("facility_type"),
        "source_format": meta.get("source_format"),
        "genre": (d.get("_brief_genre") or {}).get("genre"),
        "scoring_focus": insight.get("scoring_focus") or [],
        "quantitative": d.get("_quantitative") or {},
        "feasibility_export": d.get("feasibility_export") or {},
        "validation_summary": (d.get("validation") or {}).get("summary") or {},
        "has": {
            "insight": bool(d.get("_insight")),
            "proposal": bool(d.get("_proposal")),
            "playbook": bool(d.get("_playbook")),
            "site_context": bool(d.get("_site_context")),
        },
    }
    # 경고는 **있을 때만** 싣는다 — 빈 키가 늘면 읽는 쪽이 신호를 놓친다.
    for key in ("_contradictions", "_merge_conflicts"):
        if d.get(key):
            out[key] = d[key]
    return _json(out)


@mcp.tool()
def get_facility_pattern(facility_type: str) -> str:
    """시설유형별 **당선 패턴 + 낙선 통계** (과거 축적 집계).

    포함: 페이지 구성 분포·정량 지표 범위·컨셉 키워드, 그리고 `loser_stats`
    (낙선작 통계 — 무엇이 달랐나). 표본이 작으면(N≤2) 약한 신호다.

    시설유형 키는 `list_briefs` 결과의 `facility_type` 과 같다.
    """
    ft = (facility_type or "").strip()
    if not ft:
        return _err("EMPTY_TYPE", "시설유형이 비었습니다.")
    try:
        from config import FACILITY_TYPES
        from services.db_manager import load_pattern
        if ft not in FACILITY_TYPES:
            return _err("UNKNOWN_TYPE",
                        f"모르는 시설유형입니다. 가능한 값: {', '.join(FACILITY_TYPES)}")
        pat = load_pattern(ft)
    except Exception as e:  # noqa: BLE001
        return _err("LOAD_FAILED", f"확인 불가: {type(e).__name__}")
    if not pat:
        return _json({"facility_type": ft, "pattern": None,
                      "note": "이 시설유형은 아직 축적 데이터가 없습니다(비교분석 미실행)."})
    return _json({"facility_type": ft, "pattern": pat})


if __name__ == "__main__":
    mcp.run()
