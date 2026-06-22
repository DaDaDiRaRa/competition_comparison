# CLAUDE.md

Competition Analyzer — 건축 공모 제안서 추출·비교 풀스택 앱.

**Stack:** FastAPI + React 18/Vite + Anthropic Claude (`claude-sonnet-4-6`) + PyMuPDF. JSON-based DB. Docker + Cloud Run (gen2) + GCS 마운트 (`/data`). `main` push → GitHub Actions 자동 배포.

## Architecture

### Backend Routers (`/api/<name>`)

1. **`routers/accumulate.py`** — PDF → JSON 추출 + 개별 제출물 리포트. 비교분석은 별도 (`rerun-compare`). `add-submission`, `rerun-compare`, `rerender-report`, `cross-compare` 엔드포인트 포함.
2. **`routers/diagnose.py`** — 단일 제출물 진단. `/run` (DB 전체 패턴) + `/run-vs-projects` (사용자 선택). 완료 시 HTML 리포트 자동 생성.
3. **`routers/patterns.py`** — 시설유형별 패턴 관리 (당선 + 낙선 통계).
4. **`routers/settings.py`** — `app_settings.json` 관리. `GET /settings/meta` 가 프론트 `useMeta()` 단일 소스.
5. **`routers/upload.py`** — 청크 업로드 (Cloud Run 32MB 한도 우회). 25MB 청크 / 600MB 상한 / `/tmp/cc_uploads/` 누적.
6. **`routers/archive.py`** — FTS5 in-memory SQLite 자연어 검색.
7. **`routers/brief.py`** — 지침서 단독 분석 (PDF + DOCX + HWP/HWPX). 분류 → 추출 → 요구사항 → 검증 → JSON/MD/xlsx/HTML 저장. HTML 은 `/exports/{name}.html` 에서 인라인(text/html, 보기용), md/xlsx 는 attachment.

**MyProject 심층 분석:** 별도 라우터 없음. `accumulate.py` 가 단일 등록 시 `myproject_analyzer.deep_analyze()` 호출 → `_deep.json` + `_deep.html`. `GET /projects/{ft}/{cid}/submissions/{company}/deep-report` 로 서빙.

### Core Services

