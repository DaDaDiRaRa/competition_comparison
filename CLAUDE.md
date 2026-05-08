# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Competition Analyzer is a full-stack application for analyzing architectural competition proposals. It uses Claude AI to extract and compare design information across multiple submissions.

**Tech Stack:**

- Backend: FastAPI (Python 3.x)
- Frontend: React 18 + Vite
- AI: Anthropic Claude (claude-sonnet-4-6) via Anthropic API
- PDF Processing: PyMuPDF (fitz) — primary rasterizer in `services/utils.py`
- Database: Custom JSON-based storage
- Desktop: pywebview (native window) + pystray (tray icon) via `launcher.py`

## Architecture

### Backend (FastAPI)

Located in `competition-analyzer/backend/`, the FastAPI application serves four main routers:

1. **`routers/accumulate.py`** - Data accumulation pipeline (PDF → JSON 추출만 담당)
   - Processes competition briefs and submission PDFs
   - Extracts design information using Claude AI
   - Streams progress via Server-Sent Events
   - **비교분석은 별도 단계로 분리** — `_brief.json`과 `submissions/*.json`만 생성하고 종료
   - 추출 완료 즉시 각 제출물의 개별 리포트(`*_report.html`)도 생성
   - `GET /projects/{facility_type}/{competition_id}/report` serves saved `_report.html` via `FileResponse`
   - `GET /projects/{facility_type}/{competition_id}/submissions/{company}/report` serves individual submission report HTML
   - `POST /projects/{facility_type}/{competition_id}/rerun-compare` runs compare + pattern + report on stored JSONs; 개별 제출물 리포트도 재생성 (저장된 프로젝트 카드의 "비교분석 실행" 버튼이 이 엔드포인트 호출)
   - `POST /projects/{facility_type}/{competition_id}/add-submission` adds a single submission to existing project

2. **`routers/diagnose.py`** - New proposal diagnosis
   - Analyzes a single submission against accumulated patterns
   - Compares against historical data for the facility type
   - Returns comparison insights

3. **`routers/patterns.py`** - Pattern management
   - Stores and retrieves design patterns by facility type
   - Rebuilds patterns from accumulated data
   - Used by diagnose mode for comparison context

4. **`routers/settings.py`** - Configuration management
   - Manages app_settings.json (database path, API key, DPI settings)
   - Returns facility types and configuration

**Core Services:**

- `services/db_manager.py` - JSON-based database for projects, patterns, and reports
  - `save_submission_report(facility_type, competition_id, company, html)` — saves `*_report.html` next to submission JSON, sets `has_sub_report=True` in `_meta.json`
  - `get_submission_report_path(facility_type, competition_id, company)` — returns Path to submission report HTML
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
- `services/data_extractor.py` - Extracts structured design data from pages
- `services/llm_client.py` - Claude API 호출 래퍼 (`call_messages()`). `anthropic.Anthropic()` 직접 호출만 사용
- `services/comparator.py` - Compares proposals against accumulated patterns; uses `.replace()` (not `.format()`) for prompt templating to avoid KeyError with JSON braces; `max_tokens=32000` for compare (응답 잘림 방지)
- `services/report_generator.py` - Generates HTML comparison reports from comparison data (no extra Claude API calls; uses existing comparison JSON)
- `services/submission_report_generator.py` - **개별 제출물 HTML 리포트 생성** (LLM 호출 없음, 순수 Python 렌더링). `generate_submission_report(sub_doc: dict) -> str`. 섹션: 표지정보, 설계컨셉, 정량데이터, 평면구성, 배치·조경, 단면분석, 입면·파사드, 지속가능성, 구조·기술, 페이지 구성 차트.
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser
- `services/pdf_rasterizer.py` - Legacy fallback rasterizer using pdftoppm/pdf2image (not used by default)

**Desktop App Files (PyInstaller 빌드용):**

- `launcher.py` - pywebview 네이티브 윈도우 + pystray 트레이 아이콘으로 FastAPI 서버를 임베드해서 실행. 세션 종료 시 API 키 메모리에서 삭제.
- `updater.py` - GitHub Releases에서 최신 버전 체크 및 자동 업데이트
- `Competition-Analyzer.spec` - PyInstaller onefile 빌드 스펙
- `build.ps1` (in `competition-analyzer/`) - 프론트엔드 빌드 → PyInstaller → GitHub Release 자동화

