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
- 배포 (데스크톱): PyInstaller(`--onedir`) + PyWebView 네이티브 윈도우 (Windows EdgeChromium WebView2)
- 배포 (웹서버): Docker + Google Cloud Run (gen2) + GCS 버킷 마운트 (`/data`)

## Architecture

### Backend (FastAPI)

Located in `backend/` (repo root), the FastAPI application serves seven routers, registered in `main.py` under `/api/<name>`:

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
   - `POST /settings/db-path` — DB 경로 저장 후 `init_db()` 자동 실행. `{ db_path: str }` 바디

5. **`routers/upload.py`** - 대용량 PDF 청크 업로드 (Cloud Run 32MB 요청 한도 우회)
   - `POST /upload/start` → `upload_id` 발급, `/tmp/cc_uploads/{upload_id}/`에 청크 누적
   - `POST /upload/chunk/{upload_id}` — 25MB 단위 청크 (총 600MB 상한)
   - `POST /upload/finish/{upload_id}` — 청크 조립 → `file_ref` 반환. 파이프라인 엔드포인트(accumulate/diagnose)는 multipart 대신 이 `file_ref`를 받아 /tmp에서 직접 읽음
   - `POST /upload/cleanup/{upload_id}` — 파이프라인 완료 후 임시 파일 삭제

6. **`routers/archive.py`** - 아카이브 자연어 검색 (FTS5 in-memory SQLite, `GET /list` + `POST /search` + `GET /{ft}/{cid}`)

7. **`routers/brief.py`** - 지침서 단독 분석 엔드포인트
   - `POST /brief/analyze` — 지침서 PDF 1개 업로드 → 페이지 분류 → 데이터 추출 → 요구사항 분석 → 검증 → JSON·MD·xlsx 저장 (SSE)
   - `GET /brief/list` — `{db_path}/_briefs/*.json` 최신순 목록
   - `GET /brief/exports/{filename}` — md / xlsx 다운로드 (path traversal 방지)
   - 저장 위치: `{db_path}/_briefs/{YYYYMMDD_HHMMSS}_{facility_type}_{slug}.{json|md|xlsx}`
   - `brief_id` 명명: `{stamp}_{facility_type}_{slug}`, 최대 120자 (Windows 경로 여유)

**MyProject 심층 분석:** 별도 라우터 없음. `routers/accumulate.py`가 단일 제출물 등록 시 `services/myproject_analyzer.deep_analyze()` 호출 → `submissions/{slug}_{result}_deep.json` + `_{result}_deep.html` 생성. `GET /projects/{ft}/{cid}/submissions/{company}/deep-report`로 서빙.

**Core Services:**

- `services/db_manager.py` - JSON-based database for projects, patterns, and reports
  - `_atomic_write(path, data)` — JSON을 `.tmp`에 쓰고 `fsync` 후 rename. GCSFUSE write-back 캐시를 GCS까지 강제 플러시 (fsync 없으면 rename 시점에 GCS에 원본이 없어 데이터 유실)
  - `_sync_write(path, content)` — HTML 등 텍스트 파일용. `flush + fsync`로 GCSFUSE 플러시
  - `save_submission_report / get_submission_report_path` — 개별 제출물 HTML 리포트
  - `save_diagnosis_report(filename, html) → Path` — `{db_path}/_diagnosis_reports/` 저장
  - `get_diagnosis_report_path(filename) → Path | None`
  - `list_diagnosis_reports() → list[dict]` — 타임스탬프·라벨 파싱 목록 (최신순)
  - `get_losing_submissions(facility_type) → list[dict]` — `*_lose.json` 전체 수집
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
  - `classify_all_pages_brief()` — 지침서 PDF 전용 분류. PRIORITY RULE 2: 비중/배점/점수 컬럼이 있는 표 → `BRIEF_EVALUATION` (BRIEF_DESIGN_GUIDE보다 우선). 응답 JSON에 `has_scoring_table` 필드 추가 (판단 근거 추적용).
  - BRIEF_EVALUATION vs BRIEF_DESIGN_GUIDE 구분 기준: 배점 표(비중/배점/점수 컬럼, 합계 ≈ 100) → BRIEF_EVALUATION / 글머리기호(•) 위주 텍스트, 표 없음 → BRIEF_DESIGN_GUIDE
  - **`has_scoring_table=False` 강등:** `_normalise_brief_result()`에서 LLM이 `has_scoring_table=False`를 반환하면 BRIEF_EVALUATION → BRIEF_ADMIN으로 강등. 참여자 명단·등록업체 목록(표 있으나 배점 없음)의 오분류 방지.
  - **BRIEF_ADMIN 조건 (f):** "참여자 명단·참가업체 목록·설계공모 참여자·등록업체" 페이지는 표 유무와 무관하게 BRIEF_ADMIN. BRIEF_EVALUATION NOT 조건에 명시.