| 파일 | 책임 |
| --- | --- |
| `db_manager.py` | JSON DB. `_atomic_write` / `_sync_write` 는 GCSFUSE 플러시 위해 `fsync` 후 rename — 신규 파일 저장 함수 추가 시 반드시 사용. |
| `docx_loader.py` | DOCX 블록 분할 (PDF 와 완전 독립). `split_docx_to_blocks()` R1~R5 분할 + F1~F3 필터. vMerge 감지는 `_tc` identity + tcPr `w:vMerge` 두 시그널 조합 필수. |
| `hwpx_loader.py` | HWP/HWPX 블록 분할 (rhwp-python, PDF/DOCX 와 독립). `split_hwpx_to_blocks()` 반환 스키마가 docx_loader 와 **동일** → `classify_all_blocks_brief` / `extract_hwpx` / BRIEF_* 추출 헬퍼 그대로 재사용. `ir.iter_blocks(recurse=False)` 필수 (Critical Rules 참조). 표 HTML → 마크다운 + merge_info 는 docx 호환 `{row,col,merged_rows,value}`. `get_hwpx_source_text()` 는 docx 구현 위임. 회귀: `tests/test_hwpx_loader.py` (22, rhwp monkeypatch). |
| `page_classifier.py` | 페이지/블록 분류. `classify_all_pages_brief()` (PDF) / `classify_all_blocks_brief()` (DOCX/HWP/HWPX). `has_scoring_table=False` 면 BRIEF_EVALUATION → BRIEF_ADMIN 강등. |
| `data_extractor.py` | 페이지/블록 추출. `merge_extracted_data()` 가 `_quantitative` 자동 집계. DOCX BRIEF_EVALUATION 표는 `_extract_docx_eval_from_table()` 로 LLM 없이 파싱 (환각 차단). brief 결과면 끝에서 `feasibility_export` 블록도 부착 (try/except, 실패해도 파이프라인 무중단). HWP/HWPX 는 `extract_hwpx()` (split_hwpx_to_blocks 로 파싱, extract_docx 가 python-docx 재파싱이라 hwpx 불가 → 병렬 함수. BRIEF_* 추출 헬퍼·merge_info 스키마 재사용). |
| `feasibility_export.py` | `_brief.json` → `feasibility_export` 정규화 블록 (연동 앱 arch-law-diagnose 용, schema_version 2). **새 vision 추출 없음 · 기존 키 수정 없음 · 추가만.** 이미 추출된 값을 재배치·파싱: site_id 통일, brief_site "(부지N)" 주소 분해+접두 상속, 인증 코드화, facilities 괄호 건축법 용도, 사업 규모 노출(1차); 주차 서술→required_parking_count(부지N 마커 귀속), zoning→표준 용도지역명(불확실 시 raw), special_conditions 심의 문구→limits_determined_by(2차). 모두 후처리 파싱이라 BRIEF_* 추출 회귀 없음. 회귀: `tests/test_feasibility_export.py` (46). 무료 검증: `tools/feasibility_verify.py`. |
| `llm_client.py` | Claude API 래퍼 `call_messages()`. `system` 은 `str \| list` 모두 지원. 캐시 토큰 로깅. |
| `comparator.py` | **2-pass blind-reveal.** Pass 1: 익명화 채점, Pass 2: 리빌 후 차별화·gap 분석 (Pass 1 결과만 재전송, 80%+ 토큰 절감). `_compute_gap_analysis()` 결정적 로직으로 alignment 산출. Prompt caching ephemeral. `.replace()` 사용 (`.format()` 은 JSON 중괄호 충돌). |
| `pattern_builder.py` | 당선 패턴 + `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords). |
| `report_generator.py` | 비교 HTML 리포트 (LLM 호출 없음). `axes_for(facility_type)` 로 시설별 평가축. `gap_section` 블록이 ranking 과 diff 사이 삽입. |
| `submission_report_generator.py` | 개별 제출물 리포트. LLM 호출 없음. |
| `diagnosis_report_generator.py` | 진단 리포트. LLM 호출 없음. 종합점수 링 → 페이지바 → 패턴편차 → 충족도 → 요구사항 매핑 → 평가축 상세. |
| `myproject_analyzer.py` | MyProject 멀티패스 deep-analysis. narrative + deep evidence + 정량 + 키워드 + auto_meta. |
| `myproject_report_generator.py` | `_deep.json` → HTML. LLM 호출 없음. |
| `archive_search.py` | in-memory SQLite FTS5. `build_index()` 시작 시 1회, `rerun-compare` 후 `rebuild_index()`. `check_same_thread=False` 필수. |
| `brief_validator.py` | 지침서 검증. LLM 호출 없음. `requirements` 가 dict 아니면 `{}` 교체 (LLM 배열 반환 방어). `_check_points_mismatch` 는 `shared_with` non-empty 또는 합계가 만점과 일치 시 null 항목을 정성평가로 인정 (영등포 false positive 차단). |
| `brief_checklist_exporter.py` | 지침서 체크리스트 MD/xlsx/HTML. LLM 호출 금지. openpyxl lazy import. xlsx 시트: 1.면적·프로그램(사업개요 서브섹션 포함) / 2.심사기준 / 3.요구사항 / 4.검증경고 (+ area_rows 있으면 5.면적표상세). `to_html()` 은 `to_markdown` 과 동일한 `_extract_sections()` 데이터로 미니멀 자체완결 HTML (화이트 + 건원 RED, 5섹션, 상단 고정 nav + 핵심수치 카드 + 시설별 접기). 데이터는 `html.escape`. `_form_area_pages()` 가 '[서식 N] …면적표' 제출양식 오분류 페이지를 면적 집계에서 제외 (본문 면적표 중복 차단, 영등포 사례). 회귀: `tests/test_brief_pipeline.py::TestToHtml`. |
| `grade_helpers.py` | 등급 단일 소스. `GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade()`. 모든 리포트 generator 가 공통 import. |
| `utils.py` | PDF rasterizer (`rasterize_pdf` PyMuPDF), SSE helper, `parse_json_response()` 3단계 복구, 공유 dict 헬퍼 `_first()` / `_as_list()`, `user_error_msg()`, `normalize_design_guidelines_grouped()`. |

**Report Generation Rule:** `report_generator.py`, `submission_report_generator.py`, `diagnosis_report_generator.py`, `myproject_report_generator.py` 는 모두 Claude API 호출 금지. 기존 데이터를 HTML 로 렌더링만.

### Configuration

- `config.py` — `FACILITY_TYPES`, `PAGE_TYPES_META` (27개), `COMPARISON_AXES_BY_GROUP` (redev/general 8축씩), `RUBRIC_VERSION="v1"`, `MODEL_ID`, `MODEL_ID_CLASSIFY`.
- `FACILITY_TYPES = {key: {"label_ko": str, "group": "redev"|"general"}}` — 단순 `{key: str}` 아님. `facility_label()` / `axes_for()` 헬퍼 사용.
- `settings.db_path` — `app_settings.json` 우선, 없으면 `DB_PATH` env (Cloud Run `/data`) 또는 `~/CompetitionAnalyzerDB`.
- `settings.api_key` — 메모리 우선, 없으면 `ANTHROPIC_API_KEY` env. `_sanitize_api_key()` 가 `echo -n` 아티팩트 (`-n` 접두사·`\r\n`·따옴표) + UTF-8 BOM·zero-width 문자 자동 제거 (Critical Rules 참조).
- `app_settings.json` 추적 대상 (DB 경로·DPI·모델 ID). `anthropic_api_key` 는 메모리에만.

### Frontend Tabs (`App.jsx::TABS`)

1. **MyProjectMode** — 단일 제출물 + 결과 라벨 등록 (deep-analyze).
2. **AccumulateMode** — PDF → JSON. `ProjectList` 컴포넌트가 시설유형별 저장 프로젝트 노출 → "비교분석 실행" / "+ 제안서 추가" / 리포트 링크.
3. **CrossCompareMode** — 여러 프로젝트 교차 비교.
4. **DiagnoseMode** — 신규 제출물 진단. `pattern` prop 으로 정량 비교 바.
5. **SettingsPanel** — 설정 + `PatternViewer` (시설유형 탭 + 당선/낙선 통계).
6. **ArchiveMode** — 자연어 검색 + 카드 그리드 + 슬라이드오버 (`AxisAccordion` 펼침).
7. **BriefMode** — 지침서 단독 분석. `accept=".pdf,.docx,.hwp,.hwpx"`. docx / hwp·hwpx 선택 시 "도면 포함 지침서는 PDF로" 안내. 블록 기반 포맷(docx/hwp/hwpx)일 때 flag location `p.N` → `블록 N` 치환 (`isBlockFormat`).

**Key components:** `useMeta()` 훅이 시설유형·페이지타입·평가축 한국어 레이블 단일 소스 (`/settings/meta` 1회 fetch). 하드코딩 금지. `useMeta.jsx` JSX 포함하므로 `.jsx` 확장자 필수.

### Styling

- 화이트 테마 + 건원 RED `#e60012`. **단일 소스: [frontend/src/kunwon-tokens.css](frontend/src/kunwon-tokens.css)** — `main.jsx` 에서 전역 import.
- 컴포넌트는 인라인 스타일에서 `style={{ color: 'var(--color-accent)' }}` 패턴. hex 직접 사용 금지.
- 신규 색 필요 시 `kunwon-tokens.css` 추가 → `theme.js` 동기화.
- 비교 리포트 HTML 은 독립 문서 — `report_generator.py::_CSS` 의 `:root` CSS 변수 26개로 별도 관리.
- 감사: `tools/audit_tokens.py` 실행 → `DESIGN_AUDIT.md`.