**Configuration:**

- `config.py` - Facility types, page types, comparison axes, Claude model ID, DPI settings
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)

Located in `competition-analyzer/frontend/`, the app has three main tabs:

1. **AccumulateMode** - PDF에서 JSON 추출만 담당
   - Shows `ProjectList` component at top — 시설 유형 탭으로 필터링되는 저장된 프로젝트 목록
   - Upload brief PDF (선택), submissions JSON, and submission PDFs
   - Processes each submission to extract design data
   - Shows real-time progress via `ProgressLog`
   - Stores data in configured `db_path`
   - 추출 완료 후 "저장된 프로젝트에서 비교분석을 실행하세요" 안내 표시 (비교분석은 ProjectList에서)

2. **DiagnoseMode** - Analyzes new submissions
   - Upload facility type, brief PDF, and a single submission PDF
   - Compares against accumulated patterns
   - Returns comparison results and insights

3. **SettingsPanel** - Configuration
   - Set database path, Anthropic API key, Claude model, DPI settings
   - View facility types and manage patterns (rebuild, view)

**Key Components:**

- `AccumulateMode/ProjectList.jsx` - 저장된 프로젝트 목록. 시설 유형 탭 → 선택한 유형의 프로젝트 카드. 각 카드에: 제출물 목록(결과 뱃지 + 회사명 + "리포트" 링크), "비교분석 실행" 버튼, "+ 제안서 추가" 버튼, "비교 리포트 열기" 링크. "리포트" 링크는 `has_sub_report=true`인 제출물에만 표시.
- `common/ProgressLog.jsx` - Real-time SSE log display with progress bars (`▓░` style), current item highlight (blue background + left border), and elapsed time counter (+Ns)

**API Communication:**

- `src/api/client.js` - All backend communication
- Uses Server-Sent Events (SSE) for streaming pipeline progress
- `getReportUrl(facilityType, competitionId)` — URL for opening comparison report HTML
- `getSubmissionReportUrl(facilityType, competitionId, company)` — URL for opening individual submission report HTML (`encodeURIComponent` applied to company)
- `rerunCompare(facilityType, competitionId)` streams SSE for compare-only run (저장된 프로젝트 카드에서 호출)
- All SSE events include `_timestamp` (pipeline start time in ms) for elapsed time display
- Endpoints: `/api/accumulate`, `/api/diagnose`, `/api/patterns`, `/api/settings`

**Styling:**