- `services/data_extractor.py` - Extracts structured design data from pages; `merge_extracted_data()` returns `_quantitative` dict at top level
  - `DIGITAL_TEXT_EXCLUDE_TYPES` — `{"AREA_TABLE","TECHNICAL","INCENTIVE_TABLE","BUSINESS_VIABILITY","AREA_INCREASE","BRIEF_PROGRAM","BRIEF_REGULATIONS","BRIEF_EVALUATION"}`. 이 타입들은 fitz.get_text() Tier 0을 건너뛰고 타일-비전 경로로 처리. `BRIEF_EVALUATION` 추가 이유: HWP→PDF 변환 시 병합 셀 구조 붕괴 → 구분/항목/비중 관계 오독 위험.
  - `BRIEF_EVALUATION` 추출 스키마: `evaluation_categories[].sub_items`(구분 하위 세부항목 문자열 배열) + `evaluation_categories[].shared_with`(병합 셀로 배점이 공유된 형제 구분 이름 목록) 추가. `total_points`는 배점 합계(통상 100).
  - **BRIEF_EVALUATION 다중 페이지 스태킹:** `extract_pdf(is_brief=True)` 진입 시 BRIEF_EVALUATION 페이지가 2개 이상이면 `_stack_images_vertically()` (PIL)로 세로 이어붙임 → LLM에 1회 전달. `precomputed_eval`에 결과 저장, 나머지 페이지는 `{"data": {}, "_merged": True}` 반환. 병합 셀이 페이지 경계를 넘어도 표 구조를 한 번에 파악 가능.
  - **BRIEF_EVALUATION 스태킹 폴백:** 스태킹 추출 후 non-null points 합계(`_pts_sum`)가 0이면 스태킹 결과 폐기(`precomputed_eval = None`) → `stacked_eval_set` 비워짐 → 각 페이지 개별 추출. 연속되지 않은 페이지(예: p.21 + p.117)가 분류되어 스태킹됐을 때 LLM 혼동 방지.
  - **BRIEF_PROGRAM 다중 페이지 스태킹:** 5페이지 청크 단위(`_PROG_CHUNK=5`)로 스태킹 후 `area_rows` 추출. 청크 결과를 `extend()`로 병합.
  - **`_stack_images_vertically()` — JPEG 출력:** PIL 스태킹 결과를 **JPEG(quality=85)**로 저장. PNG 대비 파일 크기 약 1/10 → Anthropic API 5MB 이미지 한도 초과 방지. 5페이지 PNG = 7~10MB → 400 오류 / JPEG = 0.5~1MB → 정상. **PNG로 되돌리면 BRIEF_PROGRAM이 많은 지침서(36페이지 등)에서 400 오류 재발.**
  - **`_image_block()` — JPEG 마법 바이트 감지:** `img_bytes[:3] == b'\xff\xd8\xff'`이면 `media_type: "image/jpeg"`, 아니면 `"image/png"`. `safe_encode_image()`에 올바른 `fmt` 전달. 포맷 불일치는 또 다른 400 오류 원인.
  - **`points_sum_warning`:** 스태킹 후 `null`이 아닌 `points` 합계가 95~105 범위를 벗어나면 `precomputed_eval["data"]["points_sum_warning"] = True` 플래그 추가. `brief_checklist_exporter`가 경고로 노출.
  - **BRIEF_PROJECT_INFO FIELD NOTES:** 한국어 표현 → 스키마 키 명시 매핑 추가 (`건폐율(%)` → `building_coverage_pct`, `용적률(%)` → `floor_area_ratio_pct`, `대지면적(㎡)` → `site_area_sqm`, `건축규모/연면적(㎡)` → `floor_area_sqm`, `높이(m)` → `max_height_m`, `공개공지(㎡)` → `open_space_sqm`). 괄호 접두사(`(완화) 460%`) → 숫자만 추출 룰, 부지 복수 → `sites` 배열 분리 룰.
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
- `services/myproject_analyzer.py` - MyProjectMode 단일 제출물 멀티패스 deep-analysis (`deep_analyze()`). 페이지별 narrative + 평가축별 deep evidence + 정량 메트릭 + 검색 키워드 + auto_meta 추출
- `services/myproject_report_generator.py` - `_deep.json` → HTML 리포트 렌더링 (LLM 호출 없음). `generate_myproject_report(deep_doc) -> str`
- `services/archive_search.py` - in-memory SQLite FTS5 인덱싱 + 자연어 검색. `build_index()` 앱 시작 시 1회, `rerun-compare` 완료 후 `rebuild_index()`. `sqlite3.connect(":memory:", check_same_thread=False)` 필수 (FastAPI threadpool 교차).
- `services/brief_validator.py` - 지침서 검증 (LLM 호출 없음). `validate_brief(brief_data, requirements) → dict`. 반환: `{flags: [...], summary: {high, medium, low}, checked_rules}`. 각 flag: `{rule_id, severity, message, evidence}`.
- `services/brief_checklist_exporter.py` - 지침서 체크리스트 내보내기 (LLM 호출 금지). `to_markdown(brief_data, validation) → str` / `to_xlsx(brief_data, validation) → bytes`. openpyxl lazy import (`import openpyxl` 함수 내부) — PyInstaller spec에 서브모듈 전체 명시 필수.
  - **헬퍼:** `_first(data, key)` — `merge_extracted_data()` dict-or-list 반환 정규화. `_collect(data, key)` — 여러 페이지 리스트 필드 합산. `_v(val, unit)` — null/빈값 → `"(없음)"`, 리스트 → 쉼표 조인. `_write_kv(ws, label, val, row, val_end_col=2)` — 셀 병합 지원 KV 쓰기.
  - **`brief_evaluation` 다중 페이지 처리:** `_extract_sections()`에서 `brief_evaluation` 리스트 내 non-null 배점 수가 가장 많은 페이지를 `max(key=_eval_pts)`로 선택. `_first()`(항상 첫 페이지)를 쓰면 BRIEF_EVALUATION 스태킹 폴백 시 p.21이 빈 결과여도 p.117의 실제 배점표가 무시됨. **`_first(brief_evaluation)`으로 되돌리면 비연속 페이지 케이스에서 심사기준 Sheet 전체 누락 재발.**
  - **`_COST_KW` 필터:** area_table 조립 후 `{"공사비","내역서","공종","원가","견적"}` 키워드를 group_name에 포함한 그룹 제거 (개략공사비 내역서 등 비설계 항목 배제).
  - **Excel (4 시트):** Sheet 1(면적·프로그램) `freeze_panes="A3"`, KV `val_end_col=4`로 병합. Sheet 2(심사기준) 4열 구조 `항목명|배점|공유배점|세부기준`, sub_items를 col 4에 별도 행으로 렌더링, `freeze_panes="A3"`. Sheet 3(요구사항) 2열 라벨+내용 구조, 각 설계 섹션(배치·동선/입면·재료/친환경·인증/특수·보안/기타)을 라벨화된 서브리스트로 렌더링, `freeze_panes="A3"`. Sheet 4(검증경고) `freeze_panes="A3"`.
  - **MD (`to_markdown`):** 프로그램·LLM 연동용 구조화 데이터 덤프. 마크다운 표 없음. 형식: `key: value` 한 줄 / `- item` / 들여쓰기 `- sub_item` 계층 리스트. null 필드는 `(없음)` 명시. 5개 섹션: 1.사업개요 / 2.면적프로그램 / 3.심사기준(평가항목별 `### Name` 블록) / 4.요구사항·설계지침(모든 서브라벨 열거) / 5.검증경고(`[심각도] type: message | 위치: ...` 형식).
