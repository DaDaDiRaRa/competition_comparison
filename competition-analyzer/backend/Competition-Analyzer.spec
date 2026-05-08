# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Competition Analyzer desktop app (onefile mode).
# Build with: pyinstaller Competition-Analyzer.spec

from pathlib import Path

block_cipher = None

backend_dir = Path(SPECPATH)
frontend_dist = backend_dir.parent / "frontend" / "dist"
icon_path = backend_dir / "app_icon.ico"

datas = []
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend_dist"))
if icon_path.exists():
    datas.append((str(icon_path), "."))

default_settings = backend_dir / "app_settings.json"
if default_settings.exists():
    datas.append((str(default_settings), "."))

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "pystray._win32",
    # pywebview (Windows는 EdgeChromium 또는 MSHTML 엔진 사용)
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.mshtml",
    "clr",  # pythonnet (pywebview Windows 의존성)
    "System",
    "System.Windows.Forms",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "scipy",
        "tkinter",
        "test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Competition-Analyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
