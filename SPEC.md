# 설계공모 경쟁분석 시스템 — SPEC.md

> **작성 기준일:** 2026-07-01 · **개정:** 2026-07-15 (한 방 비교·프로젝트/지침서 삭제·인용 사후검증·디자인 토큰 단일소스·아카이브 BM25·OOM 8Gi 대응)  
> 이 문서는 소스 코드 직접 분석과 CLAUDE.md(ground truth)를 근거로 작성됩니다. 코드에서 직접 확인되지 않은 사항은 **(추정)** 으로 표시합니다.

---

## 1. 목적 및 배경

**설계공모 경쟁분석 시스템(Competition Analyzer)** 은 건축 설계 공모전에서 제출된 제안서 PDF와 공모 지침서(PDF/DOCX/HWP/HWPX)를 자동으로 추출·분류·비교·진단하는 풀스택 웹 애플리케이션입니다. 핵심 목적은 대형 건축사사무소가 다수의 공모 제안서를 체계적으로 분석하고, 과거 당선/낙선 패턴을 축적하여 신규 공모 진단 및 수주 전략 수립에 활용하는 것입니다.

기존의 수작업 비교 방식을 대체하기 위해 Claude AI(Sonnet 4.6 / Opus 4.8)를 LLM 엔진으로 활용하며, 추출된 정량 데이터와 AI 분석 결과를 HTML 리포트로 자동 생성합니다. 평가 결과는 숫자 점수가 아닌 5단계 등급(A/B/C/D/E) 문자열로 표현하여 임원 검토 시 정밀도 논쟁을 최소화합니다.

모든 데이터는 관계형 DB 없이 JSON 파일 시스템으로 저장되며, 운영 환경에서는 GCS 버킷을 GCSFUSE로 마운트하여 사용합니다. `main` 브랜치 push 시 GitHub Actions를 통해 Cloud Run (gen2)에 자동 배포됩니다.

---

## 2. 시스템 아키텍처

### 2.1 기술 스택

| 계층 | 기술 |
|------|------|
| 백엔드 프레임워크 | FastAPI (Python) |
| 프론트엔드 프레임워크 | React 18 + Vite |
| AI 모델 (추출·분류·비교·진단) | `claude-sonnet-4-6` |
| AI 모델 (지침서 종합 해설·수주 제안서) | `claude-opus-4-8` (`settings.model_id_advisor`) |
| PDF 래스터화 | PyMuPDF (fitz) |
| 데이터 저장 | JSON 파일 (flat file system, 관계형 DB 없음) |
| 전문 검색 | SQLite in-memory FTS5 (`archive_search.py`) |
| DOCX 파싱 | python-docx (`docx_loader.py`) |
| HWP/HWPX 파싱 | rhwp-python 0.7.0 (`hwpx_loader.py`) |
| OCR (선택적) | PaddleOCR (`requirements-ocr.txt`, Tier 1 경로) |
| 공간 데이터 | VWorld API (WMTS 위성 + WMS 지적도) |
| 대지 실측 맥락 | 터읽기(arch-site-context) `/board` 연동 (`teoilgi_client.py`, 인구·수급·재해·설계드라이버) |
| 건축법 진단 | arch-law-diagnose `/api/diagnose` + arch-law-graph `/api/lookup` 연동 (`arch_law_client.py`, 정북·envelope·심의·조문 원문) |

API 호출에는 Anthropic SDK가 아닌 `httpx`를 직접 사용하며, 엔드포인트는 `https://api.anthropic.com/v1/messages` (anthropic-version: 2023-06-01)입니다. 타임아웃은 900초, 재시도는 HTTP 502/503/529 및 `httpx.TimeoutException`에 대해 지수 백오프(2→4→8초, 최대 3회) 적용입니다.

### 2.2 배포 환경

- **운영:** Google Cloud Run (gen2), 컨테이너 이미지 빌드 후 배포
- **스토리지:** GCS 버킷 `gs://kunwon-competition-db` (GCSFUSE 마운트, `/data` 경로)
- **CI/CD:** GitHub Actions (`.github/workflows/deploy.yml`), `main` push 시 자동 트리거
- **로컬 개발:** 백엔드 `uvicorn main:app --reload --port 8000`, 프론트 `npm run dev` (Vite, port 5173, `/api/*` 프록시)
- **패키지:** `requirements.txt` (로컬) + `requirements-server.txt` (Docker, `Dockerfile`이 이것을 설치) — 양쪽 동기화 필수
- **Cloud Run 업로드 한도:** 32MB 제한 우회를 위해 청크 업로드 라우터(`/api/upload`) 사용
- **CORS:** `allow_origins=['*']`, `allow_credentials=False` — 전 오리진 허용 (의도적, per-browser API 키 모델)

### 2.3 디렉터리 구조 (주요)

```
competition_comparison/
├── backend/
│   ├── main.py                   # FastAPI 앱, 7개 라우터 마운트
│   ├── config.py                 # FACILITY_TYPES, PAGE_TYPES_META, 모델 ID, DPI 상수
│   ├── db_manager.py             # JSON DB CRUD, _atomic_write/_sync_write
│   ├── app_settings.json         # 설정 파일 (API 키 제외, git 추적)
│   ├── routers/
│   │   ├── accumulate.py         # 제안서 추출 + 비교분석 라우터
│   │   ├── diagnose.py           # 진단 라우터
│   │   ├── patterns.py           # 시설유형 패턴 관리
│   │   ├── settings.py           # 앱 설정 + /settings/meta 단일 소스
│   │   ├── upload.py             # 청크 업로드 (/tmp/cc_uploads/)
│   │   ├── archive.py            # FTS5 검색
│   │   └── brief.py              # 지침서 분석
│   ├── services/
│   │   ├── page_classifier.py    # 페이지/블록 분류
│   │   ├── data_extractor.py     # 3-tier 추출
│   │   ├── comparator.py         # 2-pass 블라인드-리빌
│   │   ├── pattern_builder.py    # 당선/낙선 패턴 집계
│   │   ├── llm_client.py         # Claude API 래퍼
│   │   ├── brief_advisor.py      # AI 종합 해설 (Opus)
│   │   ├── brief_proposal.py     # 수주 제안서 (Opus)
│   │   ├── reference_cases.py    # 시설유형별 기존 사례 참고자료 (LLM 0)
│   │   ├── vworld_analyzer.py    # VWorld 위성+지적도
│   │   ├── quant_validator.py    # 정량 정합성 검증 (LLM 0)
│   │   ├── feasibility_export.py # _brief.json → feasibility_export 블록 (arch-law 연동용)
│   │   ├── teoilgi_client.py     # 터읽기(arch-site-context) 실측 대지 맥락 연동
│   │   ├── arch_law_client.py    # arch-law-diagnose 건축법 진단 + graph 조문 원문 연동
│   │   ├── brief_genre.py        # 지침서 장르 판별 (공모 vs 입찰, LLM 0)
│   │   ├── bid_structure.py      # 입찰 2층 배점 구조 정규화 (LLM 0)
│   │   ├── brief_playbook.py     # 경험 기반 처방 (Opus, 무료 게이트)
│   │   ├── brief_playbook_report_generator.py  # 처방 HTML (LLM 0)
│   │   ├── brief_checklist_exporter.py # 지침서 체크리스트 html/md/xlsx (LLM 0)
│   │   ├── proposal_number_check.py    # 제안서 근거없는 수치 검산 (LLM 0)
│   │   ├── archive_search.py     # SQLite FTS5 인메모리
│   │   ├── grade_helpers.py      # A-E 등급 단일 소스
│   │   ├── docx_loader.py        # DOCX 블록 파싱
│   │   ├── hwpx_loader.py        # HWP/HWPX 블록 파싱
│   │   ├── report_generator.py           # 비교 HTML (LLM 0)
│   │   ├── submission_report_generator.py # 개별 리포트 HTML (LLM 0)
│   │   ├── diagnosis_report_generator.py  # 진단 HTML (LLM 0)
│   │   ├── myproject_analyzer.py          # MyProject deep analysis (LLM 1콜)
│   │   ├── myproject_report_generator.py  # deep HTML (LLM 0)
│   │   └── brief_proposal_report_generator.py  # 제안서 HTML (LLM 0)
│   └── tests/                    # 581 테스트 (2026-07-15)
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # 7탭 구조, MetaProvider/ApiKeyGate 래핑
│   │   ├── api/client.js         # API 클라이언트 함수 전체
│   │   ├── hooks/useMeta.jsx     # 시설유형·페이지타입·평가축 단일 소스
│   │   ├── kunwon-tokens.css     # 디자인 토큰 단일 소스
│   │   └── components/
│   │       ├── BriefMode/
│   │       ├── AccumulateMode/
│   │       └── ...
│   └── dist/                     # Vite 빌드 산출물 (백엔드가 SPA 서빙)
└── tests/                        # repo-root 레벨 (test_docx_extractor.py, 10건, 별도 실행)
```

