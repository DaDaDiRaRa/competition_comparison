# 설계공모 경쟁분석 — 개발자 가이드

이 문서는 **코드 수정 · 빌드 · 배포 · 테마 변경**을 담당하는 개발자/IT 담당자용입니다.
일반 사용자가 실행 파일을 받아 사용하는 흐름은 [README.md](README.md)를 참고하세요.

---

## 목차

1. [개발 환경 설치](#1-개발-환경-설치)
2. [개발 모드 실행](#2-개발-모드-실행)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [빌드 (PyInstaller)](#4-빌드-pyinstaller)
5. [배포 (zip 패키징)](#5-배포-zip-패키징)
6. [테마 / 색상 변경](#6-테마--색상-변경)
7. [디버깅 / 로그](#7-디버깅--로그)
8. [참고 문서](#8-참고-문서)

---

## 1. 개발 환경 설치

### 필요 환경

- Python 3.10 이상
- Node.js 18 이상
- (선택) Git

### 설치

```powershell
git clone <저장소 주소>
cd competition_comparison

# 백엔드
cd competition-analyzer/backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# 프론트엔드
cd ..\frontend
npm install
```

### OCR 의존성 (선택)

이미지 기반(텍스트 없는) PDF에 OCR을 적용하려면 추가 설치:

```powershell
pip install -r requirements-ocr.txt   # PaddleOCR + paddlepaddle
```

기본 파이프라인은 PyMuPDF + Claude vision으로 동작하므로 보통 불필요. 미설치 시 `services/utils.py::ocr_page()`가 자동으로 스킵.

---

## 2. 개발 모드 실행

터미널 2개를 사용합니다.

**터미널 1 — 백엔드 (FastAPI hot reload)**

```powershell
cd competition-analyzer/backend
.\venv\Scripts\activate
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**터미널 2 — 프론트엔드 (Vite dev server)**

```powershell
cd competition-analyzer/frontend
npm run dev
```

브라우저에서 `http://localhost:5173` 접속. `/api/*` 요청은 자동으로 `localhost:8000`으로 프록시됩니다 (`vite.config.js`).

---

## 3. 프로젝트 구조

```
competition_comparison/
├── competition-analyzer/
│   ├── backend/
│   │   ├── main.py                    # FastAPI 진입점
│   │   ├── launcher.py                # PyWebView/PyInstaller 진입점
│   │   ├── config.py                  # FACILITY_TYPES, axes, settings
│   │   ├── competition_analyzer.spec  # PyInstaller 빌드 spec
│   │   ├── requirements.txt
│   │   ├── requirements-ocr.txt       # 선택 (PaddleOCR)
│   │   ├── routers/                   # accumulate / diagnose / patterns / settings
│   │   ├── services/                  # comparator / db_manager / report_generator ...
│   │   └── models/                    # Pydantic 스키마
│   └── frontend/
│       ├── src/
│       │   ├── App.jsx
│       │   ├── api/client.js          # 모든 백엔드 통신
│       │   ├── components/            # AccumulateMode / DiagnoseMode / Settings ...
│       │   ├── constants/index.js     # GRADE_COLOR, GRADE_BG, COMPLIANCE_COLOR
│       │   ├── hooks/useMeta.jsx      # 시설유형/페이지타입/평가축 단일 소스
│       │   └── theme.js               # 색 토큰 명세 (참고용)
│       └── package.json
├── tools/
│   └── change_theme.py                # 일괄 색상 교체
├── build.ps1                          # 빌드 스크립트
├── README.md                          # 사용자 매뉴얼
├── DEVELOPER.md                       # 이 문서
└── CLAUDE.md                          # 아키텍처/룰 상세 (Claude Code 자동 로드)
```

상세 아키텍처 · 데이터 플로우 · 코드 룰은 [CLAUDE.md](CLAUDE.md)를 참고하세요. 백엔드 구조, 2-pass blind-reveal 비교, 패턴 빌드, 캐싱 전략, 등급(A~E) 시스템 등 모든 설계 결정의 배경이 정리되어 있습니다.

---

## 4. 빌드 (PyInstaller)

### 한 번에 빌드

```powershell
.\build.ps1
```

저장소 루트에서 실행. `npm install` → `vite build` → PyInstaller가 순차 실행됩니다.

### 단계별 빌드 (디버깅용)

```powershell
# 1) 프론트엔드 빌드
cd competition-analyzer/frontend
npm run build              # → frontend/dist/

# 2) 백엔드 + 프론트 dist를 PyInstaller로 묶기
cd ..\backend
.\venv\Scripts\activate
python -m PyInstaller competition_analyzer.spec --noconfirm
# → backend/dist/CompetitionAnalyzer/ (~120MB)
```

### 산출물 구조

```
backend/dist/CompetitionAnalyzer/
├── CompetitionAnalyzer.exe    # 실행 파일 (~14MB)
└── _internal/                 # Python interpreter + 모든 의존성 + frontend_dist (~120MB)
    ├── frontend_dist/         # 빌드된 React 정적 파일
    ├── webview/               # PyWebView 백엔드
    ├── clr_loader/            # .NET 로더
    └── ... (numpy, fitz, anthropic 등)
```

### 빌드 주의사항

- **PyWebView는 .NET 어셈블리(`System`, `System.Windows`, `System.Drawing`)를 동적 로드**합니다. 정적 분석으로는 잡히지 않으므로 spec의 다음 항목을 절대 빼지 마세요:

  ```python
  webview_datas, webview_binaries, webview_hidden = collect_all('webview')
  clr_datas, clr_binaries, clr_hidden = collect_all('clr_loader')
  pythonnet_datas, pythonnet_binaries, pythonnet_hidden = collect_all('pythonnet')
  ```

- **`console=False` (windowed 빌드)** 이므로 stdout/stderr가 어디에도 표시되지 않습니다. 디버깅 로그는 `~/.competition-analyzer/app.log`로 출력 (`launcher.py::_setup_logging()`이 `RotatingFileHandler` 설정 — 2MB×3 백업).

- **`build.ps1`이 PyInstaller stderr(INFO 로그)를 에러로 인식해 실패 표시될 수 있으나 산출물은 정상.** 의심되면 직접 `python -m PyInstaller competition_analyzer.spec --noconfirm`으로 실행해 검증.

- **PaddleOCR 등 무거운 의존성은 spec의 `excludes`에 명시.** 추가하면 번들 용량이 크게 늘어나니 신중히.

---

## 5. 배포 (zip 패키징)

### zip 만들기

```powershell
cd competition-analyzer\backend\dist
Compress-Archive -Path .\CompetitionAnalyzer\* -DestinationPath .\CompetitionAnalyzer.zip
```

생성된 `CompetitionAnalyzer.zip`(~120MB)을 사내 공유 드라이브에 올리거나 직접 전달.

### 배포 시 사용자에게 안내할 것

| 항목 | 안내 |
| --- | --- |
| 압축 해제 | 폴더 전체를 원하는 위치(예: `C:\Apps\`)에 풀 것. **`.exe`만 따로 빼면 동작 X** (`_internal/` 필수) |
| API 키 | 사용자가 직접 [console.anthropic.com](https://console.anthropic.com)에서 발급해 첫 실행 시 입력 |
| DB 경로 | M:\ 네트워크 드라이브 접근 권한 필요. 미접근 시 설정 탭에서 로컬 경로(`C:\CompetitionDB` 등)로 변경 |
| Defender 경고 | "추가 정보" → "실행" (서명되지 않은 사내 배포본) |
| WebView2 런타임 | Windows 10/11 기본 포함. 없으면 [Microsoft 사이트](https://developer.microsoft.com/microsoft-edge/webview2/)에서 다운로드 |

### 새 버전 배포

사용자 데이터(DB 경로 안의 모든 파일)는 앱 폴더와 무관합니다. 새 zip을 받아 폴더만 교체하면 같은 DB 경로를 그대로 사용합니다.

---

## 6. 테마 / 색상 변경

기본 테마는 **화이트 톤 + 네이비 액센트**.

### 빠른 교체 (프리셋)

```powershell
python tools/change_theme.py <preset>
```

| 프리셋 | 액센트 | 강조 | 분위기 |
| --- | --- | --- | --- |
| `navy` (현재 기본) | `#1e3a8a` 네이비 | `#b8860b` 골드 | Classic Professional — 건축·금융·법무 |
| `charcoal` | `#334155` 차콜 | `#0d9488` 틸 | Modern Sophisticated — 컨설팅·엔지니어링 |
| `forest` | `#15803d` 포레스트 | `#d97706` 앰버 | Organic Warm — 친환경·자연 분야 |
| `burgundy` | `#7f1d1d` 버건디 | `#fbbf24` 골드 | Luxury — 럭셔리 부동산·호텔 |
| `indigo` | `#4f46e5` 인디고 | `#ec4899` 마젠타 | Tech Vibrant — 테크 스타트업 |
| `blackgold` | `#171717` 블랙 | `#d4af37` 골드 | Minimal Luxury — 미니멀 럭셔리 |

### 직접 색 지정

```powershell
python tools/change_theme.py custom --accent "#2563eb" --hover "#1d4ed8" --highlight "#f59e0b"
```

### 적용 후 빌드 재실행

색 교체는 소스 파일을 직접 치환하므로 화면 반영을 위해 빌드 재실행이 필요합니다:

```powershell
cd competition-analyzer/frontend && npm run build
cd ../backend && python -m PyInstaller competition_analyzer.spec --noconfirm
# (또는 루트의 .\build.ps1)
```

### 색상 정의 위치 (수동 편집 시)

| 파일 | 역할 |
| --- | --- |
| [`competition-analyzer/frontend/src/theme.js`](competition-analyzer/frontend/src/theme.js) | 색 토큰 단일 명세 (참고/문서용 — 컴포넌트는 import하지 않음) |
| [`competition-analyzer/frontend/src/constants/index.js`](competition-analyzer/frontend/src/constants/index.js) | 등급(A~E) 색상 + 충족도 색상 |
| [`competition-analyzer/backend/services/report_generator.py`](competition-analyzer/backend/services/report_generator.py) | 비교 리포트 HTML — `_CSS`의 `:root` CSS 변수 26개 |
| 각 `.jsx` 컴포넌트 + `submission_report_generator.py` / `diagnosis_report_generator.py` | 인라인 hex |

> 가장 빠른 방법은 `tools/change_theme.py` 사용. 수동 편집은 미세 조정·신규 색 추가 시에만 권장.

### 등급 색상 (5-level, A~E)

화이트 BG 기준:

| 등급 | 의미 | 텍스트 색 | 배경 색 |
| --- | --- | --- | --- |
| A | 최우수 | `#16a34a` | `#dcfce7` |
| B | 우수 | `#0891b2` | `#cffafe` |
| C | 보통 | `#ca8a04` | `#fef3c7` |
| D | 미흡 | `#ea580c` | `#fed7aa` |
| E | 불량 | `#dc2626` | `#fee2e2` |

`constants/index.js`의 `GRADE_COLOR` / `GRADE_BG`에 정의.

---

## 7. 디버깅 / 로그

### 로그 위치

| 위치 | 내용 |
| --- | --- |
| `~/.competition-analyzer/app.log` | PyInstaller windowed 빌드의 launcher 로그 (2MB×3 백업) |
| 백엔드 콘솔 (개발 모드) | uvicorn + FastAPI 로그 |
| 브라우저 DevTools (개발 모드) | 프론트 콘솔 |

치명적 오류는 `launcher.py::_show_error_dialog()`가 Win32 MessageBox로 표시.

### LLM 호출 관련

- **502 오류** → Anthropic 서버 일시 장애. 재시도.
- **모델 ID:**
  - `claude-sonnet-4-6` — 추출 / 비교 / 진단 (`config.py::MODEL_ID`)
  - `claude-haiku-4-5-20251001` — 페이지 분류 (`config.py::MODEL_ID_CLASSIFY`)
- **캐시 히트 로그:** `services/llm_client.py::call_messages()`가 응답 `usage.cache_read_input_tokens` 출력. rerun-compare 시 90% 캐시 할인 확인.
- **2-pass blind-reveal:** Pass 1(블라인드 채점) → Pass 2(리빌·사후 분석). `services/comparator.py` 참고.

### 자주 마주치는 빌드/배포 문제

| 증상 | 원인 / 해결 |
| --- | --- |
| `.exe` 더블클릭 후 아무 반응 없음 | `~/.competition-analyzer/app.log` 확인. .NET 어셈블리 누락이면 spec의 `collect_all('pythonnet')` 점검 |
| 앱은 뜨는데 빈 화면 | `frontend/dist/` 빌드 누락. `npm run build` 후 재빌드 |
| "DB 경로 접근 불가" | M:\ 드라이브 미마운트. 설정 탭에서 로컬 경로로 변경 |
| Defender SmartScreen 차단 | 코드 서명 인증서 미적용. 사내 배포는 "추가 정보 → 실행" 안내로 우회 |
| API 키가 자꾸 사라짐 | 의도된 동작 — 보안상 디스크 미저장. `ANTHROPIC_API_KEY` env var fallback도 가능 |

---

## 8. 참고 문서

- [CLAUDE.md](CLAUDE.md) — 아키텍처 / 데이터 플로우 / 코드 룰 상세 (Claude Code 작업 시 자동 로드)
- [README.md](README.md) — 사용자 매뉴얼
- [Anthropic API 문서](https://docs.anthropic.com)
- [PyWebView 문서](https://pywebview.flowrl.com)
- [PyInstaller 문서](https://pyinstaller.org)
- [FastAPI 문서](https://fastapi.tiangolo.com)
- [Vite 문서](https://vitejs.dev)
