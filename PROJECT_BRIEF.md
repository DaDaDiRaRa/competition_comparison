# BRIEF: 설계공모 경쟁분석 (Competition Analyzer) v1.0.0

> Claude Skill 타입 — 공모지침서 PDF → 구조화 JSON 변환
> 채우는 방식: `<FILL: ...>` 자리에 최신화된 내용을 덮어쓰기

---

## 1. META

```yaml
app_name: competition-analyzer
korean_name: 설계공모 경쟁분석
version: v1.0.0
type: Claude Skill
target_user: 설계사업6본부 설계팀
problem_solved: 공모 제안서 수작업 분류·비교·진단을 Claude AI로 자동화
core_value_proposition: PDF 제안서 → 페이지 분류 + 항목 추출 → 당선 패턴 축적 → 신규 제안서 자동 진단
status: 배포
deployment_path: competition-analyzer/backend/dist/CompetitionAnalyzer/CompetitionAnalyzer.exe
maintainer: DaDaDiRaRa
last_updated: 2026-05-12
```

---

## 2. SCHEMA_DEFINITION

출력 JSON 최상위 구조 (최신 스키마로 덮어쓰기)

```
- meta:
    - source_pdf: 원본 PDF 파일명
    - total_pages: 전체 페이지 수
    - analyzed_at: ISO 8601 타임스탬프
- pages_by_type:
    - <PAGE_TYPE>: [page_numbers]  # 분류된 페이지 번호 목록
- extracted_data:
    - site: 위치도 추출 데이터 (list of dicts, _page 필드 포함)
    - area_table: 면적표 추출 데이터 (list)
    - concept: 컨셉 추출 데이터 (list)
    - technical: 구조·설비 추출 데이터 (list)
    - sustainability: 친환경 추출 데이터 (list)
    - floor_plan: 평면도 추출 데이터 (list)
    - section: 단면도 추출 데이터 (list)
    - elevation: 입면도 추출 데이터 (list)
- _quantitative: merge_extracted_data() 자동 집계 — AREA_TABLE 우선, SITE_PLAN 보완
```

---

## 3. PAGE_TYPE_TAXONOMY

총 27개 유형 (일반 20 + 재건축 전용 7)

```
# 일반 유형 (20개)
- COVER               : 표지 — 공모명·제출자 식별
- TOC_HERO            : 목차 — 섹션 구성 파악
- SITE_CONTEXT        : 위치도 — 대지 위치·주변 맥락
- CONCEPT             : 컨셉 — 설계 철학·핵심 아이디어
- SPECIAL_SPACE       : 핵심공간 — 주요 특화 공간 계획
- RENDERING_EXT       : 외부투시도 — 건물 외관 시각화
- RENDERING_INT       : 내부투시도 — 내부 공간 시각화
- SITE_PLAN           : 배치도 — 대지 내 건물 배치·면적 정보
- LANDSCAPE           : 조경 — 외부 공간·녹지 계획
- FLOOR_PLAN          : 평면도 — 층별 공간 구성
- SECTION             : 단면도 — 수직 단면·층고 정보
- ELEVATION           : 입면도 — 외벽 입면 계획
- CIRCULATION         : 동선도 — 보행·차량·피난 동선
- HEALTH_CENTER       : 방재 — 소방·피난 계획
- TECHNICAL           : 구조·설비 — 구조 시스템·기계설비
- AREA_TABLE          : 면적표 — 건축면적·연면적·용적률·건폐율
- SUSTAINABILITY      : 친환경 — 에너지·녹색건축 인증
- UNIT_PLAN           : 단위세대 — 주거 단위세대 평면
- INCENTIVE_TABLE     : 인센티브표 — 용적률·높이 인센티브 산정표
- BRANDING            : 브랜딩 — 브랜드 아이덴티티·네이밍

# 재건축·대안설계 전용 유형 (7개)
- BUSINESS_VIABILITY  : 사업성 — 조합원 분담금·분양가·수익성
- AREA_INCREASE       : 면적증가 — 전용면적 증가·확장 계획
- VIEW_ANALYSIS       : 조망분석 — 조망권·일조 시뮬레이션
- COMMUNITY_PROGRAM   : 커뮤니티 — 커뮤니티 시설·프로그램
- COMPANY_PORTFOLIO   : 회사실적 — 시공사·설계사 실적
- CONSTRUCTION_PLAN   : 시공계획 — 공정·공법·공사비
- UNIT_PLAN_PENTHOUSE : 펜트하우스 — 펜트하우스 특화 세대 계획
```

