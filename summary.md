# 설계공모 경쟁분석 앱 — Summary

---

## 앱 개요

**앱 이름:** 설계공모 경쟁분석 (Competition Analyzer)

**목적:** 건축 설계공모 제출 PDF를 Claude AI로 분석해 제출물 간 비교·평가·진단을 자동화하는 도구.

**주요 사용자:** 건축 설계사(건원) 내부 담당자. 설계공모 제출물을 사전 검토하거나, 당선/낙선 제출물 데이터를 축적해 다음 공모 전략을 수립할 때 사용.

**사용 맥락:** 사내 Windows PC에서 데스크톱 앱으로 실행(PyInstaller 빌드) 또는 Google Cloud Run에서 웹 앱으로 접근. DB는 로컬 `M:\` 네트워크 드라이브 또는 GCS 버킷에 저장.

---

## 기술 스택

### 백엔드
| 항목 | 내용 |
|------|------|
| 언어 | Python 3.10+ |
| 웹 프레임워크 | FastAPI 0.115+ |
| ASGI 서버 | uvicorn (standard) |
| AI 연동 | Anthropic API (`https://api.anthropic.com/v1/messages`) |
| PDF 처리 | PyMuPDF (fitz) — 래스터화, 텍스트 추출 |
| 이미지 처리 | Pillow |
| 데스크톱 창 | PyWebView 5.0 (EdgeChromium WebView2) |
| 데이터 검증 | Pydantic v2 |
| 비동기 파일 I/O | aiofiles, anyio |
| 수치 연산 | numpy (패턴 통계) |
| 선택 의존성 | PaddleOCR (이미지 기반 PDF OCR, `requirements-ocr.txt`) |

### 프론트엔드
| 항목 | 내용 |
|------|------|
| 언어 | JavaScript (ES modules) |
| UI 프레임워크 | React 18.3 |
| 빌드 도구 | Vite 5.4 |
| 스타일 | 인라인 스타일 + CSS 변수 (`kunwon-tokens.css`) |
| 상태 관리 | React Context (`MetaProvider`) + 로컬 컴포넌트 상태 |
| 통신 | Fetch API + Server-Sent Events (SSE) |
| 외부 UI 라이브러리 | 없음 (순수 React) |

### 배포
| 항목 | 내용 |
|------|------|
| 데스크톱 | PyInstaller `--onedir` + PyWebView |
| 웹 서버 | Docker (multi-stage) + Google Cloud Run gen2 |
| 스토리지 | Google Cloud Storage (GCS 버킷 마운트 `/data`) |
| 비밀 관리 | GCP Secret Manager (`anthropic-api-key`) |
| 이미지 레지스트리 | Artifact Registry (`asia-northeast3`) |

### 외부 API
- **Anthropic Claude API** — 페이지 분류(Haiku), 데이터 추출/비교/진단(Sonnet). 모든 호출은 `services/llm_client.py::call_messages()`를 통해 단일화.

---

## 핵심 기능 목록

### 1. 데이터 축적 (Accumulate)
- **PDF 업로드 및 페이지 분류** — 지침서(brief) PDF + 제출물 PDF를 업로드하면 페이지를 27개 유형으로 분류
  - `routers/accumulate.py::run_pipeline()` → `services/page_classifier.py::classify_all_pages()`
  - Claude Haiku 사용, 72 DPI, 배치 크기 5
- **구조적 데이터 추출** — 페이지 유형별 스키마로 설계 정보 추출 (면적표, 컨셉, 배치도 등)
  - `services/data_extractor.py::extract_pdf()` → Claude Sonnet, 120 DPI
  - AREA_TABLE·TECHNICAL 페이지는 2×2 타일 분할로 OCR 정밀도 향상
- **단일 제출물 즉시 리포트** — 추출 완료 즉시 개별 제출물 HTML 리포트 자동 생성 (LLM 미호출)
  - `services/submission_report_generator.py::generate_submission_report()`