- `services/grade_helpers.py` - 등급 처리 단일 소스. `LEGACY_GRADE_MAP`, `GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade(d, *, check_overall=False)`. `report_generator` / `diagnosis_report_generator` / `myproject_report_generator` 모두 여기서 import.
- `services/diagnosis_report_generator.py` - 진단 결과 HTML 리포트 생성 (LLM 호출 없음). `generate_diagnosis_report(diagnosis: dict) -> str`. 섹션: 종합점수 링 → 페이지 구성 바 → 패턴 편차 경고 → 지침서 충족도 → 요구사항 매핑 → 평가축별 상세 → 보강 포인트
- `services/pattern_builder.py` - Builds patterns from winner data + qualitative LLM summary; `build_pattern()` now also collects `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords) for loser anti-pattern comparison
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser
  - `user_error_msg(e: Exception) → str` — 예외를 사용자 친화적 한국어 메시지로 변환. `LocalProtocolError`/illegal header(API 키 형식 불량) → 401/502/429/timeout/PDF/JSON 패턴 매핑 순. `accumulate.py` / `diagnose.py`에서 공통 사용.
  - `parse_json_response(text)` — 3단계 복구: ① 펜스 제거 → ② 직접 파싱 → ③ `{...}` 또는 `[...]` 추출 + 후행 쉼표 제거. LLM이 마크다운 코드블록이나 산문을 섞어도 JSON 추출 가능.
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
  - `DEFAULT_DB_PATH` — 우선순위: `DB_PATH` 환경변수 → `M:\...KUNWON_COMPETITION_DB` (Windows 기본값)
  - Cloud Run 배포 시 `DB_PATH=/data` 환경변수로 GCS 마운트 경로 지정
  - `settings.db_path` — `app_settings.json`의 `db_path` 값 우선, 없으면 `DEFAULT_DB_PATH`
  - `settings.has_db_path` — 사용자가 명시적으로 경로를 설정했는지 여부
  - `settings.set_db_path(path)` — 경로를 `app_settings.json`에 저장
  - `settings.api_key` — 메모리 우선, 없으면 `ANTHROPIC_API_KEY` 환경변수. **양쪽 모두 `_sanitize_api_key()` 적용** — `echo -n "key"` 셸 아티팩트(`-n`접두사, `\r\n`, 따옴표) 자동 제거
  - `settings.set_api_key(key)` — 세션 메모리에만 저장. 디스크 기록 안 함
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)

Located in `frontend/` (repo root), the app has six main tabs:

1. **MyProjectMode** - 내 프로젝트 등록 (단일 제출물 + 결과 기록)
2. **AccumulateMode** - PDF에서 JSON 추출만 담당
   - Shows `ProjectList` component at top — 시설 유형 탭으로 필터링되는 저장된 프로젝트 목록
   - 추출 완료 후 "저장된 프로젝트에서 비교분석을 실행하세요" 안내 표시
3. **CrossCompareMode** - 여러 프로젝트 교차 비교
4. **DiagnoseMode** - Analyzes new submissions
   - 진단 완료 후 "진단 리포트 열기" 링크 버튼 표시 (`report_filename` SSE 이벤트 수신 시)
   - `pattern` 상태를 `DiagnosisResult`에 prop으로 전달 → 정량 비교 바 렌더링
5. **ArchiveMode** - 아카이브 자연어 검색 (검색창 + 카드 그리드 + 슬라이드오버 상세)
6. **SettingsPanel** - Configuration + PatternViewer
   - 하단에 `PatternViewer` 컴포넌트 포함 (시설유형별 당선/낙선 패턴 통계 시각화)

**Key Components:**

- `AccumulateMode/ProjectList.jsx` - 저장된 프로젝트 목록. 시설 유형 탭 → 선택한 유형의 프로젝트 카드. 각 카드에: 제출물 목록(결과 뱃지 + 회사명 + "리포트" 링크), "비교분석 실행" 버튼, "+ 제안서 추가" 버튼, "비교 리포트 열기" 링크
- `AccumulateMode/ComparisonResult.jsx` - 비교 결과 카드. `GapAnalysisCard`(블라인드 vs 실제 결과 정합도) + `key_differentiators` + `blind_ranking` 순위 + 회사별 `AxisCard` 그리드. `ranking` 옆에 "(블라인드 분석 기준)" 라벨 표시
- `DiagnoseMode/DiagnosisResult.jsx` - 진단 결과 렌더링. `QuantCompare` 컴포넌트로 당선 평균 vs 낙선 평균 vs 내 제출물 정량 비교 바 표시. `pattern` prop 필요
- `Settings/PatternViewer.jsx` - 시설유형 탭 전환 + 당선/낙선 통계. 섹션: 페이지 구성 이중 바 → 정량 지표 테이블 → 컨셉 키워드 태그 → 질적 인사이트 3열
- `SubmissionEditor/SubmissionEditor.jsx` - 저장된 제출물 메타·정량·결과 라벨 인라인 편집. `getSubmission` / `updateSubmission` 호출. `ProjectList`에서 "편집" 버튼으로 진입. `QUANT_FIELDS` 10개 정량 필드 + `MASS_TYPE_OPTIONS` + `RESULT_OPTIONS`(win/contracted/lose) 폼
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
- `setDbPath(dbPath)` — DB 경로 저장 (`POST /api/settings/db-path`)
- All SSE events include `_timestamp` (pipeline start time in ms) for elapsed time display
- Endpoints: `/api/accumulate`, `/api/diagnose`, `/api/patterns`, `/api/settings`

**Styling:**

- Inline styles (no CSS framework)
- **화이트 테마 + 건원 RED 액센트** (`#e60012`). 모든 색·타이포·간격·반경은 `frontend/src/kunwon-tokens.css` CSS 변수로 관리.
- 컴포넌트는 인라인 스타일에서 `var(--token)` 형태로 직접 사용. `main.jsx`에서 전역 import → 별도 JS import 불필요.
- `frontend/src/theme.js` — 색 토큰 참고용 JS 명세 (컴포넌트가 import하지는 않음). 색 변경 시 같이 갱신.
- Components use consistent style object pattern
- 하드코딩 감사: `tools/audit_tokens.py` 실행 → `DESIGN_AUDIT.md` 생성 (파일·줄 번호·교체 토큰 목록)

## Common Development Tasks

### Running the Application

1. **Backend** (terminal 1)

   ```powershell
   cd backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   - API runs at `http://localhost:8000`
   - Auto-reloads on code changes

