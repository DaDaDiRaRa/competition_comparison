"""Competition Analyzer 데스크톱 런처.

역할:
1. 자동 업데이트 확인 (GitHub Releases)
2. 빈 포트 자동 할당
3. FastAPI 서버를 백그라운드 스레드로 실행
4. pywebview로 네이티브 앱 창 표시 (브라우저 없음)
5. 트레이 아이콘으로 숨기기/다시 열기 지원
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path


def resource_path(rel: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).parent / rel


def find_free_port(preferred: int = 8000) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server(port: int):
    import uvicorn
    from main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def wait_for_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def setup_tray(window, icon_path: Path):
    """트레이 아이콘: 클릭 → 창 표시, 종료 메뉴."""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        print("[Tray] pystray 미설치 — 창을 닫으면 앱이 종료됩니다.")
        return None

    try:
        image = Image.open(icon_path) if icon_path.exists() else Image.new("RGBA", (64, 64), (26, 31, 46, 255))
    except Exception:
        image = Image.new("RGBA", (64, 64), (26, 31, 46, 255))

    def show(_icon, _item):
        window.show()

    def quit_app(icon, _item):
        icon.stop()
        window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("창 열기", show, default=True),
        pystray.MenuItem("종료", quit_app),
    )
    icon = pystray.Icon("CompetitionAnalyzer", image, "Competition Analyzer", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def main():
    # 1) 자동 업데이트 체크 (실패해도 무시하고 계속)
    try:
        from updater import check_and_update
        check_and_update()
    except Exception as e:
        print(f"[Updater] 건너뜀: {e}")

    # 2) 포트 할당
    port = find_free_port(8000)
    print(f"[Launcher] 포트: {port}")

    # 3) FastAPI 서버 백그라운드 실행
    threading.Thread(target=run_server, args=(port,), daemon=True).start()

    # 4) 서버 기동 대기
    if not wait_for_server(port):
        print("[Launcher] 서버 기동 실패")
        sys.exit(1)
    print("[Launcher] 서버 준비 완료")

    # 5) pywebview 네이티브 창
    try:
        import webview
    except ImportError:
        # pywebview 없으면 브라우저로 폴백
        import webbrowser
        print("[Launcher] pywebview 미설치 — 브라우저로 열립니다.")
        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        sys.exit(0)

    icon_path = resource_path("app_icon.ico")
    window = webview.create_window(
        title="Competition Analyzer",
        url=f"http://127.0.0.1:{port}",
        width=1280,
        height=860,
        min_size=(800, 600),
        text_select=False,  # 일반 앱처럼 텍스트 드래그 선택 비활성
    )

    # 트레이 아이콘은 pywebview 창이 뜬 후 연결
    def _after_start():
        setup_tray(window, icon_path)

    # 6) 메인 루프 (pywebview가 이 스레드 점유 — 창 닫으면 반환)
    webview.start(func=_after_start, debug=False)

    print("[Launcher] 종료합니다.")
    sys.exit(0)


if __name__ == "__main__":
    main()
