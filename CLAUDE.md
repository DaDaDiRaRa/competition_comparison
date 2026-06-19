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
- 배포: Docker + Google Cloud Run (gen2) + GCS 버킷 마운트 (`/data`) — GitHub Actions 자동 배포

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
   - `DELETE /upload/cleanup/{upload_id}` — 파이프라인 완료 후 임시 파일 삭제

6. **`routers/archive.py`** - 아카이브 자연어 검색 (FTS5 in-memory SQLite, `GET /list` + `POST /search` + `GET /{ft}/{cid}`)

7. **`routers/brief.py`** - 지침서 단독 분석 엔드포인트 (PDF + DOCX)
   - `POST /brief/analyze` — 지침서 1개 업로드 → 분류 → 추출 → 요구사항 → 검증 → JSON·MD·xlsx 저장 (SSE)
   - `_validate_brief_file(data, filename)` 확장자 분기: `.pdf` (≤200MB, magic byte `%PDF`) / `.docx` (≤50MB, magic byte `PK\x03\x04`). 기타 확장자 → 400 "PDF 또는 DOCX 파일만 지원합니다"
   - **PDF 경로**: `classify_all_pages_brief(pdf_path)` + `extract_pdf(..., is_brief=True)` (기존 그대로)
   - **DOCX 경로**: `split_docx_to_blocks(docx_path)` → `classify_all_blocks_brief(blocks)` → `extract_docx(docx_path, page_map, is_brief=True)`. 이미지 토큰 0
   - SSE 라벨 분기: docx → "지침서 블록 분류 중" / pdf → "지침서 페이지 분류 중"
   - `_brief_meta.source_format`: `"pdf"` | `"docx"` — 다운스트림 (UI 라벨, list 응답) 에서 사용
   - SSE `complete` 이벤트 + `GET /brief/list` 응답에 `source_format` 포함
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
- `services/docx_loader.py` - DOCX 지침서를 블록 단위로 분할 (PDF 흐름과 완전 독립)
  - `split_docx_to_blocks(path) → list[dict]` — 본문 순회 후 R1~R5 + F1~F3 규칙으로 블록 분할. 각 블록: `{block_num, header_text, paragraphs[], table_markdown, table_rows_raw, merge_info[]}`. block_num이 page_map의 `page` 역할.
  - **분할 규칙:** R1 Heading 1/2/3 스타일 / R2 폰트 휴리스틱(굵게+14pt 이상 또는 16pt 이상) / R3 섹션 번호(`^(제\d+장|\d+(\.\d+){0,3})\s`) / R4 캡션(`[표/양식/서식/별표 N]`) / R5 표는 항상 단독 블록의 마지막 요소
  - **필터/머지:** F1 TOC(`\t\d+$`) → "(목차)" 단일 블록 압축 / F2 orphan 헤더(단락1개+표없음+R3매칭) → 다음 블록의 breadcrumb 누적 ("A > B > C") / F3 단락 60개 OR 12000자 초과 → 강제 컷, " (계속)" suffix
  - **헤더 폴백 순서:** A(Heading) → B(폰트 visual) → C(캡션) → **D(표 첫 행 텍스트 60자)** → E(첫 단락) → F("(블록 N)" 디폴트)
  - **vMerge 감지:** `cell._tc` identity 비교 우선 + tcPr 내 `w:vMerge` element 검사. python-docx 가 vMerge 그룹 전체에 동일 `_tc` 인스턴스를 반환하는 동작을 활용 — XML state만으로는 그룹 시작/끝을 정확히 구분 못 함. **두 시그널을 조합한 로직을 되돌리면 merge_info 가 비게 됨.**
  - 표 → 파이프 마크다운(`table_markdown`): vMerge continue 행은 빈 칸 출력, 셀 60자 컷 + "…", 셀 안 `|` → `&#124;`, 셀 내 개행 → 공백. **`table_rows_raw`**: 동일 표의 원문 텍스트 2D 리스트 — 60자 컷 없이 개행 보존. 추출기·source_text가 이 필드를 우선 사용. `_table_to_markdown` 반환 타입: `tuple[str, list[dict], list[list[str]]]` — `(markdown_str, merge_info, rows_raw)`.
  - `get_block_source_text(block) → str` — 헤더+단락+표 결합. `table_rows_raw` 보유 시 셀당 200자 소프트 캡·행 수 제한 없이 전체 행 출력; 없으면 `table_markdown` fallback (최대 10행). 6000자 초과 시 앞 4000 + 뒤 2000 (중간 "[...생략...]"). 분류·추출 공통 입력.
  - 의존성: `python-docx>=1.1.0` (양쪽 requirements 동기화 필수 — Important Notes 참조)
- `services/page_classifier.py` - Classifies PDF pages (cover, floor plan, section, etc.)
  - `classify_all_pages_brief()` — 지침서 PDF 전용 분류. PRIORITY RULE 2: 비중/배점/점수 컬럼이 있는 표 → `BRIEF_EVALUATION` (BRIEF_DESIGN_GUIDE보다 우선). 응답 JSON에 `has_scoring_table` 필드 추가 (판단 근거 추적용).
  - `classify_all_blocks_brief(blocks) → list[dict]` — DOCX 블록 분류. 텍스트 전용 (이미지 토큰 0). 기존 `BRIEF_CLASSIFY_PROMPT`에 DOCX preamble만 prepend. `_BRIEF_DOCX_PREAMBLE` 에 "이미지 없이 텍스트와 표만으로 분류" 명시. 응답에서 `has_drawing`/`has_rendering` 항상 false 강제, `has_table` 은 block의 `table_markdown` 보유 여부로 결정 (LLM 응답 무시). page_map 스키마는 PDF 경로와 동일 (`page` 필드는 block_num).
  - BRIEF_EVALUATION vs BRIEF_DESIGN_GUIDE 구분 기준: 배점 표(비중/배점/점수 컬럼, 합계 ≈ 100) → BRIEF_EVALUATION / 글머리기호(•) 위주 텍스트, 표 없음 → BRIEF_DESIGN_GUIDE
  - **`has_scoring_table=False` 강등:** `_normalise_brief_result()`에서 LLM이 `has_scoring_table=False`를 반환하면 BRIEF_EVALUATION → BRIEF_ADMIN으로 강등. 참여자 명단·등록업체 목록(표 있으나 배점 없음)의 오분류 방지.
  - **BRIEF_ADMIN 조건 (f):** "참여자 명단·참가업체 목록·설계공모 참여자·등록업체" 페이지는 표 유무와 무관하게 BRIEF_ADMIN. BRIEF_EVALUATION NOT 조건에 명시.
