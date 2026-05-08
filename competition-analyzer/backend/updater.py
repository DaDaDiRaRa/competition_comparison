"""GitHub Releases 기반 자동 업데이트.

동작 흐름:
1. GitHub API로 최신 릴리즈 태그 조회
2. 현재 __version__과 비교 (의미적 비교)
3. 새 버전이면 사용자에게 콘솔로 확인 (Y/n)
4. 새 exe 다운로드 → updater.bat 생성 → 본 프로세스 종료 후 교체 → 재실행
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from version import __version__, GITHUB_OWNER, GITHUB_REPO


_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
_ASSET_NAME = "Competition-Analyzer.exe"


def _parse_version(tag: str) -> tuple[int, ...]:
    """v1.2.3 또는 1.2.3 → (1,2,3)"""
    nums = re.findall(r"\d+", tag)
    return tuple(int(n) for n in nums) if nums else (0,)


def _is_newer(remote: str, current: str) -> bool:
    return _parse_version(remote) > _parse_version(current)


def _is_frozen() -> bool:
    """PyInstaller로 패키징된 exe로 실행 중인지."""
    return getattr(sys, "frozen", False)


def _fetch_latest() -> dict | None:
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CompetitionAnalyzer-Updater"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _find_exe_asset(release: dict) -> dict | None:
    for asset in release.get("assets", []):
        if asset.get("name") == _ASSET_NAME:
            return asset
    return None


def _confirm(prompt: str) -> bool:
    try:
        ans = input(prompt).strip().lower()
        return ans in ("", "y", "yes")
    except EOFError:
        return False


def _download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CompetitionAnalyzer-Updater"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"[Updater] 다운로드 실패: {e}")
        return False


def _swap_and_restart(new_exe: Path, current_exe: Path):
    """현재 exe를 종료하고 새 파일로 교체 후 재실행하는 배치 스크립트."""
    bat_path = Path(tempfile.gettempdir()) / "competition_analyzer_update.bat"
    bat_content = f"""@echo off
echo Updating Competition Analyzer...
:retry
ping 127.0.0.1 -n 2 >nul
del "{current_exe}" 2>nul
if exist "{current_exe}" goto retry
move /Y "{new_exe}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
    bat_path.write_text(bat_content, encoding="cp949")
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        close_fds=True,
    )
    sys.exit(0)


def check_and_update():
    """런처에서 호출. 패키징된 exe에서만 실제로 업데이트 수행."""
    if not _is_frozen():
        # 개발 환경에서는 메시지만
        release = _fetch_latest()
        if release:
            tag = release.get("tag_name", "")
            if _is_newer(tag, __version__):
                print(f"[Updater] 새 버전 {tag} 가 GitHub에 있습니다 (현재 {__version__}). dev 모드라 자동 적용 안 함.")
        return

    release = _fetch_latest()
    if not release:
        return

    tag = release.get("tag_name", "")
    if not _is_newer(tag, __version__):
        print(f"[Updater] 최신 버전입니다 ({__version__}).")
        return

    asset = _find_exe_asset(release)
    if not asset:
        print(f"[Updater] {tag} 릴리즈에 {_ASSET_NAME} 자산이 없습니다.")
        return

    print(f"[Updater] 새 버전 발견: {tag} (현재 {__version__})")
    print(f"  변경사항: {release.get('name', tag)}")
    if not _confirm("지금 업데이트할까요? [Y/n] "):
        print("[Updater] 건너뜁니다.")
        return

    download_url = asset.get("browser_download_url")
    if not download_url:
        return

    current_exe = Path(sys.executable)
    new_exe = current_exe.with_suffix(".new.exe")
    print(f"[Updater] 다운로드 중... ({asset.get('size', 0) // (1024 * 1024)} MB)")
    if not _download(download_url, new_exe):
        return

    print("[Updater] 다운로드 완료. 앱을 재시작합니다.")
    _swap_and_restart(new_exe, current_exe)
