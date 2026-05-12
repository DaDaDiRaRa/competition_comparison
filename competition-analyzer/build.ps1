# Competition Analyzer — Windows 실행파일 빌드 스크립트
#
# 사용법:
#   .\build.ps1
#
# 결과:
#   competition-analyzer\backend\dist\CompetitionAnalyzer\CompetitionAnalyzer.exe

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $ProjectRoot "frontend"
$Backend = Join-Path $ProjectRoot "backend"
$Venv = Join-Path $Backend "venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Competition Analyzer — Windows 빌드" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1) 프론트엔드 빌드
Write-Host "`n[1/3] 프론트엔드 빌드 (vite build)..." -ForegroundColor Yellow
Push-Location $Frontend
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "node_modules 없음 → npm install 실행" -ForegroundColor Gray
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install 실패" }
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "vite build 실패" }
} finally {
    Pop-Location
}

# 2) PyInstaller 설치 확인
Write-Host "`n[2/3] PyInstaller 확인/설치..." -ForegroundColor Yellow
if (-not (Test-Path $Python)) {
    throw "venv 미발견: $Venv — backend에서 'python -m venv venv' 후 'pip install -r requirements.txt' 실행하세요."
}
& $Python -m pip show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller 설치 중..." -ForegroundColor Gray
    & $Python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 설치 실패" }
}

# 3) PyInstaller 실행
Write-Host "`n[3/3] PyInstaller 빌드..." -ForegroundColor Yellow
Push-Location $Backend
try {
    # 이전 빌드 산출물 정리
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

    & $Python -m PyInstaller competition_analyzer.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 빌드 실패" }
} finally {
    Pop-Location
}

$Output = Join-Path $Backend "dist\CompetitionAnalyzer\CompetitionAnalyzer.exe"
Write-Host "`n==========================================" -ForegroundColor Green
Write-Host " 빌드 완료!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host " 실행 파일: $Output" -ForegroundColor Green
Write-Host " 폴더 전체를 압축해서 배포하세요:" -ForegroundColor Green
Write-Host "   $(Join-Path $Backend 'dist\CompetitionAnalyzer\')" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
