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
   - 추출 완료 즉시 각 제출물의 개별 리포트(`*_report.html`)도 생성
   - `GET /projects/{facility_type}/{competition_id}/report` serves saved `_report.html` via `FileResponse`
   - `GET /projects/{facility_type}/{competition_id}/submissions/{company}/report` serves individual submission report HTML
   - `POST /projects/{facility_type}/{competition_id}/rerun-compare` runs compare + pattern + report on stored JSONs; 개별 제출물 리포트도 재생성 (저장된 프로젝트 카드의 "비교분석 실행" 버튼이 이 엔드포인트 호출)
   - `POST /projects/{facility_type}/{competition_id}/add-submission` adds a single submission to existing project

2. **`routers/diagnose.py`** - New proposal diagnosis
   - Analyzes a single submission against accumulated patterns
   - Two routes: `/run` (DB 전체 패턴 기반) + `/run-vs-projects` (사용자가 참조 공모 선택)
   - 진단 완료 후 HTML 리포트 자동 생성·저장 → SSE `complete` 이벤트에 `report_filename` 포함
   - `GET /diagnose/reports` — 진단 리포트 목록 반환
   - `GET /diagnose/reports/{filename}` — 저장된 진단 리포트 HTML 서빙

3. **`routers/patterns.py`** - Pattern management
   - Stores and retrieves design patterns by facility type
   - Rebuilds patterns from accumulated data (당선 + 낙선 통계 포함)
   - Used by diagnose mode for comparison context

4. **`routers/settings.py`** - Configuration management
   - Manages app_settings.json (database path, API key, DPI settings)
   - `GET /settings/facility-types` — `{key: label_ko}` 딕셔너리 반환
   - `GET /settings/meta` — 프론트 `useMeta()` 훅이 소비하는 단일 메타 엔드포인트. `facility_types`, `page_types`, `axes_by_group` 포함

**Core Services:**

- `services/db_manager.py` - JSON-based database for projects, patterns, and reports
  - `save_submission_report / get_submission_report_path` — 개별 제출물 HTML 리포트
  - `save_diagnosis_report(filename, html) → Path` — `{db_path}/_diagnosis_reports/` 저장
  - `get_diagnosis_report_path(filename) → Path | None`
  - `list_diagnosis_reports() → list[dict]` — 타임스탬프·라벨 파싱 목록 (최신순)
  - `get_losing_submissions(facility_type) → list[dict]` — `*_lose.json` 전체 수집
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
- `services/data_extractor.py` - Extracts structured design data from pages; `merge_extracted_data()` returns `_quantitative` dict at top level
- `services/llm_client.py` - Claude API 호출 래퍼 (`call_messages()`). `system` 인자는 `str | list` 모두 지원 (캐시 블록 전달용). 응답 `usage`의 `cache_creation_input_tokens` / `cache_read_input_tokens`를 로그 출력
- `services/comparator.py` - Compares proposals via **2-pass blind-reveal**:
  - **Pass 1 (블라인드 채점):** `_anonymize_submissions()`이 회사명을 `A안/B안/C안...`으로 치환하고 `result` 라벨 제거 → `_make_blind_static()` 프롬프트로 LLM이 결과를 모른 채 점수·강약점·`blind_ranking` 생성. `max_tokens=32000`
  - **Pass 2 (리빌·사후 분석 — 슬림):** `ACTUAL_RESULTS`(회사명→win/lose 매핑) + `BLIND_SCORES`(Pass 1 결과 전체)만 전달. 원본 `extracted_data`·`brief_data`는 재전송 안 함 → Pass 2 입력 토큰 80%+ 절감. LLM은 Pass 1 결과 내부의 strengths/weaknesses/notes만 evidence로 사용. 산출: `key_differentiators`, `winner_strengths`, `loser_weaknesses`, `gap_notes`. `max_tokens=4096`
  - `_deanonymize_blind_result()` Pass 1 결과 라벨 복구 → 회사명 키로 정규화
  - `_compute_gap_analysis(blind_ranking, results_map, gap_notes)` → `{blind_top1, actual_winners, top1_matches_winner, alignment: "high"|"partial"|"low"|"unknown", notes}` 산출. AI 1위와 실제 당선 일치율로 alignment 결정
  - 최종 반환 dict: `submissions, ranking(=blind_ranking), blind_ranking, key_differentiators, winner_strengths, loser_weaknesses, gap_analysis`
  - **Prompt caching:** `system` + 두 content 블록 각각에 `cache_control: {"type": "ephemeral"}` → rerun-compare 시 90% 캐시 할인
  - Diagnose는 여전히 1-pass (당선/낙선 패턴 비교가 본질)
  - `.replace()` (not `.format()`) for prompt templating (JSON 중괄호 충돌 방지)