- `services/data_extractor.py` - Extracts structured design data from pages; `merge_extracted_data()` returns `_quantitative` dict at top level
  - `extract_docx(docx_path, page_map, is_brief=True) → list[dict]` — DOCX 블록별 추출. rasterize 없음, 이미지 토큰 0. 반환 스키마는 `extract_pdf` 와 동일 (`[{"page": block_num, "type", "data", ...}, ...]`). 분기: ① `BRIEF_ADMIN` / priority≥3 → 스킵 ② `BRIEF_EVALUATION` + `table_markdown` 존재 → `_extract_docx_eval_from_table()` (LLM 없이 표 구조 직접 파싱, **환각 원천 차단**) ③ 그 외 → `_extract_docx_block_with_llm()` (텍스트+표 마크다운만 전달, 이미지 없음)
  - `_extract_docx_eval_from_table(block) → dict` — `table_rows_raw` 우선 사용(fallback: `table_markdown` 파싱). 표 첫 행에서 `비중|배점|점수|가중` 컬럼 자동 식별. **두 가지 vMerge 패턴 처리**: (A) name_col vMerge + 행별 points → 한 카테고리의 sub_items + 행별 점수 합 / (B) points_col vMerge → shared_with 배열 자동 생성 (영등포 환각 차단). 소계/합계 행(`소\s*계|합\s*계|총\s*계|^합계|^total`) 자동 제외 → total_points에서 빠짐. 명시적 총계 행이 95~105 범위면 그대로 total_points로 사용 (LLM 무환각 fast-path).
  - `BRIEF_PROJECT_INFO` 스키마에 **`unit_program[]` 필드** (2026-06-18 추가) — 단위세대 분배/시설별 면적 제약 표를 한 행씩 entry로 캡쳐. 필드: `{block, tenure(분양/임대/""), type_label(84형 등), area_text, ratio_text, note}`. KT 케이스(1,2BL/3BL/근린생활/부대복리/공공기여시설) 처럼 단일 site 스칼라 필드로 표현 불가한 분배 정보를 모두 보존. 프롬프트에 "표의 모든 행 빠짐없이 / 자기검열 금지" 룰 명시. `_merge_brief_project_info_pages()`가 `_TOP_LISTS`에 `unit_program` 포함 — dict 항목은 JSON repr 해시로 dedup.
  - `DIGITAL_TEXT_EXCLUDE_TYPES` — `{"AREA_TABLE","TECHNICAL","INCENTIVE_TABLE","BUSINESS_VIABILITY","AREA_INCREASE","BRIEF_PROGRAM","BRIEF_REGULATIONS","BRIEF_EVALUATION","BRIEF_PROJECT_INFO"}`. 이 타입들은 fitz.get_text() Tier 0을 건너뛰고 타일-비전 경로로 처리. `BRIEF_EVALUATION` / `BRIEF_PROJECT_INFO` 추가 이유: HWP→PDF 변환 시 병합 셀 구조 붕괴 → 구분/항목/비중 관계 오독 위험.
  - `BRIEF_EVALUATION` 추출 스키마: `evaluation_categories[].sub_items`(구분 하위 세부항목 문자열 배열) + `evaluation_categories[].shared_with`(병합 셀로 배점이 공유된 형제 구분 이름 목록) 추가. `total_points`는 배점 합계(통상 100).
  - **BRIEF_EVALUATION 다중 페이지 스태킹:** `extract_pdf(is_brief=True)` 진입 시 BRIEF_EVALUATION 페이지가 2개 이상이면 `_stack_images_vertically()` (PIL)로 세로 이어붙임 → LLM에 1회 전달. `precomputed_eval`에 결과 저장, 나머지 페이지는 `{"data": {}, "_merged": True}` 반환. 병합 셀이 페이지 경계를 넘어도 표 구조를 한 번에 파악 가능.
  - **BRIEF_EVALUATION 스태킹 폴백:** 스태킹 추출 후 non-null points 합계(`_pts_sum`)가 0이면 스태킹 결과 폐기(`precomputed_eval = None`) → `stacked_eval_set` 비워짐 → 각 페이지 개별 추출. 연속되지 않은 페이지(예: p.21 + p.117)가 분류되어 스태킹됐을 때 LLM 혼동 방지.
  - **BRIEF_PROGRAM 다중 페이지 스태킹:** 5페이지 청크 단위(`_PROG_CHUNK=5`)로 스태킹 후 `area_rows` 추출. 청크 결과를 `extend()`로 병합.
  - **`_stack_images_vertically()` — JPEG 출력:** PIL 스태킹 결과를 **JPEG(quality=85)**로 저장. PNG 대비 파일 크기 약 1/10 → Anthropic API 5MB 이미지 한도 초과 방지. 5페이지 PNG = 7~10MB → 400 오류 / JPEG = 0.5~1MB → 정상. **PNG로 되돌리면 BRIEF_PROGRAM이 많은 지침서(36페이지 등)에서 400 오류 재발.**
  - **`_image_block()` — JPEG 마법 바이트 감지:** `img_bytes[:3] == b'\xff\xd8\xff'`이면 `media_type: "image/jpeg"`, 아니면 `"image/png"`. `safe_encode_image()`에 올바른 `fmt` 전달. 포맷 불일치는 또 다른 400 오류 원인.
  - **`points_sum_warning`:** 스태킹 후 `null`이 아닌 `points` 합계가 95~105 범위를 벗어나면 `precomputed_eval["data"]["points_sum_warning"] = True` 플래그 추가. `brief_checklist_exporter`가 경고로 노출.
  - **BRIEF_PROJECT_INFO FIELD NOTES:** 한국어 표현 → 스키마 키 명시 매핑 추가 (`건폐율(%)` → `building_coverage_pct`, `용적률(%)` → `floor_area_ratio_pct`, `대지면적(㎡)` → `site_area_sqm`, `건축규모/연면적(㎡)` → `floor_area_sqm`, `높이(m)` → `max_height_m`, `공개공지(㎡)` → `open_space_sqm`). 괄호 접두사(`(완화) 460%`) → 숫자만 추출 룰, 부지 복수 → `sites` 배열 분리 룰.
  - **토큰 절감 라우팅 (제안서용):**
    - `OCR_FIRST_TYPES = {"AREA_TABLE","TECHNICAL","SUSTAINABILITY","BUSINESS_VIABILITY","AREA_INCREASE","COMPANY_PORTFOLIO","CONSTRUCTION_PLAN"}` — PaddleOCR(로컬·무료)로 텍스트 읽고 Haiku로 구조화. Sonnet+이미지 대비 페이지당 ~90% 비용 절감. `OCR_MIN_CHARS = 80` 미만이면 자동 vision fallback.
    - `SKIP_PAGE_TYPES = {"COVER","RENDERING_EXT","RENDERING_INT"}` + `SKIP_PRIORITY_THRESHOLD = 3` — 비교분석 기여도 낮은 페이지 자동 스킵. 복원하려면 `settings.extraction_priority_limit = 3`.
  - **`_extract_docx_block_with_llm` max_out 계층화:** `BRIEF_PROGRAM`/`BRIEF_EVALUATION` → 8000토큰, `BRIEF_DESIGN_MASSING`/`BRIEF_DESIGN_GUIDE`/`BRIEF_DESIGN_FACADE`/`BRIEF_DESIGN_SUSTAIN`/`BRIEF_DESIGN_SPECIAL` → 6000토큰, 기타 → 2000토큰. `_FORCE_CUT_PARAS=60` 상한으로 늘어난 블록 크기에 대응 (구 4000 → 6000). **JSON 파싱 실패 폴백:** BRIEF_DESIGN_* 파싱 실패 시 `design_guidelines_grouped`만 추출하는 단순 프롬프트로 재시도(max_out=8000) → `_fallback: true` 플래그 포함 반환. 두 번 모두 실패 시에만 `{"error": "..."}` 저장.
  - **`_extract_brief_reqs_sync` 타입 가드:** `parse_json_response()` 결과가 dict가 아닌 경우(LLM이 배열 반환 시) `{"requirements": [], "evaluation_criteria": [], "special_requirements": []}` 빈 fallback 반환. 이전엔 list가 그대로 `requirements` 인자로 전달되어 validate_brief에서 `'list' object has no attribute 'get'` 오류 발생.
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
- `services/brief_validator.py` - 지침서 검증 (LLM 호출 없음). `validate_brief(brief_data, requirements) → dict`. 반환: `{flags: [...], summary: {high, medium, low}, checked_rules}`. 각 flag: `{rule_id, severity, message, evidence}`. **진입 시 `requirements`가 dict가 아니면 `{}` 교체** — LLM이 배열 반환한 경우 방어.
- `services/brief_checklist_exporter.py` - 지침서 체크리스트 내보내기 (LLM 호출 금지). `to_markdown(brief_data, validation) → str` / `to_xlsx(brief_data, validation) → bytes`. openpyxl lazy import (`import openpyxl` 함수 내부).
  - **헬퍼:** `_first(data, key)` — `merge_extracted_data()` dict-or-list 반환 정규화. `_collect(data, key)` — 여러 페이지 리스트 필드 합산. `_v(val, unit)` — null/빈값 → `"(없음)"`, 리스트 → 쉼표 조인. `_write_kv(ws, label, val, row, val_end_col=2)` — 셀 병합 지원 KV 쓰기.
  - **`brief_evaluation` 다중 페이지 처리:** `_extract_sections()`에서 `brief_evaluation` 리스트 내 non-null 배점 수가 가장 많은 페이지를 `max(key=_eval_pts)`로 선택. `_first()`(항상 첫 페이지)를 쓰면 BRIEF_EVALUATION 스태킹 폴백 시 p.21이 빈 결과여도 p.117의 실제 배점표가 무시됨. **`_first(brief_evaluation)`으로 되돌리면 비연속 페이지 케이스에서 심사기준 Sheet 전체 누락 재발.**
  - **`_COST_KW` 필터:** area_table 조립 후 `{"공사비","내역서","공종","원가","견적"}` 키워드를 group_name에 포함한 그룹 제거 (개략공사비 내역서 등 비설계 항목 배제).
  - **`_fmt_bullets(subs, desc) → str`:** sub_items를 Excel 셀 멀티라인으로 변환. 복수 항목 → 항목별 한 줄 / 단일 항목: `\n` 개행 분리 우선(`table_rows_raw` 원본 경로), 없으면 인라인 불릿 문자(▪•·◦▸▶▷) 분리. 각 줄 앞에 `•` 없으면 자동 추가.
  - **Excel (4 시트):** Sheet 1(면적·프로그램) `freeze_panes="A3"`, KV `val_end_col=4`로 병합. Sheet 2(심사기준) **3열 구조 `구분|세부기준|배점`** — Col A 동일 이름 연속 행 병합, Col B `_fmt_bullets`로 멀티라인 세부기준(한 셀에 불릿 여러 줄), Col C 항목별 독립 배점(병합 안 함), `freeze_panes="A3"`. Sheet 3(요구사항) 2열 라벨+내용 구조, `design_guidelines_grouped` 기반 — `facility_scope != "전체"` → **"시설별 지침"** 섹션, `facility_scope == "전체"` → **"설계 지침 및 요구사항"** 섹션. `grouped`가 비어 있을 때만 flat 폴백(특수요구사항/기타설계지침/후퇴선요건 등) 표시, `freeze_panes="A3"`. Sheet 4(검증경고) `freeze_panes="A3"`.
  - **MD (`to_markdown`):** 프로그램·LLM 연동용 구조화 데이터 덤프. 마크다운 표 없음. 형식: `key: value` 한 줄 / `- item` / 들여쓰기 `- sub_item` 계층 리스트. null 필드는 `(없음)` 명시. 5개 섹션: 1.사업개요 / 2.면적프로그램 / 3.심사기준(평가항목별 `### Name` 블록) / 4.요구사항·설계지침(`design_guidelines_grouped` 기반 "시설별 지침" + "설계 지침 및 요구사항"; grouped 없을 때만 flat 폴백 표시) / 5.검증경고(`[심각도] type: message | 위치: ...` 형식).