2. **Frontend** (terminal 2)

   ```powershell
   cd frontend
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

**Brief Pipeline (지침서 단독 분석 — `POST /api/brief/analyze`):**

1. Upload brief PDF (multipart 또는 `/api/upload` `file_ref`)
2. `classify_all_pages_brief()` → 9개 BRIEF_* 타입으로 분류
3. `extract_pdf(pdf_path, page_map, is_brief=True)` → `merge_extracted_data()` → `brief_data`
4. `extract_brief_requirements(brief_data, facility_type)` → `brief_data["_requirements"]`
5. `validate_brief(brief_data, requirements)` → `brief_data["validation"]` (flags / summary)
6. 저장: `_atomic_write(json)` + `_sync_write(md)` + `_sync_write_bytes(xlsx)`
7. SSE `complete` 이벤트: `{brief_id, md_filename, xlsx_filename, validation_summary}`

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
  "db_path": "C:\\Users\\사용자명\\CompetitionAnalyzerDB",
  "raster_dpi_classify": 72,
  "raster_dpi_extract": 120,
  "model_id": "claude-sonnet-4-6",
  "model_id_classify": "claude-haiku-4-5-20251001"
}
```

- `db_path`는 설정 탭 UI 또는 `POST /api/settings/db-path`로 변경. 미설정 시 `~/CompetitionAnalyzerDB` 자동 사용.
- `anthropic_api_key`는 메모리에만 보관 — `app_settings.json`에 저장되지 않음(서버 재시작 시 초기화).
- **Environment fallback:** `ANTHROPIC_API_KEY` env var. `echo -n "key"` 형태로 설정된 경우 `-n`접두사·`\r\n`·따옴표를 `_sanitize_api_key()`가 자동 제거.

## Important Notes

- **Pipeline 분리:** 데이터 축적(`/api/accumulate/run`)은 PDF → JSON 추출까지만 수행. 비교분석/패턴/리포트는 저장된 프로젝트의 "비교분석 실행" 버튼(`rerun-compare`)에서만 실행.
- **Database Location:** 각 competition: `{db_path}/{facility_type}/{competition_id}/` — `_meta.json`, `_brief.json`, `_comparison.json`, `_report.html`, `submissions/*.json`, `submissions/*_report.html`. 진단 리포트: `{db_path}/_diagnosis_reports/*.html`. 교차비교 리포트: `{db_path}/_cross_reports/*.html`. 지침서 단독분석: `{db_path}/_briefs/{brief_id}.{json|md|xlsx}`.
- **GCSFUSE 쓰기 보장:** Cloud Run gen2 + GCS 버킷 마운트(GCSFUSE)에서 write-back 캐시로 인해 `rename()` 시점에 GCS에 원본이 없으면 데이터 유실. 모든 파일 쓰기는 `f.flush(); os.fsync(f.fileno())` 후 rename(`_atomic_write`) 또는 `_sync_write` 사용 — 새 파일 저장 함수 추가 시 반드시 fsync 포함.
- **보안 — 커밋 금지 파일:** 다음은 모두 `.gitignore`에 등록되어 있어야 하며 절대 커밋 금지:
  - `service.yaml` — Cloud Run 서비스 YAML, API 키 등 시크릿 평문 포함 가능. 수정 필요 시 로컬에서만 편집 후 `gcloud run services replace service.yaml` 실행
  - `gcp-sa-key.json`, `*-sa-key.json`, `key.json` — GCP 서비스 계정 키 (repo 루트에 존재)
  - `.env`, `env.yaml` — 환경변수 정의
  - 참고: `backend/app_settings.json`은 **추적 대상** (DB 경로·DPI·모델 ID만 저장). `anthropic_api_key`는 메모리에만 보관되며 디스크에 쓰지 않음
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
- **Grading (5-level A/B/C/D/E):** 점수는 0.0-10.0 숫자가 아닌 `grade: "A"|"B"|"C"|"D"|"E"` 문자열. `overall_grade`도 동일. 이유: 임원 검토 시 무의미한 정밀도 논쟁 차단 + 환각 검증 부담 감소.
  - **등급 색상 (라이트 테마):** A=`var(--color-success)` `#16a34a` / B=`var(--color-info)` `#0891b2` / C=`var(--color-warning)` `#ca8a04` / D=`var(--color-grade-d)` `#ea580c` / E=`var(--color-danger)` `#dc2626`. 배경(`GRADE_BG`)은 같은 hue 옅은 톤.
  - 구 데이터 자동 변환: `score`(0-10) → ≥8.5=A, ≥7=B, ≥5=C, ≥3=D, else=E. 구 `grade`("상"→B, "중"→C, "하"→D). 새 비교 실행하면 LLM이 직접 A-E 출력.
  - 백엔드 헬퍼: `services/grade_helpers.py` 단일 소스 (`GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade()`). `report_generator` / `diagnosis_report_generator` / `myproject_report_generator`가 공통 import.
  - 프론트 헬퍼: `constants/index.js`의 `GRADE_COLOR`, `GRADE_BG`, `toGrade(d)` (구 score 호환)
  - `blind_ranking`은 그대로 유지 — LLM이 상 개수 우선으로 순위 부여
