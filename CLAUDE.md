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

## Architecture

### Backend (FastAPI)

Located in `competition-analyzer/backend/`, the FastAPI application serves four main routers:

1. **`routers/accumulate.py`** - Data accumulation pipeline (PDF → JSON 추출만 담당)
   - Processes competition briefs and submission PDFs
   - Extracts design information using Claude AI
   - Streams progress via Server-Sent Events
   - **비교분석은 별도 단계로 분리** — `_brief.json`과 `submissions/*.json`만 생성하고 종료
   - `GET /projects/{facility_type}/{competition_id}/report` serves saved `_report.html` via `FileResponse`
   - `POST /projects/{facility_type}/{competition_id}/rerun-compare` runs compare + pattern + report on stored JSONs (저장된 프로젝트 카드의 "비교분석 실행" 버튼이 이 엔드포인트 호출)

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
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
- `services/data_extractor.py` - Extracts structured design data from pages
- `services/llm_client.py` - Claude API 호출 래퍼 (`call_messages()`). `anthropic.Anthropic()` 직접 호출만 사용
- `services/comparator.py` - Compares proposals against accumulated patterns; uses `.replace()` (not `.format()`) for prompt templating to avoid KeyError with JSON braces; `max_tokens=32000` for compare (응답 잘림 방지)
- `services/report_generator.py` - Generates HTML comparison reports from comparison data (no extra Claude API calls; uses existing comparison JSON)
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser
- `services/pdf_rasterizer.py` - Legacy fallback rasterizer using pdftoppm/pdf2image (not used by default)

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
   - Stores data in `~/competition_db` (or configured `db_path`)
   - 추출 완료 후 "저장된 프로젝트에서 비교분석을 실행하세요" 안내 표시 (비교분석은 ProjectList에서)

2. **DiagnoseMode** - Analyzes new submissions
   - Upload facility type, brief PDF, and a single submission PDF
   - Compares against accumulated patterns
   - Returns comparison results and insights

3. **SettingsPanel** - Configuration
   - Set database path, Anthropic API key, Claude model, DPI settings
   - View facility types and manage patterns (rebuild, view)

**Key Components:**

- `AccumulateMode/ProjectList.jsx` - 저장된 프로젝트 목록. 상단에 시설 유형 탭(데이터가 존재하는 유형만 표시) → 선택한 유형의 프로젝트만 카드로 표시. 각 카드에 "비교분석 실행" 버튼이 있어 `rerun-compare` 엔드포인트로 SSE 스트리밍
- `common/ProgressLog.jsx` - Real-time SSE log display with progress bars (`▓░` style), current item highlight (blue background + left border), and elapsed time counter (+Ns)

**API Communication:**

- `src/api/client.js` - All backend communication
- Uses Server-Sent Events (SSE) for streaming pipeline progress
- `getReportUrl(facilityType, competitionId)` returns URL for opening saved HTML report
- `rerunCompare(facilityType, competitionId)` streams SSE for compare-only run (저장된 프로젝트 카드에서 호출)
- All SSE events include `_timestamp` (pipeline start time in ms) for elapsed time display
- Endpoints: `/api/accumulate`, `/api/diagnose`, `/api/patterns`, `/api/settings`

**Styling:**

