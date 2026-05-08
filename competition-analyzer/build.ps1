# Competition Analyzer 데스크톱 앱 빌드 스크립트
# 사용법:
#   .\build.ps1                # 기본 빌드 (frontend + backend)
#   .\build.ps1 -SkipFrontend  # 백엔드만 다시 빌드
#   .\build.ps1 -Release v1.0.1 # 빌드 후 GitHub Releases에 업로드

param(
    [switch]$SkipFrontend,
    [string]$Release = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "=== Competition Analyzer Build ===" -ForegroundColor Cyan
Write-Host "Root: $root"

# 1) 프론트엔드 빌드
if (-not $SkipFrontend) {
    Write-Host "`n[1/3] Frontend build..." -ForegroundColor Yellow
    Push-Location "$root\frontend"
    try {
        if (-not (Test-Path "node_modules")) {
            Write-Host "  npm install..."
            npm install
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[1/3] Frontend build SKIPPED" -ForegroundColor DarkGray
}

# 2) 백엔드 PyInstaller 빌드
Write-Host "`n[2/3] Backend PyInstaller build..." -ForegroundColor Yellow
Push-Location "$root\backend"
try {
    # 이전 빌드 정리
    if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

    pyinstaller --noconfirm Competition-Analyzer.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $exePath = "$root\backend\dist\Competition-Analyzer.exe"
    if (-not (Test-Path $exePath)) {
        throw "Build succeeded but exe not found at $exePath"
    }
    $size = (Get-Item $exePath).Length / 1MB
    Write-Host ("  Built: {0} ({1:N1} MB)" -f $exePath, $size) -ForegroundColor Green
} finally {
    Pop-Location
}

# 3) GitHub Release (선택)
if ($Release) {
    Write-Host "`n[3/3] Publishing release $Release..." -ForegroundColor Yellow

    # 버전 일치 확인
    $versionFile = "$root\backend\version.py"
    $expectedVersion = $Release.TrimStart("v")
    $content = Get-Content $versionFile -Raw
    if ($content -notmatch "__version__\s*=\s*[`"']$([regex]::Escape($expectedVersion))[`"']") {
        Write-Warning "version.py 의 __version__ 이 $expectedVersion 와 일치하지 않습니다. 먼저 version.py를 업데이트하세요."
        Write-Host "현재 버전 라인:"
        Select-String -Path $versionFile -Pattern "__version__"
        exit 1
    }

    Push-Location $root
    try {
        gh release create $Release "$root\backend\dist\Competition-Analyzer.exe" `
            --title "Competition Analyzer $Release" `
            --notes "Release $Release" `
            --latest
        if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
    } finally {
        Pop-Location
    }
    Write-Host "  Released $Release" -ForegroundColor Green
} else {
    Write-Host "`n[3/3] Release SKIPPED (use -Release v1.x.x to publish)" -ForegroundColor DarkGray
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "EXE: $root\backend\dist\Competition-Analyzer.exe"
