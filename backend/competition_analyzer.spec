# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Competition Analyzer.

빌드:
    cd competition-analyzer/backend
    pyinstaller competition_analyzer.spec --noconfirm

산출물:
    dist/CompetitionAnalyzer/
        CompetitionAnalyzer.exe  (실행 파일)
        _internal/               (DLL, 패키지, frontend_dist 등)
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

spec_dir = Path(SPECPATH)
frontend_dist = spec_dir.parent / "frontend" / "dist"
readme_html = spec_dir.parent.parent / "README.html"

# pywebview / pythonnet은 .NET 어셈블리를 동적 로드 → 정적 분석 불가
# collect_all로 데이터+바이너리+모듈 전체 수집
webview_datas, webview_binaries, webview_hidden = collect_all('webview')
clr_datas, clr_binaries, clr_hidden = collect_all('clr_loader')
pythonnet_datas, pythonnet_binaries, pythonnet_hidden = collect_all('pythonnet')

if not frontend_dist.exists():
    raise SystemExit(
        f"[ERROR] 프론트엔드 빌드가 없습니다: {frontend_dist}\n"
        f"먼저 'cd ../frontend && npm run build' 실행하세요."
    )

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[str(spec_dir)],
    binaries=webview_binaries + clr_binaries + pythonnet_binaries,
    datas=[
        (str(frontend_dist), 'frontend_dist'),
        *( [(str(readme_html), '.')] if readme_html.exists() else [] ),
    ] + webview_datas + clr_datas + pythonnet_datas,
    hiddenimports=webview_hidden + clr_hidden + pythonnet_hidden + [
        # uvicorn 동적 import
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # 지연 import되는 라이브러리들
        'fitz',
        'anthropic',
        'PIL',
        'PIL.Image',
        'numpy',
        # PyWebView 백엔드 (Windows = EdgeChromium / WinForms)
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'clr_loader',
        'clr_loader.netfx',
        'pythonnet',
        'proxy_tools',
        'bottle',
        # 백엔드 모듈 (정적 분석으로도 잡히지만 안전망)
        'main',
        'config',
        'version',
        'routers.accumulate',
        'routers.diagnose',
        'routers.settings',
        'routers.patterns',
        'services.db_manager',
        'services.comparator',
        'services.report_generator',
        'services.diagnosis_report_generator',
        'services.submission_report_generator',
        'services.pattern_builder',
        'services.data_extractor',
        'services.page_classifier',
        'services.llm_client',
        'services.utils',
        'services.brief_checklist_exporter',
        'models.schemas',
        # openpyxl — brief_checklist_exporter.py 런타임 import
        # 함수 내부 lazy import라 정적 분석으로 미탐지 → 명시 열거
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.cell.cell',
        'openpyxl.styles',
        'openpyxl.styles.fills',
        'openpyxl.styles.fonts',
        'openpyxl.styles.alignment',
        'openpyxl.utils',
        'openpyxl.utils.cell',
        'openpyxl.writer',
        'openpyxl.writer.excel',
        'openpyxl.workbook',
        'openpyxl.worksheet',
        'openpyxl.worksheet.worksheet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # OCR 의존성은 선택 — 번들 용량 절감을 위해 제외
        'paddleocr',
        'paddle',
        'paddlepaddle',
        # 불필요한 무거운 패키지 제외
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
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
    [],
    exclude_binaries=True,
    name='CompetitionAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed 빌드 — CMD 창 미표시. 로그는 ~/.competition-analyzer/app.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CompetitionAnalyzer',
)