- **페이지 인용 강제:** compare/diagnose 프롬프트에 "각 strength/weakness/recommendation은 반드시 `(p.N)` 형식 페이지 인용 포함" 룰 명시. `_page` 필드를 `_trim_extracted()`에서 보존하여 LLM에 페이지 번호 노출. 임원 검토 시 즉시 PDF 원문 검증 가능 → 환각 억제 효과도 큼. Pass 2도 Pass 1 결과 내 (p.N)을 그대로 인용하도록 지시.
- **Report Generation Rule:** `report_generator.py`, `submission_report_generator.py`, `diagnosis_report_generator.py` 모두 Claude API 호출 금지. 기존 데이터를 HTML로 렌더링만.
- **Prompt Templating Rule:** `comparator.py` prompt templates use `.replace("{key}", value)` — JSON braces would cause `KeyError` with `.format()`.
- **DPI Settings:** Classify 72 DPI (Haiku, fast), extract 120 DPI (Sonnet). 150→120 변경으로 이미지 토큰 약 36% 절감, OCR 품질 유지선.
- **Model split:** 분류는 `model_id_classify`(기본 `claude-haiku-4-5-20251001`), 추출/비교/진단은 `model_id`(기본 `claude-sonnet-4-6`). 분류는 단순 라벨링이라 Haiku로 비용·속도 최적화.
- **CORS:** Vite dev server (5173) and localhost:3000 allowed.
- **File Naming:** Components PascalCase. API paths kebab-case.
- **Page Types:** 27개 — 일반 20개 + 재건축 전용 7개(`BUSINESS_VIABILITY`, `AREA_INCREASE`, `VIEW_ANALYSIS`, `COMMUNITY_PROGRAM`, `COMPANY_PORTFOLIO`, `CONSTRUCTION_PLAN`, `UNIT_PLAN_PENTHOUSE`). `PAGE_TYPES_META`에 전체 한국어명 정의.
- **ProgressLog Events:** All SSE events must include `_timestamp` for elapsed time display.
- **PDF Rasterizer:** Primary: `services/utils.py::rasterize_pdf` (PyMuPDF). `services/pdf_rasterizer.py` is legacy. PaddleOCR은 `services/utils.py::ocr_page()`에서 lazy-load — `requirements-ocr.txt` 미설치 시 자동 스킵.
- **FastAPI Lifespan:** `main.py`는 `@app.on_event` 대신 `@asynccontextmanager async def lifespan()` 사용. `init_db()` 실패해도 서버가 뜨도록 graceful 처리.
- **데스크톱 앱 (PyWebView + PyInstaller):** `backend/launcher.py`가 진입점. uvicorn을 백그라운드 스레드로 띄운 뒤 `webview.create_window()`로 EdgeChromium 네이티브 창 표시 (`gui` 미지정 시 Windows에서 자동 선택). `JsApi.open_external(url)` JS API 노출 → 프론트의 `App.jsx`가 `target="_blank"` 클릭을 가로채 `window.pywebview.api.open_external()`로 시스템 기본 브라우저에 위임 (리포트 인쇄/다운로드 편의). `frozen` 모드 감지(`getattr(sys, 'frozen', False)`)로 `sys._MEIPASS` 안의 `frontend_dist` 서빙.
- **PyInstaller spec:** `backend/competition_analyzer.spec`. `collect_all('webview')`, `collect_all('clr_loader')`, `collect_all('pythonnet')` 필수 — pywebview는 .NET 어셈블리(`System`, `System.Windows`, `System.Drawing`)를 동적 로드하므로 정적 분석으로 못 잡힘. PaddleOCR 등 무거운 의존성은 `excludes`. 산출물: `backend/dist/CompetitionAnalyzer/CompetitionAnalyzer.exe` (~14MB) + `_internal/` (~120MB). `console=False` (windowed 빌드) — CMD 창 미표시.
- **로깅 (windowed 빌드):** `console=False`이면 stdout/stderr가 어디에도 표시되지 않음. `launcher.py::_setup_logging()`이 `RotatingFileHandler`로 `~/.competition-analyzer/app.log`(2MB×3 백업)에 기록. 치명적 오류는 `_show_error_dialog()`로 Win32 MessageBox 표시 (`ctypes.windll.user32.MessageBoxW`). uvicorn 자체 로그는 console 없으면 사라지지만 launcher 핵심 이벤트는 모두 파일에 남음. 디버깅 시 이 파일을 먼저 확인.
- **빌드 스크립트:** 저장소 루트의 `build.ps1` — npm install → vite build → PyInstaller 일괄 실행. PowerShell의 `$ErrorActionPreference = "Stop"`이 PyInstaller stderr(INFO 로그)를 에러로 오인할 수 있어 일부 환경에서 실패 표시될 수 있으나, 실제 산출물은 정상 생성됨. 직접 `.\venv\Scripts\python.exe -m PyInstaller competition_analyzer.spec --noconfirm` 실행하면 우회.
- **테마/색상 시스템:** 화이트 테마 + **건원 RED 액센트** (`#e60012`). 색상 정의 위치:
  1. `frontend/src/kunwon-tokens.css` — **단일 소스 CSS 변수** (모든 프론트 컴포넌트가 `var(--token)` 참조). `main.jsx`에서 전역 import.
  2. `frontend/src/theme.js` — 색 토큰 명세 (참고용 문서)
  3. `frontend/src/constants/index.js` — `GRADE_COLOR`, `GRADE_BG`, `COMPLIANCE_COLOR` (CSS var 참조)
  4. `backend/services/report_generator.py` — `_CSS`의 `:root` CSS 변수 26개 (비교 리포트 HTML — 독립 문서이므로 별도 관리)
  5. `submission_report_generator.py` / `diagnosis_report_generator.py` — 리포트 HTML 인라인 hex (독립 문서)
  - **프론트 컴포넌트 색상 규칙:** 인라인 스타일에서 hex 직접 사용 금지. `style={{ color: 'var(--color-accent)' }}` 패턴 사용. 신규 색 필요 시 `kunwon-tokens.css`에 추가 후 참조.
  - **현재 브랜드 토큰 (주요):**
    - 액센트: `--color-accent: #e60012` (건원 RED) / hover `--color-accent-hover: #c0000f` / soft `--color-accent-soft: rgba(230,0,18,0.08)` / border `--color-accent-border: rgba(230,0,18,0.25)`
    - 배경: `--color-bg-page: #f8f9fa` / `--color-bg-surface: #ffffff` / `--color-bg-surface-alt: #f1f3f5`
    - 텍스트: `--color-text-body: #212529` / muted `#6c757d` / faint `#adb5bd` / subtle `#868e96`
    - 상태: `--color-success: #16a34a` (당선·win) / `--color-info: #0891b2` (계약·contracted) / `--color-warning: #ca8a04` / `--color-danger: #dc2626`
  - **등급 색상 (5-level, 화이트 BG용):**
    - A `var(--color-success)` `#16a34a` / B `var(--color-info)` `#0891b2` / C `var(--color-warning)` `#ca8a04` / D `var(--color-grade-d)` `#ea580c` / E `var(--color-danger)` `#dc2626`
    - 배경(`GRADE_BG`): `#dcfce7` / `#cffafe` / `#fef3c7` / `#fed7aa` / `#fee2e2`
  - **결과 뱃지 색상:** `win` → `--color-success`, `contracted` → `--color-info`, `lose` → `--color-text-faint`
  - **차트 팔레트 예외:** `ComparisonDashboard`의 `PALETTE` 배열, `PageDistChart`의 당선/낙선 구분 바는 데이터 다양성을 위해 `--color-purple`(`#7c3aed`) 등 차트 전용 색 허용.
  - 색 변경 시 `kunwon-tokens.css` 수정 → `theme.js`도 동기화해 단일 명세 유지. 토큰 추가 시 `CLAUDE.md` 현재 브랜드 토큰 목록도 갱신.
  - 감사 도구: `tools/audit_tokens.py` — 프론트 파일 전체에서 인라인 hex 스캔 → `DESIGN_AUDIT.md` 생성.