- **청크 업로드** — 대용량 PDF를 분할 업로드해 서버에 임시 저장 후 병합
  - `routers/upload.py`, `api/chunkUpload.js`

### 2. 비교분석 (Compare — 2-pass Blind-Reveal)
- **Pass 1 블라인드 채점** — 회사명을 A안/B안/... 으로 익명화, 당선/낙선 결과 라벨 제거 후 LLM이 결과를 모른 채 평가축별 A~E 등급 부여
  - `services/comparator.py::compare_submissions()` → `_anonymize_submissions()` → LLM
  - `max_tokens=32000`, 프롬프트 캐싱 적용
- **Pass 2 리빌 분석** — 실제 회사명·결과 공개 후 차별화 요인·당선 강점·낙선 원인 사후 분석
  - Pass 1 결과만 전달 (원본 데이터 재전송 없음) → 입력 토큰 80%+ 절감
  - `max_tokens=4096`
- **Gap Analysis** — 블라인드 1위와 실제 당선이 일치하는지 `alignment: "high"|"partial"|"low"` 판정 (결정적 로직, LLM 환각 없음)
  - `_compute_gap_analysis()`
- **비교 리포트 HTML 생성** — LLM 미호출, 기존 JSON에서 렌더링
  - `services/report_generator.py::generate_comparison_report()`

### 3. 진단 (Diagnose)
- **패턴 기반 진단** — 축적된 당선 패턴(평균±표준편차)과 내 제출물 비교, 낙선 패턴과의 거리도 경고
  - `routers/diagnose.py::run_diagnosis()` → `services/comparator.py::diagnose_submission()`
- **선택 공모 기반 진단** — 사용자가 참조 공모를 직접 선택해 ad-hoc 패턴 생성 후 진단
  - `routers/diagnose.py::run_diagnosis_vs_projects()` → `services/pattern_builder.py::build_pattern_from_submissions()`
- **진단 리포트 HTML 생성** — 종합점수 링, 페이지 구성 바, 패턴 편차 경고, 지침서 충족도, 축별 상세
  - `services/diagnosis_report_generator.py::generate_diagnosis_report()`

### 4. 패턴 관리 (Patterns)
- **자동 패턴 구축** — 시설 유형별 당선·낙선 제출물 JSON 전체를 집계해 페이지 분포 통계, 정량 지표 평균, 컨셉 키워드 빈도 산출
  - `services/pattern_builder.py::build_pattern()`
- **질적 인사이트 요약** — 상위 5개 당선 패턴·낙선 안티패턴·핵심 차별화 요인을 LLM이 요약 (Haiku)

### 5. 교차 비교 (Cross-Compare)
- **멀티 프로젝트 제출물 조합 비교** — 서로 다른 공모의 제출물을 임의로 선택해 비교분석 실행
  - `routers/accumulate.py::cross_compare()` → `{db_path}/_cross_reports/` 저장

### 6. 설정 관리 (Settings)
- **DB 경로 변경** — 로컬 경로 또는 네트워크 드라이브 경로 입력 후 즉시 `init_db()` 실행
- **API 키 관리** — 메모리에만 보관, 디스크 미저장. `ANTHROPIC_API_KEY` 환경변수 fallback
- **모델 ID·DPI 설정** — 분류/추출 모델 및 래스터화 DPI 개별 설정

### 7. 리포트 재생성
- **리렌더 (LLM 미호출)** — 기존 `_comparison.json`에서 HTML만 재생성. 리포트 디자인 변경 후 빠른 갱신
  - `POST rerender-report`
- **재비교 (LLM 재실행)** — 저장된 JSON으로 2-pass 비교 전체 재실행 (토큰 비용 발생)
  - `POST rerun-compare`

---

## 파일 구조