---

## 4. EXTRACTION_FIELDS

```
- site:
    - location          : 대지 주소 (시·구·동)
    - site_area         : 대지면적 (㎡)
    - zoning            : 용도지역·지구
    - accessibility     : 주변 교통·접근성
    - surrounding_context: 주변 건물·환경 맥락
- area_table:
    - building_area     : 건축면적 (㎡)
    - total_floor_area  : 연면적 (㎡)
    - floor_area_ratio  : 용적률 (%)
    - coverage_ratio    : 건폐율 (%)
    - building_height   : 건물 높이 (m)
    - floors_above      : 지상 층수
    - floors_below      : 지하 층수
    - parking_count     : 주차 대수
- concept:
    - keywords          : 핵심 컨셉 키워드 목록
    - massing_type      : 매스 구성 유형 (탑형·판상형·복합 등)
    - design_philosophy : 설계 철학 요약
    - spatial_concept   : 공간 구성 개념
- technical:
    - structure_system  : 구조 시스템 (RC·SRC·철골 등)
    - mechanical_system : 기계설비 계획
    - special_tech      : 특수 공법·기술
- sustainability:
    - certification     : 녹색건축·에너지 인증 등급
    - energy_grade      : 에너지 효율 등급
    - green_features    : 친환경 특화 계획
```

---

## 5. PROMPT_RULES

분류·추출 핵심 규칙 (태그/룰 기반으로만)

```
- RULE_001: 재건축 전용 페이지(BUSINESS_VIABILITY 등) 분류 신뢰도 < 0.65이면
            REDEV_FALLBACK 유형으로 안전 강등 — 오분류 방지
- RULE_002: 페이지 분류 = claude-haiku-4-5-20251001 @ 72 DPI (속도·비용 최적화)
            데이터 추출 = claude-sonnet-4-6 @ 120 DPI (OCR 품질·정확도 우선)
- RULE_003: 각 strength / weakness / recommendation 항목은 반드시 (p.N) 형식
            페이지 인용 포함 — 원문 검증 가능성 확보 + 환각 억제
- RULE_004: 정량 데이터(_quantitative)는 AREA_TABLE 추출값 우선,
            SITE_PLAN 보완 순서로 merge_extracted_data() 자동 집계
- RULE_005: 비교 분석 Pass 1에서 회사명·결과 라벨(win/lose) 제거 후 블라인드 채점
            → 앵커링·할로 효과 차단. Pass 2에서 실제 결과 공개 후 사후 분석
```

---

## 6. OCR_FALLBACK_STRATEGY

```
- digital_text_first    : PyMuPDF fitz.Page.get_text() 우선 — 벡터 PDF 텍스트 직접 추출
- ocr_trigger_condition : 이미지 전용 PDF 또는 스캔본 (텍스트 레이어 없음)
- image_render_fallback : PyMuPDF 래스터화 + Claude Vision (claude-sonnet-4-6) 이미지 분석
- accuracy_threshold    : 텍스트 기반 추출 우선; 이미지 분석은 Claude vision으로 보완
                          PaddleOCR 선택적 설치 (requirements-ocr.txt) — 기본 파이프라인 미포함
```

---

## 7. INPUT_OUTPUT_SAMPLE

```
- input_pdf            : TBD (실제 공모 PDF 샘플 미첨부)
- input_pages          : TBD
- output_json_size     : TBD
- output_sample_path   : TBD
- processing_time      : TBD
```

---

## 8. ACCURACY_METRICS

```
- page_classification_accuracy : TBD
- field_completion_rate        : TBD
- false_positive_rate          : TBD
- test_sample_count            : TBD
- known_failure_modes          : 이미지 전용 스캔 PDF(텍스트 레이어 없음) / 비표준 면적표 레이아웃 /
                                  재건축·일반 혼합 공모 오분류
```

---

## 9. INVOCATION_FLOW

