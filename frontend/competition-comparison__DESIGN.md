# Frontend Design Spec

> 모든 값은 소스 파일에서 직접 추출. 마지막 업데이트: 2026-05-22

---

## 1. 색상 코드

### 기본 팔레트 (`theme.js` 기준)

| 역할 | 색상 코드 | 비고 |
|------|-----------|------|
| **앱 배경** | `#fafafa` | 전체 페이지 배경 |
| **패널 배경** | `#ffffff` | 카드·패널 배경 |
| **패널 배경 (alt)** | `#f9fafb` | hover, 보조 배경 |
| **입력 배경** | `#ffffff` | input, select |
| **입력 배경 (readonly)** | `#f3f4f6` | 비활성 입력 |
| **보더 (기본)** | `#e5e7eb` | 카드·패널 테두리 |
| **보더 (강조)** | `#d1d5db` | 강조 구분선 |
| **액센트 (주)** | `#334155` | 버튼·탭·배지 |
| **액센트 (hover)** | `#475569` | 액센트 hover 상태 |
| **액센트 (soft)** | `#f1f5f9` | 액센트 배경 tint |
| **액센트 텍스트** | `#ffffff` | 액센트 위 텍스트 |

### 텍스트

| 역할 | 색상 코드 |
|------|-----------|
| 본문 (primary) | `#1f2937` |
| 본문 (muted) | `#4b5563` |
| 본문 (faint) | `#6b7280` |
| 본문 (subtle) | `#9ca3af` |

### 등급 색상 (A–E)

| 등급 | 텍스트 | 배경 |
|------|--------|------|
| A (최우수) | `#16a34a` | `#dcfce7` |
| B (우수) | `#0891b2` | `#cffafe` |
| C (보통) | `#ca8a04` | `#fef3c7` |
| D (미흡) | `#ea580c` | `#fed7aa` |
| E (불량) | `#dc2626` | `#fee2e2` |

### 상태·결과 색상

| 역할 | 색상 코드 |
|------|-----------|
| 성공 / 당선 (win) | `#0d9488` |
| 성공 (contracted) | `#16a34a` |
| 낙선 (lose) | `#6b7280` |
| 위험 / 삭제 | `#dc2626` |
| 경고 | `#92400e` (텍스트) / `#fef3c7` (배경) |
| 경고 보더 | `#f59e0b` |
| 진단 액센트 | `#7c3aed` (보라) |

### 지침 충족도 (COMPLIANCE_COLOR)

| 상태 | 색상 코드 |
|------|-----------|
| 충족 (yes) | `#16a34a` |
| 부분 충족 (partial) | `#ea580c` |
| 미충족 (no) | `#dc2626` |
| 불명확 (unclear) | `#6b7280` |

### 오버레이 / 특수

| 역할 | 색상 코드 |
|------|-----------|
| 모달 오버레이 | `rgba(0,0,0,0.45)` |
| 편집 모달 오버레이 | `rgba(0,0,0,0.75)` |
| 패턴 당선 바 | `#334155` |
| 패턴 낙선 바 | `#92400e` |

---

## 2. 폰트

### 크기 체계

| 용도 | `fontSize` | `fontWeight` |
|------|-----------|--------------|
| 대형 등급 링 | 36px | 700 |
| 페이지 타이틀 | 18px | 600 |
| 섹션 타이틀 | 15–16px | 600–700 |
| 카드 이름 / 본문 강조 | 14–15px | 600 |
| 버튼 (대) | 15px | 600–700 |
| 일반 본문 | 13–14px | 400 |
| 버튼 (소) | 12px | 600 |
| 라벨 / 메타 | 12–13px | 400 |
| 배지 / 태그 | 10–11px | 500–700 |
| 앱 로고 | 15px | 700 |
| 네비게이션 탭 (활성) | 14px | 600 |
| 네비게이션 탭 (비활성) | 14px | 400 |

### 폰트 패밀리

| 용도 | 값 |
|------|-----|
| 기본 (전체) | 시스템 폰트 (`-apple-system` 계열, 명시 미선언) |
| 로그 출력 (`ProgressLog`) | `monospace` |

---

## 3. 버튼 스타일

### 버튼 유형별 정의

| 유형 | background | color | border | borderRadius | padding | fontSize | fontWeight |
|------|-----------|-------|--------|-------------|---------|----------|------------|
| **Primary (실행)** | `#15803d` | `#fff` | none | 6–8px | `12px 28px` | 15px | 600–700 |
| **Primary (진단)** | `#7c3aed` | `#fff` | none | 6px | `12px 28px` | 15px | 600 |
| **Secondary (네이비)** | `#334155` | `#fff` | none | 6px | `6px 14px` | 12–13px | 600 |
| **Report (보라)** | `#6d28d9` | `#ede9fe` | none | 6px | `6px 14px` | 12px | 600 |
| **Danger (삭제)** | `#b91c1c` | `#fff` | none | 6px | `8px 16px` | 13px | — |
| **Ghost (외곽선)** | `transparent` | `#4b5563` | `1px solid #4a5568` | 6–8px | `6px 14px` | 12px | 600 |
| **Disabled (비활성)** | `#dcfce7` | `#4a5568` | none | 6–8px | — | — | — |
| **Edit (편집)** | `#e5e7eb` | `#4b5563` | `1px solid #4a5568` | 6px | `3px 9px` | 11px | 600 |
| **새로고침** | `none` | `#4b5563` | `1px solid #e5e7eb` | 6px | `4px 12px` | 12px | — |
| **텍스트 (remove)** | `none` | `#dc2626` | none | — | — | 18px | — |