## Pipelines

### Accumulate (`POST /api/accumulate/run`)

1. Brief PDF (선택) + submissions JSON + PDFs 업로드.
2. classify → extract → `_brief.json` + `submissions/*.json` 저장.
3. 각 제출물 개별 HTML 리포트 즉시 생성 (`submissions/{slug}_{result}_report.html`).
4. SSE `complete` 발송 후 종료.

비교분석은 **반드시 별도** — `ProjectList` 의 "비교분석 실행" 버튼 = `rerun-compare`.

### Compare (`POST /api/accumulate/projects/{ft}/{cid}/rerun-compare`)

1. 저장된 `_brief.json` + `submissions/*.json` 로드 (PDF 재처리 없음).
2. `compare_submissions()` — Pass 1 (블라인드) + Pass 2 (리빌 사후 분석) + `_compute_gap_analysis()`.
3. `_comparison.json` 저장 → 시설유형 패턴 재구축 (당선 + 낙선) → 비교 HTML + 개별 제출물 리포트 재생성.

`rerender-report` 는 LLM 없이 HTML 만 재생성.

### Brief (`POST /api/brief/analyze`)

1. PDF / DOCX / HWP / HWPX 업로드. `_validate_brief_file()` 확장자 + magic byte 검증 (PDF `%PDF` / DOCX·HWPX `PK\x03\x04` ZIP / HWP `\xd0\xcf\x11\xe0` OLE2). PDF ≤200MB, DOCX·HWP·HWPX ≤50MB.
2. **분류**: PDF → `classify_all_pages_brief()` (vision) / DOCX → `split_docx_to_blocks()` / HWP·HWPX → `split_hwpx_to_blocks()` → 둘 다 `classify_all_blocks_brief()` (텍스트, 이미지 토큰 0). `page_map` 스키마 동일 (`page` 필드는 블록 포맷에서 `block_num`).
3. **추출**: PDF → `extract_pdf(is_brief=True)` (vision/tiled/OCR/digital text 다단) / DOCX → `extract_docx(is_brief=True)` / HWP·HWPX → `extract_hwpx(is_brief=True)`. BRIEF_EVALUATION 표는 LLM 없이 직접 파싱.
4. `merge_extracted_data()` → `_merge_brief_project_info_pages()` 가 `sites[]` / `special_conditions[]` / `unit_program[]` 합침. brief 결과면 `feasibility_export` 블록도 부착 (Schemas 참조).
5. `extract_brief_requirements()` → `validate_brief()` → flags + summary.
6. `_brief_meta.source_format` (`"pdf"` | `"docx"` | `"hwp"` | `"hwpx"`) 기록.
7. 저장: `_atomic_write(json)` + `_sync_write(md)` + `_sync_write(html)` + `_sync_write_bytes(xlsx)`. 위치: `{db_path}/_briefs/{stamp}_{facility_type}_{slug}.{json|md|html|xlsx}` (≤120자).
8. SSE `complete`: `{brief_id, md_filename, xlsx_filename, html_filename, validation_summary, source_format}`. accumulate 의 `done`/`brief` 이벤트도 `html_filename` 포함.

### Diagnose