- Inline styles (no CSS framework)
- Dark theme (#0f1117 background, #90cdf4 accent)
- Components use consistent style object pattern

## Common Development Tasks

### Running the Application

**Dev mode (browser):**

1. **Backend** (terminal 1)

   ```powershell
   cd competition-analyzer/backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   - API runs at `http://localhost:8000`
   - Auto-reloads on code changes

2. **Frontend** (terminal 2)

   ```powershell
   cd competition-analyzer/frontend
   npm install  # First time only
   npm run dev
   ```

   - Dev server runs at `http://localhost:5173`
   - Proxies `/api/*` to backend at `http://localhost:8000`

**Desktop app mode (pywebview):**

```powershell
cd competition-analyzer/backend
..\venv\Scripts\python.exe launcher.py
```

### Building Desktop App (.exe)

```powershell
cd competition-analyzer
.\build.ps1              # 빌드만
.\build.ps1 -Release v1.0.0  # 빌드 + GitHub Release 게시
```

Output: `competition-analyzer/backend/dist/Competition-Analyzer.exe`

### Testing Backend Changes

The backend uses form data multipart uploads for:

- PDF files (brief_pdf — optional, submission_pdfs)
- JSON strings (submissions_json)
- Form fields: `facility_type`, `competition_name`, `year` (필수), `client`, `location` (선택, 빈 문자열 허용)

Test with curl or Postman by uploading files to:

- `POST /api/accumulate/run` - PDF → JSON 추출 (비교분석 미실행)
- `POST /api/accumulate/projects/{facility_type}/{competition_id}/rerun-compare` - 비교분석 + 패턴 + 리포트 생성
- `POST /api/diagnose/run` - Single submission diagnosis

## Key Data Flow Patterns

**Accumulate Pipeline (데이터 축적):**

1. Upload brief PDF (선택) + submissions JSON + submission PDFs
2. Backend classifies pages (page_classifier)
3. Extracts design data from each page (data_extractor)
4. Saves `_brief.json` and `submissions/*.json` to DB
5. **즉시** 개별 제출물 리포트 생성 → `submissions/{slug}_{result}_report.html` 저장, `_meta.json`에 `has_sub_report=true` 설정
6. Frontend receives `complete` SSE event
7. **여기서 종료** — 비교분석은 사용자가 ProjectList에서 별도로 실행

**Compare Pipeline (저장된 프로젝트의 "비교분석 실행"):**

1. Load existing `_brief.json` and `submissions/*.json` from DB (no PDF re-processing)
2. Run `compare_submissions` → save `_comparison.json`
3. Rebuild patterns for facility type
4. Generate HTML comparison report → save `_report.html`
5. 모든 제출물 개별 리포트 재생성 (기존 프로젝트 소급 처리 포함)
6. Stream SSE progress; ProjectList card shows inline ProgressLog and "비교 리포트 열기" 링크

**Diagnose Pipeline:**

1. Upload facility type + brief PDF + submission PDF
2. Classify and extract data from submission
3. Retrieve accumulated patterns for facility type
4. Compare submission against patterns (comparator)
5. Return comparison results with insights

## Configuration Files

**`app_settings.json`** (auto-created in backend directory):

```json
{
  "db_path": "M:\\06_설계사업6본부\\...",
  "anthropic_api_key": "",
  "raster_dpi_classify": 72,
  "raster_dpi_extract": 150,
  "model_id": "claude-sonnet-4-6"
}
```

- `anthropic_api_key`는 데스크톱 앱에서는 세션 전용(메모리만, 재시작 시 초기화). dev 모드에서는 파일에 저장됨.
- **Environment fallback:** `ANTHROPIC_API_KEY` env var

## Important Notes

- **Pipeline 분리:** 데이터 축적(`/api/accumulate/run`)은 PDF → JSON 추출까지만 수행. 비교분석/패턴/리포트는 저장된 프로젝트의 "비교분석 실행" 버튼(`/api/accumulate/projects/{ft}/{cid}/rerun-compare`)에서만 실행. 축적 단계에서 자동으로 비교분석을 트리거하지 않는다.
- **Database Location:** `M:\06_설계사업6본부\...\KUNWON_COMPETITION_DB` (하드코딩). 컴퓨터마다 `app_settings.json`의 `db_path`를 수정. 각 competition: `{db_path}/{facility_type}/{competition_id}/` — `_meta.json`, `_brief.json` (지침서 있을 때만), `_comparison.json` (비교분석 후), `_report.html` (비교분석 후), `submissions/*.json`, `submissions/*_report.html` (개별 리포트).
- **Individual Submission Reports:** `generate_submission_report(sub_doc)` in `submission_report_generator.py` — LLM 호출 없음, 토큰 0. 모든 추출 파이프라인(`run`, `run-single`, `add-submission`, `rerun-compare`)에서 자동 생성. 파일명: `{slug}_{result}_report.html` (JSON과 동일 디렉토리). `has_sub_report=true`가 `_meta.json`에 설정된 제출물만 ProjectList에서 "리포트" 버튼 표시.
- **`extracted_data` 구조:** `sub_doc["extracted_data"]`의 각 섹션(`cover`, `concept`, `floor_plan` 등)은 **리스트**로 저장됨 (`[{...}, {...}]`). `cover`처럼 단일처럼 보여도 실제론 리스트. `submission_report_generator.py`에서 `cover_raw[0]`으로 첫 항목을 꺼내서 사용. `_safe_list()` 헬퍼로 None/비리스트 안전 처리.
- **Claude Model:** Currently `claude-sonnet-4-6` in `app_settings.json`. `config.py`의 `MODEL_ID`는 기본값 fallback용.
- **LLM 호출:** 모든 Claude 호출은 `services/llm_client.py::call_messages()` 를 통해 이루어짐. `anthropic.Anthropic()` SDK 직접 호출. 502 오류는 Anthropic 서버 일시 장애이므로 재시도.
- **DPI Settings:** Classify uses 72 DPI (fast), extract uses 150 DPI (detailed). Set in `app_settings.json`.
- **CORS:** Vite dev server (5173) and localhost:3000 are allowed.
- **File Naming:** Components follow PascalCase. API paths are kebab-case.
- **Facility Types:** 13 types defined in config.py (public, residential, office, reconstruction 등) — `FACILITY_TYPES` 딕셔너리 참조
- **Page Types:** 20 classification categories — `COVER`, `TOC_HERO`, `CONCEPT`, `FLOOR_PLAN`, `SECTION`, `ELEVATION`, `SITE_PLAN`, `RENDERING_EXT`, `RENDERING_INT`, `SPECIAL_SPACE`, `SITE_CONTEXT`, `LANDSCAPE`, `CIRCULATION`, `HEALTH_CENTER`, `TECHNICAL`, `AREA_TABLE`, `SUSTAINABILITY`, `UNIT_PLAN`, `INCENTIVE_TABLE`, `BRANDING`
- **Comparison Axes:** 7 dimensions for analysis (concept, mass, landscape, program, facade, technical, quantitative)
- **Optional Form Fields:** `client`, `location`은 백엔드에서 `Form("")`로 선언되어 빈 문자열 허용. 프론트엔드 검증도 옵션 처리.
- **HTML Comparison Report:** Generated at end of compare pipeline using existing comparison JSON — no extra Claude API calls. Includes: submission cards, 7-axis comparison table with score bars and compliance tags (지침충족/부분충족/미충족), ranking, key differentiators, winner strength analysis. Winner entries highlighted in gold.
- **Report Generation Rule:** `report_generator.py`와 `submission_report_generator.py` 모두 Claude API 호출 금지. 기존 데이터를 HTML로 렌더링만.
- **Prompt Templating Rule:** `comparator.py` prompt templates use `.replace("{key}", value)` instead of `.format(key=value)` — the JSON schema examples in prompts contain literal braces that would cause `KeyError` with `.format()`.
- **ProgressLog Events:** All SSE events passed to `ProgressLog` must include `_timestamp` (ms since epoch, set at pipeline start) for elapsed time display. The component uses `Date.now() - events[0]._timestamp` for the `+Ns` counter on the current item.
- **PDF Rasterizer:** Primary rasterizer is `services/utils.py::rasterize_pdf` using PyMuPDF. `services/pdf_rasterizer.py` (pdftoppm/pdf2image) is legacy and not called by the current pipeline.
- **ProjectList Filtering:** 저장된 프로젝트는 `facility_type` 탭으로 필터링. 데이터가 존재하는 시설 유형만 탭으로 노출되며, 첫 번째 유형이 자동 선택됨. 각 탭에 해당 유형의 프로젝트 개수가 함께 표시됨.
- **New Machine Setup:** `git clone` 후 `pip install -r requirements.txt` + `npm install` 실행. `app_settings.json`의 `db_path`를 해당 컴퓨터 경로로 수정하고 `anthropic_api_key`를 입력 (또는 `ANTHROPIC_API_KEY` env var 설정).
- **Page Taxonomy 갱신 방법:** `db_manager.py::init_db()`는 `_config/page_taxonomy.json`이 없을 때만 생성함. PAGE_TYPES를 추가한 후 기존 DB에 반영하려면 `{db_path}/_config/page_taxonomy.json` 파일을 삭제 후 백엔드를 1회 재시작.
- **재건축사업 타입:** `facility_type="reconstruction"` 추가. 전용 PAGE_TYPES 3개: `UNIT_PLAN`(단위세대 평면+면적표), `INCENTIVE_TABLE`(인센티브 용적률 비교표, 타일 분할 적용), `BRANDING`(브랜드·슬로건). COMPARISON_AXES는 기존 7개 그대로 사용.