- **ProjectList Filtering:** 데이터 존재하는 시설 유형만 탭 노출. 첫 번째 유형 자동 선택.
- **New Machine Setup:** `git clone` → `pip install -r requirements.txt` + `npm install` → 백엔드 실행 → 브라우저에서 설정 탭에서 DB 경로 입력 + API 키 입력. DB 경로 미입력 시 `~/CompetitionAnalyzerDB` 자동 사용.
- **PaddleOCR (선택):** 이미지 기반 PDF(텍스트 없는) OCR 필요 시만 `pip install -r requirements-ocr.txt`. 기본 파이프라인은 PyMuPDF + Claude vision으로 동작하므로 불필요.
- **Page Taxonomy 갱신:** `init_db()`는 `_config/page_taxonomy.json` 없을 때만 생성. PAGE_TYPES 추가 후 기존 DB 반영하려면 해당 파일 삭제 후 백엔드 재시작.
- **재건축사업 타입:** `facility_type="reconstruction"` / `"alternative"`. 분류 신뢰도 < `REDEV_CONFIDENCE_FLOOR=0.65`이면 `REDEV_FALLBACK`으로 안전 강등(`page_classifier.py::_normalise_result`).
- **Cross-Compare:** `routers/accumulate.py::cross_compare` — 여러 프로젝트 제출물 임의 조합 비교. `{db_path}/_cross_reports/` 저장.
- **Diagnose vs Projects:** `/api/diagnose/run-vs-projects` — 사용자가 참조 공모 선택. `build_pattern_from_submissions()`으로 ad-hoc 패턴 생성 (디스크 저장 X).
- **Re-rendering Reports:**
  - `POST rerender-report` — LLM 없음. 기존 `_comparison.json` 사용해 HTML만 재생성. JSON 응답.
  - `POST rerun-compare` — LLM 재실행 (토큰 비용). 비교 결과 자체 갱신.