---

## 3. 핵심 파이프라인

### 3.1 제안서 축적 (Accumulate)

**엔드포인트:** `POST /api/accumulate/add-submission` (SSE 스트리밍)

1. **업로드:** 25MB 미만 파일은 FormData 직접 전송, 이상은 청크 업로드(`/api/upload`)로 `file_ref` 취득.
2. **분류(classify):** `page_classifier.classify_all_pages_brief()`가 PDF 페이지를 배치 처리(BATCH_SIZE=5). DPI 72, `claude-sonnet-4-6`, `max_tokens=3000`, `temperature=0`. 각 페이지에 `{page, type, confidence, sub_elements, has_text, has_drawing, has_rendering, has_table}` 반환.
3. **추출(extract):** `data_extractor.py`의 3-tier 로직 적용 (§5.2 참조). 제안서 결과에 `_quantitative` 자동 집계 및 `quant_validator`로 `_quantitative_flags` 부착(모순 시에만).
4. **저장:** `db_manager._atomic_write()` (JSON), `_sync_write()` (HTML). 개별 제출물 리포트 즉시 생성.
5. **SSE 이벤트:** `stage` / `progress` (page 번호 포함) / `done` / `error`. 모든 이벤트에 `_timestamp` (epoch ms) 필수.

**한 방 비교(`run`의 `run_compare` 폼, 기본 OFF·프론트 체크박스 기본 ON):** 켜져 있고 제출물 2개↑이면 추출 직후 같은 `run` 안에서 `compare_submissions`(2-pass)+패턴+비교리포트+아카이브 재인덱싱까지 수행하고 `complete`에 `comparison`을 동봉(`report_available:true`). 비교 실패는 비치명(`compare_error` 이벤트, 추출물 유지), <2면 `compare_skipped`. 껐을 때 비교분석은 분리 — `POST /api/accumulate/projects/{ft}/{cid}/rerun-compare`를 별도 호출. `POST .../rerender-report`는 LLM 없이 HTML만 재생성.

**프로젝트 삭제:** `DELETE /api/accumulate/projects/{ft}/{cid}` → `db_manager.delete_project`(폴더 rmtree, path traversal 가드) 후 시설 패턴·아카이브 인덱스 재구축.

**MyProject 심층 분석:** `POST /api/accumulate/run-single` 엔드포인트 경유. 단일 등록 시 `myproject_analyzer.deep_analyze()` 호출 → `_deep.json` + `_deep.html` 생성. LLM 1콜 (`max_tokens=16000`, `temperature=0.3`), 축 당 5-10 강점, 3-8 약점, 각 항목 `(p.N)` 페이지 인용 포함.

### 3.2 비교분석 (Compare) — 2-pass Blind-Reveal

**엔드포인트:** `POST /api/accumulate/projects/{ft}/{cid}/rerun-compare`

**Pass 1 (블라인드 채점):**
- 모든 제출물을 A안/B안/... 로 익명화, 결과 라벨(win/lose) 제거.
- 정적 프롬프트(`_make_blind_static()`)와 동적 데이터(brief + submissions JSON) 각각을 별도 콘텐츠 블록으로 전송하며 둘 다 `cache_control={'type': 'ephemeral'}` 적용.
- `max_tokens=32000`, `temperature=0`, `claude-sonnet-4-6`.
- 프롬프트 템플릿은 `.replace()` 사용 (`.format()`은 JSON 중괄호 충돌 회피).

**Pass 2 (리빌 + 사후 분석):**
- Pass 1 출력(블라인드 등급)과 실제 결과 라벨만 전송. 원본 추출 데이터·brief JSON은 재전송하지 않음 → 토큰 약 80% 절감.
- `max_tokens=8192`.
- `concept_comparison` 산출: 시설유형 축마다, Pass 1 결과의 strengths/weaknesses/notes(이미 (p.N) 인용 포함)만 근거로 모든 제출물의 컨셉·설계방향을 한 문단으로 나란히 비교(승/패 프레이밍 아님). 원본 데이터 재전송 없이 Pass 1 산출물만 재가공하므로 토큰 절감 구조를 깨지 않음.

**Gap Analysis (결정론):** `_compute_gap_analysis()`가 순수 Python으로 산출.
- `blind_top1`: 블라인드 1위 제출물
- `actual_winners`: result가 win 또는 contracted인 제출물
- `top1_matches_winner`: bool
- `alignment` 로직: 블라인드 상위 절반 = `ceil((n+1)/2)` 항목. top1 일치 AND 당선작의 90% 이상이 상위 절반에 → `'high'`; 50% 이상 → `'partial'`; 그 외 → `'low'`; 산출 불가 → `'unknown'`.

비교 완료 후: `_comparison.json` 저장 → 시설유형 패턴 재구축 → 비교 HTML + 개별 리포트 재생성 → FTS5 인덱스 `rebuild_index()`.

### 3.3 제안서 진단 (Diagnose)

**엔드포인트:**
- `POST /api/diagnose/run` — DB 전체 당선 패턴과 비교
- `POST /api/diagnose/run-vs-projects` — 사용자 선택 제출물 기반 `build_pattern_from_submissions()` 사용

**파이프라인:** `load_patterns` → (brief 선택: `classify_brief` → `extract_brief` → `brief_reqs`) → `classify_sub` → `extract_sub` → `diagnose` → `report` → `complete`.

- 진단 LLM 호출: `_run_diagnose_sync()`, 2-블록 캐싱(static + dynamic 모두 ephemeral), `max_tokens=8192`, `temperature=0`, `claude-sonnet-4-6`.
- 당선 패턴(loser_stats 포함) + brief_requirements + submission_data를 모두 주입.
- 완료 시 `diagnosis_report_generator.generate_diagnosis_report()`로 HTML 자동 생성 (LLM 0). 생성 실패 시 비치명, `report_filename=None`으로 complete 이벤트 전송.
- 리포트 파일명: `{YYYYMMDD_HHMMSS}_{facility_type}_{slug}.html` (slug = competition_name 최대 40자).
- **주의:** diagnose SSE 이벤트에는 `_timestamp` 필드가 없음 (brief SSE와 다름, 추정: 구현 시점 차이).

### 3.4 지침서 분석 (Brief)

**엔드포인트:** `POST /api/brief/analyze` (SSE)

**지원 포맷:** PDF (≤200MB), DOCX/HWP/HWPX (각 ≤50MB).

**파일 검증 (`_validate_brief_file()`):**
- PDF: magic byte `b'%PDF'`
- DOCX/HWPX: `b'PK\x03\x04'` (ZIP 포맷)
- HWP: `b'\xd0\xcf\x11\xe0'` (OLE2 포맷)