```
competition_comparison/
├── competition-analyzer/
│   ├── backend/
│   │   ├── main.py                          # FastAPI 앱 초기화, 라우터 마운트, SPA 서빙
│   │   ├── config.py                        # FACILITY_TYPES, PAGE_TYPES, COMPARISON_AXES, AppSettings 클래스
│   │   ├── launcher.py                      # PyWebView 진입점: uvicorn 스레드 + 네이티브 창
│   │   ├── version.py                       # 앱 버전 문자열
│   │   ├── app_settings.json                # 런타임 생성 사용자 설정 (DB 경로, DPI, 모델 ID)
│   │   ├── requirements.txt                 # Python 의존성 (FastAPI, PyMuPDF, anthropic 등)
│   │   ├── requirements-ocr.txt             # 선택 의존성 (PaddleOCR)
│   │   ├── competition_analyzer.spec        # PyInstaller 빌드 스펙
│   │   ├── routers/
│   │   │   ├── accumulate.py                # PDF 업로드·추출·비교·리포트 엔드포인트
│   │   │   ├── diagnose.py                  # 진단 실행·리포트 조회 엔드포인트
│   │   │   ├── patterns.py                  # 패턴 조회·재구축 엔드포인트
│   │   │   ├── settings.py                  # 설정·메타데이터 엔드포인트
│   │   │   └── upload.py                    # 청크 파일 업로드 핸들러
│   │   ├── services/
│   │   │   ├── llm_client.py                # Anthropic API 래퍼 (retry, prompt caching, 로그)
│   │   │   ├── page_classifier.py           # PDF 페이지 → 27개 유형 분류 (Haiku, 72 DPI)
│   │   │   ├── data_extractor.py            # 페이지 유형별 구조적 데이터 추출 (Sonnet, 120 DPI)
│   │   │   ├── comparator.py                # 2-pass 블라인드 비교 + 진단 로직
│   │   │   ├── db_manager.py                # JSON 기반 DB (프로젝트·제출물·패턴·리포트 관리)
│   │   │   ├── pattern_builder.py           # 당선·낙선 통계 집계 + LLM 질적 요약
│   │   │   ├── report_generator.py          # 비교 리포트 HTML 생성 (LLM 미호출)
│   │   │   ├── submission_report_generator.py  # 개별 제출물 HTML 리포트 생성
│   │   │   ├── diagnosis_report_generator.py   # 진단 결과 HTML 리포트 생성
│   │   │   ├── utils.py                     # PDF 래스터화, SSE 헬퍼, JSON 파서, 에러 메시지
│   │   │   └── pdf_rasterizer.py            # 레거시 래스터라이저 (미사용)
│   │   └── models/
│   │       └── schemas.py                   # Pydantic 스키마 (FacilityType, DiagnoseRequest 등)
│   └── frontend/
│       ├── package.json                     # React 18 + Vite 5 의존성
│       ├── vite.config.js                   # 개발 서버 프록시 설정 (/api/* → :8000)
│       ├── index.html                       # SPA 진입 HTML
│       └── src/
│           ├── main.jsx                     # React 루트 렌더링, kunwon-tokens.css 전역 import
│           ├── App.jsx                      # 5탭 레이아웃, PyWebView 링크 처리, README 모달
│           ├── kunwon-tokens.css            # 브랜드 CSS 변수 단일 소스 (건원 RED 액센트)
│           ├── theme.js                     # 색 토큰 참고용 JS 명세
│           ├── api/
│           │   ├── client.js               # 전체 백엔드 API 통신 함수 + SSE 헬퍼
│           │   └── chunkUpload.js          # 대용량 파일 청크 분할 업로드
│           ├── hooks/
│           │   └── useMeta.jsx             # MetaProvider + useMeta() — 시설유형·페이지타입·평가축 단일 소스
│           ├── constants/
│           │   └── index.js                # GRADE_COLOR, GRADE_BG, toGrade(), COMPLIANCE_COLOR
│           └── components/
│               ├── AccumulateMode/
│               │   ├── AccumulateMode.jsx          # PDF 업로드 폼 + SSE 진행 표시
│               │   ├── ProjectList.jsx             # 저장 프로젝트 카드 목록 (시설유형 탭 필터)
│               │   ├── ComparisonResult.jsx        # 비교 결과 (GapAnalysis + 등급 + 강약점)
│               │   └── ComparisonDashboard.jsx     # 비교 결과 대시보드 레이아웃
│               ├── MyProjectMode/
│               │   └── MyProjectMode.jsx           # 단일 제출물 등록 + 결과 기록
│               ├── DiagnoseMode/
│               │   ├── DiagnoseMode.jsx            # 진단 폼 (패턴 기반 / 프로젝트 선택)
│               │   └── DiagnosisResult.jsx         # 진단 결과 + QuantCompare 3행 바 차트
│               ├── CrossCompare/
│               │   └── CrossCompareMode.jsx        # 교차 비교 UI (여러 프로젝트 제출물 선택)
│               ├── SubmissionEditor/
│               │   └── SubmissionEditor.jsx        # 추출 데이터 수동 편집 모달
│               ├── Settings/
│               │   ├── SettingsPanel.jsx           # API 키·DB 경로·모델 설정 패널
│               │   └── PatternViewer.jsx           # 시설유형별 당선·낙선 패턴 통계 시각화
│               └── common/
│                   ├── ApiKeyGate.jsx              # API 키 미설정 시 입력 가드
│                   ├── DropZone.jsx                # 드래그앤드롭 파일 입력
│                   ├── ProgressLog.jsx             # SSE 실시간 진행 로그 (`▓░` 바 + 경과시간)
│                   └── PageDistChart.jsx           # 페이지 유형 분포 가로 바 차트
├── tools/
│   ├── change_theme.py                      # 색상 일괄 교체 (프리셋 또는 custom hex)
│   └── audit_tokens.py                      # 인라인 hex 하드코딩 감사 → DESIGN_AUDIT.md
├── build.ps1                                # 빌드 스크립트 (npm install → vite build → PyInstaller)
├── Dockerfile                               # Cloud Run 배포용 멀티스테이지 이미지
├── CLAUDE.md                                # 아키텍처·코드 룰 (Claude Code 자동 로드)
├── DEVELOPER.md                             # 개발자용 가이드 (빌드·배포·테마)
├── DEPLOYMENT.md                            # GCP Cloud Run 배포 가이드
├── GCP_CLOUDRUN_DEPLOY_GUIDE.md             # 재사용 가능한 Cloud Run 배포 상세 가이드
├── README.md                                # 사용자 매뉴얼
└── summary.md                               # 이 파일
```

