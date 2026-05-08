# Competition Analyzer — 빌드 & 릴리즈 가이드

데스크톱 앱(.exe) 빌드와 GitHub Releases를 통한 자동 업데이트 배포 절차.

---

## 사전 준비 (1회만)

```powershell
# 백엔드 의존성 (PyInstaller, pystray 포함)
cd competition-analyzer/backend
pip install -r requirements.txt

# 프론트엔드 의존성
cd ../frontend
npm install

# GitHub CLI 설치 (릴리즈 게시용)
winget install --id GitHub.cli
gh auth login
```

---

## 새 버전 릴리즈 절차

### 1. 코드 수정 + 버전 번호 올리기

`competition-analyzer/backend/version.py`:
```python
__version__ = "1.0.1"   # ← 올리기
```

### 2. 빌드

```powershell
cd competition-analyzer
.\build.ps1
```

빌드 산출물: `competition-analyzer/backend/dist/Competition-Analyzer.exe`

### 3. 로컬 테스트

```powershell
.\backend\dist\Competition-Analyzer.exe
```

- 콘솔 창이 뜨고, 자동으로 브라우저가 열림
- API 키 입력 모달 확인
- 트레이 아이콘 우클릭 → "종료" 동작 확인

### 4. Git 커밋 + 태그 + 릴리즈 (한 번에)

```powershell
git add backend/version.py
git commit -m "release: v1.0.1"
git push

# 빌드 + 릴리즈 동시
.\build.ps1 -Release v1.0.1
```

또는 수동으로:
```powershell
gh release create v1.0.1 backend/dist/Competition-Analyzer.exe `
    --title "Competition Analyzer v1.0.1" `
    --notes "변경사항 메모" `
    --latest
```

### 5. 사용자 측 자동 업데이트

- 사용자가 다음에 앱을 실행하면 GitHub API로 새 버전 발견
- 콘솔에 `새 버전 v1.0.1 발견. 업데이트할까요? [Y/n]` 표시
- Y → 새 exe 다운로드 → 자동 교체 → 재실행

---

## 첫 배포 (v1.0.0)

처음 사용자에게 줄 때:
1. `.\build.ps1 -Release v1.0.0` 실행 (빌드 + 릴리즈)
2. 사용자에게 GitHub Releases 페이지 링크 또는 직접 다운로드 URL 전달:
   - `https://github.com/DaDaDiRaRa/competition_comparison/releases/latest`
3. 사용자: `Competition-Analyzer.exe` 다운로드 → 더블클릭 → API 키 입력 → 사용

⚠️ 첫 실행 시 **Windows Defender SmartScreen** 경고가 뜰 수 있음:
- "추가 정보" 클릭 → "실행" 버튼 클릭
- 코드 서명 인증서가 없어서 발생 (정상)

---

## 트러블슈팅

### 빌드가 너무 큼 (>1GB)
PaddleOCR/PaddlePaddle 의존성 때문. 사용 안 한다면 `requirements.txt`에서 제거 후 재빌드.

### "DLL load failed" 등 import 오류
`Competition-Analyzer.spec`의 `hiddenimports`에 누락된 모듈 추가.

### 자동 업데이트가 작동 안 함
- `version.py`의 `__version__`이 새 릴리즈 태그보다 낮은지 확인
- GitHub repo가 public인지 확인 (private이면 토큰 필요)
- 콘솔 로그에서 `[Updater]` 메시지 확인

### DB 경로를 바꾸고 싶음
`backend/config.py`의 `HARDCODED_DB_PATH` 수정 → 새 버전 릴리즈