1. facility_type + submission PDF 업로드 (brief PDF 선택).
2. classify → extract → `_quantitative` 자동 집계.
3. 시설유형 패턴 retrieve (`loser_stats` 포함).
4. `diagnose_submission()` LLM 호출 → 당선 vs 낙선 대비 진단.
5. `generate_diagnosis_report()` → `{db_path}/_diagnosis_reports/{ts}_{ft}_{name}.html`.
6. SSE `complete`: `{ result, report_filename }`.

## Database Layout

```text
{db_path}/
├── {facility_type}/{competition_id}/
│   ├── _meta.json
│   ├── _brief.json
│   ├── _comparison.json
│   ├── _report.html
│   └── submissions/
│       ├── {slug}_{result}.json
│       ├── {slug}_{result}_report.html
│       └── {slug}_{result}_deep.{json|html}   # MyProject only
├── _diagnosis_reports/{YYYYMMDD}_{HHMMSS}_{ft}_{name}.html
├── _cross_reports/*.html
├── _briefs/{brief_id}.{json|md|html|xlsx}
└── _myprojects/                                # auto_meta 머지 대상
```

폴더명 = `{project_number}_{slugified_competition_name}`. 구 데이터 (`year` 만) 폴백.

## Schemas

**`_brief.json` 의 `feasibility_export` (연동 블록, schema_version 2):**

```text
feasibility_export: {
  schema_version: 2,
  sites: [{ site_id: "부지N", address, building_law_uses: [...],
            required_parking_count: int|null, parking_note: str|null,   # 2차 C
            zone_use: "준공업지역"|null, zone_use_raw: str|null,         # 2차 D (불확실 시 raw)
            limits_determined_by: "심의"|"법정",                         # 2차 E
            site_area_sqm, floor_area_ratio_pct, building_coverage_pct, max_height_m }],
  certifications: { green_building: "최우수"|"우수"|null, zeb_grade: 1~5|null,
                    renewable_pct: int|null, bf_grade: "최우수"|"우수"|null },
  construction_cost_100m_won, design_cost_100m_won, construction_period_months
}
```

1차(A~E): 재배치/정규화만. 2차(C 주차·D 용도지역·E 심의플래그): 이미 추출된 서술(brief_design_massing/zoning/special_conditions)을 **후처리에서 파싱** — vision 프롬프트 무관이라 BRIEF_* 분류·면적표 회귀 없음. `merge_extracted_data()` 가 brief 결과에 부착. `limits_determined_by="심의"` 면 60%/460% 등을 법정 한계로 보면 안 됨.

**`comparison.json`:**

```text
{
  submissions: {company: {axis: {grade, strengths, weaknesses, brief_compliance, notes, grade_justification}}},
  ranking, blind_ranking,        # ranking = blind_ranking 호환용
  key_differentiators, winner_strengths, loser_weaknesses,
  gap_analysis: {blind_top1, actual_winners, top1_matches_winner, alignment, notes},
  rubric_version: "v1"
}
```

**`diagnosis.json`:**

```text
{
  axes: {axis: {grade, strengths, weaknesses, recommendations, evidence, grade_justification}},
  overall_grade, brief_compliance, requirement_mapping, pattern_deviation,
  strengths, weaknesses, recommendations,
  submission_quantitative, rubric_version: "v1"
}
```

`grade` 는 `"A"|"B"|"C"|"D"|"E"|null`.

**`_quantitative` 키:** `site_area_sqm`, `building_area_sqm`, `total_floor_area_sqm`, `area_above_ground_sqm`, `area_below_ground_sqm`, `floor_area_ratio_pct`, `building_coverage_ratio_pct`, `floors_above`, `floors_below`, `parking_count`.

## Conventions