**파이프라인 순서:** `classify_brief` → `extract_brief` → `brief_reqs` → `validate` → (옵션) `insight` → (옵션) `site_analysis` → `save` → `complete`.

**분류:**
- PDF → `classify_all_pages_brief()` (vision 기반, 13가지 BRIEF_* 타입)
- DOCX → `split_docx_to_blocks()` + `classify_all_blocks_brief()` (텍스트 기반, 이미지 토큰 0)
- HWP/HWPX → `split_hwpx_to_blocks()` + `classify_all_blocks_brief()` (동일 텍스트 기반)

**추출 후처리:**
- `merge_extracted_data()` → `_merge_brief_project_info_pages()`로 `sites[]` / `special_conditions[]` / `unit_program[]` 합산.
- Brief 결과에 `feasibility_export` 블록 자동 부착 (try/except, 비치명).
- `extract_brief_requirements()` → `validate_brief()` → 검증 flags.

**저장 순서:** `_atomic_write(json)` → `_sync_write(md)` → `_sync_write(html)` → `_sync_write_bytes(xlsx)`.

**저장 경로:** `{db_path}/_briefs/{YYYYMMDD_HHMMSS}_{facility_type}_{slug}.{json|md|html|xlsx}` (최대 120자).

**complete SSE 이벤트 포함 필드:** `{brief_id, facility_type, total_pages, md_filename, xlsx_filename, html_filename, validation_summary, source_format, has_insight, has_proposal, proposal_filename, has_site_context, site_context, brief_genre, _timestamp}`. `/analyze` 폼 파라미터: `include_insight`(기본 ON)·`include_proposal`(기본 OFF)·`site_address`(선택).

**다중 파일 병합 (`_merge_multi_brief_data`):** `design_guidelines_grouped` 전체 연결 후 정규화, `_quantitative` 는 첫 non-null 우선, `page_map`/`total_pages` 합산, 기타 필드는 first-wins. 혼합 포맷 시 `source_format='multi'`.

#### 3.4.1 AI 종합 해설 (brief_advisor)

`POST /api/brief/{brief_id}/interpret` 또는 `/analyze`의 `include_insight=True`(기본값)로 실행.

- **역할 ("해설가"):** 사실 triage만. 지침서가 무엇을 요구·강조·배점하는지 종합. 당락 예측, 전략 처방, 외부 지식 주입 금지.
- **결정론 백본 `compute_scoring_focus()`:** LLM 0. 배점이 가장 많은 페이지(`max(key=_eval_pts)`)의 `evaluation_categories`에서 각 카테고리 점수·weight_pct·rank 산출. 분모는 `total_points` 또는 합산값. LLM 출력의 `scoring_focus`는 이 결정론 값으로 **항상 덮어씀** (환각 차단).
- **참고 사례 (`reference_cases.collect_reference_context()`):** 있을 때만, 동일 시설유형 기존 사례를 배경 참고로 payload 에 추가. `reading_guide` 배경 참고로만 쓰이고 `key_emphases`/`must_not_miss`/`hidden_constraints`/`scoring_focus` 판단 근거로는 사용 금지 (가드). 결과에 `_reference_cases` 로 부착되어 렌더러의 "참고 사례" 섹션에 노출.
- **LLM 호출:** `interpret_brief()`, `claude-opus-4-8` (settings.model_id_advisor), `max_tokens=16000`, temperature=0 (Opus는 `llm_client._NO_SAMPLING_PREFIXES`에 의해 자동 생략).
- **가드 4개:** 근거 한정, 인용 필수 (페이지 추측 금지), 예측 금지, 중립 탐지만.
- **산출물 `_insight`:** `_brief.json` 내 임베드 (별도 파일 아님). `brief_checklist_exporter`의 HTML/MD/xlsx 3종 모두 `_insight` 렌더링 (graceful skip; "참고 사례" 서브섹션은 HTML 전용).

#### 3.4.2 수주 제안서 (brief_proposal)

`POST /api/brief/{brief_id}/propose` 호출, 또는 `/analyze` 폼 **`include_proposal=True`(기본 OFF)** 로 분석과 동시 생성(단계 4.8) — 수집한 대지·법(site_context)을 버튼 없이 바로 융합. 렌더는 `/propose`·`/analyze` 공용 `_render_proposal_html`.

- **역할 ("전략가"):** 처방형 전략. `brief_advisor`(해설가)와 별개 산출물.
- **대지 근거 배치 (`placement_strategy`, 2026-07-14):** zones=[{program, site, plan(8방위+C), level, required(지침서 명시=사실 vs AI 추론), why, draws_on(대지·법·프로그램·배점 교차), basis}] — SVG 조닝/단면 다이어그램(다부지 부지별 분리). site_context.analysis·measured·law_diagnosis 를 배치 근거로 교차 합성.
- **결정론 백본 재사용:** `brief_advisor._build_advisor_payload()` + `compute_scoring_focus()` 그대로 import (드리프트 차단) — `reference_cases`(시설유형 기존 사례)도 이 payload 를 통해 공유. 기존 `_insight`는 `_prior_insight_digest()`로 요약 주입. `_pattern_signals(facility_type)`로 동일 시설유형 당선/낙선 경향을 `payload["pattern_context"]`에 주입.
- **사실/제안 2층 분리:** 사실 주장(지침서가 요구하는 것)에는 basis 인용 강제, 전략·접근은 제안 명시.
- **고정 설계 계약:** `win_themes` 1~2개로 압축, `design_directions` 상호 배타 컨셉 5안 고정 (이 필드만 triage 예외), `risks` 2층 (명시 실격 + 반복 강조 → '흔한 감점 함정' 추론).
- **AI 해석 확장층 (Phase 2):** `program_directions` / `massing_strategy` / `phasing` 신규 필드 (각 `{claim, basis}` 구조, basis 앵커 없으면 제외).
- **수치 검산:** `proposal_number_check.check_proposal_numbers()` (LLM 0). `_proposal` prose의 수치를 brief 코퍼스 + `scoring_focus`와 대조 → `_number_flags` 부착 (숫자 수정 0, 비치명).
- **산출물:** `_proposal` 임베드 + `{brief_id}_proposal.html` 별도 저장.

#### 3.4.3 대지·맥락 + 건축법 진단 (vworld_analyzer · teoilgi_client · arch_law_client)

지침서 분석 완료 후 자동(단계 4.7) 또는 `POST /api/brief/{brief_id}/site-analyze`(주소로 VWorld 재분석).

