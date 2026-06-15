"""
Competition Analyzer Launcher (PyWebView 네이티브 앱).

uvicorn을 백그라운드 스레드로 띄우고, 메인 스레드에서 PyWebView 윈도우를 연다.
target="_blank" 링크는 JS API를 통해 시스템 기본 브라우저로 위임 (리포트 보기/인쇄 편의).

console=False(windowed) 빌드 — CMD 창 미표시. 진단/디버깅용 로그는
~/.competition-analyzer/app.log 에 기록.
"""
import logging
import os
import sys
import threading
import time
import traceback
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "설계공모 경쟁분석"

LOG_DIR = Path.home() / ".competition-analyzer"
LOG_FILE = LOG_DIR / "app.log"


def _setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # console=False라도 stdout 핸들러는 두지 않음 (None인 경우 예외 발생 가능)
    return logging.getLogger("launcher")


class JsApi:
    """프론트엔드 JS에서 호출 가능한 Python 메서드.
    window.pywebview.api.open_external(url) / save_file(url, filename) 형태로 사용.
    """

    def open_external(self, url: str) -> bool:
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def save_file(self, url: str, default_filename: str) -> dict:
        """네이티브 저장 대화상자를 열고 선택한 경로에 파일을 다운로드한다."""
        import urllib.request
        try:
            import webview
        except ImportError:
            return {"ok": False, "reason": "webview 모듈 없음"}

        try:
            ext = default_filename.rsplit(".", 1)[-1].lower() if "." in default_filename else ""
            if ext == "xlsx":
                file_types = ("Excel 파일 (*.xlsx)",)
            elif ext == "md":
                file_types = ("Markdown 파일 (*.md)",)
            else:
                file_types = ()

            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=default_filename,
                file_types=file_types,
            )
            if not result:
                return {"ok": False, "reason": "cancelled"}

            save_path = result[0] if isinstance(result, (list, tuple)) else result
            urllib.request.urlretrieve(url, save_path)
            return {"ok": True, "path": save_path}
        except Exception as e:
            logging.getLogger("launcher").exception("save_file 오류")
            return {"ok": False, "reason": str(e)}


def _wait_for_server(timeout_seconds: float = 60.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{URL}/api/health", timeout=1)
            return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False


def _ensure_std_streams():
    """windowed 빌드(console=False)는 sys.stdout/stderr가 None.
    uvicorn 기본 ColourizedFormatter가 stdout.isatty()를 호출해 크래시 → devnull로 가드."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _run_uvicorn(log):
    try:
        import uvicorn
        from main import app

        # log_config=None — uvicorn 기본 로깅 비활성화. 위 _ensure_std_streams로
        # 1차 가드, log_config=None으로 2차 가드. 우리 RotatingFileHandler가 모두 수신.
        config = uvicorn.Config(
            app, host=HOST, port=PORT, log_level="info",
            access_log=False, log_config=None,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception:
        log.exception("uvicorn 서버 크래시")


def _show_error_dialog(message: str):
    """치명적 오류 시 윈도우 메시지박스로 알림 (콘솔 없는 환경 대비)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, message, f"{WINDOW_TITLE} — 오류", 0x10  # MB_ICONERROR
        )
    except Exception:
        pass


def main():
    _ensure_std_streams()
    log = _setup_logging()
    log.info("=" * 60)
    log.info("Competition Analyzer 시작")

    try:
        if getattr(sys, "frozen", False):
            bundle_dir = Path(sys._MEIPASS)
            sys.path.insert(0, str(bundle_dir))
            os.chdir(bundle_dir)
            log.info(f"frozen 모드. bundle_dir={bundle_dir}")

        # 백엔드 서버 백그라운드 시작
        threading.Thread(target=_run_uvicorn, args=(log,), daemon=True).start()

        if not _wait_for_server():
            msg = f"서버 시작 실패 ({URL})\n로그: {LOG_FILE}"
            log.error(msg)
            _show_error_dialog(msg)
            sys.exit(1)

        log.info(f"서버 응답 확인 ({URL})")

        # 네이티브 윈도우 띄우기
        import webview

        api = JsApi()
        webview.create_window(
            title=WINDOW_TITLE,
            url=URL,
            js_api=api,
            width=1400,
            height=900,
            min_size=(900, 600),
        )
        # gui 인자 미지정 → Windows에서 자동으로 EdgeChromium(WebView2) 선택
        webview.start()
        log.info("윈도우 종료. 앱 정상 종료.")
    except Exception as e:
        log.exception("치명적 오류")
        _show_error_dialog(
            f"앱 시작 실패: {e}\n자세한 내용은 로그 파일을 확인하세요:\n{LOG_FILE}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