- **Grading (5-level A/B/C/D/E):** 점수 숫자 아닌 문자열. 임원 검토 시 정밀도 논쟁 차단 + 환각 검증 부담 감소. 구 `score`(0-10) 자동 변환: ≥8.5=A / ≥7=B / ≥5=C / ≥3=D / else=E. 백엔드 `grade_helpers.py`, 프론트 `constants/index.js::GRADE_COLOR/GRADE_BG/toGrade()`.
- **2-pass Blind-Reveal:** Pass 1 에서 LLM 이 결과 라벨 모름 → 앵커링 차단. Pass 2 에서 실제 결과 공개 + 사후 분석 → `gap_analysis.alignment != "high"` 면 경고. 완벽한 익명화 아니지만 명시적 결과 라벨 제거가 최강 시그널 차단.
- **페이지 인용 강제:** compare/diagnose 프롬프트가 모든 strength/weakness/recommendation 에 `(p.N)` 형식 인용 요구. `_trim_extracted()` 가 `_page` 필드 보존.
- **Prompt Caching:** compare(2-pass)/diagnose 의 `system` + 정적/동적 content 블록 각각에 `cache_control: {"type": "ephemeral"}`. 5분 TTL, 캐시 히트 시 입력 90% 할인, 쓰기 1.25×. Sonnet 1024 토큰 이상만 캐시.
- **Prompt Templating:** `comparator.py` 는 `.replace("{key}", value)` 사용 — JSON 중괄호와 `.format()` 충돌 회피.
- **DPI:** classify 72 / extract 120. 150→120 변경으로 이미지 토큰 ~36% 절감.
- **Model:** 분류·추출·비교·진단 모두 `claude-sonnet-4-6` (`MODEL_ID_CLASSIFY` 도 Sonnet — Haiku 헤더 환각 케이스 회피).
- **Loser Anti-Pattern:** `build_pattern()` 이 `*_lose.json` 도 수집. diagnose 프롬프트에 `loser_stats` 전달. `DiagnosisResult::QuantCompare` 3행 바 (당선/낙선/내).
- **Page Types:** 27개 = 일반 20 + 재건축 7 (`BUSINESS_VIABILITY`, `AREA_INCREASE`, `VIEW_ANALYSIS`, `COMMUNITY_PROGRAM`, `COMPANY_PORTFOLIO`, `CONSTRUCTION_PLAN`, `UNIT_PLAN_PENTHOUSE`).
- **재건축 강등:** 분류 신뢰도 < `REDEV_CONFIDENCE_FLOOR=0.65` 이면 `REDEV_FALLBACK`.
- **Page Taxonomy 갱신:** `init_db()` 는 `_config/page_taxonomy.json` 없을 때만 생성. PAGE_TYPES 추가 후 반영하려면 해당 파일 삭제 + 백엔드 재시작.
- **ProgressLog Events:** 모든 SSE 이벤트 `_timestamp` 필수 (경과시간 표시용).
- **FastAPI Lifespan:** `@asynccontextmanager async def lifespan()`. `init_db()` 실패해도 graceful.
- **CORS:** Vite (5173) + localhost:3000.
- **File Naming:** Components PascalCase, API paths kebab-case.

## Token Routing (제안서 추출 비용 절감)

- **`OCR_FIRST_TYPES`** = `{AREA_TABLE, TECHNICAL, SUSTAINABILITY, BUSINESS_VIABILITY, AREA_INCREASE, COMPANY_PORTFOLIO, CONSTRUCTION_PLAN}` — PaddleOCR + Haiku 구조화. Sonnet+vision 대비 페이지당 ~90% 절감. `OCR_MIN_CHARS=80` 미만 시 vision fallback.
- **`SKIP_PAGE_TYPES`** = `{COVER, RENDERING_EXT, RENDERING_INT}` + `SKIP_PRIORITY_THRESHOLD=3` — 기여도 낮은 페이지 자동 스킵. 복원: `settings.extraction_priority_limit=3`.
- **`DIGITAL_TEXT_EXCLUDE_TYPES`** — fitz Tier 0 텍스트 경로 건너뛰고 타일-비전. `BRIEF_EVALUATION` / `BRIEF_PROJECT_INFO` 포함 이유: HWP→PDF 변환 시 병합 셀 구조 붕괴.

## Critical Rules (재발 방지)

각 항목은 한 줄 룰. 상세 배경은 git log + 코드 주석 참조.

