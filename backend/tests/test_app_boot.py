"""앱이 **뜨는지** — import 와 라우트 등록을 명시적으로 못박는다.

계기(2026-08-28): 형제앱 arch-law-diagnose 가 **테스트 340건 전부 초록인데 앱이 아예
안 뜨는** 상태를 라이브 e2e 에서야 발견했다. `main` 을 import 하는 테스트가 하나도
없었기 때문이다. 원인은 의존성 충돌이었다 — `fastapi==0.115.5`(starlette<0.42) 와
`mcp>=1.2` 가 한 venv 에 있는데 최신 `mcp` 가 `sse-starlette>=1.6.1` → `starlette>=0.49.1`
을 끌고 와 import 가 죽었다.

우리는 지금 `mcp` 를 안 쓰고 `pip check` 도 깨끗하다. 그래도 이 파일을 두는 이유:

  · 지금의 boot 보장이 **우연**이다 — `main` 을 import 하는 테스트가 6개 있지만
    전부 다른 것을 보러 온 김에 import 할 뿐이라, 그것들이 지워지면 보장도 같이 사라진다.
  · **C-1(MCP provider 전환)이 로드맵에 있다.** 그때 `mcp` 를 넣으면 저쪽이 밟은
    그 함정이 그대로 우리 것이 된다. `kunwon-ops/docs/plan-mcp-gateway.md §9` 도
    「백엔드 venv 에 mcp 를 넣으면 starlette 가 올라가 fastapi 핀이 깨지므로
    **서비스 분리 필수**」라고 적어 뒀다 — 그 실패가 여기서 먼저 보여야 한다.

느리지도 않다(import 한 번). 라우트까지 보는 이유는, import 는 되는데 라우터 등록이
누락되는 일이 실제로 있었기 때문이다(2026-08-27 `/deck` 배선 누락 — 모듈 테스트는
전부 통과했고 e2e 에서야 잡혔다).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_main_imports():
    """의존성 충돌·문법 오류로 앱이 죽으면 여기서 먼저 터진다."""
    from main import app
    assert app is not None


@pytest.mark.parametrize("path,method", [
    ("/api/brief/analyze", "POST"),
    ("/api/brief/list", "GET"),
    ("/api/brief/{brief_id}/propose", "POST"),
    ("/api/brief/{brief_id}/deck", "POST"),        # 2026-08-27 배선이 통째로 누락됐던 자리
    ("/api/brief/{brief_id}/playbook", "POST"),
    ("/api/accumulate/run", "POST"),
    ("/api/diagnose/run", "POST"),
    ("/api/settings/meta", "GET"),
    ("/api/upload/start", "POST"),
    ("/api/upload/chunk/{upload_id}", "POST"),
])
def test_core_routes_are_registered(path, method):
    """import 는 되는데 라우터 등록만 빠지는 일이 실제로 있었다."""
    from main import app
    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", ()) or ()}
    assert (path, method) in routes, f"{method} {path} 가 등록돼 있지 않다"


def test_no_broken_dependencies():
    """`pip check` 상당 — 설치된 패키지들의 요구사항이 서로 맞는가.

    ⚠ MCP provider(C-1) 착수 시 여기가 먼저 깨질 것이다. 그때 답은 핀을 푸는 게
    아니라 **서비스를 분리하는 것**이다(kunwon-ops plan-mcp-gateway §9).
    """
    from importlib.metadata import distributions

    from packaging.requirements import Requirement
    from packaging.version import InvalidVersion, Version

    installed = {}
    for d in distributions():
        name = (d.metadata["Name"] or "").lower().replace("_", "-")
        if name:
            installed[name] = d.version

    broken = []
    for d in distributions():
        owner = d.metadata["Name"] or "?"
        for raw in (d.requires or []):
            try:
                req = Requirement(raw)
            except Exception:                      # noqa: BLE001 — 파싱 불가는 판단 보류
                continue
            if req.marker is not None and not req.marker.evaluate():
                continue                            # extra/환경 조건부 의존은 제외
            have = installed.get(req.name.lower().replace("_", "-"))
            if have is None or not req.specifier:
                continue                            # 미설치 optional 은 pip check 도 안 잡는다
            try:
                if not req.specifier.contains(Version(have), prereleases=True):
                    broken.append(f"{owner} 는 {raw} 를 요구하는데 설치된 것은 {have}")
            except InvalidVersion:
                continue
    assert not broken, "의존성 충돌:\n  " + "\n  ".join(broken)