```
[사용자: PDF 업로드 + 시설유형·공모명 입력]
    ↓
[경쟁 공모 등록 탭 — 지침서 PDF(선택) + 제출물 PDF 업로드]
    ↓
[FastAPI 백엔드 SSE 스트리밍 — 진행 로그 실시간 표시]
    ↓
[PDF 파싱: PyMuPDF digital text → Claude Vision fallback]
    ↓
[페이지 분류 (27개 유형) — claude-haiku @ 72 DPI]
    ↓
[항목별 데이터 추출 — claude-sonnet @ 120 DPI]
    ↓
[{facility_type}/{competition_id}/submissions/{company}.json 저장]
    ↓
[사용자: "비교분석 실행" → 2-pass 블라인드 비교 + 패턴 축적 + 리포트 생성]
    ↓
[Output: _comparison.json + _report.html]
```

---

## 10. DOWNSTREAM_USAGE

후속 스킬/도구 연결 구조

```
- submission-analysis  : 경쟁 공모 등록 → 제출물 JSON → 교차비교(CrossCompareMode)
                          입력: facility_type + competition_id 조합 선택
                          호환 필드: extracted_data, _quantitative, pages_by_type
- winner-pattern       : 비교분석 실행 후 당선·낙선 패턴 자동 축적
                          입력: {company}_win.json / {company}_lose.json
                          호환 필드: _quantitative, pages_by_type, concept_keywords
- diagnose             : 신규 제안서 vs 당선 패턴 + 낙선 패턴 AI 진단
                          입력: submission PDF + facility_type (패턴 DB 참조)
                          출력: overall_grade(A-E) + 평가축별 강약점 + 보강 포인트
```

---

## 11. SCREENSHOTS

```
# 스크린샷 미첨부 — 추후 추가
- /screenshots/01_accumulate_upload.png  : 경쟁 공모 등록 탭 — PDF 업로드 화면
- /screenshots/02_progress_log.png       : 실시간 진행 로그 (▓░ 바 + 경과 시간)
- /screenshots/03_comparison_report.png  : HTML 비교 리포트 — 블라인드 순위 + 평가축 카드
- /screenshots/04_diagnose_result.png    : 제안서 진단 결과 — 정량 비교 바 3행
- /screenshots/05_pattern_viewer.png     : 설정 탭 패턴 뷰어 — 당선/낙선 통계 이중 바
```

---

## 12. CHANGELOG

```
- v1.0.0 (2026-05-12): 최초 배포 — PyInstaller + PyWebView 데스크톱 앱
                        경쟁 공모 등록 / 교차 비교 / 제안서 진단 / 패턴 뷰어
                        2-pass 블라인드 채점 + gap_analysis alignment 시각화
                        27개 페이지 유형 / 14개 시설 유형 (일반·재건축 2그룹)
                        5단계 등급 (A/B/C/D/E) + 당선·낙선 패턴 대비 진단
```

---

## 13. PRESENTATION_HOOKS

PPT 발표 시 강조 포인트 (각 항목이 슬라이드 1장 후보)

```
- HOOK_1            : PDF 업로드 → 27개 유형 자동 분류 → 항목 추출 → JSON 저장
                       (수작업 검토를 AI 파이프라인으로 대체)
- HOOK_2            : 2-pass 블라인드 채점 — 회사명·결과 숨긴 채 AI 순위 결정
                       → 앵커링·할로 효과 제거 → 객관적 강약점 도출
- HOOK_3            : 당선 패턴 DB 자동 축적 → 신규 제안서 즉시 진단
                       → 평가축별 A-E 등급 + 보강 포인트 제시
- BEFORE_AFTER      : 수동 검토 약 4시간/건 → 자동 추출 10분/건 + 비교분석 2분/건
- TEAM_ASSET_PLAN   : 설계사업6본부 표준 경쟁분석 도구 → 공유 DB 누적
                       → 공모 유형별 당선 패턴 학습 → 팀 경쟁력 내재화 로드맵
- LIVE_DEMO_SCENARIO: 공모 PDF 업로드 → 진행 로그 실시간 확인 →
                       비교 리포트 열기 → 평가축 카드 설명 → 진단 탭 시연
```