- **Dual requirements 동기화:** 신규 Python 패키지는 `requirements.txt` + `requirements-server.txt` 양쪽 추가. OCR 전용은 `requirements-ocr.txt` 에만. Dockerfile 이 `requirements-server.txt` 설치. `rhwp-python`(HWP/HWPX) 은 양쪽 + Dockerfile `ENV LD_PRELOAD=/lib/x86_64-linux-gnu/libfreetype.so.6` (Rust 바이너리 freetype 링킹) 동반.
- **GCSFUSE fsync:** 새 파일 저장 함수 추가 시 반드시 `_atomic_write` / `_sync_write` 사용. `flush + fsync` 후 rename — 없으면 GCS 에 데이터 유실.
- **BRIEF_PROGRAM 스태킹:** `_stack_images_vertically()` 는 JPEG(quality=85) 출력 + `_STACK_MAX_DIM=7500` 픽셀 한도 + 에러 시 `precomputed_program = None` 폴백. PNG 로 되돌리거나 한도 제거 시 5MB / 8192px 초과로 400 재발.
- **BRIEF_EVALUATION 비연속 스태킹:** non-null points 합계 0 이면 `precomputed_eval = None` 폴백. `brief_checklist_exporter._extract_sections()` 는 `max(key=_eval_pts)` 로 페이지 선택 — `_first()` 로 되돌리면 비연속 케이스 누락.
- **BRIEF_EVALUATION 환각 방어 (5중):** ① `BRIEF_CLASSIFY_PROMPT` NOT 조건 (g)~(j) ② `_NOT_EVAL_HEADER_PATTERNS` 후처리 강등 (`상품 및 내용` 패턴 포함) ③ `MODEL_ID_CLASSIFY` Sonnet 유지 (Haiku 헤더 환각) ④ `FACILITY_CONFLICT_KEYWORDS` + `brief_validator._check_facility_keyword_conflict()` ⑤ `data_extractor` BRIEF_EVALUATION 프롬프트 "환각 금지 (CRITICAL)" 블록. 어느 하나 제거하면 청사 → 연구원 환각 재발.
- **BRIEF_EVALUATION null 점수 시맨틱:** `_check_points_mismatch` 는 `shared_with` 가 채워졌거나 numeric 합이 만점과 ±1 이내 일치 시 null 항목을 정성평가로 인정 (경고 X). 단순 `points is None → missing` 으로 되돌리면 영등포 (배치계획↔공간계획 병합, 설계의 적정성·창의성 정성평가) false positive 재발. 회귀: `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스.
- **`_image_block()` JPEG 마법 바이트:** `img_bytes[:3] == b'\xff\xd8\xff'` 이면 `image/jpeg`, 아니면 `image/png`. 포맷 불일치는 400 원인.
- **API 키 BOM/zero-width 제거:** `config.py::_sanitize_api_key` 는 `.strip()` 외에 UTF-8 BOM(`﻿`)·zero-width 문자도 명시 제거. 메모장·PowerShell `Set-Content -Encoding utf8` 로 키 저장 시 선두 BOM 이 붙어 httpx 헤더 ascii 인코딩에서 `UnicodeEncodeError` 발생 (str.strip() 은 BOM 을 공백으로 안 봄). 회귀: `tests/test_pure_functions.py::TestSanitizeApiKey` 7 케이스.
- **BRIEF_DESIGN_* 그룹 처리:** `_process_design_group()` 그룹 내부는 **순차** 실행 (직전 페이지 컨텍스트 주입), 그룹간만 `asyncio.gather` 병렬. 그룹 내부 병렬화하면 컨텍스트 누적 깨짐.
- **design_guidelines_grouped 정규화:** 그룹 키 = `(facility_scope, section_path 첫 segment)` — space_scope 제외 (LLM 추출 불안정). exporter 는 `items_by_sub` 사용. `space_scope` 를 키에 다시 포함하면 비품창고 케이스 재발.
- **vMerge 감지:** `cell._tc` identity + tcPr `w:vMerge` element **두 시그널 조합**. 어느 한쪽만 쓰면 `merge_info` 가 빔.
- **rhwp `iter_blocks(recurse=False)` 필수:** 기본값 `recurse=True` 는 `TableCell.blocks`(셀 내부 문단)까지 재귀해 표 내용이 본문 블록으로 **중복 집계**됨. `split_hwpx_to_blocks` 는 `iter_blocks(scope="body", recurse=False)` 사용 (시그니처 드리프트 대비 `try/except TypeError → ir.body` 폴백). 회귀: `tests/test_hwpx_loader.py` 의 `_FakeIR` 가 `recurse is False` assert.
- **hwpx merge_info 는 docx 호환 스키마:** `_html_table_to_markdown` 이 `{row, col, merged_rows, value}` (세로병합만) 로 emit — `_extract_docx_eval_from_table` 가 이 키를 소비. `rowspan→merged_rows`, 가로병합(colspan)은 텍스트 반복(docx 동작). rhwp 원형 `rowspan/colspan` 으로 두면 BRIEF_EVALUATION 표 파싱이 `KeyError` 로 깨짐.
- **GCP 배포 확인:** `gcloud run services describe competition-analyzer --region asia-northeast3 --format="value(status.latestCreatedRevisionName)"` 로 최신 리비전명 확인. ⚠️ `metadata.creationTimestamp` 는 **서비스 최초 생성일**(리비전 시각 아님) — 실제 리비전 생성시각은 `gcloud run revisions list --service competition-analyzer --region asia-northeast3 --sort-by="~metadata.creationTimestamp" --limit=1`. 수동 fallback: `gcloud run deploy competition-analyzer --source . --region asia-northeast3`.

## 보안 — 커밋 금지 파일

`.gitignore` 등록 필수, 절대 커밋 금지:

- `service.yaml` — Cloud Run 시크릿 평문 포함. 수정 시 로컬 편집 후 `gcloud run services replace service.yaml`.
- `gcp-sa-key.json`, `*-sa-key.json`, `key.json` — GCP 서비스 계정 키.
- `.env`, `env.yaml`.

`backend/app_settings.json` 은 추적 대상 (DB 경로·DPI·모델만). API 키는 메모리에만.

## Open Issues

- **🟡 BRIEF_EVALUATION 100점 초과 추출 — 가드 4중 구현됨, 실재현 케이스 검증만 미완:** HWP→PDF 병합셀 붕괴로 중복 집계되는 케이스. 방어층: ① 프롬프트 `shared_with` 병합셀 메커니즘 (`points` 는 그룹 대표에만, 나머지 null — 중복 집계 소스 차단, `data_extractor.py` BRIEF_EVALUATION instruction) ② 프롬프트 자가검증 가드 ("합계가 total_points 를 크게 초과하면 병합셀 중복 집계이므로 반드시 수정", 둘 다 commit d4a3432 2026-06-16) ③ DOCX 결정적 표 파서 소계/합계 행 제외 (`_extract_docx_eval_from_table`) ④ `points_sum_warning` 후처리 안전망 (스태킹 95~105 + 개별 페이지 >110, `merge_extracted_data()` 끝 + 스택 경로). 층 ①②는 LLM 의존이라 **실제 병합셀 붕괴 PDF 1건으로 self-correct 작동 확인 미완** (영등포·종로는 합계 100 정상 케이스라 가드 경로 미진입). 결정적 자동 수정 (중복 행 탐지·정정) 은 어느 행이 중복인지 알 수 없어 불가 → `points_sum_warning` 경고가 최종 백스톱.
- **🟢 BRIEF_EVALUATION null 항목 false positive (해소, commit 3db1100):** 정성평가 항목 (점수 미부여) 과 `shared_with` 병합셀에 medium 경고가 잘못 발생했었음. 영등포 통합신청사 케이스로 재현·수정. 회귀: `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스.
- **🟢 BRIEF_SUBMISSION 오분류 페이지에 배점표** — 분류기 수정 없이는 해결 불가. 재분석 후 심사기준 비면 `page_map` 의 `has_scoring_table` 확인.
- **🟢 제출 양식(서식 N) 면적표 → BRIEF_PROGRAM 오분류 (리포트 측 완화):** '[서식 13] 건축 세부 면적표' 같은 제출양식이 BRIEF_PROGRAM 으로 분류되면 본문 면적표와 같은 실이 두 번 노출 (영등포). 분류기 근본 수정 대신 `brief_checklist_exporter._form_area_pages()` 가 헤더 '서식' 신호로 해당 페이지를 면적 집계에서 제외 (md/xlsx/HTML 공통). 헤더 기반 휴리스틱 — 다른 지침서에서 본문 면적표 누락 시 신호 보강 필요.