### DB 구조 (런타임 생성)

```
{db_path}/
├── _config/
│   └── page_taxonomy.json                   # 페이지 유형 분류표
├── _patterns/
│   └── {facility_type}.json                 # 패턴 통계 (당선·낙선 분리)
├── _diagnosis_reports/
│   └── {YYYYMMDD}_{HHMMSS}_{ft}_{name}.html # 진단 HTML 리포트
├── _cross_reports/
│   └── {YYYYMMDD}_{HHMMSS}_{label}.html     # 교차비교 HTML 리포트
└── {facility_type}/
    └── {project_number}_{competition_slug}/
        ├── _meta.json                       # 프로젝트 메타 (이름·번호·발주처·위치·제출물 목록)
        ├── _brief.json                      # 지침서 추출 데이터
        ├── _comparison.json                 # 비교 결과 (rankings, grades, gap_analysis)
        ├── _report.html                     # 비교 HTML 리포트
        └── submissions/
            ├── {slug}_{result}.json         # 제출물 추출 데이터
            └── {slug}_{result}_report.html  # 개별 제출물 HTML 리포트
```

---

## 데이터 흐름

### A. 데이터 축적 파이프라인

```
[사용자]
  → PDF 업로드 (지침서 + 제출물 × N) + 메타데이터 폼
      ↓ POST /api/accumulate/run (SSE 스트림)
[page_classifier.py]
  → PDF → 72 DPI PNG → base64 → Claude Haiku
  → 각 페이지: {primary_type, secondary_type, confidence, key_elements}
      ↓
[data_extractor.py]
  → 페이지 유형별 추출 스키마 구성
  → PDF → 120 DPI PNG (AREA_TABLE은 2×2 타일) → base64 → Claude Sonnet
  → {concept, site_plan, floor_plan, area_table, ...} 구조적 JSON
  → merge_extracted_data() → _quantitative 자동 집계
      ↓
[db_manager.py]
  → _brief.json, submissions/{slug}_{result}.json 저장
  → submission_report_generator.py → {slug}_{result}_report.html 저장
      ↓
[클라이언트] SSE "complete" 이벤트 수신 → ProjectList에 프로젝트 표시
```

