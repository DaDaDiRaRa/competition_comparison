# 설계공모 경쟁분석 — 개발자 가이드

이 문서는 **코드 수정 · 배포 · 테마 변경**을 담당하는 개발자/IT 담당자용입니다.

---

## 목차

1. [개발 환경 설치](#1-개발-환경-설치)
2. [개발 모드 실행](#2-개발-모드-실행)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [GCP 배포](#4-gcp-배포)
5. [테마 / 색상 변경](#5-테마--색상-변경)
6. [디버깅 / 로그](#6-디버깅--로그)
7. [참고 문서](#7-참고-문서)

---

## 1. 개발 환경 설치

### 필요 환경

- Python 3.10 이상
- Node.js 18 이상
- Git

### 설치

```powershell
git clone <저장소 주소>
cd competition_comparison

# 백엔드
cd backend
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

기본 파이프라인은 PyMuPDF + Claude vision으로 동작하므로 보통 불필요.

---

## 2. 개발 모드 실행

터미널 2개를 사용합니다.

**터미널 1 — 백엔드 (FastAPI hot reload)**

```powershell
cd backend
.\venv\Scripts\activate
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**터미널 2 — 프론트엔드 (Vite dev server)**

```powershell
cd frontend
npm run dev
```

브라우저에서 `http://localhost:5173` 접속. `/api/*` 요청은 자동으로 `localhost:8000`으로 프록시됩니다 (`vite.config.js`).

---

## 3. 프로젝트 구조

```text
competition_comparison/
├── backend/
│   ├── main.py                    # FastAPI 진입점
│   ├── config.py                  # FACILITY_TYPES, axes, settings
│   ├── requirements.txt           # 로컬 개발용
│   ├── requirements-server.txt    # Docker/Cloud Run용 (항상 동기화)
│   ├── requirements-ocr.txt       # 선택 (PaddleOCR)
│   ├── routers/                   # accumulate / diagnose / patterns / settings / brief ...
│   ├── services/                  # comparator / db_manager / report_generator ...
│   └── models/                    # Pydantic 스키마
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api/client.js          # 모든 백엔드 통신
│   │   ├── components/            # AccumulateMode / DiagnoseMode / BriefMode ...
│   │   ├── constants/index.js     # GRADE_COLOR, GRADE_BG
│   │   ├── hooks/useMeta.jsx      # 시설유형/페이지타입/평가축 단일 소스
│   │   ├── kunwon-tokens.css      # CSS 변수 단일 소스 (색상·타이포·간격)
│   │   └── theme.js               # 색 토큰 명세 (참고용)
│   └── package.json
├── tools/
│   ├── audit_tokens.py            # 인라인 hex 하드코딩 감사
│   ├── change_theme.py            # 일괄 색상 교체
│   └── eval/                      # 추출 정확도 평가 하네스
├── tests/
│   └── test_docx_extractor.py     # DOCX 흐름 단위 테스트
├── .github/workflows/deploy.yml   # GitHub Actions 자동 배포
├── Dockerfile                     # 멀티스테이지 빌드 (Node → Python)
├── DEPLOYMENT.md                  # GCP 배포 설정값 참조
├── DEVELOPER.md                   # 이 문서
└── CLAUDE.md                      # 아키텍처/룰 상세 (Claude Code 자동 로드)
```

상세 아키텍처 · 데이터 플로우 · 코드 룰은 [CLAUDE.md](CLAUDE.md)를 참고하세요.

---

## 4. GCP 배포

**`main` 브랜치에 push하면 GitHub Actions(`.github/workflows/deploy.yml`)가 자동으로 Docker 이미지를 빌드하고 Cloud Run에 배포합니다.**

```bash
git push origin main
# → 자동 빌드 → 자동 배포
```

GCP 프로젝트 정보, 환경변수, 트러블슈팅은 [DEPLOYMENT.md](DEPLOYMENT.md) 참고.

### 신규 Python 패키지 추가 시 주의

`backend/requirements.txt`(로컬용)와 `backend/requirements-server.txt`(Docker용) **두 파일을 반드시 함께 수정**해야 합니다. `requirements-server.txt` 누락 시 GCP 배포 후 `ModuleNotFoundError` 발생.

---

## 5. 테마 / 색상 변경

현재 테마: **화이트 + 건원 RED 액센트** (`#e60012`).

### 색상 정의 위치

| 파일 | 역할 |
| ---- | ---- |
| `frontend/src/kunwon-tokens.css` | **단일 소스** — 모든 CSS 변수. 여기서만 수정 |
| `frontend/src/theme.js` | 색 토큰 명세 (참고용, 컴포넌트가 import하지 않음) |
| `frontend/src/constants/index.js` | 등급(A~E) 색상 + 충족도 색상 |
| `backend/services/report_generator.py` | 비교 리포트 HTML — `:root` CSS 변수 26개 (독립 문서) |

### 일괄 교체 (프리셋)

```powershell
python tools/change_theme.py <preset>
# 예: python tools/change_theme.py charcoal
```

### 인라인 하드코딩 감사

```powershell
python tools/audit_tokens.py
# → DESIGN_AUDIT.md 생성 (파일·줄 번호·교체 토큰 목록)
```

### 등급 색상 (5-level, A~E)

| 등급 | 텍스트 색 | 배경 색 |
| ---- | --------- | ------- |
| A | `#16a34a` | `#dcfce7` |
| B | `#0891b2` | `#cffafe` |
| C | `#ca8a04` | `#fef3c7` |
| D | `#ea580c` | `#fed7aa` |
| E | `#dc2626` | `#fee2e2` |

---

## 6. 디버깅 / 로그

### 개발 모드 로그

| 위치 | 내용 |
| ---- | ---- |
| 백엔드 콘솔 | uvicorn + FastAPI 로그 (LLM 호출, 캐시 히트 등) |
| 브라우저 DevTools | 프론트 콘솔 |

### LLM 호출 관련

- **502 오류** → Anthropic 서버 일시 장애. 재시도.
- **모델 ID:**
  - `claude-sonnet-4-6` — 분류 / 추출 / 비교 / 진단 전체
- **캐시 히트 로그:** `services/llm_client.py::call_messages()`가 응답 `usage.cache_read_input_tokens` 출력. rerun-compare 시 90% 캐시 할인 확인.
- **2-pass blind-reveal:** Pass 1(블라인드 채점) → Pass 2(리빌·사후 분석). `services/comparator.py` 참고.

### 자주 마주치는 문제

| 증상 | 원인 / 해결 |
| ---- | ----------- |
| GCP 배포 후 구 버전이 뜸 | GitHub Actions 실행 여부 확인. 실패했으면 Actions 탭 로그 확인 |
| GCP 배포 후 `ModuleNotFoundError` | `requirements-server.txt`에 패키지 누락. 두 파일 동기화 후 재push |
| API 키가 자꾸 사라짐 | 의도된 동작 — 보안상 디스크 미저장. 재시작마다 설정 탭에서 재입력 |
| PDF 400 오류 (이미지 크기) | `_stack_images_vertically()` JPEG 출력 + `_STACK_MAX_DIM=7500` 확인 |

---

## 7. 참고 문서

- [CLAUDE.md](CLAUDE.md) — 아키텍처 / 데이터 플로우 / 코드 룰 상세
- [DEPLOYMENT.md](DEPLOYMENT.md) — GCP 설정값 / 트러블슈팅
- [Anthropic API 문서](https://docs.anthropic.com)
- [FastAPI 문서](https://fastapi.tiangolo.com)
- [Vite 문서](https://vitejs.dev)
