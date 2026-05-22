# Competition Analyzer — 앱 작동 방식 & 배포 가이드

---

## 1. 앱 개요

건축 설계공모 제안서(PDF)를 Claude AI로 분석해 당선/낙선 패턴을 비교·진단하는 도구입니다.

**주요 기능**

| 탭 | 기능 |
|----|------|
| 내 프로젝트 등록 | 우리 회사 제안서 단건 등록 + 결과(당선/낙선) 기록 |
| 경쟁 공모 등록 | 한 공모의 여러 회사 제안서를 한꺼번에 등록·비교분석 |
| 제안서 진단 | 새 제안서를 과거 당선 패턴과 대조해 강점·약점 진단 |
| 교차비교 | 다른 공모의 제안서끼리 임의 조합 비교 |
| 설정 | API 키·DB 경로·DPI 설정, 패턴 뷰어 |

---

## 2. 기술 스택

```
Frontend  React 18 + Vite  (브라우저 UI)
Backend   FastAPI (Python 3.12)  (AI 호출·PDF 처리·데이터 저장)
AI        Anthropic Claude  (claude-sonnet-4-6 / claude-haiku-4-5)
PDF       PyMuPDF(fitz)  (래스터라이즈)
DB        JSON 파일 기반  (별도 DB 서버 없음)
```

---

## 3. 데이터 흐름

### 3-1. 데이터 축적 파이프라인 (PDF → JSON)

```
사용자가 PDF 업로드
    │
    ▼
페이지 분류 (Haiku, 72 DPI)
  → COVER / FLOOR_PLAN / SECTION / RENDERING_EXT ... 27개 유형
    │
    ▼
유형별 데이터 추출 (Sonnet, 120 DPI)
  → 각 페이지를 전용 프롬프트로 구조화된 JSON으로 변환
  → 면적표·기술 페이지는 4분할 타일로 정밀 추출
    │
    ▼
JSON 저장
  {db_path}/{facility_type}/{competition_id}/
    ├── _brief.json          (지침서 데이터)
    ├── _meta.json           (공모 메타)
    └── submissions/
          ├── {회사명}_win.json
          └── {회사명}_lose.json
    │
    ▼
개별 제출물 리포트 자동 생성 → submissions/{slug}_report.html
```

> 추출 후 비교분석은 실행되지 않습니다. "비교분석 실행" 버튼을 별도로 눌러야 합니다.

---

### 3-2. 비교분석 파이프라인 (2-pass 블라인드 채점)

```
저장된 JSON 로드 (PDF 재처리 없음)
    │
    ▼
Pass 1 — 블라인드 채점 (Sonnet, max 32000 토큰)
  · 회사명 → A안/B안/C안 익명화
  · 결과(win/lose) 라벨 제거
  · LLM이 결과를 모른 채 8개 평가축별 등급(A~E) + 강약점 채점
  · blind_ranking 생성
    │
    ▼
Pass 2 — 리빌 분석 (Sonnet, max 4096 토큰)
  · 실제 회사명·결과 공개
  · Pass 1 결과만 전달 (원본 데이터 재전송 없음 → 토큰 80% 절감)
  · 차별화 요인·당선/낙선 원인 분석
  · gap_notes: 블라인드 1위와 실제 당선이 다른 이유 추론
    │
    ▼
gap_analysis 계산 (결정적 로직, LLM 없음)
  · alignment: high / partial / low / unknown
    │
    ▼
_comparison.json 저장 + 비교 리포트 HTML 생성
```

**평가축**

| 그룹 | 적용 시설 | 평가축 (8개) |
|------|-----------|-------------|
| redev | 재건축·대안설계 | 사업성, 조합원 혜택, 상품 경쟁력, 단지 계획, 커뮤니티, 디자인·브랜드, 시공성, 회사 역량 |
| general | 공공·주거·업무·교통 등 나머지 | 컨셉·아이덴티티, 대지 대응·맥락, 프로그램·기능, 건축 형태·매스, 공공성·이용자, 지속가능성, 기술·시공, 지침 충족·정량 |

---

### 3-3. 진단 파이프라인

```
새 제안서 PDF 업로드
    │
    ▼
페이지 분류 + 데이터 추출 (축적과 동일)
    │
    ▼
DB에서 해당 시설 유형의 당선·낙선 패턴 로드
    │
    ▼
1-pass 진단 (Sonnet)
  · 당선 패턴 vs 낙선 패턴 vs 내 제안서 비교
  · 평가축별 등급 + 강점·약점·개선 권고
  · 패턴 편차 경고 (낙선 패턴과 유사한 지표 강조)
    │
    ▼
진단 리포트 HTML 저장
  {db_path}/_diagnosis_reports/{날짜}_{시설유형}_{이름}.html
```

---

### 3-4. 대용량 PDF 업로드 (청크 업로드)

Cloud Run은 HTTP 요청을 32MB로 제한합니다. 25MB를 초과하는 파일은 자동으로 청크 업로드됩니다.

```
프론트엔드
  ├── 파일 < 25MB → 기존 방식 (단일 요청)
  └── 파일 ≥ 25MB → 청크 업로드
        POST /api/upload/start           → upload_id 발급
        POST /api/upload/chunk/{id}      → 20MB씩 분할 전송
        POST /api/upload/finish/{id}     → /tmp에서 조립
        파이프라인 완료 후
        DELETE /api/upload/cleanup/{id}  → 임시 파일 삭제
```

- 파일 1개 최대: 200MB
- 세션 합계 최대: 600MB

---

## 4. 파일 구조