## 다음 작업 (단기)

- **🟡 BRIEF_EVALUATION 100점 초과 — 검증만 잔여:** 프롬프트 가드·안전망 4중은 이미 구현됨 (Open Issue 🟡 참조). 남은 건 코드가 아니라 **검증** — HWP→PDF 병합셀 붕괴 PDF 1건 확보 시 `tools/analyze_brief_cli.py` 로 분석해 ① 합계가 100 근처로 self-correct 되는지 ② 안 되면 `points_sum_warning` 이 켜지는지 확인. 케이스 없으면 보류.
- **진짜 단순형(1~2단) area_table 케이스 확보:** API 검증 P0-3/P1-3/P2-3/KI/V-10e 는 2026-06-22 완료 (`tools/api_validation.py`, 11 PASS/0 FAIL). 단, 당초 "종로구청=단순형" 전제가 틀림 — 종로구청 세부지침서도 통합청사라 5단 복잡 계층. 영등포·종로 둘 다 복잡형이므로 **단순형(1~2단) area_table 추출 검증은 미확보**. 소규모 단일시설 지침서 1건 확보 시 `tools/analyze_brief_cli.py` 분석 후 별도 검증.

## Sequences (Future Work, 보류)

- **시퀀스 B — 추출 정확도 평가 하네스:** `tools/eval/` 폴더에 B-2 까지 구현. 재개 조건: 제안서 PDF 5건 + ground_truth JSON. 다음 단계 B-3 (CI 통합 훅). `python tools/eval/run_harness.py --pdf-dir pdfs/ --max-samples 5` 로 평가, `~$0.27/PDF`. `_quantitative` 키 10개는 `tolerance.json` 과 일치 필수.
- **시퀀스 C — 멀티파일 지침서 업로드:** 1파일 안정화 완료 후 재개. 접근 A (multi-file 동시 분석, `_brief_meta.source_files: list[...]` 도입) 권장. 충돌 우선순위 룰 미결 — 지침서 vs 과업지시서 중복 시 어느 쪽 우선인지 사용자 결정 필요.

## 앱 실행 검증 체크리스트 (API 키 필요)

코드는 완성됐으나 실제 LLM 호출 end-to-end 검증 미완. 소규모 데이터로 한 번씩.

