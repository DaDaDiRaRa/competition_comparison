# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Competition Analyzer is a full-stack application for analyzing architectural competition proposals. It uses Claude AI to extract and compare design information across multiple submissions.

**Tech Stack:**

- Backend: FastAPI (Python 3.x)
- Frontend: React 18 + Vite
- AI: Anthropic Claude API (claude-sonnet-4-20250514)
- PDF Processing: PyMuPDF (fitz) — primary rasterizer in `services/utils.py`
- Database: Custom JSON-based storage

## Architecture

### Backend (FastAPI)

Located in `competition-analyzer/backend/`, the FastAPI application serves four main routers:

1. **`routers/accumulate.py`** - Data accumulation pipeline
   - Processes competition briefs and submission PDFs
   - Extracts design information using Claude AI
   - Stores patterns for facility types
   - Streams progress via Server-Sent Events
   - `GET /projects/{facility_type}/{competition_id}/report` serves saved `_report.html` via `FileResponse`
   - `POST /projects/{facility_type}/{competition_id}/rerun-compare` reruns compare + report only using existing DB data (no PDF re-processing)

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
- `services/comparator.py` - Compares proposals against accumulated patterns; uses `.replace()` (not `.format()`) for prompt templating to avoid KeyError with JSON braces
- `services/report_generator.py` - Generates HTML comparison reports from comparison data (no extra Claude API calls; uses existing comparison JSON)
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser
- `services/pdf_rasterizer.py` - Legacy fallback rasterizer using pdftoppm/pdf2image (not used by default)

**Configuration:**

- `config.py` - Facility types, page types, comparison axes, Claude model ID, DPI settings
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)

Located in `competition-analyzer/frontend/`, the app has three main tabs:

1. **AccumulateMode** - Builds the database
   - Shows `ProjectList` component at top — lists saved projects with "비교분석 재실행" button per project
   - Upload brief PDF, submissions JSON, and submission PDFs for new analysis
   - Processes each submission to extract and store patterns
   - Shows real-time progress via `ProgressLog`
   - Stores data in `~/competition_db`
   - After pipeline completes, shows "HTML 비교 리포트 열기" button (opens `_report.html` in new tab)

2. **DiagnoseMode** - Analyzes new submissions
   - Upload facility type, brief PDF, and a single submission PDF
   - Compares against accumulated patterns
   - Returns comparison results and insights

3. **SettingsPanel** - Configuration
   - Set database path, Anthropic API key, Claude model, DPI settings
   - View facility types and manage patterns (rebuild, view)

**Key Components:**

- `AccumulateMode/ProjectList.jsx` - Shows saved projects list; each card has "비교분석 재실행" button that calls `rerun-compare` endpoint and streams progress inline
- `common/ProgressLog.jsx` - Real-time SSE log display with progress bars (`▓░` style), current item highlight (blue background + left border), and elapsed time counter (+Ns)

**API Communication:**

- `src/api/client.js` - All backend communication
- Uses Server-Sent Events (SSE) for streaming pipeline progress
- `getReportUrl(facilityType, competitionId)` returns URL for opening saved HTML report
- `rerunCompare(facilityType, competitionId)` streams SSE for compare-only rerun
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

- PDF files (brief_pdf, submission_pdfs)
- JSON strings (submissions_json)
- Form fields (facility_type, competition_name, year, client, location)

Test with curl or Postman by uploading files to:

- `POST /api/accumulate/run` - Full pipeline
- `POST /api/accumulate/projects/{facility_type}/{competition_id}/rerun-compare` - Compare + report only
- `POST /api/diagnose/run` - Single submission diagnosis

### Key Data Flow Patterns

**Accumulate Pipeline (전체):**

1. Upload brief PDF + submissions JSON + submission PDFs
2. Backend classifies pages (page_classifier)
3. Extracts design data from each page (data_extractor)
4. Compares all submissions against each other (comparator)
5. Stores project in database (db_manager)
6. Rebuilds patterns for facility type (pattern_builder)
7. **Generates HTML comparison report** (report_generator) — saved as `_report.html`, no extra Claude API call
8. Frontend receives `complete` SSE event with `report_available: true`; shows "HTML 비교 리포트 열기" button

**Rerun Compare Pipeline (비교분석 재실행):**

1. Load existing `_brief.json` and `submissions/*.json` from DB (no PDF re-processing)
2. Run compare_submissions → save `_comparison.json`
3. Rebuild patterns for facility type
4. Generate and save `_report.html`
5. Stream SSE progress; frontend shows inline ProgressLog per project card

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
  "model_id": "claude-sonnet-4-20250514"
}
```

**Environment fallback:**

- Anthropic API key: reads from `ANTHROPIC_API_KEY` env var if not in settings

## Important Notes

- **Database Location:** User-configurable, defaults to `~/competition_db`. Each competition is stored under `{db_path}/{facility_type}/{competition_id}/` with files: `_meta.json`, `_brief.json`, `_comparison.json`, `_report.html`, `submissions/*.json`.
- **Claude Model:** Currently set to `claude-sonnet-4-20250514` in config.py. Update `MODEL_ID` to change.
- **DPI Settings:** Classify uses 72 DPI (fast), extract uses 150 DPI (detailed). Set in `app_settings.json`.
- **CORS:** Vite dev server (5173) and localhost:3000 are allowed.
- **File Naming:** Components follow PascalCase. API paths are kebab-case.
- **Facility Types:** 12 types defined in config.py (public, residential, office, etc.)
- **Page Types:** 16 classification categories (cover, floor plan, section, elevation, etc.)
- **Comparison Axes:** 7 dimensions for analysis (concept, mass, landscape, program, facade, technical, quantitative)
- **HTML Report:** Generated at end of accumulate pipeline using existing comparison JSON — no extra Claude API calls. Report includes: submission cards, 7-axis comparison table with score bars and compliance tags (지침충족/부분충족/미충족), ranking, key differentiators, winner strength analysis. Winner entries highlighted in gold.
- **Report Generation Rule:** `report_generator.py` must not make any Claude API calls. It only renders existing data from `comparison` dict into HTML.
- **Prompt Templating Rule:** `comparator.py` prompt templates use `.replace("{key}", value)` instead of `.format(key=value)` — the JSON schema examples in prompts contain literal braces that would cause `KeyError` with `.format()`.
- **ProgressLog Events:** All SSE events passed to `ProgressLog` must include `_timestamp` (ms since epoch, set at pipeline start) for elapsed time display. The component uses `Date.now() - events[0]._timestamp` for the `+Ns` counter on the current item.
- **PDF Rasterizer:** Primary rasterizer is `services/utils.py::rasterize_pdf` using PyMuPDF. `services/pdf_rasterizer.py` (pdftoppm/pdf2image) is legacy and not called by the current pipeline.