- `services/grade_helpers.py` - 등급 처리 단일 소스. `LEGACY_GRADE_MAP`, `GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade(d, *, check_overall=False)`. `report_generator` / `diagnosis_report_generator` / `myproject_report_generator` 모두 여기서 import.
- `services/diagnosis_report_generator.py` - 진단 결과 HTML 리포트 생성 (LLM 호출 없음). `generate_diagnosis_report(diagnosis: dict) -> str`. 섹션: 종합점수 링 → 페이지 구성 바 → 패턴 편차 경고 → 지침서 충족도 → 요구사항 매핑 → 평가축별 상세 → 보강 포인트
- `services/pattern_builder.py` - Builds patterns from winner data + qualitative LLM summary; `build_pattern()` now also collects `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords) for loser anti-pattern comparison
- `services/utils.py` - PDF rasterizer using PyMuPDF (`rasterize_pdf`), SSE helper, JSON parser. **공유 dict 헬퍼 `_first(data, key) → dict`, `_as_list(data, key) → list` 도 여기 단일 정의** — 다른 모듈에서 `from services.utils import _first, _as_list`. 이전엔 `brief_checklist_exporter` / `brief_validator` 에 중복 정의돼 있던 것을 통합 (2026-06-18).
  - `user_error_msg(e: Exception) → str` — 예외를 사용자 친화적 한국어 메시지로 변환. `LocalProtocolError`/illegal header(API 키 형식 불량) → 401/502/429/timeout/PDF/JSON 패턴 매핑 순. `accumulate.py` / `diagnose.py`에서 공통 사용.
  - `parse_json_response(text)` — 3단계 복구: ① 펜스 제거 → ② 직접 파싱 → ③ `{...}` 또는 `[...]` 추출 + 후행 쉼표 제거. LLM이 마크다운 코드블록이나 산문을 섞어도 JSON 추출 가능.

**Configuration:**

- `config.py` - Facility types, page types, comparison axes, Claude model ID, DPI settings
  - `FACILITY_TYPES = {key: {"label_ko": str, "group": "redev"|"general"}}` — 구조 변경됨. 단순 `{key: str}` 아님
  - `facility_label(facility_type) → str` — label_ko 반환 헬퍼
  - `PAGE_TYPES_META = {PAGE_TYPE: "한국어명", ...}` — 27개 전체
  - `COMPARISON_AXES_BY_GROUP = {"redev": {...8축...}, "general": {...8축...}}` — 그룹별 axes
  - `axes_for(facility_type) → dict` — facility_type의 group에 맞는 axes 반환
  - `axes_keys_for(facility_type) → list` — axes 키 목록
  - `COMPARISON_AXES_META` / `COMPARISON_AXES` — legacy aliases (redev 그룹, 하위호환용)
  - `DEFAULT_DB_PATH` — 우선순위: `DB_PATH` 환경변수(GCP에서 `/data`) → `~/CompetitionAnalyzerDB` (로컬 기본값)
  - Cloud Run 배포 시 `DB_PATH=/data` 환경변수로 GCS 마운트 경로 지정
  - `settings.db_path` — `app_settings.json`의 `db_path` 값 우선, 없으면 `DEFAULT_DB_PATH`
  - `settings.has_db_path` — 사용자가 명시적으로 경로를 설정했는지 여부
  - `settings.set_db_path(path)` — 경로를 `app_settings.json`에 저장
  - `settings.api_key` — 메모리 우선, 없으면 `ANTHROPIC_API_KEY` 환경변수. **양쪽 모두 `_sanitize_api_key()` 적용** — `echo -n "key"` 셸 아티팩트(`-n`접두사, `\r\n`, 따옴표) 자동 제거
  - `settings.set_api_key(key)` — 세션 메모리에만 저장. 디스크 기록 안 함
- `app_settings.json` - User-configurable settings (created at runtime)

### Frontend (React + Vite)

Located in `frontend/` (repo root), the app has seven main tabs (정의: `App.jsx::TABS`):

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
6. **ArchiveMode** - 아카이브 자연어 검색 (검색창 + 카드 그리드 + 슬라이드오버 상세)
7. **BriefMode** - 지침서 단독 분석 UI (`POST /api/brief/analyze`)
   - 지침서 PDF **또는 DOCX** 업로드 → SSE 진행 → 분석 완료 시 md/xlsx 다운로드 + 검증 경고 요약 표시
   - DropZone `accept=".pdf,.docx"` — 두 형식 모두 허용. docx 선택 시 "텍스트와 표만 분석됩니다. 도면이 포함된 지침서는 PDF로 업로드해주세요" 안내 박스 표시
   - `sourceFormat` 결정: complete 이벤트의 `source_format` 우선, 없으면 업로드 파일 확장자
   - flag location 라벨: `sourceFormat==="docx"` 일 때 `p.N` → `블록 N` 정규식 치환 (UI 일관성)
   - `routers/brief.py`와 짝을 이루는 유일한 프론트 모드

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

1. Upload brief **PDF or DOCX** (multipart 또는 `/api/upload` `file_ref`). `_validate_brief_file()` 가 확장자 + magic byte 검증 후 `source_format` 결정 (`"pdf"` | `"docx"`).
2. **분류 (분기):**
   - PDF: `classify_all_pages_brief(pdf_path)` — 이미지 기반 vision 분류
   - DOCX: `split_docx_to_blocks(docx_path)` → `classify_all_blocks_brief(blocks)` — 텍스트 기반 분류 (이미지 토큰 0)
   - 결과 스키마는 동일 (page_map). DOCX 경우 `page` = `block_num`.
3. **추출 (분기):**
   - PDF: `extract_pdf(pdf_path, page_map, is_brief=True)` — vision/tiled/OCR/digital text 다단 추출
   - DOCX: `extract_docx(docx_path, page_map, is_brief=True)` — 텍스트+표 마크다운만 전달. BRIEF_EVALUATION 표는 `_extract_docx_eval_from_table()` 로 LLM 없이 직접 파싱 (환각 차단)
4. `merge_extracted_data(page_map, extractions)` → `brief_data`. BRIEF_PROJECT_INFO 다중 페이지/블록은 `_merge_brief_project_info_pages()` 로 합쳐짐 (sites[]·special_conditions[]·unit_program[] 모두).
5. `extract_brief_requirements(brief_data, facility_type)` → `brief_data["_requirements"]`
6. `validate_brief(brief_data, requirements)` → `brief_data["validation"]` (flags / summary)
7. `_brief_meta` 에 `source_format` 기록 (검증 단계 이전에 설정 — `_check_facility_keyword_conflict` 가 facility_type 읽음)
8. 저장: `_atomic_write(json)` + `_sync_write(md)` + `_sync_write_bytes(xlsx)`
9. SSE `complete` 이벤트: `{brief_id, md_filename, xlsx_filename, validation_summary, source_format}`

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

**`app_settings.json`** (저장 위치: `backend/app_settings.json`. `config.py::_resolve_settings_file()` 참조):

```json
{
  "db_path": "C:\\Users\\사용자명\\CompetitionAnalyzerDB",
  "raster_dpi_classify": 72,
  "raster_dpi_extract": 120,
  "model_id": "claude-sonnet-4-6",
  "model_id_classify": "claude-sonnet-4-6"
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
- **Model split:** 분류·추출·비교·진단 모두 `claude-sonnet-4-6`. **분류기는 2026-06-18 Sonnet으로 통일** — Haiku 4.5가 페이지 헤더 텍스트를 일반화/환각하는 케이스 발견(영등포구 청사 케이스: p.18 헤더를 "[표 06] 심사평가 주안점" 대신 "배점 표"로 일반화 → 헤더 기반 후처리 강등 무력화). Sonnet 분류 비용은 페이지당 ~$0.004로 분류 오류로 인한 토큰 손실보다 작음.
- **CORS:** Vite dev server (5173) and localhost:3000 allowed.
- **File Naming:** Components PascalCase. API paths kebab-case.
- **Page Types:** 27개 — 일반 20개 + 재건축 전용 7개(`BUSINESS_VIABILITY`, `AREA_INCREASE`, `VIEW_ANALYSIS`, `COMMUNITY_PROGRAM`, `COMPANY_PORTFOLIO`, `CONSTRUCTION_PLAN`, `UNIT_PLAN_PENTHOUSE`). `PAGE_TYPES_META`에 전체 한국어명 정의.
- **ProgressLog Events:** All SSE events must include `_timestamp` for elapsed time display.
- **PDF Rasterizer:** `services/utils.py::rasterize_pdf` (PyMuPDF) 가 단일 경로. PaddleOCR은 `services/utils.py::ocr_page()`에서 lazy-load — `requirements-ocr.txt` 미설치 시 자동 스킵.
- **FastAPI Lifespan:** `main.py`는 `@app.on_event` 대신 `@asynccontextmanager async def lifespan()` 사용. `init_db()` 실패해도 서버가 뜨도록 graceful 처리.
- **배포:** `main` 브랜치 push → GitHub Actions(`.github/workflows/deploy.yml`) 자동 실행 → Docker 이미지 빌드 → Cloud Run 배포. 수동 배포나 빌드 스크립트 불필요. 자세한 내용은 `DEPLOYMENT.md` 참조.
- **로깅 (GCP):** Cloud Run 로그는 `gcloud logging read "resource.type=cloud_run_revision" --limit=50`으로 확인. 개발 모드에서는 uvicorn 콘솔 로그 직접 확인.
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
- **New Machine Setup:** `git clone` → `pip install -r requirements.txt` + `npm install` → 백엔드/프론트 실행 → 브라우저 설정 탭에서 DB 경로 + API 키 입력. DB 경로 미입력 시 `~/CompetitionAnalyzerDB` 자동 사용. 배포는 `git push origin main` → GitHub Actions 자동 처리.
- **PaddleOCR (선택):** 이미지 기반 PDF(텍스트 없는) OCR 필요 시만 `pip install -r requirements-ocr.txt`. 기본 파이프라인은 PyMuPDF + Claude vision으로 동작하므로 불필요.
- **DOCX 지침서 지원:** `python-docx`(필수, 양쪽 requirements 동기화) + `services/docx_loader.py` 모듈. PDF 흐름과 완전 독립 — `classify_all_blocks_brief` / `extract_docx` 가 별도 함수. block_num을 page 필드로 재사용해 page_map 스키마 호환. **이미지 토큰 0**(텍스트+표 마크다운만 LLM에 전달). 도면/렌더링 페이지는 인식 불가 — UI에서 "도면 포함 지침서는 PDF로" 안내.
- **테스트 스위트 — DOCX 흐름:** `tests/test_docx_extractor.py` (pytest). 10개 단위 테스트: split 6케이스 (빈 docx, 표 3개, 폰트 휴리스틱, vMerge·merge_info, TOC 압축, force-cut 31단락) + eval 4케이스 (정상 100점, points_col vMerge→shared_with, 소계행 자동 제외, 배점 컬럼 없음→빈 결과). 모든 픽스처 python-docx로 in-memory 생성(LLM/네트워크 의존 없음). 실행: `backend/venv/Scripts/python.exe -m pytest tests/test_docx_extractor.py -v`. **신규 docx 관련 코드 추가 시 회귀 보호 필수 — 새 시나리오는 반드시 테스트 추가**.
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
- **구조:** 각 axis에 `label_ko` + `label_dash`(차트용 대시 형식) + `description`(1줄) + `icon` + `signals`(4~5개) + `rubric`(A~E 정의). `FACILITY_AXIS_OVERRIDES[facility_type][axis_key]`로 `signals_extra` + `rubric_hint` 추가.
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

1. **BRIEF_EVALUATION 환각 심사기준 (오분류 → 스태킹 → LLM 환각)**
   - **증상:** 청사 공모(facility_type=`public`)에서 추출된 `evaluation_categories.sub_items`에 "본 연구원의 특성", "연구원의 전체성" 등 PDF에 존재하지 않는 문구. 배점 합계는 100점으로 맞아 떨어져 `_check_points_mismatch`로는 검출 불가.
   - **원인 사슬:**
     1. **B1 (분류 오분류):** Haiku 분류기가 `[서식 19] 참가자 소명서`(별첨), `결과 발표`, `시상금 내역` 같은 행정 페이지를 `BRIEF_EVALUATION + has_scoring_table=true`로 잘못 분류
     2. **B2 (스태킹):** 실제 심사기준 페이지(p.18~19)와 오분류된 별첨/결과 페이지(p.21, p.117)가 함께 스태킹돼 한 이미지로 합쳐짐
     3. **B3 (환각):** Sonnet 추출기가 혼란 + 학습 데이터 패턴(과거 연구원 공모)으로 fill-in → "연구원" 평가항목 환각. 100점 합계도 자동 맞춤
   - **현재 상태: FIXED (2026-06-17 ~ 2026-06-18)** — 5중 방어:
     - **B1a:** `page_classifier.py::BRIEF_CLASSIFY_PROMPT`에 BRIEF_EVALUATION NOT 조건 (g)~(j) 추가 (결과 발표·시상금·**상품 및 내용**·서식·별첨·부록·소명서 헤더 → BRIEF_ADMIN). 헤더 키워드 명시.
     - **B1b:** 분류기 응답 스키마에 `page_header_text` 필드 추가 + `_normalise_brief_result()`에 `_NOT_EVAL_HEADER_PATTERNS` 정규식 후처리 (`상품 및 내용`, `상품` 단독 패턴 포함). LLM이 EVAL로 잘못 답해도 헤더 패턴 매칭 시 BRIEF_ADMIN으로 강등.
     - **B1c (2026-06-18):** `config.py::MODEL_ID_CLASSIFY`를 Haiku → Sonnet으로 변경. Haiku가 페이지 헤더 텍스트를 일반화/환각하여 B1b의 헤더 후처리가 무력화되는 케이스 발견 (영등포구 청사: p.18 헤더 "[표 06] 심사평가 주안점" 대신 "배점 표"로 일반화). Sonnet은 헤더를 원문 그대로 반환.
     - **B3:** `config.py::FACILITY_CONFLICT_KEYWORDS` 14개 시설유형 매핑(public→연구원/병원/공장/리조트 등) + `brief_validator.py::_check_facility_keyword_conflict()` — `evaluation_categories.name`/`sub_items`에 충돌 키워드 등장 시 `severity=high` 플래그.
     - **B4 (2026-06-18):** `data_extractor.py::BRIEF_EVALUATION` 추출 프롬프트에 환각 금지 가드 추가. 이미지에 명시되지 않은 카테고리 추출 금지, 흐릴 때 빈 결과 반환 룰, 시설 충돌 키워드 발견 시 카테고리 추출 중단 룰. 추출 단계의 마지막 안전망.
   - **재발 조건:**
     - `BRIEF_CLASSIFY_PROMPT`에서 (g)~(j) NOT 조건이나 `page_header_text` 필드를 제거 → B1a/B1b 무력화
     - `_normalise_brief_result()`의 `_NOT_EVAL_HEADER_PATTERNS` 강등 블록 제거
     - `_NOT_EVAL_HEADER_PATTERNS`에서 `상품 및 내용`/`상품` 패턴 제거 → p.22 같은 상품 표 재오분류
     - `MODEL_ID_CLASSIFY`를 Haiku로 되돌리면 헤더 환각으로 B1b 후처리 무력화 → 재발
     - `FACILITY_CONFLICT_KEYWORDS`에서 시설유형 항목 제거 또는 `_check_facility_keyword_conflict`를 `validate_brief()`에서 호출 제거
     - `data_extractor.py::BRIEF_EVALUATION` 프롬프트의 "환각 금지 (CRITICAL)" 블록 제거 → 추출 단계 안전망 사라짐
   - **하드코딩 금지 원칙:** 페이지 번호는 절대 하드코딩 안 함 — 모든 룰이 헤더 텍스트 또는 시설유형 키워드 기반.
   - **진단 방법:**
     1. `_brief.json`의 `page_map`에서 각 페이지 `page_header_text` 확인 → "결과 발표"/"시상금"/"[서식"/"별첨"/"소명서" 포함 페이지가 BRIEF_EVALUATION이면 분류 오류
     2. `_brief.json.validation.flags`에 `facility_keyword_conflict` 플래그가 보이면 PDF와 대조 필수
     3. 발견 시 `app_settings.json`의 `model_id_classify`가 `"claude-sonnet-4-6"` (Sonnet)인지 확인 후 재분석 — **Haiku로 되돌리면 헤더 환각으로 방어 로직 무력화**

---

### 🔴 운영 주의 — GCP 재배포 누락

1. **로컬 코드 변경이 GCP에 반영되지 않는 문제**
   - **증상:** 로컬에서 수정·테스트 후 오류가 사라졌는데 GCP 앱에서는 동일 오류 재발.
   - **배포 방식:** GitHub `main` 브랜치에 push하면 **GitHub Actions가 자동으로 GCP Cloud Run에 배포**. 수동 `gcloud run deploy` 불필요.
   - **진단:** `gcloud run services describe competition-analyzer --region asia-northeast3 --format="value(status.latestCreatedRevisionName,metadata.creationTimestamp)"` — 타임스탬프가 최근 커밋 이전이면 GitHub Actions 실행 여부 확인.
   - **수동 배포 (Actions 실패 시 fallback):**

     ```powershell
     cd d:\APPS\competition_comparison
     gcloud run deploy competition-analyzer --source . --region asia-northeast3
     ```

   - **이번 세션 이력:** 로컬 JPEG 수정이 5월 21일 이후 배포되지 않아 6월 17일까지 GCP에서 400 오류 지속. 2회 배포 후 해결(revision 00055, 00056).

1. **신규 의존성 추가 시 양쪽 requirements 동기화 (CRITICAL)**
   - **증상:** 로컬은 정상 동작하는데 GCP 배포 후 `ModuleNotFoundError: No module named 'xxx'` 발생.
   - **원인:** `backend/requirements.txt` (로컬 dev 용) 와 `backend/requirements-server.txt` (Docker/Cloud Run 용) 는 **분리된 파일**. Dockerfile 16행이 `requirements-server.txt` 를 설치하므로 거기 없으면 GCP 컨테이너에 미설치.
   - **체크리스트 — 신규 Python 패키지 추가 시 항상 두 파일 모두 수정:**
     1. `backend/requirements.txt` 에 추가 (로컬 dev용, 보통 `>=` 버전 핀)
     2. `backend/requirements-server.txt` 에 추가 (서버용, `==` 정확한 버전 핀)
   - **OCR 전용 패키지는 예외:** PaddleOCR 등 무거운 의존성은 `requirements-ocr.txt` 에만 (선택 설치).
   - **이번 세션 이력:** 2026-06-18 DOCX 지원 추가 시 `python-docx` 를 `requirements.txt` 에만 추가하고 `requirements-server.txt` 누락 → GCP 배포 후 첫 DOCX 분석 시 ModuleNotFoundError. 두 파일 동기화 후 재배포로 해결.

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

## 시퀀스 C — 멀티파일 지침서 업로드 (보류, 2026-06-18 결정)

같은 프로젝트에 지침서 + 과업지시서가 별도 파일(또는 별첨/부록)로 분리돼 있는 케이스를 지원. 현재는 `/brief/analyze` 가 단일 파일만 받음. 형식 혼합(PDF + DOCX) 도 흔하므로 형식 무관 처리 필요.

**검토한 3가지 접근:**

- **A. 업로드 시점 multi-file 동시 분석 (권장)** — DropZone `multiple=true`, 백엔드는 파일별로 분할/분류 후 `page_map` 항목에 `source_file: "지침서.docx"` 필드 추가하여 단일 `brief_id` 로 머지. xlsx/검증 flag 마다 출처 라벨 노출. 작업량: ① 업로드 multi-file + ② page_map source_file 필드 + ③ exporter 출처 라벨링.
- **B. 파일별 별도 brief + 프로젝트 그룹 개념** — 각 파일이 독립 brief_id, `project_group_id` 로 묶음. 그룹 카드 UI 신설. 장점: 파일 단위 재분석 가능. 단점: 그룹 모델·UI·통합 비교 로직 모두 신규.
- **C. 파일 병합 후 단일 분석** — PDF 는 PyMuPDF 머지, DOCX 는 본문 이어붙이기. 단순하지만 `p.50` 이 어느 파일인지 모르게 되어 검증 flag location 추적이 의미 잃음. 채택 비권장.

**보류 사유:** 우선 1파일 케이스 안정화 (Adjustment A/B/C 검증 + 영등포 PDF 회귀 확인) 가 선행되어야 함.

**재개 조건:**

1. 사용자가 실제 멀티파일 케이스(지침서 + 과업지시서) 샘플 제공.
2. **충돌 우선순위 룰 결정** — 두 파일이 같은 사업개요·심사기준을 중복 담고 있을 때 어느 쪽이 우선인지 (예: "지침서" 라벨 파일 우선, 또는 파일명 알파벳순, 또는 사용자 명시 순서).
3. 진행 시 접근 A 부터 시작 — `_brief_meta.source_files: list[{name, format, blocks_or_pages_range}]` 도입.

**영향 범위 (재개 시):**

- 백엔드: `routers/brief.py::analyze_brief` 시그니처 변경 (`UploadFile | list[UploadFile]`), `_validate_brief_file` 파일별 호출, `merge_extracted_data` 가 source_file 보존
- 프론트: `BriefMode.jsx` DropZone `multiple` + 업로드 리스트 UI
- exporter: 시트1 r4~ 행에 "[지침서] / [과업지시서]" 라벨 컬럼 추가, 검증 flag location 에 `source_file` 포함

---

## 시퀀스 D — BRIEF_DESIGN_* 다중 페이지 섹션 연속성 (B안: 순차 + 컨텍스트 주입, 2026-06-19)

PDF 지침서의 설계지침 섹션이 페이지 경계를 넘어갈 때 자식 항목이 부모 섹션과 분리되어 가공의 top-level 헤더 아래에 평탄화되는 문제. 영등포구 통합 신청사 PDF p.45~46 직무공간 케이스에서 확인.

### 진화 이력

- **A안 (청크 스태킹, 폐기됨, 2026-06-19):** 3페이지 청크로 `_stack_images_vertically()` → 1회 LLM. 시각적 들여쓰기로 부모-자식 관계 보존하려 했으나 두 가지 치명적 실패:
  1. **해상도 페널티:** 3페이지 압축 → 페이지당 1/3 해상도 → 작은 글씨 자식 항목(면대실/비품창고 등) 누락
  2. **계층 보존 실패:** 영등포 p.45 청크 결과가 여전히 `facility_scope="전체"` 평탄화 — 청크 안에서도 부모 헤더가 한 페이지에만 있으면 LLM이 컨텍스트 못 살림
  - V-10b 회귀 검증에서 "오히려 내용이 사라진 것처럼 보임"으로 드러나 폐기. BRIEF_PROGRAM 스태킹이 같은 이유로 폐기된 전례 반복.

- **B안 (채택, 2026-06-19):** 같은 type 연속 페이지를 그룹핑하고, 그룹 내에서는 **순차 실행**하면서 직전 페이지의 마지막 grouped 항목(facility_scope/space_scope/section_path)을 다음 페이지 프롬프트에 컨텍스트 힌트로 주입.

### 구현 위치

- `data_extractor.py::extract_pdf()` 진입부 BRIEF_DESIGN_* 그룹 처리 블록
- `_process_design_group()` 내부 async 함수 — 그룹 안에서는 순차, 다른 그룹끼리는 `asyncio.gather`로 병렬

### 동작 요약

- 같은 type 연속 페이지를 그룹핑 (max chunk size 없음 — 그룹 크기 자유)
- 그룹 첫 페이지: 컨텍스트 없이 추출
- 그룹 N+1 페이지: 직전 페이지의 마지막 3개 grouped 항목에서 `{facility_scope, space_scope, section_path}` 추출 → 프롬프트에 한국어 힌트로 prepend
- 프롬프트 룰: "이 페이지 상단에 새 굵은 헤더가 보이지 않으면 위 컨텍스트 계승. 새 헤더가 보이면 새 컨텍스트 시작. 가공의 상위 헤더 생성 금지."
- type 경계(BRIEF_DESIGN_GUIDE → MASSING)에서는 새 그룹 → 컨텍스트 자동 리셋
- 결과는 `precomputed_design: dict[int, dict]`에 저장 → `extract_one()`에서 캐시 조회
- 페이지별 풀 해상도(150 DPI) 유지 → 자식 항목 누락 없음

### 비용/시간

- 영등포 PDF 22개 BRIEF_DESIGN_* 페이지 → 22회 LLM 호출 (스태킹: 12회)
- 그룹 수만큼 병렬 (BRIEF_DESIGN_GUIDE / MASSING / SUSTAIN / SPECIAL 동시) → 분석 시간 ~2분 증가
- 자식 항목 누락 회복 + 계층 정상화로 트레이드오프 우호적

### 재발 조건

- `_extract_page_sync()`에 `_is_stacked` 분기 추가하거나 `_stack_images_vertically()`를 BRIEF_DESIGN_*에 적용하면 A안 회귀
- `_process_design_group()`를 병렬(`asyncio.gather` 내부)로 바꾸면 컨텍스트 누적 깨짐 — 반드시 그룹 내부 순차 유지

### 회귀 확인

- 영등포 p.45 인접 페이지의 `design_guidelines_grouped`에서 면대실/비품창고가 `facility_scope="구청"` + `section_path="직무공간 (부서 사무실) > ..."`로 추출되는지
- xlsx 시트 3 "시설별 지침 > 구청" 아래 정상 묶이는지
- 통합 민원실 / 회의 및 행사공간은 별도 top-level로 유지되는지 (컨텍스트 과적용 방지 확인)

---

## 시퀀스 E — design_guidelines_grouped 계층 정규화 (2026-06-19)

LLM 추출이 `section_path` 를 `"A > B > C"` 형태 깊은 경로로 나누고 `space_scope` 도 sub-segment 별로 다르게 매기는 케이스가 빈번 (영등포 110 entries 중 64% orphan, 36% depth ≥ 3). 결과적으로 exporter 가 형제 sub-section 을 별개 굵은 헤더로 그려서 자식이 부모처럼 보이는 문제.

### 정규화 룰 (services/utils.py::normalize_design_guidelines_grouped)

- **그룹 키 = `(facility_scope, section_path 의 첫 segment)`**  — space_scope 는 키에서 제외 (LLM 의 space_scope 추출 불안정성 보정)
- **sub_path = 첫 segment 이후 잔여 segments** — depth ≥ 3 도 `"B > C"` breadcrumb 으로 보존
- **R1 dedup**: 동일 그룹 키 + 동일 sub_path → items concat
- **R5 item dedup**: 같은 sub_path 안에서 label+text 동일 → 1회만
- **출력 스키마**: 기존 entry 형식 + `items_by_sub: [{sub_path, items}]` 추가. 하위 호환을 위해 기존 `items` 는 sub_path == "" 인 항목으로 채움
- **호출 위치**: `merge_extracted_data()` 의 `grouped_all` 집계 직후. exporter 진입점 `_extract_sections()` 에서도 lazy fallback (`_ensure_normalized_grouped`) 로 옛 데이터 호환

### Exporter 렌더 결과

**Before (사용자 신고 케이스)** — 굵은 헤더 4개로 분리:

```text
**[직무공간] 직무공간 (부서 사무실)**
  - 일반 항목
**[직무공간] 직무공간 (부서 사무실)**      ← 35행 중복 헤더
  - 대민업무상담실 자식
**[비품창고] 직무공간 (부서 사무실) > 비품창고**   ← 형제가 부모로 둔갑
**[직무공간] 직무공간 (부서 사무실) > 기타 부서별 요청사항**
```

**After** — 굵은 헤더 1회 + inline sub-header:

```text
**[직무공간] 직무공간 (부서 사무실)**
  - 일반 항목 ×4
  - 대민업무상담실
    ① 업무 효율...
    ② 6명 이용 가능한...
  - 비품창고
    ① 각 부서별...
  - 기타 부서별 요청사항
    ① 감사담당관 ... ⑧ 주택과
```

### 정규화 룰 재발 조건

- `normalize_design_guidelines_grouped` 의 그룹 키에 `space_scope` 를 다시 포함하면 비품창고 케이스 재발 (LLM 이 sub-section 의 space_scope 를 부모와 다르게 매김)
- exporter 가 `items_by_sub` 대신 `items` (flat) 만 사용하면 sub-header 인라인 처리 안 됨 → 다시 굵은 헤더로 분리
- `merge_extracted_data` 에서 정규화 호출이 사라지면 새 분석은 깨진 형태로 저장됨. exporter 의 lazy fallback 이 받아주지만 비효율

### 단위 테스트

`backend/tests/test_normalize_design_grouped.py` — 13 케이스 (R1 dedup, R2 parent-child, R3 3-level breadcrumb, R4 orphan, R5 item dedup, 순서 보존, 시설 분리, 빈 path, 하위 호환, 잘못된 입력 가드).

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
| V-10a | BRIEF_DESIGN_* 페이지별 추출 (스태킹 폐기 확인) | 영등포구 통합 신청사 PDF로 `/api/brief/analyze` 실행 → `_brief.json` 의 `brief_design_guide` 배열 확인 | 각 페이지가 자체 `data.design_guidelines_grouped` 보유. `_stacked_pages` / `_merged: true` 필드 없음 (A안 잔재 부재) |
| V-10b | 컨텍스트 주입 → facility_scope 정상화 | V-10a 와 동일 `_brief.json` 에서 p.46/47의 면대실·비품창고·기타 부서별 요청사항 항목 확인 | `facility_scope: "구청"` (이전 버그: "전체"·스태킹 후에도 "전체") + `section_path` 가 `"직무공간 (부서 사무실) > ..."` 형식 |
| V-10c | 엑셀 시트 3 라우팅 정상화 | V-10a 와 동일 분석 결과의 xlsx 다운로드 → 시트 3 "시설별 지침" 섹션 확인 | "구청 > 직무공간" 아래에 페이지 45+46 항목 (직무공간 일반사항, 면대실, 비품창고, 기타 부서별 요청사항)이 함께 묶여 나타남. "통합 민원실", "회의 및 행사공간" 은 별도 top-level 섹션 |
| V-10d | 컨텍스트 과적용 방지 | V-10a 결과에서 p.46의 "통합 민원실" / "회의 및 행사공간" 같은 새 헤더가 시작되는 항목 확인 | 새 헤더 항목은 직전 컨텍스트("직무공간") 계승하지 않고 자체 facility_scope/section_path 부여 — LLM이 "새 굵은 헤더 보이면 새 컨텍스트" 룰 준수 |
| V-10e | 그룹 병렬·내부 순차 동작 | 영등포 분석 중 서버 로그 확인 | BRIEF_DESIGN_GUIDE / MASSING / SUSTAIN / SPECIAL 4개 그룹이 동시 시작. 같은 그룹 내 페이지는 직렬 (앞 페이지 완료 후 다음 페이지 호출) |

**확인 우선순위:** V-2 → V-3 → V-4 (지침서 분류 파이프라인 핵심) → V-10a/b/c/d/e (시퀀스 D-B 회귀 검증, 영등포 PDF 필수) → V-1 (토큰 절감 실측) → V-6/V-7 (rubric 버전) → V-9 (grade_justification)

**주의:** V-8(스캔본 PDF)은 텍스트 없는 실제 스캔 PDF가 없으면 검증 불가. 향후 스캔본 지침서 확보 시 진행.