- `services/report_generator.py` - Generates HTML comparison reports (no LLM calls); facility-type-aware axes via `axes_for(facility_type)`. `gap_section` 블록이 `{ranking_section}`과 `{diff_section}` 사이에 삽입되어 블라인드 vs 실제 결과 정합도(alignment) 시각화
- `services/submission_report_generator.py` - 개별 제출물 HTML 리포트 생성 (LLM 호출 없음). `generate_submission_report(sub_doc: dict) -> str`
- `services/diagnosis_report_generator.py` - 진단 결과 HTML 리포트 생성 (LLM 호출 없음). `generate_diagnosis_report(diagnosis: dict) -> str`. 섹션: 종합점수 링 → 페이지 구성 바 → 패턴 편차 경고 → 지침서 충족도 → 요구사항 매핑 → 평가축별 상세 → 보강 포인트
- `services/pattern_builder.py` - Builds patterns from winner data + qualitative LLM summary; `build_pattern()` now also collects `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords) for loser anti-pattern comparison
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser
- `services/pdf_rasterizer.py` - Legacy fallback rasterizer (not used by default)

**Configuration:**

- `config.py` - Facility types, page types, comparison axes, Claude model ID, DPI settings
  - `FACILITY_TYPES = {key: {"label_ko": str, "group": "redev"|"general"}}` — 구조 변경됨. 단순 `{key: str}` 아님
  - `facility_label(facility_type) → str` — label_ko 반환 헬퍼
  - `PAGE_TYPES_META = {PAGE_TYPE: "한국어명", ...}` — 27개 전체
  - `COMPARISON_AXES_BY_GROUP = {"redev": {...8축...}, "general": {...8축...}}` — 그룹별 axes
  - `axes_for(facility_type) → dict` — facility_type의 group에 맞는 axes 반환
  - `axes_keys_for(facility_type) → list` — axes 키 목록
  - `COMPARISON_AXES_META` / `COMPARISON_AXES` — legacy aliases (redev 그룹, 하위호환용)
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)

Located in `competition-analyzer/frontend/`, the app has five main tabs:

1. **MyProjectMode** - 내 프로젝트 등록 (단일 제출물 + 결과 기록)
2. **AccumulateMode** - PDF에서 JSON 추출만 담당
   - Shows `ProjectList` component at top — 시설 유형 탭으로 필터링되는 저장된 프로젝트 목록
   - 추출 완료 후 "저장된 프로젝트에서 비교분석을 실행하세요" 안내 표시
3. **CrossCompareMode** - 여러 프로젝트 교차 비교
4. **DiagnoseMode** - Analyzes new submissions
   - 진단 완료 후 "진단 리포트 열기" 링크 버튼 표시 (`report_filename` SSE 이벤트 수신 시)
   - `pattern` 상태를 `DiagnosisResult`에 prop으로 전달 → 정량 비교 바 렌더링
5. **SettingsPanel** - Configuration + PatternViewer
   - 하단에 `PatternViewer` 컴포넌트 포함 (시설유형별 당선/낙선 패턴 통계 시각화)

**Key Components:**

- `AccumulateMode/ProjectList.jsx` - 저장된 프로젝트 목록. 시설 유형 탭 → 선택한 유형의 프로젝트 카드. 각 카드에: 제출물 목록(결과 뱃지 + 회사명 + "리포트" 링크), "비교분석 실행" 버튼, "+ 제안서 추가" 버튼, "비교 리포트 열기" 링크
- `AccumulateMode/ComparisonResult.jsx` - 비교 결과 카드. `GapAnalysisCard`(블라인드 vs 실제 결과 정합도) + `key_differentiators` + `blind_ranking` 순위 + 회사별 `AxisCard` 그리드. `ranking` 옆에 "(블라인드 분석 기준)" 라벨 표시
- `DiagnoseMode/DiagnosisResult.jsx` - 진단 결과 렌더링. `QuantCompare` 컴포넌트로 당선 평균 vs 낙선 평균 vs 내 제출물 정량 비교 바 표시. `pattern` prop 필요
- `Settings/PatternViewer.jsx` - 시설유형 탭 전환 + 당선/낙선 통계. 섹션: 페이지 구성 이중 바 → 정량 지표 테이블 → 컨셉 키워드 태그 → 질적 인사이트 3열
- `common/ProgressLog.jsx` - Real-time SSE log display with progress bars (`▓░` style), current item highlight, elapsed time counter (+Ns)
- `hooks/useMeta.jsx` - **프론트 메타 단일 소스.** `MetaProvider`로 앱 전체를 감싸면 `/settings/meta` 1회 fetch. `useMeta()` 반환값: `{ ready, facilityLabel, facilityGroup, facilityTypes, pageTypeLabel, axesFor, axisLabel }`

**API Communication:**

- `src/api/client.js` - All backend communication
- Uses Server-Sent Events (SSE) for streaming pipeline progress
- `getReportUrl(facilityType, competitionId)` — comparison report URL
- `getSubmissionReportUrl(facilityType, competitionId, company)` — individual submission report URL
- `getDiagnosisReportUrl(filename)` — 진단 리포트 URL
- `listDiagnosisReports()` — 저장된 진단 리포트 목록 fetch
- `rerunCompare(facilityType, competitionId)` — compare-only SSE stream
- `rerenderReport(facilityType, competitionId)` — LLM 없이 HTML 재생성 (JSON 응답)
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

2. **Frontend** (terminal 2)

   ```powershell
   cd competition-analyzer/frontend
   npm install  # First time only
   npm run dev
   ```

   - Dev server runs at `http://localhost:5173`
   - Proxies `/api/*` to backend at `http://localhost:8000`