### B. 비교분석 파이프라인 (2-pass Blind-Reveal)

```
[사용자] ProjectList에서 "비교분석 실행" 클릭
  → POST /api/accumulate/{id}/rerun-compare (SSE 스트림)
      ↓
[db_manager.py] _brief.json + submissions/*.json 로드 (PDF 재처리 없음)
      ↓
[comparator.py::compare_submissions()]

  ▶ Pass 1 (블라인드 채점):
    _anonymize_submissions()
      {company: "건원" → "A안", result: "win" → 제거}
    LLM (Sonnet, 32000 tokens, cached):
      시설유형별 8개 평가축 × 각 제출물 → grade(A~E), strengths, weaknesses
    _deanonymize_blind_result() → 회사명 복원
    → blind_ranking 생성

  ▶ Pass 2 (리빌 분석):
    ACTUAL_RESULTS + BLIND_SCORES만 전달 (원본 데이터 재전송 없음)
    LLM (Sonnet, 4096 tokens, cached):
      key_differentiators, winner_strengths, loser_weaknesses, gap_notes
    _compute_gap_analysis() → alignment: "high"|"partial"|"low"
      ↓
[db_manager.py] _comparison.json 저장
[pattern_builder.py] 패턴 재구축 (당선+낙선 통계)
[report_generator.py] _report.html 생성 (LLM 미호출)
[submission_report_generator.py] 각 제출물 리포트 재생성
      ↓
[클라이언트] SSE "complete" → ComparisonResult 렌더링 + 리포트 링크 표시
```

### C. 진단 파이프라인

```
[사용자] 시설유형 + 지침서 PDF (선택) + 내 제출물 PDF
  → POST /api/diagnose/run (SSE 스트림)
      ↓
[db_manager.py] 시설유형별 패턴 로드 (당선 패턴 + loser_stats)
      ↓
[page_classifier.py] + [data_extractor.py]
  → 내 제출물 분류·추출 → _quantitative 집계
      ↓
[comparator.py::diagnose_submission()]
  LLM (Sonnet, cached):
    당선 패턴 vs 낙선 패턴 vs 내 제출물
    → axes (grade, strengths, weaknesses, recommendations)
    → overall_grade, brief_compliance, requirement_mapping
    → pattern_deviation (낙선 패턴 유사 항목 경고)
      ↓
[diagnosis_report_generator.py]
  → {ts}_{ft}_{name}.html 저장 (LLM 미호출)
      ↓
[클라이언트] SSE "complete": {result: diagnosis, report_filename: "..."}
  → DiagnosisResult 렌더링 (QuantCompare 3행 바: 당선/낙선/내 제출물)
  → "진단 리포트 열기" 버튼 표시
```

### D. Anthropic API 호출 전략 (토큰 비용 최적화)