- **자동 실행 조건:** `feasibility_export.sites[]` 에 주소가 있거나, `/analyze` 폼의 **`site_address`(선택)** 로 사용자가 직접 입력. `site_address` override 는 지침서 미추출/오추출 주소를 고정(첫 부지 대체·envelope 유지→law 작동, 부지 테이블 없으면 vision+measured만). 모든 하위 취득은 graceful(하나 실패해도 나머지 유지).
- **부지별 병렬 (다부지 비대칭 해소):** 주소 있는 전 부지를 `asyncio.gather` 로 각각 분석. `_site_context` 대표값(analysis·measured·matched_address)=첫 부지(단일부지·호환), `_site_context.sites[]`=전 부지 {site_id, address, analysis, measured}. 첫 부지 이미지만 히어로로 저장.
- **① VWorld vision** (`settings.has_vworld_key()` True 시): 아래 위성·지적도·Vision 상세.
- **② 터읽기 실측** (`teoilgi_client.fetch_board_context`, 키 무관·graceful): `POST /board {brief:true, synthesize:false}` → 인구지수·수급·재해·설계 드라이버(시군구 평균). `_site_context.measured`. 터읽기 ②AI판단·notes 는 경계상 제외.
- **③ 건축법 진단** (`arch_law_client`, always-on·`ARCH_LAW_DISABLE`로만 끔): feasibility 허용 한도로 최대 매스 역산 → `POST /api/diagnose`(부지별) → `digest_diagnosis` → `_site_context.law_diagnosis[]`(정북 일조·가로구역·envelope·심의·law_refs·low_confidence·limit_mismatch). ⚠계약: `applicable_reviews` 는 dict `{items[]}`(배열 아님), `높이_일조.pass` 는 envelope 모드 항상 null. **Phase 3**: law_refs → arch-law-graph `/api/lookup` → `_site_context.law_texts`(조문 원문, found만).
- **소비:** 체크리스트 html/md/xlsx "대지·법적 골격" 섹션(제안서 없이도 표시) + 수주 제안서 placement 법근거 + 법적 골격 패널(조문 각주).
- **VWorld 세부:** ↓
- **지오코딩:** `GET /req/address` (ROAD → PARCEL 순서로 시도), EPSG:4326 반환.
- **위성 이미지:** WMTS 타일 `https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{z}/{y}/{x}.jpeg`. 기본 zoom=16 (`_DEFAULT_ZOOM`), 3×3 타일 그리드 (`_TILE_GRID=3`) → 위도 37도 기준 약 1.8km 범위.
- **지적도 오버레이:** WMS GetMap `/req/wms`, layers=`lp_pa_cbnd_bonbun,lp_pa_cbnd_bubun`, CRS=EPSG:3857, FORMAT=image/png, TRANSPARENT=true. 중앙 900m 구간 (`_CADASTRAL_SPAN_M=900`) 을 768px (`_CADASTRAL_REQ_PX=768`) 로 요청 (~1.2m/px) → 비례 축소 후 광역 위성 중앙에 합성. **스케일 임계는 m/px (절대 span 아님).** 구 레이어명 `lp_pa_cn_A`는 오타 (LayerNotDefined 발생).
- **병렬 취득:** `asyncio.gather`로 WMTS와 WMS 동시 요청.
- **폴백:** alpha 채널 전체 0(스케일 미충족), 오프셋 이탈, PIL 오류 시 → 위성 단독 이미지 (비치명, try/except 보장). `has_cadastral` 플래그가 `_site_context`, vision 프롬프트, 제안서 썸네일 캡션까지 전파.
- **Vision 분석:** `claude-sonnet-4-6`, `max_tokens=1500`, `temperature=0`. 출력 JPEG quality=90. 반환 필드: `{orientation, road_access, surrounding_uses, natural_assets, special_context, overall_summary, confidence, caveats}`.
- **저장:** `_site_context` → `_brief.json` 내 임베드 + `{brief_id}_site.jpg` 별도 파일.

### 3.5 교차 비교 (Cross-Compare)

**엔드포인트:** `POST /api/accumulate/cross-compare` (SSE)

여러 프로젝트에서 선택한 제출물들을 교차 비교합니다. `crossCompare(items)` 클라이언트 함수가 items 배열을 JSON 문자열로 FormData에 `items_json`으로 전송합니다. 결과는 `_cross_reports/*.html`로 저장되며, `GET /api/accumulate/cross-compare/reports`로 목록 조회(`has_data` 플래그 포함), `GET /cross-compare/reports/{filename}`으로 개별 리포트를 서빙합니다.

**다공모 지침서:** 서로 다른 공모 제출물이면 공통 지침서가 없으므로, 제출물별로 자기 공모 지침서 요약(`_brief_digest`)을 `extracted_data._brief_context`에 실어 `comparator`가 각 제출물을 **자기 지침서로** 판정(단일 공모면 그 지침서를 공통 기준). **구조화 persist:** HTML 옆에 `save_cross_compare_data`로 `{stem}.json`(meta·items·submissions·comparison) 저장 → `POST /cross-compare/reports/{filename}/rerender`로 **LLM 재호출 없이** 재렌더.

### 3.6 아카이브 검색 (Archive)

**엔드포인트:** `GET /api/archive/list`, `POST /api/archive/search`, `GET /api/archive/{ft}/{cid}`

- **FTS5 인덱스:** 앱 시작 시 `build_index()` 1회 구축 (in-memory SQLite). `rerun-compare` 후 `rebuild_index()` 호출.
- **테이블 컬럼:** `competition_id, facility_type, ranking, key_differentiators, winner_patterns, concept_keywords, gap_analysis_alignment, extra_meta`.
- **토크나이저:** trigram (SQLite 3.34+ 필요) 시도 후 OperationalError 시 unicode61 폴백.
- **검색 흐름:** 2자 이하 → 전체 리스트 반환. 3자 이상 → Claude (`settings.model_id_classify`, `max_tokens=300`) 가 2-5개 FTS 키워드 추출 → FTS5 OR 쿼리 (키워드 각각 쌍따옴표 감쌈, `_fts_escape()` 처리). LLM 실패 시 직접 키워드 검색 폴백.
- **BM25 관련도 랭킹:** `_ranked_match`가 `ORDER BY bm25(archive_fts, _BM25_WEIGHTS)`로 best-first 정렬(컬럼 가중치=시설유형·컨셉키워드 우대), bm25 미지원 SQLite면 무순 폴백. keyword·natural 검색 공유. ⚠trigram은 2자 미만 미매칭(병원·시청 단독 무결과).
- **extra_meta:** MyProject deep analysis 텍스트 (`concept_narrative`, `search_keywords` 등) + 조달 유형 동의어 + 사업 단계 동의어 포함.
- **result_filter:** `'win'` (gap_analysis.actual_winners truthy), `'lose'` (falsy), `'all'`.

---

## 4. 데이터 모델

### 4.1 DB 레이아웃 (파일 시스템)

```
{db_path}/
├── {facility_type}/{competition_id}/
│   ├── _meta.json
│   ├── _brief.json              # 지침서 추출 결과 + _insight + _proposal + _site_context
│   ├── _comparison.json         # 비교분석 결과
│   ├── _report.html             # 비교 리포트
│   └── submissions/
│       ├── {slug}_{result}.json         # 제출물 추출 결과
│       ├── {slug}_{result}_report.html  # 개별 리포트
│       └── {slug}_{result}_deep.{json|html}  # MyProject only
├── _patterns/{facility_type}.json      # 당선+낙선 통계 패턴
├── _diagnosis_reports/{YYYYMMDD_HHMMSS}_{ft}_{name}.html
├── _cross_reports/*.html
├── _briefs/{brief_id}.{json|md|html|xlsx}
├── _briefs/{brief_id}_proposal.html
├── _briefs/{brief_id}_site.jpg
└── _config/page_taxonomy.json          # 페이지 분류 메타 (시작 시 1회 생성)
```

`competition_id` = `{slugify(project_number)}_{slugify(name)}`. `result` = `win` | `lose` | `contracted`. `slug` = `_slugify(company)` (비단어/비한글 제거, 공백→언더스코어).

**운영 환경 db_path:** GCS 버킷 GCSFUSE 마운트 (`/data`). 로컬 Windows 기본값: 하드코딩된 M: 드라이브 경로 (config.py line 36-37). DB_PATH 환경변수 또는 설정 패널에서 override 가능. 미설정 시 `~/CompetitionAnalyzerDB`.

### 4.2 주요 JSON 스키마

**`_comparison.json`:**
```json
{
  "submissions": {"<company>": {"<axis>": {"grade": "A|B|C|D|E", "strengths": [], "weaknesses": [], "brief_compliance": "", "notes": "", "grade_justification": ""}}},
  "ranking": [],
  "blind_ranking": [],
  "key_differentiators": [],
  "concept_comparison": {"<axis>": "<Korean paragraph comparing every submission's concept/design approach with (p.N) citations>"},
  "winner_strengths": [],
  "loser_weaknesses": [],
  "gap_analysis": {"blind_top1": "", "actual_winners": [], "top1_matches_winner": true, "alignment": "high|partial|low|unknown", "notes": ""},
  "rubric_version": "v1"
}
```