### Testing Backend Changes

The backend uses form data multipart uploads for:

- PDF files (brief_pdf — optional, submission_pdfs)
- JSON strings (submissions_json)
- Form fields: `facility_type`, `competition_name`, `project_number` (필수), `client`, `location` (선택, 빈 문자열 허용)

Test with curl or Postman by uploading files to:

- `POST /api/accumulate/run` - PDF → JSON 추출 (비교분석 미실행)
- `POST /api/accumulate/projects/{facility_type}/{competition_id}/rerun-compare` - 비교분석 + 패턴 + 리포트 생성
- `POST /api/diagnose/run` - Single submission diagnosis (리포트 자동 생성 포함)

## Key Data Flow Patterns

**Accumulate Pipeline (데이터 축적):**

1. Upload brief PDF (선택) + submissions JSON + submission PDFs
2. Backend classifies pages (page_classifier)
3. Extracts design data from each page (data_extractor)
4. Saves `_brief.json` and `submissions/*.json` to DB
5. **즉시** 개별 제출물 리포트 생성 → `submissions/{slug}_{result}_report.html` 저장
6. Frontend receives `complete` SSE event
7. **여기서 종료** — 비교분석은 사용자가 ProjectList에서 별도로 실행

**Compare Pipeline (저장된 프로젝트의 "비교분석 실행" — 2-pass blind-reveal):**