- **HTML Comparison Report:** 다크 톤(#1a2138) + 골드 액센트(#d4af37). 자동 섹션 넘버링. `report_generator.py::_CSS`의 `:root` CSS 변수로 26개 토큰 통합 관리. Ctrl+P → A4 landscape PDF 출력 지원. `gap_section` 블록이 순위와 차별화 사이에 배치되어 alignment 색상(green/orange/red)으로 정합도 강조.
- **comparison.json 스키마:** `{submissions: {company: {axis: {grade, strengths, weaknesses, brief_compliance, notes}}}, ranking, blind_ranking, key_differentiators, winner_strengths, loser_weaknesses, gap_analysis: {blind_top1, actual_winners, top1_matches_winner, alignment, notes}}`. `ranking`은 호환성을 위해 `blind_ranking`과 동일 값 유지. `grade`는 "A"|"B"|"C"|"D"|"E"|null.
- **diagnosis.json 스키마:** `{axes: {axis: {grade, strengths, weaknesses, recommendations, evidence}}, overall_grade, brief_compliance, requirement_mapping, pattern_deviation, strengths, weaknesses, recommendations}`. `overall_grade`도 "A"|"B"|"C"|"D"|"E".
- **Project Number:** 폴더명 = `{project_number}_{slugified_competition_name}`. 구 데이터(`year` 필드만 있는 폴더)는 폴백 처리.

---

## Archive Mode

**구현 완료.** `routers/archive.py` + `services/archive_search.py`.

- **데이터:** GCS(`/data`) 하위 `_comparison.json` + `_meta.json` 읽기 전용. 쓰기 없음.
- **인덱싱:** 앱 시작 시 `build_index()` 1회. `rerun-compare` 완료 후 `rebuild_index()` 호출로 갱신.
- **검색:** `search_natural()` — Claude API로 자연어 → 키워드+시설유형 추출 후 FTS5 MATCH. API 키 없으면 `search_keyword(q)` 폴백.
- **FTS 동의어:** `FACILITY_SYNONYMS`로 시설유형 컬럼에 영어 키 + 한국어 레이블 + 구어체 함께 인덱싱.
- **MyProject 연동:** `_myprojects/` 하위도 스캔. `search_keywords`, `narrative`, `memo` 필드 FTS5 인덱스 포함.
- **auto_meta:** `deep_analyze()`가 `auto_meta` 추출 → `update_project_meta()`로 `_meta.json` 머지 (비어있는 키만 채움).
- **프론트:** `ArchiveMode.jsx` (검색창+카드 그리드) + `ArchiveCard.jsx` + `ArchiveDetail.jsx` (슬라이드오버). `AxisAccordion` 컴포넌트로 평가축 행별 독립 펼침 상태.
- `all_cards() → list[dict]` 공개 메서드로 `_cards` 사설 속성 캡슐화 완료.

## Rubric 시스템 (config.py)

**3-A/B/C/D 모두 완료 (2026-06-12~15).**

- **단일 소스:** `build_axis_rubric_block(facility_type, axes_keys=None)` — comparator·myproject_analyzer 공통 사용.
- **구조:** 각 axis에 `description`(1줄) + `signals`(4~5개) + `rubric`(A~E 정의). `FACILITY_AXIS_OVERRIDES[facility_type][axis_key]`로 `signals_extra` + `rubric_hint` 추가.
- **14개 시설유형 override 시드 완료** (시설당 평균 2축, 총 30+ 엔트리). **임원·실무진 검토 후 보정 필요** — 현재는 일반 건축 지식 기반 초안.
- **`grade_justification` 자기검증:** 3개 분석 스키마(MyProject/비교/진단) 모두 `"신호 X/Y개 충족 → <등급> 기준 행과 일치"` 형식. 기존 데이터(필드 없음)는 UI 박스 미표시.
- **`RUBRIC_VERSION = "v1"`** (`config.py`): `axis_rubric_for()` 반환 + `_comparison.json`/`_deep.json`/`diagnosis.json` 저장 파일에 자동 기록. 개정 시 상수만 올리면 전파됨.

---

## Known Issues — TODO

우선순위 표시: 🔴 = 재발 위험 높음, 🟡 = 미해결 버그, 🟢 = 엣지 케이스.

---

### 🔴 재발 위험 — 현재 작동하지만 되돌리면 즉시 망가지는 것들

1. **BRIEF_PROGRAM 스태킹 이미지 크기 한도 (400 Bad Request)**
   - **증상:** `_brief.json`의 `brief_program[0].error` = "Client error '400 Bad Request'", `area_rows: []`. Sheet 5 "면적표상세" 미생성, `## 2. 면적 프로그램` 공백.
   - **원인(1):** `_stack_images_vertically()`가 PNG를 반환하면 5페이지 기준 7~10MB → Anthropic 5MB 한도 초과.
   - **원인(2):** JPEG 변환 후에도 **픽셀 한도 초과** 가능 — Anthropic API는 한 변이 8192px를 초과하면 400 반환. A4 portrait 5페이지 at 150 DPI = 1240×8770px → 초과. `_STACK_MAX_DIM = 7500` 제한으로 수정.
   - **원인(3):** 스태킹 실패 시 **에러 폴백 없음** — `precomputed_program`이 에러 포함 상태로 세팅되어 35개 페이지 전부 개별 추출이 차단됨. 에러 시 `precomputed_program = None` → 개별 추출로 폴백 추가.
   - **현재 상태: FIXED (2026-06-17)** — ① JPEG 출력 + ② 7500px 픽셀 한도 + ③ 에러 시 per-page 폴백. `safe_encode_image()`의 `fitz.Pixmap(io.BytesIO(...))` → `fitz.Pixmap(bytes)` BytesIO 버그도 수정.
   - **재발 조건:** `_stack_images_vertically()` 포맷을 PNG로 되돌리거나, `_STACK_MAX_DIM` 제한을 제거하거나, 폴백 로직(`precomputed_program = None`)을 제거하면 재발.
   - **진단 방법:** 재발 시 GCS `_briefs/*.json`에서 `brief_program[0]` 확인 → `"error": "400"` 여부.

1. **BRIEF_EVALUATION 비연속 페이지 스태킹 → 심사기준 누락**
   - **증상:** `evaluation_categories = [{"name": "평가항목", "points": null}]` — 실제 배점 항목(창의성 및 공공성 등) 누락. Sheet 2 "심사기준" 공백.
   - **원인:** 문서 앞쪽 페이지(예: p.21)와 뒤쪽 페이지(예: p.117)가 모두 BRIEF_EVALUATION으로 분류되어 이어붙여짐 → LLM이 두 맥락을 혼동하여 의미없는 결과 반환.
   - **현재 상태: FIXED** — `_pts_sum == 0`이면 `precomputed_eval = None` → 개별 페이지 추출 폴백. `brief_checklist_exporter._extract_sections()`에서 non-null 배점 최다 페이지를 `max()`로 선택.
   - **재발 조건:** `_extract_sections()`를 `_first(brief_evaluation)`으로 되돌리면 재발.
   - **미해결 엣지:** 실제 배점표가 p.19 같은 BRIEF_SUBMISSION 오분류 페이지에 있는 경우 — 분류기 수정 없이는 해결 불가. 재분석 후에도 심사기준이 비면 `_brief.json`의 `page_map`에서 BRIEF_SUBMISSION 페이지의 `has_scoring_table` 필드를 확인할 것.

---

### 🔴 운영 주의 — GCP 재배포 누락

1. **로컬 코드 변경이 GCP에 반영되지 않는 문제**
   - **증상:** 로컬에서 수정·테스트 후 오류가 사라졌는데 GCP 앱에서는 동일 오류 재발.
   - **원인:** `gcloud run deploy` 실행을 잊음. GCP Cloud Run은 소스를 자동으로 감시하지 않음.
   - **진단:** `gcloud run services describe competition-analyzer --region asia-northeast3 --format="value(status.latestCreatedRevisionName,metadata.creationTimestamp)"` — 타임스탬프가 최근 커밋 이전이면 재배포 필요.
   - **배포 명령:**

     ```powershell
     cd d:\APPS\competition_comparison
     gcloud run deploy competition-analyzer --source . --region asia-northeast3
     ```

   - **이번 세션 이력:** 로컬 JPEG 수정이 5월 21일 이후 배포되지 않아 6월 17일까지 GCP에서 400 오류 지속. 2회 배포 후 해결(revision 00055, 00056).

---

### 🟡 미해결 버그

1. **`BRIEF_EVALUATION` 배점 합계가 100 초과로 추출되는 문제**
   - 실제 배점 합계가 100점인 지침서에서 160점 등으로 추출됨
   - 원인: HWP→PDF 변환 시 병합셀 구조 붕괴로 동일 배점이 여러 행에 중복 집계되는 것으로 추정
   - 수정안: `data_extractor.py` BRIEF_EVALUATION 추출 프롬프트에 "배점 합계 ≈ 100이 되도록 병합셀 중복 제거" 룰 추가, 또는 후처리로 `total_points > 110`이면 경고 flag

---

### 🟢 엣지 케이스

1. **`/run-single` 재실행 시 `_meta.json`의 `submissions` 리스트 초기화**
   - `routers/accumulate.py:676-679` → `save_project_meta(...)`는 항상 `meta["submissions"] = []`로 시작
   - 같은 `project_number + competition_name`으로 두 번째 회사 등록 시 첫 회사의 메타 엔트리가 사라짐 (submission JSON 파일은 디스크에 고아로 남음)
   - MyProjectMode는 1프로젝트=1제출물 전제라 통상 발생 안 함. 다회사 추가는 `/add-submission` 사용
   - 수정안: `save_project_meta`에 `merge=True` 옵션을 두고 기존 `submissions` 리스트를 보존하거나, `/run-single` 진입 시 기존 cid 존재 여부 검사 후 명시적 에러

---

## 추출 정확도 평가 하네스 (tools/eval/)

> B-1 설계 + B-2 구현 완료 (2026-06-15). **B-3 이후는 미진행.**

### 목적

5~10건 과거 공모 PDF에 사람이 라벨링한 정답 JSON과 앱 추출 결과를 비교해 `Brief competition analyzer.md` §8 `ACCURACY_METRICS`의 TBD를 채운다.

### 디렉터리 구조

```text
tools/eval/
├── tolerance.json            # 정량 필드별 허용 오차 (abs/rel OR 조건)
├── ground_truth/             # 라벨러 작성 *_gt.json (커밋 대상)
│   └── TEMPLATE_gt.json      # 복사해서 채우는 템플릿
├── predicted_cache/          # LLM 추출 결과 캐시 (.gitignore)
├── reports/                  # 출력 리포트 (.gitignore)
├── lib/
│   ├── comparators.py        # numeric/jaccard/keyword/normalize 비교
│   ├── loaders.py            # GT 스캔, 캐시 로드/저장
│   └── metrics.py            # 페이지·정량·범주형 비교 + 집계
├── run_pipeline.py           # backend 직접 import → LLM 추출 래퍼
└── run_harness.py            # CLI 진입점
```

### 실행 방법

```powershell
# 캐시 전용 — LLM 비용 없음 (캐시 없는 샘플 스킵)
python tools/eval/run_harness.py --skip-extraction

# PDF 추출 후 평가 ⚠️ ~$0.27/PDF (Haiku 분류 + Sonnet 추출)
python tools/eval/run_harness.py --pdf-dir path/to/pdfs

# 샘플 수 제한 + 시설유형 필터
python tools/eval/run_harness.py --pdf-dir pdfs/ --max-samples 5 --facility-type residential

# 캐시 무시 전체 재추출 ⚠️ LLM 비용 발생
python tools/eval/run_harness.py --pdf-dir pdfs/ --force-rerun
```

### 출력물

- `reports/{ts}_summary.json` — 전체 집계 지표
- `reports/{ts}_per_sample.json` — 샘플별 상세 (misclassified 목록 포함)
- `reports/{ts}_report.md` — 마크다운 리포트 (페이지 유형별 F1 테이블 포함)
- `reports/{ts}_brief_block.md` — `Brief competition analyzer.md` §8에 붙여넣을 ACCURACY_METRICS 블록

### GT 라벨링 가이드

1. `ground_truth/TEMPLATE_gt.json` 복사 → `ground_truth/{facility_type}/{competition_id}/{slug}_gt.json`
2. `pages_by_type`: 각 페이지 번호를 해당 PAGE_TYPE 배열에 기입. 애매한 페이지는 `_ambiguous` 처리 → 분모 제외
3. `quantitative_truth`: 수치 + `source_page` 기입. PDF에 없는 필드는 삭제
4. `field_presence`: PDF에 명시된 필드만 `true` — `false`인데 앱이 값 채우면 환각(field-level FP)으로 집계
5. 2인 교차 라벨링 권장 (건축 실무자 + 검수자)

### `_quantitative` 실제 키 (tolerance.json과 일치)

`merge_extracted_data()` 출력 기준:
`site_area_sqm` · `building_area_sqm` · `total_floor_area_sqm` · `area_above_ground_sqm` · `area_below_ground_sqm` · `floor_area_ratio_pct` · `building_coverage_ratio_pct` · `floors_above` · `floors_below` · `parking_count`

### B-3 이후 미진행 항목

- **B-3**: CI 통합 — `rerun-compare` 완료 후 자동 재평가 훅
- **B-4**: confusion matrix HTML 렌더링 (임원 보고용)
- **B-5**: 모델 ID 교체 시 ΔAccuracy 추적 (sonnet-4-6 → 4-7 회귀 감시)
- `Brief competition analyzer.md` §8 ACCURACY_METRICS 실제 수치 채우기 — GT 라벨링 완료 후 `run_harness.py` 1회 실행으로 생성

---

## 시퀀스 B — 추출 정확도 측정 하네스 (보류)

- B-2까지 구현 완료 (`tools/eval/` 폴더)
- 재개 조건: 제안서 PDF 5건 + 정답지(ground_truth JSON) 준비
- 정답지 형식: `tools/eval/ground_truth/TEMPLATE_gt.json` 참고
- 대상: `D:\EVAL_DB\` (GCS kunwon-competition-db 로컬 복사본)
- 다음 단계: B-3 (ground_truth 2건 이상 완성 후 `run_harness.py` 실행)

---

## 앱 실행 검증 체크리스트 (API 키 필요)

아래 항목들은 코드 로직은 완성됐으나, 실제 Claude API 호출이 필요한 end-to-end 검증이 아직 이루어지지 않은 부분이다. 앱을 기동하고 소규모 실제 데이터로 한 번씩 확인한다.

| # | 확인 항목 | 확인 방법 | 기대 결과 |
| --- | --- | --- | --- |
| V-1 | Tier 0 fast-path 실제 동작 | 디지털 지침서 PDF로 `/api/accumulate/run` SSE 실행 → 서버 로그 확인 | `_source: "digital_haiku"` 로그 출력. 이미지 토큰 대비 입력 토큰 감소 확인 |
| V-2 | `classify_all_pages_brief()` 분류 품질 | 지침서 PDF 업로드 → 분류 결과 JSON 확인 (`_brief.json`의 `pages` 배열) | BRIEF_PROGRAM (면적표 페이지), BRIEF_DESIGN_GUIDE (텍스트 지침), BRIEF_EVALUATION (심사기준) 등 적절히 분류됨 |
| V-3 | BRIEF_PROGRAM / BRIEF_EVALUATION → Vision 경로 강제 | V-2와 동일 실행 + 서버 로그에서 BRIEF_PROGRAM, BRIEF_EVALUATION 페이지 처리 경로 확인 | DIGITAL_TEXT_EXCLUDE_TYPES에 속해 Tier 0 텍스트 경로 미진입, Vision(이미지) 경로로 처리됨 |
| V-4 | BRIEF_* 추출 스키마 적용 | `_brief.json` 열어서 각 BRIEF_* 타입 페이지의 `data` 키 확인 | BRIEF_PROGRAM 페이지에 `required_areas` / `optional_areas` 리스트 등 스키마 키 존재 |
| V-5 | BRIEF_SUBMISSION / BRIEF_ADMIN skip | `_brief.json`의 해당 페이지 엔트리 확인 | `_skipped: true` 또는 `data: {}` — 행정 서식 페이지가 빈 추출 결과로 저장됨 |
| V-6 | `rubric_version` 필드 전파 | `rerun-compare` 실행 후 `_comparison.json` / 진단 후 `diagnosis` JSON 확인 | 최상위에 `"rubric_version": "v1"` 필드 존재 |
| V-7 | MyProject `rubric_version` | MyProjectMode로 단일 제출물 등록 → `_deep.json` 확인 | `"rubric_version": "v1"` 존재 |
| V-8 | 스캔본 PDF → Vision fallback | 텍스트 없는 스캔 PDF로 파이프라인 실행 (보유 시) | Tier 0 None 반환 → Vision(이미지 기반) 추출로 자연 전환. `_source: "vision"` 로그 |
| V-9 | `grade_justification` 출력 | 비교분석 또는 MyProject 실행 후 JSON / HTML 리포트 확인 | 각 axis에 `grade_justification` 문자열 존재. 형식: `"신호 X/Y개 충족 (충족: ... / 미충족: ...) → <등급> 기준 행과 일치"` |

**확인 우선순위:** V-2 → V-3 → V-4 (지침서 분류 파이프라인 핵심) → V-1 (토큰 절감 실측) → V-6/V-7 (rubric 버전) → V-9 (grade_justification)

**주의:** V-8(스캔본 PDF)은 텍스트 없는 실제 스캔 PDF가 없으면 검증 불가. 향후 스캔본 지침서 확보 시 진행.