| # | 항목 | 방법 | 기대 결과 |
| --- | --- | --- | --- |
| V-1 | Tier 0 fast-path | 디지털 지침서 PDF로 `/api/accumulate/run` → 로그 | `_source: "digital_haiku"` 로그 + 토큰 감소 |
| V-2 | `classify_all_pages_brief()` 품질 | 지침서 PDF 업로드 → `_brief.json` 의 `pages` | BRIEF_PROGRAM / BRIEF_DESIGN_GUIDE / BRIEF_EVALUATION 적절 분류 |
| V-3 | BRIEF_PROGRAM/EVALUATION Vision 강제 | V-2 + 로그 | `DIGITAL_TEXT_EXCLUDE_TYPES` 로 Tier 0 미진입, Vision 처리 |
| V-4 | BRIEF_* 추출 스키마 | `_brief.json` 의 `data` 키 확인 | BRIEF_PROGRAM 에 `required_areas` 등 스키마 키 존재 |
| V-5 | BRIEF_SUBMISSION/ADMIN skip | 해당 페이지 엔트리 | `_skipped: true` 또는 `data: {}` |
| V-6 | `rubric_version` 비교 | `rerun-compare` 후 `_comparison.json` | `"rubric_version": "v1"` 최상위 |
| V-7 | `rubric_version` MyProject | MyProject 등록 → `_deep.json` | `"rubric_version": "v1"` |
| V-8 | 스캔본 PDF → Vision fallback | 스캔 PDF 파이프라인 | Tier 0 None → Vision 자연 전환, `_source: "vision"` |
| V-9 | `grade_justification` 출력 | 비교/MyProject JSON·HTML | 각 axis 에 `"신호 X/Y개 충족 → <등급> 기준 행과 일치"` |
| V-10a ✓ | BRIEF_DESIGN_* 페이지별 추출 | 영등포 청사 PDF → `_brief.json` | 각 페이지 자체 `design_guidelines_grouped`. `_merged: true` 없음 |
| V-10b ✓ | 컨텍스트 주입 정상화 | p.46/47 면대실·비품창고 항목 | `facility_scope: "구청"` + `section_path: "직무공간 (부서 사무실) > ..."` |
| V-10c ✓ | 엑셀 시트 3 라우팅 | xlsx 시트 3 `[직무공간] (부서 사무실)` 헤더 | 대민업무상담실·비품창고·기타 부서별 자식으로 묶임 |
| V-10d ✓ | 컨텍스트 과적용 방지 | p.46 새 헤더 항목 | 새 헤더는 직전 컨텍스트 미계승 |
| V-10e ✓ | 그룹 병렬·내부 순차 | 종로구청 분석 stderr 로그 (2026-06-22) | PASS: 5개 design 그룹이 16ms 내 동시 시작(병렬), 다중 페이지 그룹 내부는 직렬(page N+1 은 page N HTTP 완료 후 시작). 코드 구조(`asyncio.gather` + 그룹 내 `for await`)로도 보장 |

**우선순위 (잔여):** V-2/V-3/V-4 (지침서 핵심) → V-1 → V-6/V-7 → V-9. V-10a~e 는 2026-06-22 전부 PASS (`design_guidelines_grouped` 정규화 회귀, 영등포 PDF).

**V-10 자동 회귀:** V-10a~d 는 2026-06-19 영등포 PDF 로 PASS 확정. V-10e (그룹 병렬·내부 순차) 는 2026-06-22 종로구청 분석 stderr 로그로 PASS 확정 — 단, 아래 무료 회귀 도구는 fixture 기반이라 V-10a~d 만 재검증 (V-10e 는 stderr 필요로 SKIP). 코드 변경 시:

```powershell
backend\venv\Scripts\python.exe tools\v10_validate.py
```

스크립트가 `C:\Temp\CompTestDB\_briefs\20260619_161407_public_*.{json,xlsx}` fixture 기준 4 PASS 확인. PDF 재분석으로 brief_id 바뀌면 `PATTERN` 상수 갱신.

## Local Dev

```powershell
# Backend (terminal 1)
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
# http://localhost:8000

# Frontend (terminal 2)
cd frontend
npm install   # First time only
npm run dev
# http://localhost:5173 (proxies /api/* to 8000)
```

**New Machine Setup:** `git clone` → `pip install -r requirements.txt` + `npm install` → 백엔드/프론트 실행 → 설정 탭에서 DB 경로 + API 키 입력. DB 경로 미입력 시 `~/CompetitionAnalyzerDB` 자동.

**PaddleOCR (선택):** `pip install -r requirements-ocr.txt`. 기본 파이프라인은 PyMuPDF + Claude vision 으로 동작하므로 불필요.

**테스트:** `cd backend && venv/Scripts/python.exe -m pytest tests/ -v` (현재 288 passed, suite = `backend/tests/`). HWP/HWPX 코드 추가 시 `tests/test_hwpx_loader.py` 회귀 보호 필수 (22 케이스, rhwp monkeypatch — rhwp 미설치 환경도 통과). `tests/test_normalize_design_grouped.py` 13 케이스, `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스도 동일. `feasibility_export.py` 수정 시 `tests/test_feasibility_export.py` 46 케이스 + 무료 검증 `tools/feasibility_verify.py`. ⚠️ DOCX 회귀 `test_docx_extractor.py` (10 케이스) 는 repo-root `tests/` 에 있어 backend 기준 suite(288)에 **미포함** — DOCX 수정 시 별도 실행 (repo-root cwd): `backend/venv/Scripts/python.exe -m pytest tests/test_docx_extractor.py`.

## Deployment

- `main` push → GitHub Actions (`.github/workflows/deploy.yml`) → Docker 빌드 → Cloud Run.
- 수동 fallback: `gcloud run deploy competition-analyzer --source . --region asia-northeast3`.
- 로그: `gcloud logging read "resource.type=cloud_run_revision" --limit=50`.
- 상세는 `DEPLOYMENT.md`.

Cloud Run 청크 업로드 (`/api/upload`) 가 32MB 한도 우회. 파이프라인은 multipart 대신 `file_ref` 받음.