`ranking`/`blind_ranking`/`gap_analysis`는 archive_search·pattern_builder 등 기존 소비자를 위해 계속 산출되지만, 비교 결과 화면(`report_generator.py`, `ComparisonDashboard.jsx`)에는 더 이상 렌더링하지 않는다(2026-07-01) — "누가 1등이냐"보다 `concept_comparison`(축별 컨셉·설계방향 비교)이 더 유용하다는 결정. `gap_analysis`는 내부 QA(블라인드 채점이 실제 결과와 정렬되는지) 용도로만 보존.

**`_quantitative` 키 (제출물 JSON 내):**
`site_area_sqm`, `building_area_sqm`, `total_floor_area_sqm`, `area_above_ground_sqm`, `area_below_ground_sqm`, `floor_area_ratio_pct`, `building_coverage_ratio_pct`, `floors_above`, `floors_below`, `parking_count`

**`_quantitative_flags` (제안서 추출 시, 모순 있을 때만):**
```json
[{"rule": "coverage_mismatch|floor_area_below_far_implied|building_gt_site|far_above_ground_mismatch|out_of_bounds|coverage_gt_far", "severity": "error|warn", "fields": ["<_quantitative 키...>"], "detail": "<한국어 사유>"}]
```
Brief 결과에는 미부착. `error` 필드는 `pattern_builder._build_quant_stats`에서 집계 제외.

**`feasibility_export` (schema_version 2, `_brief.json` 내):**
```json
{
  "schema_version": 2,
  "sites": [{"site_id": "부지N", "address": "", "building_law_uses": [], "required_parking_count": null, "parking_note": null, "zone_use": "준공업지역|null", "zone_use_raw": null, "limits_determined_by": "심의|법정", "site_area_sqm": null, "floor_area_ratio_pct": null, "building_coverage_pct": null, "max_height_m": null}],
  "certifications": {"green_building": "최우수|우수|null", "zeb_grade": "1~5|null", "renewable_pct": null, "bf_grade": "최우수|우수|null"},
  "construction_cost_100m_won": null,
  "design_cost_100m_won": null,
  "construction_period_months": null
}
```
`limits_determined_by="심의"` 시 법정 한계로 해석 금지.

**`_insight` (schema_version 1, `_brief.json` 내):**
```json
{
  "schema_version": 1, "brief_id": "", "facility_type": "", "generated_at": "", "model_id": "claude-opus-4-8",
  "synthesis_summary": "",
  "key_emphases": [{"topic": "", "signal_strength": "strong|medium|weak", "signals": [], "basis": [], "note": ""}],
  "scoring_focus": [{"category": "", "points": null, "weight_pct": null, "shared_with": [], "rank": null}],
  "must_not_miss": [{"item": "", "basis": ""}],
  "hidden_constraints": [{"issue": "", "basis": "", "note": ""}],
  "reading_guide": [],
  "data_confidence": "high|medium|low",
  "caveats": [],
  "_reference_cases": {}
}
```

`_reference_cases`는 `reference_cases.collect_reference_context()` 원본 (없으면 `{}`) — 동일 시설유형 다른 공모 참고자료, 이 지침서 사실 판단 근거로는 미사용 (렌더러 "참고 사례" 섹션용).

**`_proposal` (schema_version 1, `_brief.json` 내):**
```json
{
  "schema_version": 1, "brief_id": "", "facility_type": "", "generated_at": "", "model_id": "claude-opus-4-8",
  "executive_summary": "",
  "win_themes": [{"theme": "", "rationale": "", "scoring_link": "", "basis": []}],
  "design_directions": [{"direction": "", "narrative": "", "addresses": "", "scoring_play": "", "tradeoffs": "", "site_rationale": "", "basis": []}],
  "program_directions": [{"claim": "", "detail": "", "basis": []}],
  "massing_strategy": [{"claim": "", "detail": "", "basis": []}],
  "phasing": [{"claim": "", "detail": "", "basis": []}],
  "priorities": [{"rank": 1, "focus": "", "why": "", "scoring_weight": ""}],
  "risks": [{"risk": "", "severity": "high|medium|low", "mitigation": "", "basis": ""}],
  "kickoff_checklist": [],
  "open_questions": [],
  "scoring_focus": [],
  "caveats": [],
  "_number_flags": [{"value": "", "field": "", "context": ""}],
  "_reference_cases": {}
}
```

`_reference_cases`는 `_insight`와 동일하게 `reference_cases.collect_reference_context()` 원본 (없으면 `{}`) — `brief_proposal_report_generator`가 있을 때만 "참고 사례" 섹션 렌더.

---

## 5. AI 분류·추출 로직

### 5.1 페이지/블록 분류

**페이지 타입 수:** 제안서 27개 (일반 20 + 재건축 전용 7), 지침서 13개 (BRIEF_*).

**재건축 전용 7개:** BUSINESS_VIABILITY, AREA_INCREASE, VIEW_ANALYSIS, COMMUNITY_PROGRAM, COMPANY_PORTFOLIO, CONSTRUCTION_PLAN, UNIT_PLAN_PENTHOUSE.

**분류 모델:** `claude-sonnet-4-6` (`MODEL_ID_CLASSIFY`). Haiku는 헤더 환각 문제로 배제.

**배치:** BATCH_SIZE=5페이지/콜. 길이 불일치 시 최대 2회 재시도 후 1페이지씩 개별 분류 폴백.

**분류 신뢰도 다운그레이드 (재건축 타입):**
`REDEV_CONFIDENCE_FLOOR=0.65` 미만 시 안전 폴백으로 강등:
- BUSINESS_VIABILITY → AREA_TABLE
- VIEW_ANALYSIS → SITE_PLAN
- COMMUNITY_PROGRAM → SPECIAL_SPACE
- COMPANY_PORTFOLIO → BRANDING
- CONSTRUCTION_PLAN → TECHNICAL
- UNIT_PLAN_PENTHOUSE → UNIT_PLAN