```
competition_comparison/
├── frontend/               React + Vite
│   └── src/
│       ├── components/     AccumulateMode, DiagnoseMode, CrossCompare, Settings ...
│       ├── api/            client.js (SSE 통신), chunkUpload.js
│       └── hooks/          useMeta.jsx (시설유형·평가축 메타 단일 소스)
│
├── backend/                FastAPI
│   ├── main.py             앱 진입점, 라우터 등록
│   ├── config.py           시설유형·페이지유형·평가축 정의, AppSettings
│   ├── routers/
│   │   ├── accumulate.py   축적·비교분석·리포트 엔드포인트
│   │   ├── diagnose.py     진단 엔드포인트
│   │   ├── patterns.py     패턴 관리
│   │   ├── settings.py     설정·메타 엔드포인트
│   │   └── upload.py       청크 업로드
│   └── services/
│       ├── page_classifier.py        페이지 분류
│       ├── data_extractor.py         데이터 추출
│       ├── comparator.py             2-pass 비교분석·진단
│       ├── pattern_builder.py        당선·낙선 패턴 구축
│       ├── report_generator.py       비교 리포트 HTML
│       ├── submission_report_generator.py  개별 제출물 리포트 HTML
│       ├── diagnosis_report_generator.py   진단 리포트 HTML
│       ├── db_manager.py             JSON DB 읽기·쓰기
│       ├── llm_client.py             Claude API 호출 래퍼
│       └── utils.py                  PDF 래스터라이즈, JSON 파싱, SSE 헬퍼
│
├── Dockerfile              Cloud Run 배포용 컨테이너
└── .github/workflows/
    └── deploy.yml          GitHub Actions CI/CD
```

---

## 5. DB 구조

JSON 파일 기반 데이터베이스입니다. 별도의 DB 서버가 없습니다.

```
{db_path}/
├── {facility_type}/               예: reconstruction, public
│   └── {project_number}_{공모명}/
│       ├── _meta.json             공모 메타 (이름·발주처·위치 등)
│       ├── _brief.json            지침서 추출 데이터
│       ├── _comparison.json       비교분석 결과
│       ├── _report.html           비교 리포트 (인쇄·다운로드용)
│       └── submissions/
│           ├── {회사}_win.json
│           ├── {회사}_win_report.html
│           ├── {회사}_lose.json
│           └── {회사}_lose_report.html
├── _patterns/
│   └── {facility_type}.json       당선·낙선 패턴 통계
├── _diagnosis_reports/
│   └── {날짜}_{시설유형}_{이름}.html
└── _cross_reports/
    └── {날짜}_cross_{id}.html
```

---

## 6. 배포 방식 (Google Cloud Run)

**구조**

```
GitHub main 브랜치 push
    │
    ▼ (GitHub Actions)
Docker 이미지 빌드 (멀티스테이지)
  Stage 1: Node.js → React 빌드 (frontend/dist)
  Stage 2: Python 3.12 + FastAPI
    │
    ▼
Artifact Registry 푸시
  asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app
    │
    ▼
Cloud Run 배포
  리전: asia-northeast3 (서울)
  메모리: 2GB  /  CPU: 2코어  /  타임아웃: 3600초
  최대 인스턴스: 1개 (동시성 제한)
    │
    ▼
GCS 버킷 마운트
  kunwon-competition-db → /data (DB_PATH 환경변수)
  → JSON 파일이 Cloud Storage에 영구 저장됨
```

**환경변수**

| 변수 | 값 | 설명 |
|------|----|------|
| `DB_PATH` | `/data` | GCS 버킷 마운트 경로 |
| `PYTHONUNBUFFERED` | `1` | 로그 즉시 출력 |
| `ANTHROPIC_API_KEY` | (배포 시 제거) | 보안상 서버에 저장 안 함. 사용자가 UI에서 직접 입력 |

**API 키 정책**
- 서버에 API 키를 저장하지 않습니다.
- 사용자가 설정 탭에서 입력한 키는 서버 **메모리에만** 보관됩니다.
- 서버 재시작 시 초기화됩니다. (세션 종료와 동일)

---

## 7. 로컬 개발 환경 실행

```powershell
# 터미널 1 — 백엔드
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 터미널 2 — 프론트엔드
cd frontend
npm install   # 최초 1회
npm run dev   # http://localhost:5173 (→ /api/* 를 :8000으로 프록시)
```

**최초 설정 순서**
1. 백엔드·프론트엔드 기동
2. 브라우저에서 `http://localhost:5173` 접속
3. 설정 탭 → API 키 입력 → DB 경로 입력 (미입력 시 `~/CompetitionAnalyzerDB` 자동 사용)

---

## 8. 비용 구조 (AI 토큰)

| 작업 | 모델 | 비용 수준 |
|------|------|----------|
| 페이지 분류 | Haiku (저렴) | 낮음 |
| 데이터 추출 | Sonnet (고성능) | 중간 |
| 비교분석 Pass 1 | Sonnet, max 32000 토큰 | 높음 |
| 비교분석 Pass 2 | Sonnet, max 4096 토큰 | 낮음 (Pass 1의 20%) |
| 진단 | Sonnet, max 8192 토큰 | 중간 |
| 리포트 생성 | 없음 (LLM 호출 안 함) | 0 |

**프롬프트 캐싱**: 비교분석·진단 시 정적 블록에 `cache_control` 적용 → 재실행 시 입력 토큰 90% 할인.

**"리포트만 재생성" 버튼**: LLM 호출 없이 저장된 JSON에서 HTML만 재생성. 비용 0.