1. Load existing `_brief.json` and `submissions/*.json` from DB (no PDF re-processing)
2. `compare_submissions(brief_data, submissions, facility_type)` 내부:
   - **Pass 1:** `_anonymize_submissions()` → A안/B안/... 라벨로 치환 + `result` 제거 → LLM 블라인드 채점 → `_deanonymize_blind_result()` 회사명 복구
   - **Pass 2:** 실제 회사명·결과·blind_result 노출 → LLM 사후 분석(차별화·당선/낙선 요인·gap_notes)
   - `_compute_gap_analysis()` 결정적 로직으로 alignment 산출 (LLM 환각 방지)
   - 결과 머지하여 `_comparison.json` 저장
3. Rebuild patterns for facility type (당선 + 낙선 통계 모두)
4. Generate HTML comparison report → save `_report.html` (gap_section 포함)
5. 모든 제출물 개별 리포트 재생성
6. Stream SSE progress

**Diagnose Pipeline:**

1. Upload facility type + brief PDF (선택) + submission PDF
2. Classify and extract data from submission
3. `sub_data["_quantitative"]` — merge_extracted_data가 정량 데이터 자동 집계
4. Retrieve accumulated patterns for facility type (loser_stats 포함)
5. Run `diagnose_submission()` → LLM이 당선 패턴 vs 낙선 패턴 대비 진단
6. `diagnosis.update({ ..., "submission_quantitative": sub_data.get("_quantitative", {}) })` — 프론트 QuantCompare용
7. `generate_diagnosis_report(diagnosis)` → `{db_path}/_diagnosis_reports/{ts}_{ft}_{name}.html` 저장
8. SSE `complete` 이벤트: `{ result: diagnosis, report_filename: "..." }`

## Configuration Files

**`app_settings.json`** (auto-created in backend directory):

```json
{
  "db_path": "M:\\06_설계사업6본부\\...",
  "anthropic_api_key": "",
  "raster_dpi_classify": 72,
  "raster_dpi_extract": 120,
  "model_id": "claude-sonnet-4-6",
  "model_id_classify": "claude-haiku-4-5-20251001"
}
```

- `anthropic_api_key`는 메모리에만 보관 — `app_settings.json`에 저장되지 않음(서버 재시작 시 초기화).
- **Environment fallback:** `ANTHROPIC_API_KEY` env var

## Important Notes

- **Pipeline 분리:** 데이터 축적(`/api/accumulate/run`)은 PDF → JSON 추출까지만 수행. 비교분석/패턴/리포트는 저장된 프로젝트의 "비교분석 실행" 버튼(`rerun-compare`)에서만 실행.
- **Database Location:** 각 competition: `{db_path}/{facility_type}/{competition_id}/` — `_meta.json`, `_brief.json`, `_comparison.json`, `_report.html`, `submissions/*.json`, `submissions/*_report.html`. 진단 리포트: `{db_path}/_diagnosis_reports/*.html`. 교차비교 리포트: `{db_path}/_cross_reports/*.html`.
- **FACILITY_TYPES 구조:** `{key: {"label_ko": str, "group": "redev"|"general"}}`. `group`으로 어느 axes 세트를 쓸지 결정. `facility_label(key)`, `axes_for(key)` 헬퍼 사용. 단순 `FACILITY_TYPES[key]`는 dict를 반환하므로 문자열로 쓰면 안 됨.
- **Comparison Axes — 두 그룹:**
  - `"redev"` 그룹 (재건축/대안설계): `business_viability`, `member_benefit`, `product_competitiveness`, `site_planning`, `community`, `design_brand`, `constructability`, `firm_capability`
  - `"general"` 그룹 (공공·주거·업무·교통·상업·문화·숙박·교육·산업·의료·복합·마스터플랜): `concept_clarity`, `site_response`, `program_planning`, `architectural_form`, `public_value`, `sustainability`, `technical_feasibility`, `brief_compliance_quant`
  - axes 추가·수정 시 `config.py::COMPARISON_AXES_BY_GROUP`만 수정하면 comparator/report_generator/frontend 전체 자동 반영 (단일 소스)