**지침서 추가 후처리:**
- `has_scoring_table=False` → BRIEF_EVALUATION을 BRIEF_ADMIN으로 강등
- `_NOT_EVAL_HEADER_PATTERNS` 정규식 일치 (결과 발표, 결과 공고, 시상식, 상품 및 내용, [서식, 별첨, 부록 등) → BRIEF_EVALUATION 강등

**BRIEF_EVALUATION 환각 방어 5중:**
1. `BRIEF_CLASSIFY_PROMPT` NOT 조건 (g)~(j)
2. `_NOT_EVAL_HEADER_PATTERNS` 후처리 정규식
3. `MODEL_ID_CLASSIFY` Sonnet 고정 (Haiku 헤더 환각 차단)
4. `FACILITY_CONFLICT_KEYWORDS` + `brief_validator._check_facility_keyword_conflict()`
5. BRIEF_EVALUATION 추출 프롬프트 "CRITICAL 환각 금지" 블록

### 5.2 추출 티어 (Tier 0 / OCR / Vision)

**Tier 0 — 디지털 텍스트 (fitz.get_text()):**
- 조건: `DIGITAL_TEXT_EXCLUDE_TYPES`에 포함되지 않는 타입
- 제외 타입: AREA_TABLE, TECHNICAL, INCENTIVE_TABLE, BUSINESS_VIABILITY, AREA_INCREASE, BRIEF_PROGRAM, BRIEF_REGULATIONS, BRIEF_EVALUATION, BRIEF_PROJECT_INFO (HWP→PDF 변환 시 병합 셀 구조 붕괴 방지)

**Tier 1 — OCR (PaddleOCR + Haiku 구조화):**
- 대상 `OCR_FIRST_TYPES`: AREA_TABLE, TECHNICAL, SUSTAINABILITY, BUSINESS_VIABILITY, AREA_INCREASE, COMPANY_PORTFOLIO, CONSTRUCTION_PLAN
- Sonnet+vision 대비 페이지당 약 90% 비용 절감
- `OCR_MIN_CHARS=80` 미만 시 Tier 2(vision)로 폴백

**Tier 2 — Full Vision (Sonnet + 이미지):**
- 나머지 모든 타입. DPI 120 (`RASTER_DPI_EXTRACT`).
- `max_tokens=4000` (일반), `max_tokens=6000` (BRIEF_DESIGN_* 타입: BRIEF_DESIGN_MASSING, BRIEF_DESIGN_GUIDE, BRIEF_DESIGN_FACADE, BRIEF_DESIGN_SUSTAIN, BRIEF_DESIGN_SPECIAL).

**타일 분할 추출:**
- `TILE_PAGE_TYPES`: AREA_TABLE, TECHNICAL, INCENTIVE_TABLE, BUSINESS_VIABILITY, AREA_INCREASE
- 2×2 타일로 분할 → 실효 해상도 약 1.6배 향상
- 페이지 분류 신뢰도 < `CONFIDENCE_DOWNGRADE_THRESHOLD=0.7` 시 타일 추출 → 일반 추출 다운그레이드

**스킵 타입 (`SKIP_PAGE_TYPES`):** COVER, RENDERING_EXT, RENDERING_INT (및 priority=3 타입: BRANDING, BRIEF_SUBMISSION, BRIEF_ADMIN) — `settings.extraction_priority_limit`(기본 3) 기준 적용.

**이미지 포맷 감지:** `img_bytes[:3] == b'\xff\xd8\xff'` → `image/jpeg`, 그 외 → `image/png` (포맷 불일치는 API 400 원인).

**BRIEF_PROGRAM 스태킹:** 여러 페이지를 수직 스택 이미지로 합성. JPEG quality=85, `_STACK_MAX_DIM=7500px` 상한. non-null points 합계 0이면 `precomputed_eval=None` 폴백.

**BRIEF_EVALUATION 표 파싱:** DOCX/HWPX는 `_extract_docx_eval_from_table()` 로 LLM 없이 직접 파싱 (환각 차단). merge_info 스키마: `{row, col, merged_rows, value}` (docx/hwpx 공통).

### 5.3 LLM 라우팅 및 비용 최적화

| 용도 | 모델 | max_tokens | temperature |
|------|------|-----------|-------------|
| 페이지 분류 | claude-sonnet-4-6 | 3000 | 0 |
| 데이터 추출 | claude-sonnet-4-6 | 4000 (BRIEF_DESIGN: 6000) | 0 |
| 비교분석 Pass 1 | claude-sonnet-4-6 | 32000 | 0 |
| 비교분석 Pass 2 | claude-sonnet-4-6 | 4096 | 0 |
| 진단 | claude-sonnet-4-6 | 8192 | 0 |
| VWorld vision | claude-sonnet-4-6 | 1500 | 0 |
| FTS 키워드 추출 | claude-sonnet-4-6 | 300 | 0 |
| MyProject deep analyze | claude-sonnet-4-6 | 16000 | 0.3 |
| AI 종합 해설 | claude-opus-4-8 | 16000 | 0 (자동 생략) |
| 수주 제안서 | claude-opus-4-8 | 16000 | 0 (자동 생략) |

**Opus temperature 자동 생략:** `llm_client._NO_SAMPLING_PREFIXES = ('claude-opus-4-7', 'claude-opus-4-8', 'claude-fable', 'claude-mythos')`. 이 접두사로 시작하는 모델에 temperature/top_p/top_k 전송 시 HTTP 400 발생 → `llm_client`가 request body에서 자동 제거.

**프롬프트 캐싱:**
- `cache_control={'type': 'ephemeral'}` (5분 TTL)
- 비교(comparator): 정적 프롬프트 블록 + 동적 데이터 블록 각각 ephemeral 마킹
- 진단(diagnose): 동일 2-블록 패턴
- Sonnet 캐싱 최소 1024 토큰. 캐시 히트 시 입력 토큰 약 90% 할인, 캐시 쓰기 1.25×.
- Pass 2는 Pass 1 결과만 재전송 → 토큰 약 80% 절감.

**DPI 설정:**
- 분류: 72 (`RASTER_DPI_CLASSIFY`)
- 추출: 120 (`RASTER_DPI_EXTRACT`, 150에서 변경 → 이미지 토큰 약 36% 절감)
- Claude API는 내부적으로 최장 변 ~1568px로 리사이즈하므로 150 이상은 효과 없음.

---

## 6. 품질 보증

### 6.1 정량 검증 (quant_validator)

`quant_validator.validate_quantitative()` — LLM 0, 숫자 수정 0, 플래그만.

**검증 규칙:**
| 규칙 | severity | 조건 |
|------|----------|------|
| `building_gt_site` | error | `building_area_sqm > site_area_sqm × 1.02` |
| `coverage_mismatch` | error | `|100×건축/대지 - 건폐율| > 3.0pp` |
| `far_above_ground_mismatch` | error | `|100×지상연면적/대지 - 용적률| > 5.0pp` (area_above_ground 있을 때 우선) |
| `floor_area_below_far_implied` | error | `총연면적 < (용적률/100 × 대지) × 0.9` (area_above_ground 없을 때 폴백) |
| `out_of_bounds` | error | 건폐율 0-100%, 용적률 0-1500%, 지상층 0-120, 지하층 0-12, 주차 0-50000 벗어남 |
| `coverage_gt_far` | warn | `건폐율 > 용적률 + 1` |

**단일 소스:** `merge_extracted_data` (추출 직후 `_quantitative_flags` 부착) + `pattern_builder._build_quant_stats` (error 필드 집계 제외) + `tools/data_health.py` (무료 감사).

**패턴 오염 차단 2단:**
1. `merge_extracted_data`가 추출 직후 `_quantitative_flags` 부착 (제안서만)
2. `pattern_builder._build_quant_stats`가 error 필드를 제출물별 집계에서 제외. 구 레코드(플래그 훅 이전)는 집계 시점에 `validate_quantitative()` 재검증.

실 사례: 하안주공(건폐율 27.46% vs 실제 81.6%), public-a(총연면적 < 대지×용적률)가 패턴 오염 방지 검증에 사용됨.

### 6.2 지침서 검증 (brief_validator)

`validate_brief()` — LLM 0.

- `_check_points_mismatch`: `shared_with` 비어있지 않거나 numeric 합이 만점과 ±1 이내 일치 시 null 항목을 정성평가로 인정 (영등포 false positive 차단). 단순 `points is None → missing` 로직은 사용하지 않음.
- `requirements`가 dict가 아니면 `{}` 교체 (LLM 배열 반환 방어).
- `brief_checklist_exporter._form_area_pages()`가 `[서식 N] …면적표` 제출양식 오분류 페이지를 면적 집계에서 제외 (본문 면적표 중복 차단).

### 6.3 테스트 커버리지

**백엔드 테스트 스위트:** `backend/tests/`, 총 581건 (pytest 확인, 2026-07-15). arch-law 연동은 `test_arch_law_client.py`(20, 네트워크 0 — ⚠mock 은 실제 응답 형태로: applicable_reviews dict·높이_일조.pass null·law_refs), 대지·법 렌더는 `test_brief_pipeline.py`(TestSiteLawSection·TestSiteLawXlsx)·`test_brief_proposal_report.py`(법적 골격 패널·다부지·조문 각주).

| 테스트 파일 | 케이스 수 | 주요 커버리지 |
|------------|----------|-------------|
| `test_quant_validator.py` | 19 | quant_validator 규칙 + TestPatternBuilderExcludesFlagged |
| `test_feasibility_export.py` | 46 | feasibility_export 전체 |
| `test_hwpx_loader.py` | 22 | HWP/HWPX 파싱 (rhwp monkeypatch) |
| `test_brief_proposal_report.py` | 27 | 제안서 HTML 렌더 |
| `test_pure_functions.py` | N/A | parse_json_response, merge_extracted_data, _compute_gap_analysis, to_grade, validate_brief (TestBriefValidatorPointsMismatch 15케이스 포함) |
| `test_normalize_design_grouped.py` | 13 | design_guidelines_grouped 정규화 |
| `test_proposal_number_check.py` | 11 | 수치 검산 |
| `test_vworld_analyzer.py` | 8 | 기하/bbox 수학 (네트워크 0) |
| `test_reference_cases.py` | N/A | reference_cases 참고 사례 조회 |
| `test_brief_advisor.py` | N/A | brief_advisor |
| `test_brief_pipeline.py` | N/A | TestToHtml 포함 |
| `test_tier0_routing.py` | N/A | Tier 0 라우팅 |

**별도 실행 (repo-root):** `tests/test_docx_extractor.py` (10건, backend 393에 미포함). 실행: `backend/venv/Scripts/python.exe -m pytest tests/test_docx_extractor.py`.

**알려진 사전 실패:** `test_force_cut_31_paragraphs` (docx_loader F3 force-cut 미발동, brief 전용, 미해결).

---

## 7. 프론트엔드

### 7.1 탭 구성

`App.jsx`의 `TABS` 배열 (총 7개, 이 순서 고정):

| 순번 | id | label | 컴포넌트 |
|------|-----|-------|---------|
| 1 | myproject | 내 프로젝트 등록 | MyProjectMode |
| 2 | accumulate | 경쟁 공모 등록 | AccumulateMode |
| 3 | crosscompare | 교차 비교 | CrossCompareMode |
| 4 | diagnose | 제안서 진단 | DiagnoseMode |
| 5 | settings | 설정 | SettingsPanel |
| 6 | archive | 아카이브 검색 | ArchiveMode |
| 7 | brief | 지침서 분석 | BriefMode |

기본 활성 탭: `'myproject'` (useState 초기값). 라우터 라이브러리 없음, 단순 조건부 렌더링.

전체 앱 트리 래핑 순서: `<MetaProvider>` → `<ApiKeyGate>` → 탭 콘텐츠.

도움말 모달: `<iframe src='/api/readme'>` (fixed 오버레이, zIndex 1000).

PyWebView 통합: `target='_blank'` 링크 클릭 시 `window.pywebview.api.open_external(href)` 호출 (API 존재 시) (추정: PyInstaller 데스크톱 빌드용).

### 7.2 API 클라이언트

**API 기반 URL:** `BASE = '/api'` (client.js), 상대 경로 (Vite dev proxy → localhost:8000, 운영에서는 동일 오리진 (추정)).

**API 키 저장:** localStorage key `'anthropic_api_key'`. 함수: `getStoredApiKey()`, `setStoredApiKey(key)`, `clearStoredApiKey()`, `hasStoredApiKey()`. LLM 호출 함수들은 `X-Anthropic-Api-Key` 헤더로 전송.

**청크 업로드 임계:** `25 * 1024 * 1024` bytes (25MB). 미만은 FormData 직접, 이상은 `chunkUpload(file)` → `file_ref` 문자열 치환.

**SSE 스트리밍:** `streamSSE(url, formData)` 는 async generator. ReadableStreamReader로 스트림 읽기, `data: ` 접두사 행을 JSON 파싱 후 yield. HTTP 401 시 사용자 친화적 API 키 오류 throw.

**주요 API 함수 목록:**
- 프로젝트 관리: `getProjects`, `getPattern`, `rebuildPattern`, `addSubmission`, `runAccumulatePipeline`, `rerunCompare`, `rerenderReport`, `getSubmission`, `updateSubmission`
- 진단: `runDiagnosePipeline`, `runDiagnoseVsProjects`, `listDiagnosisReports`, `getDiagnosisReportUrl`
- 지침서: `runBriefAnalyze`, `listBriefs`, `getBriefExportUrl`, `reinterpretBrief`, `analyzeSite`, `getBriefSiteImageUrl`, `getBriefSiteContext`, `proposeBrief`
- 검색/교차: `listArchive`, `searchArchive`, `getArchiveDetail`, `crossCompare`, `listCrossCompareReports`
- 설정: `getSettings`, `updateSettings`, `setDbPath`, `getFacilityTypes`, `getMeta`
- 리포트 URL 반환: `getReportUrl`, `getSubmissionReportUrl`, `getMyProjectDeepReportUrl`, `getCrossCompareReportUrl`
- MyProject: `runMyProjectPipeline`

### 7.3 스타일 시스템

**단일 소스:** `frontend/src/kunwon-tokens.css` (화이트 테마 + 건원 RED `#e60012`). `main.jsx`에서 전역 import.

컴포넌트는 인라인 스타일에서 `style={{ color: 'var(--color-accent)' }}` 패턴 사용. hex 직접 사용 금지. 신규 색 필요 시 `kunwon-tokens.css`에 추가.

**useMeta 훅 (`frontend/src/hooks/useMeta.jsx`):**
- `MetaContext` + `MetaProvider` 구현. 마운트 시 `getMeta()` 1회 fetch.
- 노출 인터페이스: `ready`, `facilityLabel(key)`, `facilityGroup(key)`, `facilityTypes`, `pageTypeLabel(key)`, `axesFor(facility_type)`, `axisLabel(facility_type, axis_key)`.
- `GET /api/settings/meta`가 단일 소스. 하드코딩 금지.

**자체완결 리포트 HTML:** 독립 문서(프론트 `kunwon-tokens.css` 못 씀) — **`report_theme.py::THEME_VARS` 단일 소스**(건원 RED + 명조/Montserrat)를 7개 generator(비교·진단·개별·MyProject·제안서·플레이북·체크리스트)가 `inject_theme()`(`/*__THEME__*/` 마커, 없으면 예외) 또는 prepend로 주입. 색·폰트는 `var(--accent)` 등 공유 토큰 참조, 레이아웃 CSS만 각자 보유. LLM 텍스트는 `html.escape` 필수. 진단·비교 리포트는 `report_badges`(AI 해석 배지=`var(--ai)`)로 사실/추론 구분, 경고 밴드는 `report_theme.warning_band` 공용 shell(`citation_check`·`quant_validator` 공유).

**등급 색상 (`grade_helpers.py::GRADE_COLORS`):**
- A: 전경 `#16a34a`, 배경 `#dcfce7`
- B: 전경 `#0891b2`, 배경 `#cffafe`
- C: 전경 `#ca8a04`, 배경 `#fef3c7`
- D: 전경 `#ea580c`, 배경 `#fed7aa`
- E: 전경 `#dc2626`, 배경 `#fee2e2`

---

## 8. 운영 규칙 및 제약

### 8.1 파일 저장 규칙 (GCSFUSE 대응)

운영 스토리지는 GCSFUSE (GCS 버킷 마운트)이므로 Python의 일반 파일 쓰기는 GCS에 플러시를 보장하지 않습니다. **모든 신규 파일 저장 함수는 반드시 다음 두 원시 함수 중 하나를 사용해야 합니다:**

- **`_atomic_write(path, data)`:** `.tmp` 파일에 쓰기 → `fsync` → `rename`. JSON 저장에 사용. 크래시 내성(partial write 없음).
- **`_sync_write(path, text)` / `_sync_write_bytes(path, bytes)`:** 타겟 경로에 직접 쓰기 + `fsync`. HTML/xlsx 저장에 사용. (추정: rename 없어 크래시 시 부분 파일 가능성 있음)

**Windows 로컬 개발에서 fsync:** Python `os.fsync()`는 Windows에서 `FlushFileBuffers()`로 매핑. POSIX `rename()`의 원자성 보장과 동일하지 않으므로 Windows 로컬 환경에서의 데이터 안전성은 Linux/GCS 수준보다 낮음 (추정).

**패키지 동기화:** 신규 Python 패키지는 `requirements.txt` + `requirements-server.txt` 양쪽에 추가 필수 (Dockerfile은 `requirements-server.txt` 사용). OCR 전용은 `requirements-ocr.txt`에만. `rhwp-python`은 양쪽 + `Dockerfile ENV LD_PRELOAD=/lib/x86_64-linux-gnu/libfreetype.so.6` 동반 필수.

**리포트 생성 규칙:** `report_generator.py`, `submission_report_generator.py`, `diagnosis_report_generator.py`, `myproject_report_generator.py`, `brief_proposal_report_generator.py`는 모두 Claude API 호출 금지. 기존 JSON 데이터를 HTML로 렌더링만.

### 8.2 API 키·보안

- **API 키 전달:** HTTP 헤더 `X-Anthropic-Api-Key`로 매 요청 전송. 세션 쿠키/토큰 없음.
- **API 키 우선순위:** asyncio ContextVar (per-request) → 세션 메모리 → `ANTHROPIC_API_KEY` 환경변수.
- **API 키 영속화 금지:** `app_settings.json`에 `anthropic_api_key` 키가 있어도 로드 시 자동 제거 (config.py line 860). `update()` 메서드도 API 키 변경 차단.
- **API 키 정제 (`_sanitize_api_key()`):** UTF-8 BOM (`﻿`), zero-width 문자 (8203, 8204, 8205, 8288), 선두 `-n ` shell 아티팩트, 양쪽 따옴표 제거. 메모장/PowerShell `Set-Content -Encoding utf8`으로 저장 시 BOM이 붙어 httpx 헤더 ASCII 인코딩 `UnicodeEncodeError` 발생.
- **VWorld API 키:** `VWORLD_API_KEY` 환경변수 전용. `app_settings.json` 미지원.
- **커밋 금지 파일:** `service.yaml` (Cloud Run 시크릿 평문 포함), `gcp-sa-key.json`, `.env`, `env.yaml`. `.gitignore` 필수.
- **인증/접근 제어:** 현재 로그인 시스템 없음. 의도적 보류 (MEMORY.md security posture). 재개 시 앱 비밀번호 vs Google IAP 검토 필요.

### 8.3 알려진 한계

**PDF 크기 제한:** 단일 파일 최대 200MB (`_MAX_PDF_BYTES`). DOCX/HWP/HWPX는 50MB (`_MAX_DOCX_BYTES`). 초과 시 HTTP 400.

**no 관계형 DB:** `list_submissions()`는 submissions/ 디렉터리의 모든 .json 파일을 매 호출마다 읽음. `list_projects()`는 모든 시설유형 디렉터리를 순회. 프로젝트 수 증가에 따라 성능 선형 저하 (추정).

**경쟁 ID 충돌:** `make_competition_id()` = `{slugify(project_number)}_{slugify(name)}`. 동일 slugify 결과 생성 시 데이터 덮어씀.

**결과 변경 시 파일 불일치:** `update_submission()`이 결과(result) 변경 시 `{stem}_report.html`은 rename하지만 `{slug}_{result}_deep.json` / `{slug}_{result}_deep.html`은 rename하지 않음 → MyProject deep analysis 파일 고아 발생 가능.

**page_taxonomy.json 갱신:** `init_db()`는 파일이 없을 때만 생성. 현재 파일에는 재건축 전용 7개 타입이 누락됨. 갱신 방법: 파일 삭제 후 백엔드 재시작.

**아카이브 인덱스 휘발:** FTS5 인덱스는 in-memory — 프로세스 재시작 시 소실, 재구축 필요. `check_same_thread=False` 필수.

**CORS 전 오리진 허용:** `allow_origins=['*']` — 어떤 웹사이트에서도 API 호출 가능. 의도적 설계 (per-browser API 키 모델)이나 서버 측 접근 제어 없음.

**OCR 의존성:** Tier 1 OCR 경로는 PaddleOCR 설치 필요 (`requirements-ocr.txt`). 미설치 시 Tier 1 스킵 후 Tier 2(vision) 폴백 (추정).

**대지·법 연동 내재 한계 (외부 앱 소관, 수정 불가):**
- **터읽기 measured = 시군구 평균** (proximity="시군구") — 대지 고유 형상·방위 없음. 방위 근거는 오직 VWorld vision.
- **arch-law 모드 A(용량)** — brief 는 허용 한도만 주고 설계 산출물(건축면적·층수) 없어 최대 매스 역산. `floors_above` 추정(층고 4m), `north_setback_m`·`road_height_limit_m` 지역·고시에 따라 null 흔함(정북은 `shadow_min_setback_m` 필요이격이 실신호), 건폐/용적 pass 는 한도맞춤이라 항상 true(가치는 limit 값·정북·가로구역·심의·mismatch).
- **주소 의존** — feasibility 에 주소 없으면(부지 테이블 없는 청사류 등) 대지·법 전부 skip. `site_address` 선택 입력으로 사용자 고정 가능(단 부지 테이블 없으면 envelope 없어 law skip).
- **지연** — 진단 부지당 65~110초(외부 엔진). 부지별 병렬·전 단계 graceful 이나 분석 시간 증가.

---

## 9. 미결·보류 사항

**당면 TODO (2026-07-14 기준):** 대지·법 연동 대작업 완료 — arch-law-diagnose 되받기(Phase 2, prod 활성)·arch-law-graph 조문 원문(Phase 3)·터읽기 실측·다부지 부지별 분석·선택 대지 주소·`include_proposal` 토글·체크리스트 대지·법 섹션·placement_strategy(부지별 다이어그램). 시퀀스 E Phase 3(매거진 덱)도 완료(2026-07-13). 남은 것: SketchUp MCP 3D 매스(F-③)와 내재적 한계(§8.3).

**보류 시퀀스:**

| 시퀀스 | 내용 | 보류 사유 |
|--------|------|----------|
| B — 추출 정확도 평가 하네스 | `tools/eval/` B-2까지 구현. 다음: B-3 CI 통합. | 제안서 PDF 5건 + ground_truth JSON 미확보 |
| C — 멀티파일 지침서 업로드 | 1파일 안정화 완료. 접근 A(multi-file 동시 분석) 권장. | 충돌 우선순위 룰(지침서 vs 과업지시서 중복 시 우선순위) 사용자 결정 필요 |
| D — 오프라인/제로-API 지침서 분석 | Claude Code가 classify/extract 핸드오프 수행. DOCX/HWP/HWPX 텍스트 기반이라 최적. | 배포 앱 불가(Cloud Run은 API만 가능), PDF는 vision 필요, 소량 수동 전용 |
| ~~E Phase 3 — 수주 제안서 매거진형 덱~~ **✅ 완료 (2026-07-13)** | `to_proposal_html()` 매거진화(명조+Montserrat·흰 페이퍼)+결정 요약 cockpit+권장 종합안+입찰 2층 배점. | 후폴로우: 섹션별 takeaway 한 줄·본문 축약 |
| F-③ — SketchUp MCP 3D 매스 | 시퀀스 F 대지분석 통합의 3D 매스 시각화. 위성+지적도 하이브리드 이미지는 이미 완료. | 사용자가 자료 줄 때 재개 |

**시스템 제약 미해결:**
- `test_force_cut_31_paragraphs`: docx_loader F3 force-cut 미발동 (brief 전용, 원인 미규명).
- 하안주공·public-a 수치 추출 오류: 추출 시점 정합성 검증 미완 (data_health.py 감사에서 HARD 결함 적발).
- `diagnose.py` SSE 이벤트의 `_timestamp` 누락 (brief SSE와 불일치, 수정 필요).
