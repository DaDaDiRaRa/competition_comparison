# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Competition Analyzer is a full-stack application for analyzing architectural competition proposals. It uses Claude AI to extract and compare design information across multiple submissions.

**Tech Stack:**
- Backend: FastAPI (Python 3.x)
- Frontend: React 18 + Vite
- AI: Anthropic Claude API (claude-sonnet-4-20250514)
- PDF Processing: pdf2image, Pillow
- Database: Custom JSON-based storage

## Architecture

### Backend (FastAPI)
Located in `competition-analyzer/backend/`, the FastAPI application serves four main routers:

1. **`routers/accumulate.py`** - Data accumulation pipeline
   - Processes competition briefs and submission PDFs
   - Extracts design information using Claude AI
   - Stores patterns for facility types
   - Streams progress via Server-Sent Events

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
- `services/db_manager.py` - JSON-based database for projects and patterns
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
- `services/data_extractor.py` - Extracts structured design data from pages
- `services/comparator.py` - Compares proposals against accumulated patterns
- `services/pdf_rasterizer.py` - Converts PDF pages to images for processing

**Configuration:**
- `config.py` - Facility types, page types, comparison axes, Claude model ID, DPI settings
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)
Located in `competition-analyzer/frontend/`, the app has three main tabs:

1. **AccumulateMode** - Builds the database
   - Upload brief PDF, submissions JSON, and submission PDFs
   - Processes each submission to extract and store patterns
   - Shows real-time progress
   - Stores data in `~/competition_db`

2. **DiagnoseMode** - Analyzes new submissions
   - Upload facility type, brief PDF, and a single submission PDF
   - Compares against accumulated patterns
   - Returns comparison results and insights

3. **SettingsPanel** - Configuration
   - Set database path, Anthropic API key, Claude model, DPI settings
   - View facility types and manage patterns (rebuild, view)

**API Communication:**
- `src/api/client.js` - All backend communication
- Uses Server-Sent Events (SSE) for streaming pipeline progress
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
- `POST /api/diagnose/run` - Single submission diagnosis

### Key Data Flow Patterns

**Accumulate Pipeline:**
1. Upload brief PDF + submissions JSON + submission PDFs
2. Backend classifies pages (page_classifier)
3. Extracts design data from each page (data_extractor)
4. Stores project in database (db_manager)
5. Rebuilds patterns for facility type (pattern_builder)
6. Frontend receives progress updates via SSE

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

- **Database Location:** User-configurable, defaults to `~/competition_db`. Stores projects and patterns as JSON.
- **Claude Model:** Currently set to claude-sonnet-4 in config.py. Update `MODEL_ID` to change.
- **DPI Settings:** Classify uses 72 DPI (fast), extract uses 150 DPI (detailed).
- **CORS:** Vite dev server (5173) and localhost:3000 are allowed.
- **File Naming:** Components follow PascalCase. API paths are kebab-case.
- **Facility Types:** 12 types defined in config.py (public, residential, office, etc.)
- **Page Types:** 16 classification categories (cover, floor plan, section, elevation, etc.)
- **Comparison Axes:** 7 dimensions for analysis (concept, mass, landscape, program, facade, technical, quantitative)