### 탭형 버튼 (Pill)

| 유형 | 활성 | 비활성 |
|------|------|--------|
| 시설유형 탭 | `bg #334155 / color #fff` | `bg #e5e7eb / color #4b5563` |
| 참조방식 토글 | `bg #ede9fe / color #5b21b6 / border #a78bfa` | `bg #fff / color #6b7280 / border #e5e7eb` |
| 패턴 탭 | `bg #f9fafb / color #334155 / border #334155` | `bg #fff / color #6b7280 / border #e5e7eb` |
| 공통 borderRadius | 20px | |

### 결과 선택 버튼 (ResultBtn)

| 결과 | 선택 시 color | 선택 시 background | border |
|------|--------------|-------------------|--------|
| 당선 (win) | `#0d9488` | `#fef3c7` | `2px solid #0d9488` |
| 수의계약 | `#16a34a` | `#dcfce7` | `2px solid #16a34a` |
| 낙선 (lose) | `#6b7280` | `#ffffff` | `2px solid #6b7280` |
| 비선택 | `#4a5568` | `#ffffff` | `2px solid #e5e7eb` |

---

## 4. 레이아웃 구조

### 전체 페이지 구조 (`App.jsx`)

```
<body>  background: #fafafa, minHeight: 100vh
├── <Header>  background: #fff, borderBottom: 1px solid #e5e7eb
│   ├── Logo  (flexShrink: 0, padding: 16px 0)
│   └── Nav Tabs  (display: flex, gap: 4, flex: 1)
└── <Main Content>  maxWidth: 1100px, margin: 0 auto, padding: 24px
    └── 활성 탭 컴포넌트 렌더링
```

### 모달 구조

```
Overlay  position: fixed, inset: 0, bg: rgba(0,0,0,0.45), display: flex, alignItems: flex-start
└── Modal  bg: #fff, borderRadius: 10, width: 100%, maxWidth: 960px, height: 85vh
    ├── ModalHeader  padding: 14px 20px, borderBottom: 1px solid #e5e7eb
    └── ModalBody  overflow: auto
```

### 패널 공통 구조

모든 탭의 주요 콘텐츠 영역은 동일한 패턴을 사용합니다.

```
Panel  background: #fff, borderRadius: 12px, padding: 24px
├── Title  fontSize: 18px, fontWeight: 600, marginBottom: 20px
├── Form Grid  display: grid, gridTemplateColumns: 1fr 1fr, gap: 12–16px
│   └── Group  marginBottom: 14px
│       ├── Label  fontSize: 13px, color: #4b5563
│       └── Input / Select  background: #fff, border: 1px solid #e5e7eb
├── Divider  borderTop: 1px solid #e5e7eb, marginTop: 20px, paddingTop: 16px
└── Run Button  width: 100%, marginTop: 16px
```

### 편집 모달 구조 (`SubmissionEditor`)

```
Overlay  position: fixed, inset: 0, bg: rgba(0,0,0,0.75), zIndex: 1000
└── Modal  bg: #fff, borderRadius: 14px, width: 90%, maxWidth: 920px, maxHeight: 90vh, display: flex, flexDirection: column
    ├── Header  padding: 18px 24px, borderBottom
    ├── Body  display: flex, flex: 1, overflow: hidden
    │   ├── Sidebar  width: 160px, borderRight, padding: 12px 8px (섹션 네비게이션)
    │   └── Content  flex: 1, overflowY: auto, padding: 24px
    └── Footer  padding: 14px 24px, borderTop, display: flex, justifyContent: flex-end
```

### 프로젝트 카드 구조 (`ProjectList`)

```
Card  bg: #fff, border: 1px solid #e5e7eb, borderRadius: 8px, padding: 14px 16px, marginBottom: 10px
├── CardHeader  display: flex, alignItems: center, gap: 10
│   ├── Badge (시설유형)
│   └── ProjectName
├── Meta  fontSize: 12px, color: #6b7280
├── SubmissionList  display: flex, flexWrap: wrap, gap: 6
│   └── 결과 뱃지 + 회사명 + [리포트 버튼] + [편집 버튼]
└── Actions  display: flex, gap: 8, marginTop: 10, flexWrap: wrap
    ├── 비교분석 실행 (green)
    ├── 제안서 추가 (navy)
    ├── 비교 리포트 열기 (purple, 조건부)
    └── 리포트만 재생성 (ghost, 조건부)
```

---

## 5. 컴포넌트 목록

### 공통 컴포넌트 (`components/common/`)