- **useMeta 단일 소스:** 프론트에서 시설유형·페이지타입·평가축 한국어 레이블은 모두 `useMeta()` 훅을 통해 `/settings/meta`에서 받아옴. 하드코딩 금지. `useMeta.jsx`는 JSX를 포함하므로 반드시 `.jsx` 확장자.
- **Loser Anti-Pattern:** `build_pattern(facility_type)`이 `*_lose.json`도 수집해 `pattern["loser_stats"]` 구성. diagnose LLM 프롬프트에 `loser_stats` 전달 → 낙선 패턴과 가까운 지표 경고. `DiagnosisResult::QuantCompare`에서 3행 바(당선/낙선/내제출물)로 시각화.
- **Diagnosis Reports:** `{db_path}/_diagnosis_reports/{YYYYMMDD}_{HHMMSS}_{facility_type}_{name}.html`. `list_diagnosis_reports()`가 최신순 정렬 목록 반환. `GET /api/diagnose/reports/{filename}`으로 서빙.
- **Pattern Viewer:** `Settings/PatternViewer.jsx` — 설정 탭 하단. 시설유형 탭 전환 → 당선/낙선 통계. 페이지구성 이중바(blue=당선, orange=낙선) + 정량지표 테이블 + 키워드 태그(낙선 대비 우세 여부 색상) + 질적 인사이트 3열. "패턴 재구축" 버튼으로 즉시 갱신.
- **Individual Submission Reports:** `generate_submission_report(sub_doc)` — LLM 호출 없음. 모든 추출 파이프라인에서 자동 생성. `has_sub_report=true`인 제출물만 ProjectList에서 "리포트" 버튼 표시.
- **`extracted_data` 구조:** `sub_doc["extracted_data"]`의 각 섹션은 **리스트**. `_quantitative` 키는 `merge_extracted_data()`가 AREA_TABLE → SITE_PLAN 우선순위로 자동 집계.
- **Claude Model:** `claude-sonnet-4-6`. `config.py`의 `MODEL_ID`는 기본값 fallback용.
- **LLM 호출:** 모든 Claude 호출은 `services/llm_client.py::call_messages()`. 502 오류는 Anthropic 서버 일시 장애 — 재시도.
- **Prompt Caching:** compare(2-pass) / diagnose 호출 시 `system` 배열 + 정적 content 블록 + 동적 content 블록 각각에 `cache_control: {"type": "ephemeral"}` 부여. 5분 TTL, 캐시 히트 시 입력 토큰 90% 할인 / 캐시 쓰기 1.25× 비용. Sonnet은 1024 토큰 이상 블록만 캐시 가능. `rerun-compare`로 재실행 시 큰 비용 절감.
- **2-pass Blind-Reveal 의도:** Pass 1에서 LLM이 결과 라벨(`win`/`lose`)을 모르게 채점 → 앵커링·할로 효과 제거. Pass 2에서 실제 결과를 공개하고 사후 분석 → 블라인드 1위와 실제 당선이 다를 때 `gap_analysis.alignment != "high"`로 경고 가능. 완벽한 익명화는 불가능 (PDF 내 로고·텍스트 등 식별 정보 잔존)지만 명시적 결과 라벨 제거가 가장 강한 시그널 차단.
- **Report Generation Rule:** `report_generator.py`, `submission_report_generator.py`, `diagnosis_report_generator.py` 모두 Claude API 호출 금지. 기존 데이터를 HTML로 렌더링만.
- **Prompt Templating Rule:** `comparator.py` prompt templates use `.replace("{key}", value)` — JSON braces would cause `KeyError` with `.format()`.
- **DPI Settings:** Classify 72 DPI (Haiku, fast), extract 120 DPI (Sonnet). 150→120 변경으로 이미지 토큰 약 36% 절감, OCR 품질 유지선.
- **Model split:** 분류는 `model_id_classify`(기본 `claude-haiku-4-5-20251001`), 추출/비교/진단은 `model_id`(기본 `claude-sonnet-4-6`). 분류는 단순 라벨링이라 Haiku로 비용·속도 최적화.
- **CORS:** Vite dev server (5173) and localhost:3000 allowed.
- **File Naming:** Components PascalCase. API paths kebab-case.
- **Page Types:** 27개 — 일반 20개 + 재건축 전용 7개(`BUSINESS_VIABILITY`, `AREA_INCREASE`, `VIEW_ANALYSIS`, `COMMUNITY_PROGRAM`, `COMPANY_PORTFOLIO`, `CONSTRUCTION_PLAN`, `UNIT_PLAN_PENTHOUSE`). `PAGE_TYPES_META`에 전체 한국어명 정의.
- **ProgressLog Events:** All SSE events must include `_timestamp` for elapsed time display.
- **PDF Rasterizer:** Primary: `services/utils.py::rasterize_pdf` (PyMuPDF). `services/pdf_rasterizer.py` is legacy.
- **ProjectList Filtering:** 데이터 존재하는 시설 유형만 탭 노출. 첫 번째 유형 자동 선택.
- **New Machine Setup:** `git clone` → `pip install -r requirements.txt` + `npm install`. `app_settings.json`의 `db_path` 수정 + API 키 입력.
- **Page Taxonomy 갱신:** `init_db()`는 `_config/page_taxonomy.json` 없을 때만 생성. PAGE_TYPES 추가 후 기존 DB 반영하려면 해당 파일 삭제 후 백엔드 재시작.
- **재건축사업 타입:** `facility_type="reconstruction"` / `"alternative"`. 분류 신뢰도 < `REDEV_CONFIDENCE_FLOOR=0.65`이면 `REDEV_FALLBACK`으로 안전 강등(`page_classifier.py::_normalise_result`).
- **Cross-Compare:** `routers/accumulate.py::cross_compare` — 여러 프로젝트 제출물 임의 조합 비교. `{db_path}/_cross_reports/` 저장.
- **Diagnose vs Projects:** `/api/diagnose/run-vs-projects` — 사용자가 참조 공모 선택. `build_pattern_from_submissions()`으로 ad-hoc 패턴 생성 (디스크 저장 X).
- **Re-rendering Reports:**
  - `POST rerender-report` — LLM 없음. 기존 `_comparison.json` 사용해 HTML만 재생성. JSON 응답.
  - `POST rerun-compare` — LLM 재실행 (토큰 비용). 비교 결과 자체 갱신.
- **HTML Comparison Report:** 다크 톤(#1a2138) + 골드 액센트(#d4af37). 자동 섹션 넘버링. `report_generator.py::_CSS`의 `:root` CSS 변수로 26개 토큰 통합 관리. Ctrl+P → A4 landscape PDF 출력 지원. `gap_section` 블록이 순위와 차별화 사이에 배치되어 alignment 색상(green/orange/red)으로 정합도 강조.
- **comparison.json 스키마:** `{submissions, ranking, blind_ranking, key_differentiators, winner_strengths, loser_weaknesses, gap_analysis: {blind_top1, actual_winners, top1_matches_winner, alignment, notes}}`. `ranking`은 호환성을 위해 `blind_ranking`과 동일 값 유지.
- **Project Number:** 폴더명 = `{project_number}_{slugified_competition_name}`. 구 데이터(`year` 필드만 있는 폴더)는 폴백 처리.