| 단계 | 모델 | 토큰 상한 | DPI | 프롬프트 캐싱 |
|------|------|-----------|-----|---------------|
| 페이지 분류 | Haiku | 3,000 | 72 | 배치 5장 |
| 데이터 추출 | Sonnet | 8,000/페이지 | 120 | — |
| 비교 Pass 1 | Sonnet | 32,000 | — | 정적 prefix + 데이터 블록 |
| 비교 Pass 2 | Sonnet | 4,096 | — | 정적 prefix (재사용) |
| 진단 | Sonnet | 32,000 | — | 정적 prefix + 패턴 블록 |
| 패턴 요약 | Haiku | 2,000 | — | — |

- 프롬프트 캐싱: 5분 TTL, 캐시 히트 시 입력 토큰 90% 할인 / 캐시 쓰기 1.25× 비용
- rerun-compare 재실행 시 Pass 1 정적 prefix + 데이터가 캐시에 남아 대폭 절감

---

## 현재 한계 / 미완성 부분

### 기능 한계

1. **DB 동시 쓰기 불가** — JSON 파일 기반 DB는 파일 단위 원자적 쓰기는 지원하지만 진정한 트랜잭션이 없음. Cloud Run 배포 시 `max-instances=1` 강제 필요. 동시 사용자가 여럿이면 쓰기 충돌 가능.

2. **PDF 내 식별 정보** — 블라인드 비교에서 회사명은 익명화되지만 PDF 이미지 안의 로고·텍스트는 LLM에 그대로 노출됨. "완전한 더블블라인드"는 아님 (CLAUDE.md에 명시된 한계).

3. **교차 비교 프론트엔드 미완** — `CrossCompareMode.jsx`는 UI가 존재하지만 비교 결과 표시 컴포넌트가 `ComparisonResult.jsx`를 재사용하며, 교차 비교 특유의 시각화는 별도 미구현.

4. **PaddleOCR 미기본화** — 이미지 기반(텍스트 없는) PDF는 추출 품질이 저하되나 PaddleOCR은 선택 의존성. 기본 파이프라인(PyMuPDF + Claude vision)이 이미지만 처리.

5. **웹 배포 시 데이터 분리** — 데스크톱 앱(M:\ 드라이브)과 웹 앱(GCS 버킷)의 데이터가 별도 관리됨. 동기화는 수동 `gsutil rsync` 필요.

6. **패턴 편차 경고 가중치** — `pattern_deviation` 계산이 누락 페이지 유형을 감지하지만 정량적 가중치 없이 목록만 반환. 심각도 기준이 없음.

7. **구 데이터 자동 변환 미완** — `score`(0~10 숫자) → A~E 등급 변환 함수(`toGrade()`)가 프론트에 있지만, 매우 구버전 데이터(그룹화된 `grade: "상/중/하"`)는 일부 경로에서 처리 누락 가능.

### 코드 구조 한계

8. **`models/schemas.py` 미활용** — `DiagnosisResult`, `ComparisonAxis` 등 Pydantic 스키마가 정의되어 있으나 실제 라우터의 응답 타입 선언에 사용되지 않음. SSE 스트림 응답이라 런타임 검증이 없음.

9. **프론트 에러 처리 일관성** — SSE 에러 이벤트 처리가 컴포넌트별로 달라 일부는 에러 메시지를 UI에 표시하지 않고 콘솔에만 출력.

10. **테스트 코드 없음** — 백엔드·프론트엔드 모두 자동화 테스트 파일 없음. PDF 처리·LLM 호출·DB 쓰기 모두 수동 검증 의존.

11. **`change_theme.py` 미동기화** — 현재 브랜드가 건원 RED(`#e60012`)로 변경되었으나 `tools/change_theme.py`의 프리셋 목록은 구 navy/charcoal 등 옛 테마 기준으로 남아있음.

---

*생성일: 2026-05-22 | 분석 대상: competition-analyzer/backend + frontend 전체 소스*