| 컴포넌트 | 파일 | 설명 |
|----------|------|------|
| `DropZone` | `DropZone.jsx` | PDF 드래그 & 클릭 업로드 영역 |
| `ProgressLog` | `ProgressLog.jsx` | SSE 실시간 진행 로그 (monospace, ▓░ 스타일 진행바) |
| `PageDistChart` | `PageDistChart.jsx` | 페이지 유형 분포 차트 |
| `ApiKeyGate` | `ApiKeyGate.jsx` | API 키 미입력 경고 배너 |

### 경쟁 공모 탭 (`components/AccumulateMode/`)

| 컴포넌트 | 설명 |
|----------|------|
| `AccumulateMode` | 탭 메인. 공모 정보 입력 + 제안서 목록 관리 |
| `SubmissionInput` *(내부)* | 제안서 1건 입력 폼 (회사명·결과·PDF) |
| `ProjectList` | 저장된 프로젝트 카드 목록 (시설유형 탭 필터) |
| `ProjectCard` *(내부)* | 프로젝트 1건 카드 (비교분석 실행·리포트 링크) |
| `AddSubmissionForm` *(내부)* | 기존 프로젝트에 제안서 추가 폼 |
| `ComparisonResult` | 비교분석 결과 렌더링 |
| `GapAnalysisCard` *(내부)* | 블라인드 분석 vs 실제 결과 정합도 카드 |
| `AxisCard` *(내부)* | 평가축별 등급·강약점 카드 |
| `ComparisonDashboard` | 다크 테마 대시보드 (전체 비교 시각화) |
| `CompanyFilterBar` *(내부)* | 회사 필터 버튼 바 |
| `CategoryRow` *(내부)* | 카테고리별 접기/펼치기 행 |
| `RankingBlock` *(내부)* | 종합 순위 블록 |

### 교차비교 탭 (`components/CrossCompare/`)

| 컴포넌트 | 설명 |
|----------|------|
| `CrossCompareMode` | 여러 프로젝트 제안서 조합 선택 & 비교 실행 |
| `ProjectCard` *(내부)* | 프로젝트 + 제안서 체크박스 선택 카드 |
| `SelectionBar` *(내부)* | 선택된 제안서 수 표시 + 실행 버튼 |

### 진단 탭 (`components/DiagnoseMode/`)

| 컴포넌트 | 설명 |
|----------|------|
| `DiagnoseMode` | PDF 업로드 + 진단 실행 (단건 / 참조 공모 선택) |
| `DiagnosisResult` | 진단 결과 렌더링 전체 |
| `GradeRing` *(내부)* | 원형 등급 표시 (전체 등급 + 축별) |
| `AxisDiagCard` *(내부)* | 평가축별 진단 카드 |
| `QuantCompare` *(내부)* | 당선 평균 / 낙선 평균 / 내 제출물 3행 바 비교 |
| `BarRow` *(내부)* | 수평 진행바 1행 |
| `LegendDot` *(내부)* | 범례 점 + 라벨 |
| `RequirementMapping` *(내부)* | 지침서 요구사항 매핑 테이블 |
| `MissingPageTypes` *(내부)* | 누락된 페이지 유형 경고 태그 |

### 내 프로젝트 탭 (`components/MyProjectMode/`)

| 컴포넌트 | 설명 |
|----------|------|
| `MyProjectMode` | 단건 제안서 등록 + 결과 기록 |
| `DiagnosisPanel` *(내부)* | 낙선 분석 결과 패널 |

### 설정 탭 (`components/Settings/`)

| 컴포넌트 | 설명 |
|----------|------|
| `SettingsPanel` | API 키·DB 경로·DPI·모델 설정 |
| `PatternViewer` | 시설유형별 당선·낙선 패턴 통계 |
| `PageDistBars` *(내부)* | 페이지 분포 이중 바 (당선 navy / 낙선 amber) |
| `QuantTable` *(내부)* | 정량 지표 비교 테이블 |
| `KeywordCloud` *(내부)* | 컨셉 키워드 클라우드 (우위 여부 색상 구분) |
| `QualitativeInsights` *(내부)* | 질적 인사이트 3열 카드 |

### 편집 모달 (`components/SubmissionEditor/`)

| 컴포넌트 | 설명 |
|----------|------|
| `SubmissionEditor` | 제안서 추출 결과 편집 전체 모달 |
| `QuantSection` *(내부)* | 정량 데이터 (면적·세대수 등) 편집 |
| `MetaSection` *(내부)* | 메타 정보 편집 |
| `ConceptSection` *(내부)* | 컨셉·슬로건·키워드 편집 |
| `TagInput` *(내부)* | 키워드 태그 추가/삭제 입력 |
| `FloorSection` *(내부)* | 층별 용도 편집 |
| `AreaSection` *(내부)* | 면적표 편집 |
| `CoverSection` *(내부)* | 표지 정보 편집 |
| `AdvancedSection` *(내부)* | 원시 JSON 직접 편집 |

### 훅 (`hooks/`)

| 훅 | 설명 |
|----|------|
| `MetaProvider` | 앱 전체를 감싸는 메타 컨텍스트 프로바이더 |
| `useMeta` | 시설유형 라벨·그룹, 페이지타입 라벨, 평가축 정보 제공 |