- Inline styles (no CSS framework)
- Dark theme (#0f1117 background, #90cdf4 accent)
- Components use consistent style object pattern

## Common Development Tasks

### Running the Application

1. **Backend** (terminal 1)

   ```powershell
   cd competition-analyzer/backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   - API runs at `http://localhost:8000`
   - Auto-reloads on code changes
   - Check health at `http://localhost:8000/api/health`

2. **Frontend** (terminal 2)

   ```powershell
   cd competition-analyzer/frontend
   npm install  # First time only
   npm run dev
   ```

   - Dev server runs at `http://localhost:5173`
   - Proxies `/api/*` to backend at `http://localhost:8000`
   - Hot module reloading enabled

### Building

**Frontend (production build):**

```powershell
cd competition-analyzer/frontend
npm run build
```

Output: `dist/` directory

### Testing Backend Changes

The backend uses form data multipart uploads for:

- PDF files (brief_pdf — optional, submission_pdfs)
- JSON strings (submissions_json)
- Form fields: `facility_type`, `competition_name`, `year` (필수), `client`, `location` (선택, 빈 문자열 허용)

Test with curl or Postman by uploading files to:

- `POST /api/accumulate/run` - PDF → JSON 추출 (비교분석 미실행)
- `POST /api/accumulate/projects/{facility_type}/{competition_id}/rerun-compare` - 비교분석 + 패턴 + 리포트 생성
- `POST /api/diagnose/run` - Single submission diagnosis

### Key Data Flow Patterns

**Accumulate Pipeline (데이터 축적):**

1. Upload brief PDF (선택) + submissions JSON + submission PDFs
2. Backend classifies pages (page_classifier)
3. Extracts design data from each page (data_extractor)
4. Saves `_brief.json` and `submissions/*.json` to DB
5. Frontend receives `complete` SSE event with `report_available: false`
6. **여기서 종료** — 비교분석은 사용자가 ProjectList에서 별도로 실행

**Compare Pipeline (저장된 프로젝트의 "비교분석 실행"):**

1. Load existing `_brief.json` and `submissions/*.json` from DB (no PDF re-processing)
2. Run `compare_submissions` → save `_comparison.json`
3. Rebuild patterns for facility type
4. Generate HTML report → save `_report.html`
5. Stream SSE progress; ProjectList card shows inline ProgressLog and "HTML 리포트 열기" 링크

**Diagnose Pipeline:**

1. Upload facility type + brief PDF + submission PDF
2. Classify and extract data from submission
3. Retrieve accumulated patterns for facility type
4. Compare submission against patterns (comparator)
5. Return comparison results with insights

### Configuration Files

**`app_settings.json`** (auto-created in backend directory):

```json
{
  "db_path": "~/competition_db",
  "anthropic_api_key": "sk-...",
  "raster_dpi_classify": 72,
  "raster_dpi_extract": 150,
  "model_id": "claude-sonnet-4-6"
}
```

**Environment fallback:**

- Anthropic API key: reads from `ANTHROPIC_API_KEY` env var if not in settings

## Important Notes

- **Pipeline 분리:** 데이터 축적(`/api/accumulate/run`)은 PDF → JSON 추출까지만 수행. 비교분석/패턴/리포트는 저장된 프로젝트의 "비교분석 실행" 버튼(`/api/accumulate/projects/{ft}/{cid}/rerun-compare`)에서만 실행. 축적 단계에서 자동으로 비교분석을 트리거하지 않는다.
- **Database Location:** User-configurable, defaults to `~/competition_db`. Each competition is stored under `{db_path}/{facility_type}/{competition_id}/` with files: `_meta.json`, `_brief.json` (지침서가 업로드된 경우만), `_comparison.json` (비교분석 실행 후 생성), `_report.html` (비교분석 실행 후 생성), `submissions/*.json`.
- **Claude Model:** Currently set to `claude-sonnet-4-6` in `app_settings.json`. `config.py`의 `MODEL_ID`는 기본값 fallback용.
- **LLM 호출:** 모든 Claude 호출은 `services/llm_client.py::call_messages()` 를 통해 이루어짐. `anthropic.Anthropic()` SDK 직접 호출 (Anthropic API 토큰 차감).
- **DPI Settings:** Classify uses 72 DPI (fast), extract uses 150 DPI (detailed). Set in `app_settings.json`.
- **CORS:** Vite dev server (5173) and localhost:3000 are allowed.
- **File Naming:** Components follow PascalCase. API paths are kebab-case.
- **Facility Types:** 12 types defined in config.py (public, residential, office, etc.) — `FACILITY_TYPES` 딕셔너리 참조
- **Page Types:** 17 classification categories (cover, floor plan, section, elevation, etc.)
- **Comparison Axes:** 7 dimensions for analysis (concept, mass, landscape, program, facade, technical, quantitative)
- **Optional Form Fields:** `client`, `location`은 백엔드에서 `Form("")`로 선언되어 빈 문자열 허용. 프론트엔드 검증도 옵션 처리.
- **HTML Report:** Generated at end of compare pipeline using existing comparison JSON — no extra Claude API calls. Report includes: submission cards, 7-axis comparison table with score bars and compliance tags (지침충족/부분충족/미충족), ranking, key differentiators, winner strength analysis. Winner entries highlighted in gold.
- **Report Generation Rule:** `report_generator.py` must not make any Claude API calls. It only renders existing data from `comparison` dict into HTML.
- **Prompt Templating Rule:** `comparator.py` prompt templates use `.replace("{key}", value)` instead of `.format(key=value)` — the JSON schema examples in prompts contain literal braces that would cause `KeyError` with `.format()`.
- **ProgressLog Events:** All SSE events passed to `ProgressLog` must include `_timestamp` (ms since epoch, set at pipeline start) for elapsed time display. The component uses `Date.now() - events[0]._timestamp` for the `+Ns` counter on the current item.
- **PDF Rasterizer:** Primary rasterizer is `services/utils.py::rasterize_pdf` using PyMuPDF. `services/pdf_rasterizer.py` (pdftoppm/pdf2image) is legacy and not called by the current pipeline.
- **ProjectList Filtering:** 저장된 프로젝트는 `facility_type` 탭으로 필터링. 데이터가 존재하는 시설 유형만 탭으로 노출되며, 첫 번째 유형이 자동 선택됨. 각 탭에 해당 유형의 프로젝트 개수가 함께 표시됨.
- **New Machine Setup:** `git clone` 후 `pip install -r requirements.txt` + `npm install` 실행. `app_settings.json`의 `db_path`를 해당 컴퓨터 경로로 수정하고 `anthropic_api_key`를 입력 (또는 `ANTHROPIC_API_KEY` env var 설정).
- **Page Taxonomy 갱신 방법:** `db_manager.py::init_db()`는 `_config/page_taxonomy.json`이 없을 때만 생성함. PAGE_TYPES를 추가한 후 기존 DB에 반영하려면 `{db_path}/_config/page_taxonomy.json` 파일을 삭제 후 백엔드를 1회 재시작하면 최신 버전(v1.1)으로 재생성됨.
- **재건축사업 타입:** `facility_type="reconstruction"` 추가. 전용 PAGE_TYPES 3개: `UNIT_PLAN`(단위세대 평면+면적표), `INCENTIVE_TABLE`(인센티브 용적률 비교표, 타일 분할 적용), `BRANDING`(브랜드·슬로건). COMPARISON_AXES는 기존 7개 그대로 사용.
