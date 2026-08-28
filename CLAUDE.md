# CLAUDE.md

Competition Analyzer — 건축 공모 제안서 추출·비교 풀스택 앱.

**Stack:** FastAPI + React 18/Vite + Anthropic Claude (추출·분류·비교·진단·대지분석 `claude-sonnet-4-6` / AI 종합 해설·수주 제안서만 `claude-opus-4-8`) + PyMuPDF. JSON-based DB. Docker + Cloud Run (gen2) + GCS 마운트 (`/data`). `main` push → GitHub Actions 자동 배포.

## Architecture

### Backend Routers (`/api/<name>`)

**형제앱이 우리를 읽는 경로 (역방향, 2026-08-27 문서화):** `arch-law-diagnose` 가 **우리 GCS 버킷의 `_briefs/` 를 GCSFUSE 로 마운트해 직접 읽는다**(env `BRIEF_DIR`, HTTP 아님). `GET /api/feasibility/briefs`(목록·카테고리 필터·최근 N건만 본문 파싱 + (이름,수정시각) 캐시) · `GET /api/feasibility/briefs/{file_id}` → `brief_importer.map_brief` 가 사업성 prefill(`target_*`)로 매핑 → 프론트 `FeasibilityMode/BriefList.jsx`(카테고리 14종 = **우리 파일명 suffix**)·`BriefImportPanel`·**`MultiSiteCompare`(다부지 비교)**. 산출은 그쪽 사업성 MD/xlsx/HTML. ⚠**우리가 파일명 규칙(`YYYYMMDD_HHMMSS_카테고리_슬러그`)이나 `brief_project_info.sites` 스키마를 바꾸면 그쪽이 조용히 깨진다** — 그쪽은 정렬·필터를 파일명만으로 한다. 딥링크는 없다(브리프 선택은 그쪽 화면에서). 그쪽 활성 TODO 2건이 우리 몫이다: **brief 추가 샘플(민간·다부지)** · **사내 시설용도 매핑표**(없어서 `facility_use` 자동 채움을 포기 중 — 우리 `feasibility_export.sites[].building_law_uses` 가 재료).

1. **`routers/accumulate.py`** — PDF → JSON 추출 + 개별 제출물 리포트. `run` 의 `run_compare`(기본 OFF, 폼) 켜면 추출 직후 비교분석(2-pass)+패턴+리포트까지 **같은 run 에서**(제출물 2개↑, 비치명 — 비교 실패해도 추출물 유지). 끄면 비교분석은 별도 (`rerun-compare`). `add-submission`, `rerun-compare`, `rerender-report`, `cross-compare` 엔드포인트 포함. **삭제**: `DELETE /projects/{ft}/{cid}`(`db_manager.delete_project` rmtree + 패턴·아카이브 재구축, path traversal 가드). **교차비교 persist**: `save/load_cross_compare_data` 로 HTML 옆 구조화 JSON 저장(`has_data`), `POST /cross-compare/reports/{filename}/rerender`(LLM 0 재렌더).
2. **`routers/diagnose.py`** — 단일 제출물 진단. `/run` (DB 전체 패턴) + `/run-vs-projects` (사용자 선택). 완료 시 HTML 리포트 자동 생성.
3. **`routers/patterns.py`** — 시설유형별 패턴 관리 (당선 + 낙선 통계).
4. **`routers/settings.py`** — `app_settings.json` 관리. `GET /settings/meta` 가 프론트 `useMeta()` 단일 소스.
5. **`routers/upload.py`** — 청크 업로드 (Cloud Run 32MB 한도 우회). 25MB 청크 / 600MB 상한 / `/tmp/cc_uploads/` 누적.
6. **`routers/archive.py`** — FTS5 in-memory SQLite 자연어 검색.
7. **`routers/brief.py`** — 지침서 단독 분석 (PDF + DOCX + HWP/HWPX). 분류 → 추출 → 요구사항 → 검증 → (옵션) AI 종합 해설 → JSON/MD/xlsx/HTML 저장. HTML 은 `/exports/{name}.html` 에서 인라인(text/html, 보기용), md/xlsx 는 attachment. `analyze` 폼 `include_insight`(기본 ON) 가 같은 run 에서 종합 해설까지 한 방. `POST /{brief_id}/interpret` 는 해설만 재생성(추출 재처리 0, 분석 시 껐거나 프롬프트 개선 후 재적용용) 후 **파생 3종(html·md·xlsx) 모두 재렌더** — 셋 다 새 `_insight` 반영. `POST /{brief_id}/propose` 는 **프로젝트 수주 제안서** 생성(추출 재처리 0, LLM 1콜) → `_proposal` 임베드 + 별도 `{brief_id}_proposal.html` 렌더(`/exports` 인라인 서빙, `has_proposal` 노출). **'변수' steering v1(2026-07-29):** propose 가 선택 JSON body `ProposeRequest{steering, reset_steering}` 수용(빈 POST 하위호환) — 방향 지시를 `_brief.json._steering_log` 에 누적(지시당 500자·최대 20개, 초과 400)하고 전체 지시로 해석층만 재생성. **로그는 LLM 성공 후에만 persist**(실패 시 로그↔제안서 불일치 방지), reset 은 항상 clean 재생성 동반. 응답 `steering_count`/`steering_log`, `list_briefs` 항목에도 `steering_log` 노출. A층(결정론 scoring_focus·required 배치)은 후처리 덮어쓰기로 구조적 불변. `POST /{brief_id}/playbook` 는 **경험 기반 처방** 생성(추출 재처리 0, LLM 최대 1콜) → `_playbook` 임베드 + 별도 `{brief_id}_playbook.html` 렌더(`has_playbook` 노출) — 같은 시설유형 과거 축적 데이터(`reference_cases`) 없으면 **LLM 미호출·`has_playbook:false`+`reason`** 반환(무료 게이트). `interpret`=사실 triage(해설가), `propose`=수주 전략 처방(전략가), `playbook`=과거 경험 기반 처방(과거 당락→이 지침서 적용) — **셋 다 별개 산출물**. `POST /{brief_id}/deck` 는 **발표 장표**(A3 편집가능 PPTX) — `_proposal` 을 `proposal_deck.build_deck` 로 `deck_render/1.0` 에 옮겨 터읽기가 그린다(**LLM 0 · API 키 불필요 · 추출 재처리 0**). 응답은 바이너리 + RFC 6266 한글 파일명 + `X-Deck-Slides`/`X-Deck-Missing`(ASCII 숫자만 — 헤더는 latin-1). 형제앱 장애는 502. 멀티파일: `analyze` 는 지침서+과업지시서 등 **복수 파일 동시 분석** 지원(`brief_pdf_refs` JSON 배열, `_merge_multi_brief_data` first_wins — 충돌해소는 업로드 순서뿐, 도메인 규칙 없음).

**MyProject 심층 분석:** 별도 라우터 없음. `accumulate.py` 가 단일 등록 시 `myproject_analyzer.deep_analyze()` 호출 → `_deep.json` + `_deep.html`. `GET /projects/{ft}/{cid}/submissions/{company}/deep-report` 로 서빙.

### Core Services

| 파일 | 책임 |
| --- | --- |
| `db_manager.py` | JSON DB. `_atomic_write` / `_sync_write` 는 GCSFUSE 플러시 위해 `fsync` 후 rename — 신규 파일 저장 함수 추가 시 반드시 사용. |
| `docx_loader.py` | DOCX 블록 분할 (PDF 와 완전 독립). `split_docx_to_blocks()` R1~R5 분할 + F1~F3 필터. vMerge 감지는 `_tc` identity + tcPr `w:vMerge` 두 시그널 조합 필수. |
| `hwpx_loader.py` | HWP/HWPX 블록 분할 (rhwp-python, PDF/DOCX 와 독립). `split_hwpx_to_blocks()` 반환 스키마가 docx_loader 와 **동일** → `classify_all_blocks_brief` / `extract_hwpx` / BRIEF_* 추출 헬퍼 그대로 재사용. `ir.iter_blocks(recurse=False)` 필수 (Critical Rules 참조). 표 HTML → 마크다운 + merge_info 는 docx 호환 `{row,col,merged_rows,value}`. `get_hwpx_source_text()` 는 docx 구현 위임. 회귀: `tests/test_hwpx_loader.py` (22, rhwp monkeypatch). |
| `page_classifier.py` | 페이지/블록 분류. `classify_all_pages_brief()` (PDF) / `classify_all_blocks_brief()` (DOCX/HWP/HWPX). `has_scoring_table=False` 면 BRIEF_EVALUATION → BRIEF_ADMIN 강등. |
| `data_extractor.py` | 페이지/블록 추출. `merge_extracted_data()` 가 `_quantitative` 자동 집계. DOCX BRIEF_EVALUATION 표는 `_extract_docx_eval_from_table()` 로 LLM 없이 파싱 (환각 차단). 제안서(브리프 제외) 결과엔 `quant_validator.validate_quantitative()` 로 `_quantitative_flags` 부착 (모순 시에만, 숫자 수정 안 함). brief 결과면 끝에서 `feasibility_export` 블록도 부착 (try/except, 실패해도 파이프라인 무중단). HWP/HWPX 는 `extract_hwpx()` (split_hwpx_to_blocks 로 파싱, extract_docx 가 python-docx 재파싱이라 hwpx 불가 → 병렬 함수. BRIEF_* 추출 헬퍼·merge_info 스키마 재사용). |
| `brief_merge_conflicts.py` | 멀티파일 병합 **충돌 탐지** (LLM 0 · 값 수정 0). `analyze` 가 지침서+과업지시서를 같이 받으면 병합은 `first_wins` 인데 **진 값이 어디에도 안 남는 게** 문제였다 — 두 문서가 대지면적을 다르게 적어도 화면엔 하나만 뜨고 그게 `feasibility_export`→진단→**법적 골격**까지 흘러간다. `detect_conflicts(data_list, source_names)` → `_merge_conflicts`. 3종: **quantitative**(`_quantitative` 필드별) · **site**(`brief_project_info.sites[]` 정량, site_id 매칭 — 순서 아님) · **block**(뒤 파일 최상위 블록이 통째로 유실). ⚠**정밀 flag 가 있으면 같은 블록의 block 통지는 억제**(같은 사실 두 번 말하면 정확한 줄이 묻힌다). ⚠**자동 판정 안 함** — concept-studio 는 출처 등급(`gazette > guideline`)으로 자동 해소하지만 그건 **권위 서열이 실재하는** 문서군이라 가능하다. 지침서·과업지시서·설계지침은 **전부 같은 발주처 문서**라 어느 쪽이 이겨야 하는지가 공모마다 다르다(과업지시서가 지침서를 정정하기도, 본문이 별첨을 이긴다고 명시하기도). 파일 이름 날짜는 `later_differs` **힌트로만**(파일명은 사람이 붙인 것). 렌더: `band_html`(체크리스트 HTML, 본문 **앞**) · `md_lines`(md·HWPX §0.4). 회귀: `tests/test_brief_merge_conflicts.py` (33). |
| `quant_validator.py` | `_quantitative` 내부 정합성 결정론 검증 (LLM 0 · 숫자 수정 0). 건폐율=건축/대지, 총연면적≥용적률×대지 등 항등식으로 추출 오류(필드 오결합·환각)를 flag 로만 표시 (`severity: error\|warn`). **단일 소스** — `merge_extracted_data`(추출 직후 `_quantitative_flags` 부착, 제안서만) · `pattern_builder`(error flag 필드 집계 제외) · `tools/data_health.py`(무료 감사) 가 공유. 관대(false positive 회피 — 영등포 교훈). 회귀: `tests/test_quant_validator.py`. |
| `feasibility_export.py` | `_brief.json` → `feasibility_export` 정규화 블록 (schema_version 2). ⚠**소비자 정정(2026-08-27)**: 「연동 앱 arch-law-diagnose 용」이라고 적어 왔지만 **그쪽은 이 블록을 안 쓴다** — `brief_importer.map_brief` 가 `brief_project_info.sites`·`brief_site`·`_quantitative` 를 **직접 재파싱**한다(그쪽 `_parse_site_addresses` 가 우리 「'(부지N)' 주소 분해+접두 상속」을 독립 구현 — 같은 데이터에 같은 파싱이 두 레포에 있다. 한쪽이 파싱 버그를 고쳐도 다른 쪽은 모른다). **실제 소비자는 우리 자신**: `arch_law_client.to_request`(진단 요청) · `brief_massing`(부지 지오메트리) · `_facts_band_html`(사업 규모) · `brief_advisor`·`bid_structure`. → 그쪽이 이 블록으로 갈아타면 주소 분해·`zone_use` 정규화·`limits_determined_by`(심의)·`required_parking_count` 를 공짜로 얻고 자기 파서를 지울 수 있다(제안 대기). **새 vision 추출 없음 · 기존 키 수정 없음 · 추가만.** 이미 추출된 값을 재배치·파싱: site_id 통일, brief_site "(부지N)" 주소 분해+접두 상속, 인증 코드화, facilities 괄호 건축법 용도, 사업 규모 노출(1차); **목표 연면적**(`floor_area_sqm`, 2026-08-27 — `brief_project_info.sites` 에 **이미 있던 값**인데 이 블록에만 안 실려서 제안서·장표의 「사업 규모」 팩트 밴드에 **연면적이 통째로 빠져 있었다**. 실측 prod 부지 **31/31** 채워짐. 대안 `_quantitative.total_floor_area_sqm` 은 21건 중 11건뿐이고 **prod 절반이 다부지**라 총합으로는 부지별 값을 못 대신한다. ⚠`open_space_sqm`·`open_space_notes` 는 **일부러 안 싣는다** — 우리 소비처가 없다. 소비처 없는 필드는 같은 값의 출처만 둘로 만든다(arch-law-diagnose 지적 2026-08-27: 「얻는 건 0, 새로 생기는 건 갈라질 자리」). 쓰는 쪽이 생기면 그때. ⚠**schema_version 은 2 유지** — 추가만이라 하위호환이고 소비 측 게이트가 `>=2` 라 올리면 옛 판본을 읽던 코드가 갈라진다); 주차 서술→required_parking_count(부지N 마커 귀속), zoning→표준 용도지역명(**불확실 시 raw** — ⚠**다중 매칭은 판단 보류**, 2026-08-27 arch-law-diagnose 제보. 옛 `max(matches, key=len)` 은 `_ZONE_USES` 16개에 포함관계가 없어 길이 동점에서 **앞 항목**을 골랐다: 「제3종…(제2종…에서 종상향)」→ 종상향 **前**, 다중 용도지역 → 임의 첫째. 조용히 틀리고 이 값이 `arch_law_client.zone_use_override` 로 가 건폐/용적 한도를 좌우한다 — 비우면 진단 엔진이 주소로 직접 조회), special_conditions 심의 문구→limits_determined_by(2차). ⚠**`limits_determined_by` 판정 조건(건폐율·용적률·높이)을 넓히려면 arch-law-diagnose 에 먼저 통지**(2026-08-28 상호 확인) — 그쪽이 이 값을 `review_premised` 로 받아 **상한에만** 적용하는 전제가 그것이다(주차 같은 법정 **최소**는 심의로 면제 안 됨). 한쪽이 넓히면 다른 쪽이 조용히 어긋난다. 그쪽이 읽는 건 이 값 + `required_parking_count`·`parking_note` + 사업규모 3종뿐이고, **나머지 필드는 우리 소비처 기준으로 자유롭게 넣고 뺀다** — 블록은 연동 계약이 아니라 우리 내부 정규화 층이다(2026-08-28 양쪽 합의). 모두 후처리 파싱이라 BRIEF_* 추출 회귀 없음. 회귀: `tests/test_feasibility_export.py` (46). 무료 검증: `tools/feasibility_verify.py`. |
| `llm_client.py` | Claude API 래퍼 `call_messages()`. `system` 은 `str \| list` 모두 지원. 캐시 토큰 로깅. `_NO_SAMPLING_PREFIXES`(opus-4.7/4.8·fable·mythos) 로 시작하는 모델엔 `temperature`/`top_p`/`top_k` 를 body 에서 자동 생략 — 이 모델군은 샘플링 파라미터 전송 시 **400** (Sonnet/Haiku/Opus4.6 은 유지). |
| `comparator.py` | **2-pass blind-reveal.** Pass 1: 익명화 채점, Pass 2: 리빌 후 차별화·gap 분석 + `concept_comparison`(축별로 각 회사의 컨셉·설계방향을 (p.N) 인용과 함께 나란히 서술하는 비교 — Pass 1 결과의 strengths/weaknesses/notes 만 근거로 사용, 원본 재전송 없음) (Pass 1 결과만 재전송, 80%+ 토큰 절감). `_compute_gap_analysis()` 결정적 로직으로 alignment 산출 — **결과 화면엔 더 이상 렌더하지 않고 내부 QA 용으로만 comparison.json 에 보존**(2026-07-01, "누가 1등이냐"보다 컨텐츠 비교가 더 유용하다는 사용자 결정). Prompt caching ephemeral. `.replace()` 사용 (`.format()` 은 JSON 중괄호 충돌). **차별화 심화(Layer 2)**: Pass 2 reveal 프롬프트가 `key_differentiators` 를 명시적 win↔lose 대비+인과 포맷("당선작은 ~(p.N), 낙선작은 ~(p.M) — 이 대비가 당락을 갈랐다")으로, `winner_strengths`/`loser_weaknesses` 를 SPECIFICITY 규칙(추상어 금지·구체근거+인용)으로 강제 — `report_generator` 핵심 요약 카드의 연료. 크기 상한 kd 4개/70자·wl 3개/45자. **오버플로우 가드**: Pass 2 실패해도 raise 대신 Pass 1(축별 등급) 보존 + `_coverage_note` 고지(대규모 교차비교 방어), `concept_comparison` 전 축 키 보장. **인용 사후검증**: `_run_compare_sync`/`_run_diagnose_sync` 가 `citation_check` 로 `_citation_flags` 부착(환각 쪽번호 flag, 비치명). `_run_diagnose_sync` 는 parse 결과가 dict 아니면(LLM 배열 반환) 명시 ValueError. |
| `pattern_builder.py` | 당선 패턴 + `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords). `_build_quant_stats()` 는 `quant_validator` 가 error 로 지목한 필드를 **제출물별** 집계에서 제외 (환각 수치 패턴 유입 차단; warn 은 유지). 저장 `_quantitative_flags` 우선, 없으면(플래그 훅 이전 추출된 구 레코드) 집계 시점 `validate_quantitative()` 재검증. 회귀: `tests/test_quant_validator.py::TestPatternBuilderExcludesFlagged`. |
| `report_generator.py` | 비교 HTML 리포트 (LLM 호출 없음). `axes_for(facility_type)` 로 시설별 평가축. 종합 순위(`ranking`)·블라인드 정렬 분석(`gap_analysis`) 섹션은 미렌더. **구조(2026-07 재편):** 최상단 **핵심 요약**(① `_render_keydiff_card()` 가 `key_differentiators` 를 축 헤더+당선/낙선 색강조+💡 인과의 구조화 카드로 — 버려지던 신호 노출, ② 당선요인↔낙선함정 2열, ③ `gap_analysis` 정합성 노트·발산 시 "설계 외 요인" 경고) → **당선작 강점 분석**(강점-only, 대표 강점 헤드라인+불릿, 약점·balanced 제거) → **설계 축별 비교 분석**(대시보드 아코디언, notes 를 `_strip_grade_tail()` 로 "B 수준" 꼬리만 절삭한 판정 헤드라인) → `concept_comparison` "축별 컨셉·설계 방향 비교". 등급은 3단계(우수/보통/미흡, `grade_label*`). 회귀: `tests/test_dashboard_readability.py`. |
| `submission_report_generator.py` | 개별 제출물 리포트. LLM 호출 없음. |
| `diagnosis_report_generator.py` | 진단 리포트. LLM 호출 없음. 종합점수 링 → 페이지바 → 패턴편차 → 충족도 → 요구사항 매핑 → 평가축 상세. |
| `myproject_analyzer.py` | MyProject 멀티패스 deep-analysis. narrative + deep evidence + 정량 + 키워드 + auto_meta. |
| `myproject_report_generator.py` | `_deep.json` → HTML. LLM 호출 없음. |
| `archive_search.py` | in-memory SQLite FTS5. `build_index()` 시작 시 1회, `rerun-compare` 후 `rebuild_index()`. `check_same_thread=False` 필수. **BM25 관련도 랭킹**: `_ranked_match` 가 `ORDER BY bm25(archive_fts, _BM25_WEIGHTS)` 로 best-first(컬럼 가중치=시설유형·컨셉키워드 우대), bm25 미지원 시 무순 폴백. keyword·natural 검색 공유. ⚠trigram 은 2자 미만 미매칭(병원·시청). 회귀: `tests/test_archive_bm25.py`. |
| `brief_validator.py` | 지침서 검증. LLM 호출 없음. `requirements` 가 dict 아니면 `{}` 교체 (LLM 배열 반환 방어). `_check_points_mismatch` 는 `shared_with` non-empty 또는 합계가 만점과 일치 시 null 항목을 정성평가로 인정 (영등포 false positive 차단). |
| `brief_checklist_exporter.py` | 지침서 체크리스트 MD/xlsx/HTML. LLM 호출 금지. openpyxl lazy import. xlsx 시트: (`_insight` 있으면 맨 앞 "종합 해설") / 1.면적·프로그램(사업개요 서브섹션 포함) / 2.심사기준 / 3.요구사항 / 4.검증경고 (+ area_rows 있으면 5.면적표상세). `to_markdown` 도 `_insight` 있으면 헤더 직후 `## 0. 종합 해설` 섹션 삽입(`_md_insight_block`). (렌더 표기는 "종합 해설" — "AI" 접두 제거 2026-07-29; 내부 개념명 "AI 종합 해설"은 코드 주석·문서에 잔존.) xlsx·md·html **3종 모두** insight 임베드(없으면 graceful skip). `to_html()` 은 `to_markdown` 과 동일한 `_extract_sections()` 데이터로 미니멀 자체완결 HTML (화이트 + 건원 RED, 5섹션, 상단 고정 nav + 핵심수치 카드 + 시설별 접기). `to_html()` 의 "지침서 종합 해설" 섹션은 `insight._reference_cases` 있으면 "참고 사례" 서브섹션도 렌더(`_reference_cases_section_html`, html 전용 v1 — md/xlsx 는 미포함). 데이터는 `html.escape`. `_form_area_pages()` 가 '[서식 N] …면적표' 제출양식 오분류 페이지를 면적 집계에서 제외 (본문 면적표 중복 차단, 영등포 사례). **프로그램 면적 스택(2026-07-29):** `_program_area_stack_svg()` 가 면적표를 비례 스택 다이어그램(SVG, `report_theme.CATEGORY_COLORS`, 라벨에 ㎡·%)으로 렌더 — 사실 기반(추출 면적만, LLM 0). 공용 헬퍼 `program_stack_html(brief_data)`(내부 `_extract_sections()["area"]` 경유, 실패·부족 시 "") 로 **수주 제안서 덱과 단일 소스 공유**('한 문서화'). **블록 집계 정리(영등포 교훈):** `_program_stack_blocks` 는 다부지 표에서 `'부지'` 이름 단 `site_total` 아래 '요약 시설'만 채택하고 각 부지는 선언 subtotal 도달 시 닫아 **①②③ 재집계 헤더·상세 dump 를 배제**(안 하면 구청이 24%/14%/2% 3중 노출). `_clean_program_blocks` 가 앞머리 장식기호(▣■ 등) 제거·소계/전용 계/총계 이름 행 제외·동일 라벨(부지별 주차 등) 합산 → 부지별 시설 합이 연면적 총합과 일치. 회귀: `tests/test_brief_pipeline.py` (TestProgramAreaStack — 다부지 스코핑·소계 제외·기호 정리). |
| `brief_advisor.py` | 지침서 "AI 종합 해설" (안전한 ②: 종합·번역 + 강조점 탐지, **외부 당락 예측 없음**). 결정론 백본 `compute_scoring_focus()`(배점 랭킹, null/shared_with 시맨틱=`brief_validator._check_points_mismatch` 와 동일) + `extract_emphasis_signals()`(강조어휘 문장 + category_weights, 강조문장 dedup) + `reference_cases.collect_reference_context()`(시설유형 기존 사례, 있을 때만) → 이 신호 위에서 `interpret_brief()`(LLM 1콜, comparator 패턴) 가 종합. **모델 = `settings.model_id_advisor`(기본 Opus `claude-opus-4-8`), `max_tokens=16000`** (해설은 지침서당 1콜뿐이라 Opus 비용 부담 작음; 추출·비교·진단은 Sonnet 유지). temperature=0 전송하나 Opus 는 `llm_client` 가 자동 생략. 가드 4: 근거한정·인용필수(페이지 추측 금지)·예측금지·중립탐지. `reference_cases` 는 `reading_guide` 배경 참고로만 — key_emphases/must_not_miss/hidden_constraints/scoring_focus 등 이 지침서 판단 근거로는 사용 금지(가드 강화). LLM 의 scoring_focus 환각은 결정론 값으로 덮어씀. 연료=`brief_evaluation`+`design_guidelines_grouped`. `interpret_brief()` 결과에 `_reference_cases` 부착(렌더러용). 회귀: `tests/test_brief_advisor.py`. |
| `brief_proposal.py` | 지침서 "프로젝트 수주 제안서" (**전략가**: `brief_advisor`가 사실 triage(해설가)라면 이쪽은 앞을 보는 처방). `propose_project()` (LLM 1콜, Opus `settings.model_id_advisor`, `max_tokens=16000`, comparator 패턴). 결정론 백본은 `brief_advisor._build_advisor_payload()`와 단일 소스 재사용 — `reference_cases`(시설유형 기존 사례 참고자료) 도 이 payload 를 통해 공유. 설계 계약·패턴 결합·AI 해석 확장층 상세는 표 아래 [파일별 상세](#core-services-상세-표에-담기엔-긴-항목) 참조. |
| `bid_structure.py` | 입찰(bid) **2층 배점 구조** 정규화(LLM 0, 결정론) — `build_bid_structure(brief_data)` → `_bid_structure`(genre=="bid" 일 때만, `routers/brief.py` 가 requirements 추출 **직후** 부착 — bid_structure 가 `_requirements` 를 소비하므로 merge 시점엔 불가). 상위(top_layer): 종합평점=사업수행능력%×w + 가격%×(100-w), w 는 **연면적 규모별 밴드**(8만/24만㎡→20/30/40% vs 80/70/60%). 하위(pq_detail): 사업수행능력 100점표(참여기술자50·유사용역실적40·신용도10, brief_evaluation 재집계). **다중표 병합**: `_find_eval_pages` 가 brief_evaluation 여러 페이지에서 상위층(사업수행능력+가격 2축) 페이지와 PQ상세(100점표) 페이지를 **분리 식별** — 각 층을 올바른 표에서 가져온다. **견고성(3소스 우선순위)**: ① 상위층 페이지 `evaluation_method` 서술(`_parse_bands_from_method`, "8만㎡미만(사업수행능력평가 20%, 가격평가 80%)…" — run 간 안정적, 최우선) ② evaluation_criteria 항목(`_parse_bands`) ③ requirements 범위(`_parse_range`, "가격 60~80% 차등"). axis 는 `bands`(정확) 또는 `weight_range`(범위). LLM 이 evaluation_criteria 밴드를 떨궈도 method 소스로 정확 밴드 복원. **정직성**: 밴드 기준=연면적인데 연면적 미추출이면 적용 밴드 단정 금지(대지면적 대체 추정 금지 — 21만㎡ 대지 ≠ 연면적), `applicable.note` 로 "확인 필요". 렌더: `brief_checklist_exporter._bid_structure_html` (심사기준 섹션), advisor payload 주입. 회귀: `tests/test_bid_structure.py` (14). |
| `brief_genre.py` | 지침서 **장르 판별**(LLM 0, 결정론) — `detect_brief_genre(brief_data)` → `_brief_genre` 부착. `competition`(설계공모: 배치·공간계획 등 설계축) vs `bid`(설계자 선정 입찰: 사업수행능력=참여기술자·유사용역실적·신용도 + 가격) vs `unknown`. 최강 판별자 = **평가 카테고리명 자체**(가중 3) + 본문 텍스트 마커(적격심사·낙찰 vs 심사위원·당선작, 가중 2). bare "공모"/"입찰"은 양쪽 혼재라 약신호. `merge_extracted_data`(brief)·`_merge_multi_brief_data`(합쳐진 eval 로 재판별)가 부착. 다운스트림 오인 차단: `brief_validator`(입찰은 건폐율·용적률 등 설계지표 누락 오경고 스킵), advisor/proposal/playbook 프롬프트에 genre 주입, exporter eyebrow·프론트 배지. 회귀: `tests/test_brief_genre.py` (7). |
| `reference_cases.py` | 시설유형별 "기존 사례 참고자료" 결정론 조회(LLM 0) — `brief_advisor`·`brief_proposal` 공유 단일 소스. `collect_reference_context(facility_type)` 가 세 서브키 반환: `pattern_summary`(기존 `pattern_builder` 집계 통계 이관), `case_excerpts`(당선 제출물 `concept.main_strategy` 실제 서술, 최근순 최대 3건, `get_winning_submissions`), `concept_comparison_excerpts`(과거 비교분석 `concept_comparison` 축별 서술, 최대 4건, `load_comparison`). 셋 다 비면 전체 `{}` 반환. 실패해도 `{}` (본 파이프라인 비차단). 소비 측이 반드시 "다른 공모 자료 — 이 지침서 사실 근거 아님" 가드레일을 프롬프트에 명시(브리프 자체 `basis` 에 섞이지 않게). 결과 리포트에 "참고 사례" 섹션으로 노출(2026-07-01 사용자 결정) — `brief_proposal_report_generator._reference_cases_html()` / `brief_checklist_exporter._reference_cases_section_html()`. 회귀: `tests/test_reference_cases.py`. |
| `brief_massing.py` | 지침서 **부지별 개념 매스** 다이어그램(LLM 0, 결정론, Report Generation Rule) — 새 추출 없음, `feasibility_export.sites[]` 지오메트리 + 면적표 시설 프로그램 재배치. `build_massing_sites(brief_data)`(테스트용 순수 데이터) → `massing_html(brief_data)`(SVG 섹션, graceful ""). **가로 배치**(`_fit_svg`, viewBox 690 풀와이드 — 세로 타워는 오른쪽 여백 과다로 폐기, 사용자 결정 2026-07-30): 부지당 3개 가로 바 **용적 봉투(허용, 회색)=footprint×봉투층 / 지상 프로그램(소요, 시설 색 세그먼트+초과분 빨강) / 지하(빗금, 용적 제외)** + **용적 상한 세로 점선**(봉투 폭=지상 허용 한계, 초과분이 이 선 너머 빨강) + 시설 범례(`_legend_html`, 색·㎡·%). NYC 조닝 permitted vs achieved 방식. 용량 모델: footprint=대지×건폐, 봉투층=min(용적/건폐, 높이한도/층고 4.3m), cap=footprint×봉투층. **다부지**는 `_per_site_programs` 가 '부지N' site_total 로 프로그램 버킷 분리(program_stack 과 동일 로직이나 부지별 보존·dedup 안 함), 지오메트리와 문서순 zip. ⚠**정직성**: 시설 소계(예 구청)가 지상·지하층을 한 값에 섞어 담아 분리 불가 → 지하는 이름 '지하' 표기 시설만 제외하므로 지상 추정은 **과대 가능**(캡션 고지), '초과'는 단정 아닌 "지하 배분·효율 재검토" 신호로 표기. 정북 일조·가로구역 계단컷 미반영(향후). 소비: `brief_proposal_report_generator._massing_section`(제안서 덱 '개념 매스·용적 봉투' 섹션, 면적 구성 직후), `routers/brief.py::_render_proposal_html` 주입. 회귀: `tests/test_brief_massing.py` (17). |
| `brief_proposal_report_generator.py` | `_proposal` → 자체완결 **매거진형 덱** HTML (LLM 0, Report Generation Rule). 명조 본문(`--serif`) + Montserrat 제목(`--sans`) + 건원 RED, 회색 페이지 위 흰 페이퍼. **컨셉 표지**(`_concept_cover_html`, 덱 오프닝 — `concept_hook` 있을 때만: 한 단어 keyword(건원 RED 大)+3축 tagline+축별 ko/en/근거 앵커, "제안" 배지·"팀이 갈아끼우는 출발점" 라벨로 사실과 구분, graceful skip) + **결정 요약 cockpit**(`_decision_cockpit_html`, 최상단 6칸: 발주의도·승부처·권장방향·최대리스크·착수1순위·신뢰도, 각 칸→근거 섹션 앵커, 결정론) + **권장 종합안**(`_recommended_synthesis_html`+`_recommend`, 5안 중 최고 배점축 겨냥안을 뼈대로·볼륨 안 깎는 안 접목·나머지 조건부, 설계 접근 섹션 최상단). 입찰이면 `_bid_structure_html`로 2층 배점 구조 섹션(공모는 5안/권장종합) — `to_proposal_html(bid_structure=)`. **대지 근거 배치 다이어그램(2026-07-29 재설계):** hero = 위성 이미지 있으면 `_zone_site_overlay_svg`(위성 배경 + `parcel_norm` 실측 필지경계 빨간선 + 존 블록), 없으면 `_zone_site_plan_svg`(흰 박스 top-view 배치도, N▲/W/E/S 방위 크롬 + 지하 띠) — **평면은 방위만 표기, 층(상/중/저)은 존 카드 `pz-loc`("남측·저층")로 분리**(plan축≠section축). 조닝 ALT 는 `_zone_alts_html` 2안(`alts[:2]`, `_zone_site_plan_svg` 재사용, required 존 동일 고지). **"AI" 자기지칭 라벨 전면 제거(2026-07-29)**: 배지 문구 `_AI_BADGE`="제안"(클래스명 `ai-badge` 유지), 푸터 "AI 생성" 삭제 — 사실/제안 2층 구분 자체는 유지. **'한 문서화'(2026-07-29)**: `to_proposal_html(program_stack_html=, key_emphases=)` — `_program_stack_section`(면적 비례 스택, 팩트 밴드 뒤)·`_emphases_html`(`_insight.key_emphases` → "지침서가 강조하는 요소", 와플 뒤) 섹션 추가(임원 PPT S8·S10 대응, 실무자가 제안서 하나로 착수). 데이터는 `_render_proposal_html` 이 주입, 없으면 graceful skip. **개념 매스(2026-07-29)**: `to_proposal_html(massing_html=)` — `_massing_section`(`brief_massing.massing_html` 결과, 면적 구성 섹션 직후 '개념 매스·용적 봉투', nav "매스") 삽입, 부지별 가로 바(봉투/소요/지하 + 용적 상한 세로 점선, 초과 시 "지하 배분 재검토" 신호). 실무자 표준 2D 포맷(NYC 용량 스터디) — 아이소메트릭·세로 타워 거부(비표준·여백 과다). 히어로·팩트밴드·대지·해석 확장층·참고 사례 등 상세는 표 아래 [파일별 상세](#core-services-상세-표에-담기엔-긴-항목) 참조. 회귀: `tests/test_brief_proposal_report.py` (74). |
| `brief_playbook.py` | 지침서 "경험 기반 처방"(experiential playbook, **세 번째 산출물** — `interpret`=해설가, `propose`=전략가에 이은 것). `build_playbook()` (LLM 최대 1콜, Opus `settings.model_id_advisor`, `max_tokens=16000`, comparator 패턴). **advisor/propose 와 정반대**: 저 둘은 `reference_cases`(같은 시설유형 과거 당선/낙선 축적)를 *배경 참고로만* 쓰고 이 지침서 판단 근거로는 못 쓰게 가드가 걸려 있음 — playbook 은 그 관계를 **뒤집어** reference_cases 를 *주연료*로 삼아 "과거엔 이래서 됐고/떨어졌으니 이 지침서에선 이걸 이렇게" 능동 처방. `_build_advisor_payload` 재사용. **무료 게이트: `collect_reference_context` 가 비면 LLM 미호출 sentinel(`has_accumulated_data=False`)** (연료 없는데 과금 방지). **오염 방지 — 교차 앵커**: `applications` 각 항목은 과거 교훈(`rooted_in`)+이 지침서 실제 사실(`basis`, p.N/항목명) **둘 다** 앵커, 못 달면 제외. 과거 공모 수치를 이 지침서 사실로 옮기기 금지·당락 예측 금지. 결정론 덮어씀: `data_basis`(표본 규모)·`scoring_focus`. 전제조건=DB에 같은 시설유형 과거 데이터 축적. 회귀: `tests/test_brief_playbook.py` (7). |
| `brief_playbook_report_generator.py` | `_playbook` → 자체완결 HTML (LLM 0, Report Generation Rule). 화이트 + 건원 RED. 2층 시각 분리: **과거·사실**(당선 교훈·낙선 함정·당락 축, 파란 `source` 칩=과거 공모명) vs **해석**(`applications`, "해석" 배지 + `rooted_in` 과거 앵커 + `basis` 이 지침서 앵커 동시 노출). 상단 표본 근거 밴드(win/lose/발췌 수)·범례·디스클레이머. `has_accumulated_data=False` 면 안내 카드만(graceful). `to_playbook_html()`. 데이터 `html.escape`. |
| `proposal_deck.py` | `_proposal` → **A3 편집가능 PPTX 장표 내용**(`deck_render/1.0`, LLM 0 · 새 숫자 0). **내용은 우리가, 그리기는 터읽기가** — `POST /deck/render` 가 그쪽 `app/deck/style.py` 의 A3 네이티브 편집가능 조각(`kpi_card`·`table`·`caption_band`)으로 그린다. 렌더러를 복제하지 않는다(deck-builder 가 접힌 교훈). 계약의 낱말은 **다섯뿐**(`cover`·`kpi`·`cards`·`table`·`text`) — 늘리면 그 앱이 우리 도메인을 알기 시작한다. 장 순서 = **임원 발표 순서**(사실 → 배점 → 5안 → 권장), 결정 요약만 맨 앞(결론 먼저). 판단(`cockpit_cells`·`_recommend`)은 **HTML 덱과 같은 함수**를 불러 쓴다(드리프트 차단). 슬라이드마다 `sources` 에 `basis` 를 실어 터읽기가 **캡션 밴드에 근거를 찍는다**(PPTX 는 `data-ev` 를 못 단다). 한 장 상한(kpi 4·cards 4·rows 12)은 **우리가 먼저 나눠** 보낸다 — 잘린 안은 회의에서 없는 것으로 읽힌다(5안은 3장씩, 사업 규모는 부지 제원/사업비 2장). 못 만든 장은 `missing` + **덱 마지막 장**에 사유를 적는다(헤더는 latin-1 이라 한글을 못 싣고, 파일만 들고 가는 사람에겐 헤더가 없는 것과 같다). ⚠**`filename` 은 ASCII 필수** — 터읽기가 그 값을 그대로 `Content-Disposition` 에 박는다(한글이면 **그쪽이** 500). 한 장 상한은 `CARD_BODY_MAX`(290자)까지 — 터읽기 카드 본문 박스는 **고정 높이**라 넘친 글자는 줄어드는 게 아니라 카드 밖으로 흘러넘친다(실측 영등포 296~348자). 자를 땐 어절 경계를 찾는다(「…예정돼(placem…」 방지). 회귀: `tests/test_proposal_deck.py` (25) · `tests/test_proposal_deck_route.py` (9). |
| `teoilgi_client.py` | **터읽기(arch-site-context) 형제앱 연동** (2026-07-09) — `POST /board {brief:true,synthesize:false}` 로 **실측** 대지 맥락(전국=100 인구지수·근접도·수급진단·재해·★지배 설계 드라이버) 취득. vision(vworld_analyzer)을 대체 않고 **보강**: 정량·사실은 measured 우선, vision 은 형상·조망 시각판독. `FACILITY_TO_USE_TYPE`(14종→주거/상업/의료), env `TEOILGI_BOARD_URL`(기본 Cloud Run). graceful(실패→None, 제안서는 vision 만으로). `routers/brief.py` 가 `_site_context.measured` 로 병합, `brief_proposal._measured_digest`가 프롬프트 주입(터읽기 ②AI판단·notes 제외 = 경계: 우리는 제안서 컨셉안 소유, 터읽기는 사실+드라이버까지). 회귀: `tests/test_teoilgi_client.py` (6). **`render_deck()`(2026-08-27)** 는 `POST /deck/render` 로 `deck_render/1.0` → PPTX bytes — `board_brief` 와 달리 **graceful 하지 않다**(사용자가 파일을 기다리는 자리라 조용한 None 은 「왜 안 받아지지」가 된다). 실패는 이유를 들고 raise → 라우터가 502. |
| `arch_law_client.py` | **arch-law-diagnose(건축법 자동진단)+graph 형제앱 연동** (2026-07-14, Phase 2·3, prod 활성). feasibility_export 허용 한도로 **최대 매스 역산**(모드 A) → `POST /api/diagnose`(공개 배포 URL 기본값, `ARCH_LAW_API_URL` override, **always-on**·`ARCH_LAW_DISABLE=1`로만 끔) → 정북 일조사선·가로구역 최고높이·건폐/용적 한도·심의여부 되받아 배치 **법적 골격**. `to_request`·`diagnose`(timeout 120·graceful)·`digest_diagnosis`(골격 추림+null가드+low_confidence+limit_mismatch+law_refs). ⚠**계약**: `applicable_reviews` 는 dict `{items[],required_count}`(배열 아님 — items[] 순회), severity=REQUIRED/**MAYBE**/NONE, `높이_일조.pass` 는 envelope 모드 **항상 null**(low_confidence 판정 제외 — 건폐/용적 pass만 유효). **Phase 3**: `graph_url`+`fetch_law_texts`(arch-law-graph `/api/lookup`, 조문 원문·found+content만·graceful). **시행일(2026-08-27)**: graph F-1·F-4 로 생긴 `ef_yd`(조문 시행일, **중앙법령 조문만**)·`law_ef_yd`(법규 판본 시행일, 조례·고시·별표는 이쪽만)를 **키째 보존**하고 `effective_label()` 이 표기로 바꾼다 — 조문일 있으면 「시행 2026-02-27」, 없으면 **법규임을 밝혀** 「법규 시행 2026-07-13」(graph 웹앱 `data.js efInfo` 와 같은 규칙). ⚠**두 필드를 섞지 말 것** — 법제처가 자치법규엔 조문시행일을 안 준다(조례 88조문 전부 null). 판례·해석례는 `law_ef_yd:null` → 표기 없음. 라이브 검증(2026-08-27): 건축법 제42조 `20260227` · 시행령 제86조 `20260728` · 서울 도시계획 조례 제55조 `ef_yd=""`+`law_ef_yd=20260713`. 소비: `_law_diagnosis_html` 각주 배지(`.law-ef`) · `_md_site_law_block` 「근거 조문」 목록(md·HWPX 로도 출처가 따라간다). `routers/brief.py` 4.7 이 부지별 `asyncio.gather` 병렬 진단→`_site_context.law_diagnosis`(+`law_texts`), `_law_diagnosis_html`(brief_proposal_report_generator, brief_checklist_exporter 공용)이 법적 골격 패널+조문 각주 렌더, `brief_proposal` 이 placement 법근거 주입. 배포: `deploy.yml --update-env-vars` 에 `ARCH_LAW_API_URL` 고정. 회귀: `tests/test_arch_law_client.py` (20, 네트워크 0). |
| `vworld_analyzer.py` | 지침서 "대지·맥락 분석" — 주소→지오코딩→VWorld 위성(WMTS)+지적도(WMS) 합성→Claude Sonnet vision 판독. 지침서 분석 완료 후 `feasibility_export.sites[0].address` 로 자동 실행 (키 있을 때만, 실패해도 비치명). 위성은 **WMTS 전용**(WMS GetMap 미지원), 지적도는 **WMS 전용**(WMTS 미제공) — 레이어명 `lp_pa_cbnd_bonbun,lp_pa_cbnd_bubun` (구 `lp_pa_cn_A` 는 오타, 확인은 GetCapabilities로). 광역 위성(zoom16, 3×3≈1.8km) **중앙**에 지적도를 고해상(900m@768px≈1.2m/px) 요청 후 비례 축소·합성 — 스케일 임계는 **절대 span 아닌 m/px**. `has_cadastral` 플래그가 `_site_context`·vision 프롬프트·제안서 썸네일 캡션까지 전파. 빈 타일·오프셋 이탈·PIL 에러는 위성 단독 폴백. **실측 필지 경계 (2026-07-29):** `_fetch_parcel_polygon()` 이 VWorld **2D데이터 API GetFeature**(`LP_PA_CBND_BUBUN`, geomFilter=POINT)로 필지 벡터 폴리곤을 병렬 취득 → `_geom_outer_rings`+`_project_ring_norm`(WGS84→3857→이미지 정규화 0~1)으로 `parcel_norm` 반환(실패 시 None, graceful) — 제안서 배치도 위성 오버레이가 빨간 실측 경계선으로 렌더. `GET /brief/{id}/site-context` 로 서빙. 회귀: `tests/test_vworld_analyzer.py` (13, 네트워크 0 — bbox/m/px 기하 + 필지 투영). |
| `proposal_number_check.py` | 제안서 prose **근거 없는 수치 검산** (LLM 0 · 숫자 수정 0, `quant_validator` 의 제안서판). `check_proposal_numbers(proposal, brief_data)` — `_proposal` 의 LLM 작성 서술에 나온 수치를 코퍼스(brief_data 전체 + 결정론 scoring_focus)와 대조해 원천에 없는 숫자만 flag (분양가·ROI 등 발명/일반지식 수치가 사실처럼 새는 것 차단). basis(근거 인용)·메타 제외. **2-pass:** ① **위험 단위 쌍**(억/만원/원/%/세대/가구/호)에 붙은 수치는 `(숫자,단위)` 쌍으로 대조 — 자릿수 무관, 소액 발명(공실률 12%·30억·480세대)까지 포착 ② 그 외 **bare 다자리** 수치는 코퍼스 막대조(한 자리 구조 숫자 1순위·5안 제외). 코퍼스는 over-permissive(false positive 회피), 단 위험 단위만 쌍 정밀도. 배점 비중 'N%'는 scoring_focus weight_pct 로 허용(오탐 방지). `_propose_sync` 가 `result["_number_flags"]` 부착(비치명), 렌더러가 "근거 미확인 수치" 경고 밴드로 노출. **구조 검사 추가(2026-08-27) `check_unanchored_claims()`** — concept-studio `render/numbers.py` 원리를 우리 데이터 모델로: `basis` 앵커가 **계약상 필수인 블록**(win_themes·design_directions·program_directions·massing_strategy·phasing·placement zones·risks)이 수치를 들면서 `basis` 가 비면 flag → `_unanchored_flags`. **코퍼스 검사와 잡는 것이 다르다** — 코퍼스=지침서 어디에도 없다(*지어냈다*), 구조=숫자는 있는데 출처를 안 밝혔다(*확인할 수 없다*). 임원이 「그 숫자 어디서 났습니까」 묻는 자리는 후자. ⚠`basis` 칸이 **없는** 블록(executive_summary·kickoff_checklist·caveats·open_questions)은 검사 제외(없는 칸을 비었다고 나무라면 헛경고) · ⚠`risks[].basis` 만 **문자열**(나머지 리스트) · 항목당 flag 1개(목록 길면 아무도 안 읽는다). ⚠**빌드를 세우지 않는다** — concept-studio 는 모든 수치가 레지스터 소속이라 하드 게이트가 가능하지만, 우리 제안서는 지침서 수치를 산문에 인용하는 자리가 정당하게 많아 렌더를 막으면 정당한 산출물이 안 나온다. 회귀: `tests/test_proposal_number_check.py` (11) + `tests/test_unanchored_claims.py` (22). |
| `grade_helpers.py` | 등급 단일 소스. `GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade()`. 모든 리포트 generator 가 공통 import. |
| `requirement_coverage.py` | 지침서 요구 **완결성 감사** (LLM 0 · 매트릭스 수정 0, `quant_validator`·`citation_check` 의 요구사항판). 진단은 이미 `requirement_mapping`(요구·축·충족여부·근거) 표를 내지만 **그 목록을 LLM 이 고른다** — 분모(`_requirements.requirements`)의 어느 항목이 표에 안 나와도 표는 멀쩡해 보이고 없는 줄은 안 보인다. `check_coverage()` 가 분모×분자를 대조해 **N개 중 M개**를 세고 빠진 요구를 이름 대고 말한다(**탈락은 누락에서 난다**). 매칭은 **포함 계수**(교집합÷짧은 쪽) — LLM 요약 30자 vs 지침서 장문이라 길이 비대칭에 Jaccard 는 같은 항목도 낮게 나온다. 문턱 `MATCH_MIN=0.50`, 같은 축이면 `AXIS_MATCH_MIN=0.30`(관대 — 헛경고 하나가 진짜 누락 열 개의 신뢰를 깎는다). **일대일 매칭 안 함**(중복 요구를 누락으로 세우면 헛경고) · 요구 0건이면 `coverage_pct: None`(**0% 아님** — 잴 것이 없는 것과 못 맞춘 것은 다르다) · `unanchored`(요구에 안 붙는 표 항목)는 추출 누락일 수도 있어 **단정 않고 이름만**. 소비: `comparator._run_diagnose_sync`(→`_requirement_coverage`) · `diagnosis_report_generator._render_requirement_mapping`(제목 옆 카운트 + 누락 경고 밴드, 표가 비어도 경고는 낸다). 회귀: `tests/test_requirement_coverage.py` (20). |
| `citation_check.py` | LLM 서술의 `(p.N)` 인용 **사후검증** (LLM 0 · 텍스트 수정 0, `quant_validator` 의 인용판). `collect_page_bound`(total_pages 우선, 없으면 관측 `_page` 최대, 둘 다 없으면 검증 스킵) 로 유효 상한 잡고 `1..bound` 밖 인용만 flag (관대 — 문서 안 페이지는 태깅 안 됐어도 통과, `(p.?)` 허용). 소비: `comparator._run_compare_sync`(→`_citation_flags`, compare+cross 커버)·`_run_diagnose_sync`·`myproject_analyzer.deep_analyze`. `flags_band_html()` 경고 밴드는 `report_theme.warning_band` 공용 shell 사용. 회귀: `tests/test_citation_check.py`. |
| `report_badges.py` | 사실/해석 2층 분리 렌더 헬퍼 (LLM 0 · 인라인 스타일). `ai_badge()`(해석 배지 — 기본 문구 "해석", **색=`var(--ai)` 테마 토큰** — 제안서 "제안"·플레이북 "해석" 칩과 통일)·`fact_interp_legend()`. 진단(recommendations)·비교(당선/낙선 사후요약) 리포트에서 추론을 사실과 구분. 회귀: `tests/test_report_badges.py`. |
| `report_theme.py` | 자체완결 리포트 HTML **공유 디자인 토큰 단일 소스**(건원 RED + 명조/Montserrat). `THEME_VARS`(:root 팔레트·폰트), `inject_theme(css)`(`/*__THEME__*/` 마커 치환 — 마커 없으면 예외로 silent no-op 방지), `warning_band(title,rows)`(citation_check·quant_validator 경고 밴드 공용 shell), `CATEGORY_COLORS`(카테고리형 스택/조닝 다이어그램 공용 8색 팔레트 — proposal `_ZONE_COLORS`·checklist 면적 스택 공유). 7개 generator(report/diagnosis/myproject/submission/playbook/checklist/proposal)가 주입. 리포트는 자체완결이라 프론트 `kunwon-tokens.css` 못 써 Python 상수 공유. **새 리포트 generator 는 THEME 주입 필수.** 회귀: `tests/test_report_theme.py`. |
| `utils.py` | PDF rasterizer (`rasterize_pdf` PyMuPDF), SSE helper, `parse_json_response()` 3단계 복구, 공유 dict 헬퍼 `_first()` / `_as_list()`, `user_error_msg()`, `normalize_design_guidelines_grouped()`, **`html_file_response()`** — 자체완결 HTML 리포트 서빙 단일 소스(inline/`?download=1` attachment 분기, 한글 파일명은 RFC 6266 `filename*=UTF-8''` + ascii 폴백 — 헤더에 한글 직접 넣으면 latin-1 인코딩 500). accumulate/brief/diagnose 라우터 공용. 회귀: `tests/test_brief_export_serving.py` (6). |
| `readme_renderer.py` | 도움말(`/api/readme`) 단일 소스. `README.md` 원문 → 화이트+건원RED 자체완결 HTML. LLM 호출 없음. `markdown`(tables/fenced_code/sane_lists/toc + `slugify_unicode` 로 한글 목차 앵커 동작) 사용, 렌더 실패 시 `<pre>` 폴백. 외부 링크는 새 탭, 로컬 문서 링크(DEVELOPER.md 등 미서빙)는 클라이언트 스크립트가 비활성화. 별도 `README.html` 미유지 → 드리프트 없음. |

### Core Services 상세 (표에 담기엔 긴 항목)

표 셀 하나에 담기엔 너무 긴 두 파일의 전체 내용. 표에는 요약만 남겨두었다.

#### `brief_proposal.py`

지침서 "프로젝트 수주 제안서" (**전략가**: `brief_advisor` 가 사실 triage(해설가)라면 이쪽은 앞을 보는 처방 — 수주 핵심 테마·설계 접근 방향·착수 우선순위·리스크/대응·착수 체크리스트).
`propose_project()` (LLM 1콜, Opus `settings.model_id_advisor`, `max_tokens=16000`, comparator 패턴).
결정론 백본 **단일 소스 재사용** — `brief_advisor._build_advisor_payload()` + `compute_scoring_focus()` 그대로(드리프트 차단), 기존 `_insight` 는 `_prior_insight_digest()` 로 토대 요약 주입.
**사실/제안 2층 분리**: 사실 주장(지침서가 요구·강조·배점하는 것)엔 근거 인용 강제, 전략·접근은 제안으로 명시.
가드: 사실근거한정·인용형식(페이지 추측 금지)·당선 보장 금지·약하면 약하다고.
배점은 결정론 `scoring_focus` 로 덮어씀(LLM 환각 차단).
caveats 에 "실제 심사 결과 보장 못 함" 강제.

**설계 계약(사용자 결정 2026-06-25/2026-06-26 갱신):**

- `executive_summary` 첫 줄 = "발주처가 진짜 원하는 것"(배점 쏠림으로 읽은 parti)
- `win_themes` **1~2개로 압축**(좁힘)
- `design_directions` **상호 배타 컨셉 5안 고정**(펼침, 변주 아닌 전제가 다른 5개; 이 필드만 triage 예외)
- `risks` 2층(명시 실격/제약 + 반복강조→'흔한 감점 함정' 추론, 단정 금지)

**'변수' steering v1(2026-07-29):** `propose_project(brief_data, facility_type, steering=None)` — steering(list[str], 누적 지시) 있으면 user content 에 **3번째 텍스트 블록**(`_steering_block`, cache_control 없음 — block1/2 캐시 prefix 유지로 반복 루프 입력 캐시 히트) 추가. `_STEERING_RULES`: 해석층만 반영·A층 사실(배점·필수제약·required=true 배치·인용) 불변·충돌 시 사실 우선+사유는 open_questions·새 숫자 사실화 금지. 결과에 `_steering_applied` 부착(렌더 안 함 — 사용자 결정: 리포트 미표시, 내부 감사용). 없으면 기존 경로와 바이트 동일. 회귀: `tests/test_brief_proposal_steering.py` (14).

**패턴 결합(2026-06-26 추가):** `_pattern_signals(facility_type)` 가 `load_pattern()` 으로 동일 시설유형 당선·낙선 경향을 `payload["pattern_context"]` 로 주입.
사실 근거 인용 금지·전략 힌트 전용·N≤2 는 약신호 명시 — 지침서 우선 원칙 유지.

**AI 해석 확장층(시퀀스 E Phase 2, 2026-06-29):** `design_directions` 에 `scoring_play`(득점)·`site_rationale`(이 부지라서) + 신규 `program_directions`/`massing_strategy`/`phasing`(각 `{claim, basis}`).
1층 사실 위 추론을 펼치되 **각 claim 에 basis 앵커 강제**(앵커 못 달면 제외), **새 숫자를 사실로 만들기 금지**(가정은 open_questions/caveats).

#### `brief_proposal_report_generator.py`

`_proposal` → 자체완결 HTML (LLM 0, Report Generation Rule). 화이트 + 건원 RED, 상단 nav.

**시퀀스 E Phase 1(2026-06-29, 밀도 업그레이드):** 덱 최상단 **히어로**(위성+지적도 실측 이미지 + 대지 요약 — "상상 아닌 실측" 첫인상, `_hero_html`) + **사업 규모 팩트 밴드**(`feasibility_export` 실추출 수치 대형 숫자, `_facts_band_html` — 첨부물의 날조 분양가/ROI 정반대로 지침서 사실 숫자만).
히어로가 이미지 보이면 대지 섹션은 compact(필드·주의만, b64 중복 0). `to_proposal_html(site_image_b64=, feasibility=)`. brief.py propose 가 주입.

**시퀀스 E Phase 2(2026-06-29, 해석 확장층):** 상단 **명시적 범례**(근거 칩=사실 vs "제안" 배지=추론, `_legend_html`) + 설계 5안 카드에 득점·이 부지라서 필드 + 신규 해석 섹션 **프로그램 방향·매스 전략·단계 접근**(`_interp_section`, 각 항목 근거 앵커 + "제안" 배지) + 하단 **근거 미확인 수치** 경고 밴드(`_number_flags_html`, `_number_flags` 있을 때만). ("AI 해석" → "제안" 문구 전환 2026-07-29 — 2층 구분 구조는 동일.)

섹션 순서: 전략요약 → **사업 규모**(옵션) → **대지·맥락 분석**(옵션, `_site_context` 있을 때만) → 배점 무게중심 카드(결정론 scoring_focus 상위) → 수주 핵심 테마 → 설계 접근 방향 → 착수 우선순위(rank 정렬) → 리스크·대응(severity 정렬) → 착수 체크리스트 → 발주처 확인 → 한계.

**대지 섹션:** `to_proposal_html(site_context=, site_image_b64=)` 받으면 전략요약 직후 삽입 — VWorld 위성 썸네일(base64 임베드, 자체완결 유지) + overall_summary + 5개 판독 필드(향/도로/주변/자연/특이) + "위성 AI 판독 기반·현장 확인 필요(추론 포함)" 라벨 고정.
brief.py propose 가 `_brief.json._site_context` + `{brief_id}_site.jpg` 로 주입. 데이터 `html.escape`. 빈 섹션 graceful skip.

상단에 "수주 전략 가설 · 당락 예측 아님" 디스클레이머 고정. 회귀: `tests/test_brief_proposal_report.py` (72).

**Report Generation Rule:** `report_generator.py`, `submission_report_generator.py`, `diagnosis_report_generator.py`, `myproject_report_generator.py`, `brief_proposal_report_generator.py`, `brief_playbook_report_generator.py` 는 모두 Claude API 호출 금지. 기존 데이터를 HTML 로 렌더링만.

### Configuration

- `config.py` — `FACILITY_TYPES`, `PAGE_TYPES_META` (27개), `COMPARISON_AXES_BY_GROUP` (redev/general 8축씩), `RUBRIC_VERSION="v1"`, `MODEL_ID`, `MODEL_ID_CLASSIFY`, `MODEL_ID_ADVISOR`(Opus, AI 종합 해설 전용; `settings.model_id_advisor` 로 override).
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
7. **BriefMode** — 지침서 단독 분석. `accept=".pdf,.docx,.hwp,.hwpx"`. docx / hwp·hwpx 선택 시 "도면 포함 지침서는 PDF로" 안내. 블록 기반 포맷(docx/hwp/hwpx)일 때 flag location `p.N` → `블록 N` 치환 (`isBlockFormat`). "종합 해설 포함" 체크박스(기본 ON, **UI 라벨에서 "AI" 자기지칭 제거 2026-07-29**)로 `include_insight` 토글, 결과에 포함 배지 / 미포함 시 재생성 버튼(`reinterpretBrief`). 리포트/제안서 카드에 **다운로드 버튼**(`?download=1` → `utils.html_file_response` attachment). 이력 카드 "🛰 재분석" 토글 열 때 **알던 대지 주소 자동 채움**(`item.site_address`, 재입력 불필요). **'변수' 방향 지시 UI(2026-07-29):** 제안서 있는 결과/이력 카드에 "🎛 방향 지시" 토글(`steerId`/`steerText`) → `renderSteerPanel` 공용 패널(textarea 500자 + [✦ 방향 반영 재생성] + 지시 이력 리스트 + [↺ 지시 초기화]=confirm 후 clean 재생성). `handlePropose(briefId, {steering|resetSteering})` 확장, 성공 시에만 입력 클리어. 결과·이력에 **프로젝트 수주 제안서** 생성/열기 버튼(`proposeBrief` → `{brief_id}_proposal.html` 새 탭, `has_proposal` 배지) — 요약·정리를 넘어선 수주 전략 제안. 결과·이력에 **경험 기반 처방** 생성/열기 버튼(`buildBriefPlaybook` → `{brief_id}_playbook.html` 새 탭, `has_playbook`/'경험 처방' 배지) — 같은 시설유형 과거 축적 데이터를 이 지침서에 적용한 처방(과거 데이터 없으면 안내 메시지, LLM 미호출).

**Key components:** `useMeta()` 훅이 시설유형·페이지타입·평가축 한국어 레이블 단일 소스 (`/settings/meta` 1회 fetch). 하드코딩 금지. `useMeta.jsx` JSX 포함하므로 `.jsx` 확장자 필수.

### Styling

- 화이트 테마 + 건원 RED `#e60012`. **단일 소스: [frontend/src/kunwon-tokens.css](frontend/src/kunwon-tokens.css)** — `main.jsx` 에서 전역 import.
- 컴포넌트는 인라인 스타일에서 `style={{ color: 'var(--color-accent)' }}` 패턴. hex 직접 사용 금지.
- 신규 색 필요 시 `kunwon-tokens.css` 에 추가 (단일 소스).
- 자체완결 리포트 HTML(비교·진단·개별·MyProject·제안서·플레이북·체크리스트)은 독립 문서 — **`report_theme.py::THEME_VARS` 단일 소스**(건원 RED + 명조/Montserrat)를 각 generator 가 `inject_theme()`(`/*__THEME__*/` 마커) 또는 prepend 로 주입. 각 리포트는 레이아웃 CSS 만 자체 보유하고 색·폰트는 공유 토큰(`var(--accent)` 등) 참조. 프론트 `kunwon-tokens.css` 는 자체완결이라 못 씀. LLM 텍스트(강점/약점/notes/컨셉 등)는 `html.escape` 필수(마크업 깨짐 방지).
- 감사: `tools/audit_tokens.py` 실행 → `DESIGN_AUDIT.md`.

## Pipelines

### Accumulate (`POST /api/accumulate/run`)

1. Brief PDF (선택) + submissions JSON + PDFs 업로드.
2. classify → extract → `_brief.json` + `submissions/*.json` 저장.
3. 각 제출물 개별 HTML 리포트 즉시 생성 (`submissions/{slug}_{result}_report.html`).
4. **`run_compare`(폼, 기본 OFF·프론트 체크박스 기본 ON) 켜져 있고 제출물 2개↑이면** 여기서 `compare_submissions`+패턴+비교리포트+아카이브 재인덱싱까지 수행(`report_available:true`, `complete` 에 `comparison` 동봉). 비교 실패는 비치명(`compare_error` 고지, 추출물 유지). 꺼졌거나 <2 면 스킵.
5. SSE `complete` 발송 후 종료.

`run_compare` 껐을 때 비교분석은 **별도** — `ProjectList` 의 "비교분석 실행" 버튼 = `rerun-compare`.

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
6. **AI 종합 해설 (옵션, `include_insight` 기본 ON)** [4.5]: `brief_advisor.interpret_brief()` Opus 1콜(`settings.model_id_advisor`) → `brief_data["_insight"]` 임베드 (별도 파일 아님). 한 방 통합(diagnose 패턴), 실패해도 비치명적(추출 산출물 유지). `to_html`·`to_markdown`·`to_xlsx` **3종 모두** `_insight` 를 "종합 해설" 섹션/시트로 렌더(LLM 0; html 은 핵심수치 카드 직후, md 는 `## 0`, xlsx 는 맨 앞 시트). ⚠ 이 단계는 site_context(7단계) **이전**이라 자동 해설은 대지·법을 못 씀 — 그건 수주 제안서(8단계 propose)가 소비.
7. **대지·맥락 분석 (자동)** [4.7]: `feasibility_export.sites[]` 주소(또는 선택 입력 `site_address` override)로 **부지별 병렬**(`asyncio.gather`) — `vworld_analyzer.run_site_analysis`(vision, VWorld 키 有) + `teoilgi_client.fetch_board_context`(터읽기 measured) + `arch_law_client`(건축법 진단 `law_diagnosis` + graph `law_texts`). `_site_context` = 대표(첫 부지) analysis·measured + `sites[]`(전 부지 vision/measured, **다부지 비대칭 해소**) + `law_diagnosis`(전 부지)·`law_texts`. 전부 graceful. `site_address`(선택 Form) 로 지침서 미추출/오추출 주소 고정(첫 부지 대체·envelope 유지→law 작동, 부지 없으면 vision+measured만).
8. **수주 제안서 (옵션, `include_proposal` 기본 ON)** [4.8]: 분석 한 방에 `brief_proposal.propose_project()` (배점×대지실측×법 envelope×프로그램 종합→placement·법적 골격) → `_proposal` + `{brief_id}_proposal.html`. graceful. `_render_proposal_html` 헬퍼로 `/propose` 와 렌더 단일 소스.
9. `_brief_meta.source_format` (`"pdf"` | `"docx"` | `"hwp"` | `"hwpx"`) 기록.
10. 저장: `_atomic_write(json)` + `_sync_write(md)` + `_sync_write(html)` + `_sync_write_bytes(xlsx)`. **체크리스트 html/md/xlsx 3종 모두** `_site_context` 있으면 "대지·법적 골격" 섹션/시트 렌더(`_site_law_section_html`·`_md_site_law_block`·xlsx 시트, LLM 0 — 제안서 안 켜도 대지·법 표시).
11. SSE `complete`: `{brief_id, md/xlsx/html_filename, validation_summary, source_format, has_insight, has_site_context, has_proposal, proposal_filename, brief_genre}`.
12. 분석 후 별도 엔드포인트(추출 재처리 0): `POST /{brief_id}/interpret`(해설 재생성), `POST /{brief_id}/propose`(수주 제안서), `POST /{brief_id}/playbook`(경험 기반 처방), `POST /{brief_id}/site-analyze`(대지 재분석 — 주소 미입력 시 기존 `_site_context`/`feasibility_export` 주소 **자동 폴백**, `parcel_norm` 저장, **`_proposal` 있으면 LLM 0 으로 제안서 HTML 자동 재렌더** 후 `has_parcel`/`proposal_rerendered` 반환, 2026-07-29), **`DELETE /{brief_id}`**(파생 파일 전부 삭제 — `{id}.*`+`{id}_*` glob, ⚠**glob 메타문자 `* ? [ ]` 거부** 필수: `Path().name` 만으론 `DELETE /brief/*` 가 전 지침서 삭제).

### Diagnose

1. facility_type + submission PDF 업로드 (brief PDF 선택).
2. classify → extract → `_quantitative` 자동 집계.
3. 시설유형 패턴 retrieve (`loser_stats` 포함).
4. `diagnose_submission()` LLM 호출 → 당선 vs 낙선 대비 진단. 직후 `citation_check`(환각 쪽번호)·`requirement_coverage`(지침서 요구 완결성) 결정론 감사 부착 — 둘 다 LLM 0·수정 0·비치명.
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
            site_area_sqm, floor_area_ratio_pct, building_coverage_pct, max_height_m,
            floor_area_sqm }],                                     # 목표 연면적 (2026-08-27 추가)
  certifications: { green_building: "최우수"|"우수"|null, zeb_grade: 1~5|null,
                    renewable_pct: int|null, bf_grade: "최우수"|"우수"|null },
  construction_cost_100m_won, design_cost_100m_won, construction_period_months
}
```

1차(A~E): 재배치/정규화만. 2차(C 주차·D 용도지역·E 심의플래그): 이미 추출된 서술(brief_design_massing/zoning/special_conditions)을 **후처리에서 파싱** — vision 프롬프트 무관이라 BRIEF_* 분류·면적표 회귀 없음. `merge_extracted_data()` 가 brief 결과에 부착. `limits_determined_by="심의"` 면 60%/460% 등을 법정 한계로 보면 안 됨.

**`_brief.json` 의 `_site_context` (대지·맥락, `routers/brief.py` 4.7 조립, graceful):**

```text
_site_context: {
  matched_address, lat, lng, radius_m, has_cadastral,   # 대표(첫 부지) VWorld
  parcel_norm,                                           # 실측 필지 경계(이미지 정규화 0~1 링 배열) 또는 null — 2D데이터 API GetFeature
  analysis: { orientation, road_access, surrounding_uses, natural_assets, special_context,
              overall_summary, confidence, caveats },   # 첫 부지 vision 판독
  measured: {...},                                       # 첫 부지 터읽기 board_brief
  sites: [{ site_id, address, analysis, measured }],     # 전 부지 (다부지 비대칭 해소)
  law_diagnosis: [{ site_id, address, signal, overall_score,
                    envelope:{bcr_limit_pct, far_limit_pct},
                    height_solar:{shadow_applies, shadow_min_setback_m, shadow_setback_rule,
                                  north_setback_m, road_height_limit_m, parcel_north_depth_m},
                    reviews_required:[{name, law_ref, reasons}], has_required_review,
                    low_confidence, source_notes, limit_mismatch:[{field,brief_pct,diagnose_limit_pct}],
                    law_refs:[{name, url}] }],             # arch-law 진단 (전 부지)
  law_texts: { "<law_ref name>": {title, content, source_url, law_nm, article_no,
                                  ef_yd, law_ef_yd} }   # Phase 3 graph 원문(found만) + 시행일 2종
}
```

vision·measured·law_diagnosis·law_texts 각각 독립 graceful(하나 실패해도 나머지 유지). 소비: `brief_proposal`(placement 법근거)·`brief_proposal_report_generator._law_diagnosis_html`(법적 골격 패널+조문 각주)·`brief_checklist_exporter`(대지·법 섹션 html/md/xlsx). ⚠**모드 A(용량)**: `north_setback_m`·`road_height_limit_m` 은 지역·고시에 따라 null 흔함(정북은 `shadow_min_setback_m` 필요이격이 실신호), 건폐/용적 pass 는 한도맞춤이라 항상 true(가치는 limit 값·정북·가로구역·심의·mismatch).

**`comparison.json`:**

```text
{
  submissions: {company: {axis: {grade, strengths, weaknesses, brief_compliance, notes, grade_justification}}},
  ranking, blind_ranking,        # ranking = blind_ranking 호환용. gap_analysis 계산용으로만 내부 보존 — 비교 결과 화면엔 미노출(2026-07-01)
  key_differentiators, winner_strengths, loser_weaknesses,
  concept_comparison: {axis: "<Korean paragraph — 각 회사가 이 축에서 채택한 컨셉·설계방향을 (p.N) 인용과 함께 나란히 서술>"},
  gap_analysis: {blind_top1, actual_winners, top1_matches_winner, alignment, notes},  # 내부 QA 전용, 화면 미렌더
  rubric_version: "v1"
}
```

**`diagnosis.json`:**

```text
{
  axes: {axis: {grade, strengths, weaknesses, recommendations, evidence, grade_justification}},
  overall_grade, brief_compliance, requirement_mapping, pattern_deviation,
  strengths, weaknesses, recommendations,
  submission_quantitative, rubric_version: "v1",
  _requirement_coverage: {total, mapped, coverage_pct, by_status, unmapped[], unanchored[]}
}
```

`_requirement_coverage` 는 결정론 완결성 감사(`requirement_coverage.py`, LLM 0) — `requirement_mapping` 은 **LLM 이 고른 목록**이라 지침서 요구가 빠져도 표만 봐선 안 보인다. `total`=글이 있는 요구 수(분모) · `unmapped`=진단이 답하지 않은 요구 · `coverage_pct: null`=잴 요구가 없음(0% 아님). 매트릭스는 **안 고친다**(flag 만).

`grade` 는 `"A"|"B"|"C"|"D"|"E"|null`.

**`_brief.json` 의 `_insight` (AI 종합 해설, `brief_advisor.interpret_brief()` 결과, schema_version 1):**

```text
_insight: {
  schema_version: 1, brief_id, facility_type, generated_at, model_id,
  synthesis_summary: str,                                   # ① 평어 압축
  key_emphases: [{topic, signal_strength: "strong|medium|weak",
                  signals: [...], basis: [...], note}],     # 안전한 ②
  scoring_focus: [{category, points, weight_pct, shared_with, rank}],  # 결정론 (LLM 환각 차단용 덮어씀)
  must_not_miss: [{item, basis}],
  hidden_constraints: [{issue, basis, note}],
  reading_guide: [str], data_confidence: "high|medium|low", caveats: [str],
  _reference_cases: {...}                                   # reference_cases.collect_reference_context() 원본, 없으면 {}
}
```

`basis`/인용은 데이터에 실재하는 위치만 (`(p.N)` 또는 카테고리명) — 페이지 추측 금지. 외부 당락 예측 없음.
`_reference_cases` 는 동일 시설유형 **다른 공모**의 참고자료(렌더러 "참고 사례" 섹션용) — `reading_guide` 배경 참고로만 쓰였고, 이 지침서에 대한 사실 판단 근거로는 사용되지 않음.

**`_brief.json` 의 `_proposal` (프로젝트 수주 제안서, `brief_proposal.propose_project()` 결과, schema_version 1):**

```text
_proposal: {
  schema_version: 1, brief_id, facility_type, generated_at, model_id,
  executive_summary: str,                                  # 발주 의도 + 권장 전략 (제안형)
  concept_hook: {                                          # 덱 오프닝 컨셉 표지 파르티 (AI 제안 시안, 근거 없으면 LLM 생략)
    keyword, tagline,                                      # 한 단어 압축 + 3축 슬로건
    axes: [{term, ko, en, basis: [...]}] },               # 각 축 배점/대지/강조에서 도출·basis 앵커 강제
  win_themes: [{theme, rationale, scoring_link, basis: [...]}],          # 수주 핵심 테마
  design_directions: [{direction, narrative, addresses, scoring_play, tradeoffs, site_rationale, basis: [...]}],  # 설계 접근 5안 (Phase 2: narrative=2~4문장·득점·이 부지라서)
  program_directions: [{claim, detail, basis: [...]}],    # AI 해석층 — 프로그램 방향 (Phase 2, detail=2~4문장)
  massing_strategy:   [{claim, detail, basis: [...]}],    # AI 해석층 — 매스 전략 (Phase 2, detail=2~4문장)
  phasing:            [{claim, detail, basis: [...]}],    # AI 해석층 — 단계 접근 (Phase 2, detail=2~4문장)
  placement_strategy: {                                   # 대지 근거 배치 (2026-07-14) — 교차 합성
    synthesis, section_note,
    zones: [{program, plan: "N|S|E|W|NE|NW|SE|SW|C", level: "지하|저층|중층|상층",
             required: bool,                              # 지침서 명시 위치=true(사실·필수), AI 추론=false(제안)
             why, draws_on: ["대지:…","법:…","프로그램:…","배점:…"], basis: [...]}],
    alternatives: [{label, based_on, premise,             # 조닝 ALT (최대 3안, design_directions 연결) — compact zones
                    zones: [{program, plan, level, required}]}] },  # 사실-락: required 존은 zones(권장안) 기준으로 3안 동일 고정(brief_proposal._lock_placement_alternatives, LLM 0)
  priorities: [{rank, focus, why, scoring_weight}],        # 배점 기반 착수 우선순위
  risks: [{risk, severity: "high|medium|low", mitigation, basis}],
  kickoff_checklist: [str], open_questions: [str],
  scoring_focus: [...],                                    # 결정론 (LLM 환각 차단용 덮어씀)
  _number_flags: [{value, field, context}],               # 지침서에 없는 수치 (코퍼스 검사, 숫자 수정 0)
  _unanchored_flags: [{value, field, context}],           # 수치를 들면서 basis 를 안 단 주장 (구조 검사)
  _reference_cases: {...},                                 # reference_cases.collect_reference_context() 원본, 없으면 {}
  _steering_applied: [str],                                # '변수' — 이 제안서에 반영된 누적 지시 (렌더 안 함, _steering_log 와 일치)
  data_confidence: "high|medium|low", caveats: [str]
}
```

**`_brief.json` 의 `_merge_conflicts` (멀티파일 충돌, 파일 2개 이상일 때만):** `[{kind: "quantitative"|"site"|"block", key, chosen, chosen_from, others: [{value, from}], later_differs}]` — `chosen`=first_wins 채택값(**안 고침**), `others`=진 값과 그 파일, `later_differs`=나중 날짜 파일이 다르게 말함(정정 가능성 **힌트**, 판정 아님).

**`_brief.json` 의 `_steering_log` ('변수' 누적 방향 지시, 최상위 키):** `[{instruction, generated_at}]` — propose 성공 시에만 갱신(실패 시 미persist). `list_briefs` 가 instruction 배열로 노출(프론트 이력·초기화 UI 용).

`interpret`(=`_insight`, 해설가) 과 별개. 사실 주장엔 근거 인용 강제, 전략·접근은 제안으로 명시. `concept_hook` 은 덱 오프닝 **컨셉 표지 파르티**(keyword 한 단어 + 3축 tagline) — 배점 무게중심·win_themes·대지에서 도출하고 각 축 `basis` 앵커 강제(못 달면 축 제외, 3축 못 채우면 전체 생략), "아무 프로젝트에나 붙는 뻔한 슬로건" 금지. **사실 아닌 AI 제안 시안**(렌더에 배지+"팀이 갈아끼우는 출발점" 라벨) — 결정론 덮어씀 없음(LLM 생략 시 graceful). **당락 보장 금지** — caveats 에 "실제 심사 결과 보장 못 함" 강제. 별도 `{brief_id}_proposal.html` 로 렌더. **2층 분리(Phase 2):** `program_directions`/`massing_strategy`/`phasing` = AI 해석 확장층 — 1층 사실(배점·강조·대지) 위 추론, 각 항목 `basis` 앵커 강제, 새 숫자를 사실로 만들지 않음(가정은 open_questions/caveats). 렌더는 명시적 범례 + "제안" 배지로 사실과 구분("AI" 자기지칭 문구 제거 2026-07-29).

**`_brief.json` 의 `_playbook` (경험 기반 처방, `brief_playbook.build_playbook()` 결과, schema_version 1):**

```text
_playbook: {
  schema_version: 1, brief_id, facility_type, generated_at, model_id,
  has_accumulated_data: bool,                              # false = 과거 데이터 없음 (LLM 미호출 sentinel)
  data_basis: {win_n, lose_n, case_count, comparison_count},  # 결정론 — 과거 표본 규모 (LLM 환각 차단용 덮어씀)
  summary: str,                                            # 과거×현재 엮은 핵심 2~3문장
  winning_lessons: [{lesson, evidence, source, confidence: "strong|tentative"}],  # 과거·사실 (당선 교훈)
  losing_pitfalls: [{pitfall, evidence, source, confidence}],                      # 과거·사실 (낙선 함정)
  applications: [{guidance, rooted_in, brief_anchor, basis: [...], confidence}],   # AI 해석 (과거 교훈 × 이 지침서 교차 앵커)
  watch_axes: [{axis, why, source}],                       # 과거·사실 (당락 가른 축, key_differentiators)
  scoring_focus: [...],                                    # 결정론 (렌더러 배점 무게중심 참조)
  _reference_cases: {...},                                 # reference_cases.collect_reference_context() 원본
  data_confidence: "high|medium|low|none", caveats: [str]
}
```

`interpret`(해설가)·`propose`(전략가) 와 **별개인 세 번째 산출물**. advisor/propose 가 `reference_cases` 를 배경 참고로만 쓰는 것과 정반대 — playbook 은 그것을 **주연료**로 삼아 과거 당락→이 지침서 능동 처방. **핵심 오염 방지:** `applications` 각 항목은 과거 교훈(`rooted_in`)+이 지침서 실제 사실(`basis`, p.N/항목명) **둘 다** 앵커, 못 달면 제외 — 과거 공모 수치를 이 지침서 사실로 옮기기 금지. **무료 게이트:** `reference_cases` 비면 LLM 미호출·`has_accumulated_data=false` sentinel. 별도 `{brief_id}_playbook.html` 로 렌더(2층 시각 분리 + "해석" 배지). 당락 예측·보장 없음. 전제조건=DB에 같은 시설유형 과거 데이터 축적.

**`_brief.json` 의 `_brief_genre` (장르 판별, `brief_genre.detect_brief_genre()` 결과, schema_version 1):**

```text
_brief_genre: {
  schema_version: 1,
  genre: "competition"|"bid"|"unknown",       # 설계공모 / 설계자 선정 입찰 / 미확정
  confidence: "high|medium|low",
  bid_score, competition_score,               # 가중 점수 (축 3 + 텍스트 2)
  signals: {bid_axis, bid_text, competition_axis, competition_text}  # 히트 마커
}
```

결정론·LLM 0. `bid` = 입찰(자격·실적·가격 심사)이라 참여기술자(50)/유사용역실적(40)/신용도(10) 배점표를 **설계축으로 오인하면 안 됨** — validator 는 입찰의 설계지표(건폐율·용적률·연면적) 누락 경고를 스킵, advisor/proposal/playbook 프롬프트가 genre 로 해석 전환, exporter eyebrow·프론트 배지 표기. `unknown` 이면 데이터가 가리키는 대로.

**`_brief.json` 의 `_bid_structure` (입찰 2층 배점, `bid_structure.build_bid_structure()` 결과, schema_version 1, genre=="bid" 일 때만):**

```text
_bid_structure: {
  schema_version: 1,
  top_layer: {
    basis_dimension: "연면적"|"대지면적"|"unknown",   # 밴드 기준 차원
    thresholds_sqm: [80000, 240000],                # 정확 밴드 경계 (있을 때)
    axes: [{name, role: "pq"|"price",
            bands: [{label, min_sqm, max_sqm, weight_pct}],  # 정확 밴드
            weight_range: [lo, hi]|null}],           # 폴백(범위만 확보 시)
    applicable: {basis_value_sqm, band_label, weights: {축:%}, note}  # 기준값 확보 시만 채움
  },
  pq_detail: {total_points, categories: [{name, points}], source: "brief_evaluation"}
}
```

새 추출 없음(feasibility_export 패턴) — brief_evaluation 여러 페이지에서 상위층/PQ상세를 분리 식별(`_find_eval_pages`), 상위 밴드는 상위층 페이지 `evaluation_method` 서술 우선(run 안정적) → evaluation_criteria → requirements 범위 순. axis 는 `bands`(정확) 또는 `weight_range`(범위). **밴드 기준=연면적인데 연면적 미추출이면 적용 밴드 단정 금지**(대지면적 대체 추정 금지) — `applicable` 은 기준값 확보 시에만. 렌더는 심사기준 섹션 "2층 배점 구조" 블록.

**`_quantitative` 키:** `site_area_sqm`, `building_area_sqm`, `total_floor_area_sqm`, `area_above_ground_sqm`, `area_below_ground_sqm`, `floor_area_ratio_pct`, `building_coverage_ratio_pct`, `floors_above`, `floors_below`, `parking_count`.

**`_quantitative_flags` (제안서 추출 시 모순 있을 때만 부착, `quant_validator.validate_quantitative` 결과):**

```text
[{ rule: "coverage_mismatch"|"floor_area_below_far_implied"|"building_gt_site"
        |"far_above_ground_mismatch"|"out_of_bounds"|"coverage_gt_far",
   severity: "error"|"warn",
   fields: [<_quantitative 키...>],
   detail: "<한국어 사유>" }]
```

`error` = 항등식 위반(건폐율≠100×건축/대지, 총연면적<용적률×대지 등) → `pattern_builder._build_quant_stats` 가 해당 `fields` 를 그 제출물 집계에서 제외. `warn` = 소프트 신호(유지). **숫자는 절대 수정 안 함 (플래그만)**. brief 결과엔 미부착. 무료 감사: `tools/data_health.py` (LLM 0, `_quantitative` 정합 + 결측 + 비교 드리프트 + 패턴 N 점검, HARD 결함 수를 exit code 로).

## Conventions

- **Grading (내부 5-level A/B/C/D/E · 표시 3단계 우수/보통/미흡):** 점수 숫자 아닌 문자열. 임원 검토 시 정밀도 논쟁 차단 + 환각 검증 부담 감소. 구 `score`(0-10) 자동 변환: ≥8.5=A / ≥7=B / ≥5=C / ≥3=D / else=E. **내부(순위·차별화·패턴 계산)는 A~E 유지, 리포트/UI 뱃지·링 표시만 3단계 라벨**(A·B→우수 / C→보통 / D·E→미흡, 색도 3단계 collapse — 임원 요청 2026-07). 백엔드 `grade_helpers.py`(`to_grade`·`grade_label`·`grade_label_colors`·`grade_label_ring`), 프론트 `constants/index.js`(`toGrade`·`gradeLabel`·`gradeLabelColor`·`gradeLabelBg`; `GRADE_LABEL`/매핑은 백엔드 `GRADE_LABEL_3` 와 **동일 유지 필수**). ⚠**표시 코드에서 letter(A~E) 직접 노출 금지** — 반드시 `grade_label()` 경유(리포트 generator·프론트 grade 뱃지 전부).
- **2-pass Blind-Reveal:** Pass 1 에서 LLM 이 결과 라벨 모름 → 앵커링 차단. Pass 2 에서 실제 결과 공개 + 사후 분석 → `gap_analysis.alignment != "high"` 면 경고. 완벽한 익명화 아니지만 명시적 결과 라벨 제거가 최강 시그널 차단.
- **페이지 인용 강제:** compare/diagnose 프롬프트가 모든 strength/weakness/recommendation 에 `(p.N)` 형식 인용 요구. `_trim_extracted()` 가 `_page` 필드 보존.
- **Prompt Caching:** compare(2-pass)/diagnose 의 `system` + 정적/동적 content 블록 각각에 `cache_control: {"type": "ephemeral"}`. 5분 TTL, 캐시 히트 시 입력 90% 할인, 쓰기 1.25×. Sonnet 1024 토큰 이상만 캐시.
- **Prompt Templating:** `comparator.py` 는 `.replace("{key}", value)` 사용 — JSON 중괄호와 `.format()` 충돌 회피.
- **DPI:** classify 72 / extract 120. 150→120 변경으로 이미지 토큰 ~36% 절감.
- **Model:** 분류·추출·비교·진단·대지분석 모두 `claude-sonnet-4-6` (`MODEL_ID_CLASSIFY` 도 Sonnet — Haiku 헤더 환각 케이스 회피). **예외: AI 종합 해설·수주 제안서만 `MODEL_ID_ADVISOR`=`claude-opus-4-8`** (지침서당 각 1콜이라 비용 부담 작음, triage·종합문 품질↑; 사실 정확도는 결정론 백본이 정하므로 모델 무관). Opus·Fable·Mythos 는 `temperature`/`top_p`/`top_k` 미지원 → `llm_client._NO_SAMPLING_PREFIXES` 가 자동 생략(전송 시 400).
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
- **다단계 PQ 배점표 points_col 식별 (`_extract_docx_eval_from_table`):** 배점 컬럼은 `_points_header_rank()` 로 후보 점수화해 고른다 — "계산/산출/방법" 헤더(예 "점수 계산 방법" = 등급별 산출점수 컬럼)는 **배제**(-1), "배점/비중/가중" 우선(3), bare "점수"만 차선(1), 동점 시 최좌측. 단순 `if 비중|배점|점수|가중: points_col=i`(last-match)로 되돌리면 "점수 계산 방법"이 여러 번 나오는 사업수행능력(PQ) 표에서 배점 대신 등급점수·세대수 임계값을 배점으로 오추출(대치미도 입찰지침서: total 989.8, 정상 100). 또 pattern B(points 세로병합) 이름 수집은 `name_groups`(merge_info) 우선 — 다단계 col0 병합의 빈 하위 행이 이름 ''로 새지 않게(유사용역실적/신용도 귀속). 회귀: `tests/test_eval_table_multilevel.py` (4). ⚠️ 이 표는 **설계공모가 아니라 설계자 선정 입찰(PQ+가격)** 장르 — 파이프라인은 공모 배점표(합계 100 단일표) 가정이라 상위 사업수행능력%↔가격% 2층 구조와 3레벨 표는 여전히 부분적(카테고리 이름 반복). 근본 개선은 미착수.
- **BRIEF_EVALUATION 환각 방어 (5중):** ① `BRIEF_CLASSIFY_PROMPT` NOT 조건 (g)~(j) ② `_NOT_EVAL_HEADER_PATTERNS` 후처리 강등 (`상품 및 내용` 패턴 포함) ③ `MODEL_ID_CLASSIFY` Sonnet 유지 (Haiku 헤더 환각) ④ `FACILITY_CONFLICT_KEYWORDS` + `brief_validator._check_facility_keyword_conflict()` ⑤ `data_extractor` BRIEF_EVALUATION 프롬프트 "환각 금지 (CRITICAL)" 블록. 어느 하나 제거하면 청사 → 연구원 환각 재발.
- **BRIEF_EVALUATION null 점수 시맨틱:** `_check_points_mismatch` 는 `shared_with` 가 채워졌거나 numeric 합이 만점과 ±1 이내 일치 시 null 항목을 정성평가로 인정 (경고 X). 단순 `points is None → missing` 으로 되돌리면 영등포 (배치계획↔공간계획 병합, 설계의 적정성·창의성 정성평가) false positive 재발. 회귀: `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스.
- **환각 수치 패턴 유입 차단 (2단):** `quant_validator.validate_quantitative` 단일 소스로 ① `merge_extracted_data` 가 추출 직후 `_quantitative_flags`(제안서만, 숫자 수정 X) 부착 ② `pattern_builder._build_quant_stats` 가 **error** flag 필드를 패턴 집계에서 제외 (저장 플래그 없으면 재검증 폴백 — 구 레코드도 정화). ②(소비 측)를 빼면 하안주공·public-a 같은 오추출 수치(건폐율 27.46% vs 81.6% 등)가 시설 패턴을 다시 오염시킴. 효과는 패턴 재구축(rerun-compare) 시 반영. 회귀: `tests/test_quant_validator.py` (`TestPatternBuilderExcludesFlagged` 포함). 무료 감사: `tools/data_health.py`.
- **`_image_block()` JPEG 마법 바이트:** `img_bytes[:3] == b'\xff\xd8\xff'` 이면 `image/jpeg`, 아니면 `image/png`. 포맷 불일치는 400 원인.
- **API 키 BOM/zero-width 제거:** `config.py::_sanitize_api_key` 는 `.strip()` 외에 UTF-8 BOM(`﻿`)·zero-width 문자도 명시 제거. 메모장·PowerShell `Set-Content -Encoding utf8` 로 키 저장 시 선두 BOM 이 붙어 httpx 헤더 ascii 인코딩에서 `UnicodeEncodeError` 발생 (str.strip() 은 BOM 을 공백으로 안 봄). 회귀: `tests/test_pure_functions.py::TestSanitizeApiKey` 7 케이스.
- **BRIEF_DESIGN_* 그룹 처리:** `_process_design_group()` 그룹 내부는 **순차** 실행 (직전 페이지 컨텍스트 주입), 그룹간만 `asyncio.gather` 병렬. 그룹 내부 병렬화하면 컨텍스트 누적 깨짐.
- **design_guidelines_grouped 정규화:** 그룹 키 = `(facility_scope, section_path 첫 segment)` — space_scope 제외 (LLM 추출 불안정). exporter 는 `items_by_sub` 사용. `space_scope` 를 키에 다시 포함하면 비품창고 케이스 재발.
- **vMerge 감지:** `cell._tc` identity + tcPr `w:vMerge` element **두 시그널 조합**. 어느 한쪽만 쓰면 `merge_info` 가 빔.
- **rhwp `iter_blocks(recurse=False)` 필수:** 기본값 `recurse=True` 는 `TableCell.blocks`(셀 내부 문단)까지 재귀해 표 내용이 본문 블록으로 **중복 집계**됨. `split_hwpx_to_blocks` 는 `iter_blocks(scope="body", recurse=False)` 사용 (시그니처 드리프트 대비 `try/except TypeError → ir.body` 폴백). 회귀: `tests/test_hwpx_loader.py` 의 `_FakeIR` 가 `recurse is False` assert.
- **hwpx merge_info 는 docx 호환 스키마:** `_html_table_to_markdown` 이 `{row, col, merged_rows, value}` (세로병합만) 로 emit — `_extract_docx_eval_from_table` 가 이 키를 소비. `rowspan→merged_rows`, 가로병합(colspan)은 텍스트 반복(docx 동작). rhwp 원형 `rowspan/colspan` 으로 두면 BRIEF_EVALUATION 표 파싱이 `KeyError` 로 깨짐.
- **GCP 배포 확인:** `gcloud run services describe competition-analyzer --region asia-northeast3 --format="value(status.latestCreatedRevisionName)"` 로 최신 리비전명 확인. ⚠️ `metadata.creationTimestamp` 는 **서비스 최초 생성일**(리비전 시각 아님) — 실제 리비전 생성시각은 `gcloud run revisions list --service competition-analyzer --region asia-northeast3 --sort-by="~metadata.creationTimestamp" --limit=1`. 수동 fallback: `gcloud run deploy competition-analyzer --source . --region asia-northeast3`.
- **대지 주장은 공간 데이터 확보 전 추론 라벨 필수:** 위성·지적도 확인 전에 대지 특성(리버뷰/조망 등)을 단정하면 틀린 전제로 이어짐 (실제로 "강변 리버뷰" 오추론 → 위성 판독 후 "산을 낀 도심 부지"로 정정된 사례). `vworld_analyzer` 결과 없이 대지를 논할 땐 반드시 "추론·현장 확인 필요"로 표시.

## 보안 — 커밋 금지 파일

`.gitignore` 등록 필수, 절대 커밋 금지:

- `service.yaml` — Cloud Run 시크릿 평문 포함. 수정 시 로컬 편집 후 `gcloud run services replace service.yaml`.
- `gcp-sa-key.json`, `*-sa-key.json`, `key.json` — GCP 서비스 계정 키.
- `.env`, `env.yaml`.

`backend/app_settings.json` 은 추적 대상 (DB 경로·DPI·모델만). API 키는 메모리에만.

## Sequences (Future Work, 보류)

- **시퀀스 B — 추출 정확도 평가 하네스:** `tools/eval/` 폴더에 B-2 까지 구현. 재개 조건: 제안서 PDF 5건 + ground_truth JSON. 다음 단계 B-3 (CI 통합 훅). `python tools/eval/run_harness.py --pdf-dir pdfs/ --max-samples 5` 로 평가, `~$0.27/PDF`. `_quantitative` 키 10개는 `tolerance.json` 과 일치 필수.
- **시퀀스 C — 멀티파일 지침서 업로드:** ✅ 기본 구현 완료 (접근 A: `analyze` 가 `brief_pdf_refs` JSON 배열로 복수 파일 동시 분석, `_brief_meta.source_files: list[...]`, `_merge_multi_brief_data`). ~~**남은 보류: 충돌 우선순위**~~ **✅ 절반 해소(2026-08-27)** — 해소는 그대로 `first_wins` 지만 **더는 조용하지 않다**: 진 값이 `_merge_conflicts` 로 남고 체크리스트 HTML·md 에 경고로 뜬다(`brief_merge_conflicts`). 적어 뒀던 개선 방향(「숨기지 말고 경고로 노출해 사람이 판단」) 그대로. **자동 판정은 의도적으로 안 한다** — 같은 발주처 문서끼리는 권위 서열이 실재하지 않는다(상세는 Core Services 행).
- **시퀀스 D — 오프라인 / 제로-API 지침서 분석 (Claude Code 가 LLM 엔진):** API 토큰 절감용 **로컬·소량 전용** 경로. 동기: 파이프라인에서 LLM 필요 단계는 **classify / extract / requirements 3개뿐**이고 나머지(파싱·표 배점 파싱·`merge_extracted_data`·`validate_brief`·exporter)는 이미 결정론적 무료. DOCX/HWP/HWPX 는 **텍스트·표 기반(비전 불필요)** 이라 그 3단계가 "블록 텍스트 읽고 JSON 생성"에 불과 → **Claude Code(또는 claude.ai)가 직접 수행 가능**(구독 기반이면 API 미터 미사용, API 키 종량제면 과금됨). 구현안: `tools/analyze_brief_offline.py` — ① 결정론적 파싱 → 블록 + `source_text` + classify/extract 프롬프트를 파일로 출력, ② Claude Code 가 그 핸드오프를 읽고 classify/extract JSON 채움, ③ 다시 도구가 `merge_extracted_data` → `validate_brief` → 기존 exporter 로 **동일한 xlsx/html/md** 산출. 한계: **배포 앱엔 불가**(Cloud Run 서버는 구독 호출 불가, API 만 가능) · PDF 는 비전 필요로 핸드오프 무거움(DOCX/HWP/HWPX 가 최적) · 소량 수동 전용(배치 부적합). 같은 원리로 compare/diagnose 도 가능하나 제안서 PDF 는 비전+복잡해 손이 더 감.
- **시퀀스 E — 수주 제안서 비주얼 덱 출력 (`brief_proposal` 출력 고도화):** Phase 1(히어로+팩트밴드) ✅ / Phase 2(AI 해석 확장층·범례·근거 미확인 수치 밴드) ✅ / **Phase 3(매거진형 덱 재설계) ✅ 완료 (2026-07-13)** — 명조+Montserrat, 회색 위 흰 페이퍼, **결정 요약 cockpit**(6칸, AI 판단 응축+근거 앵커) + **권장 종합안**(5안을 뭉개지 않고 최고 배점축 뼈대+접목+조건부, KT 참고본의 "권장안+비교" 방식) + 입찰 2층 배점. 참고본(KT 명당 수동 생성본)의 **매거진 형식은 취하되 날조 수치는 거부**(근거·AI배지·근거미확인 경고 유지)가 핵심 결정. **남은 후보: takeaway 섹션별 한 줄(프로토타입엔 있으나 백엔드 미이식)·본문 문장 축약·논리 사슬/결정 변수 강화.** 현재 `brief_proposal_report_generator.to_proposal_html` 은 *보고서형*(스크롤 섹션). 사용자 피드백으로 **PPT형 스크롤 덱**이 더 낫다고 확정 — 향후 그 양식을 앱 기본 출력으로 이식. 디자인 계약(수동 검증 완료): ① **하나의 통일 캔버스**(섹션별 배경색 분리 금지 — "페이지 나눈 느낌" 역효과) ② 글을 줄일 땐 **삭제 말고 도식·아이콘으로 치환**(SVG: 맥락 개념도·100칸 와플 배점·매트릭스+상세카드·단면 긴장도·인허가 타임라인) ③ **밀도 높게**(나란히 배치) ④ 5안은 매트릭스(한눈) + **상세 카드**(공간전략/득점/포기/이 부지라서 + 매스 실루엣)로 — 이게 사용자가 "최종적으로 얻고 싶은" 산출물 ⑤ 매스는 *평면 만화 금지*(실무자 역효과), 측면 개념 실루엣까지만. 참고 산출물은 수동 생성본(시퀀스 D 경로) 존재. Phase 1 히어로는 사용자가 디자인·표현·이미지 해석 로직 불만족(2026-06-29) → Phase 3에서 히어로 재설계 포함.
- **시퀀스 F — 대지·맥락 분석 통합:** ✅ 구현·자동 파이프라인 통합 완료 (2026-06-26~29, 위성+지적도 하이브리드 단일 이미지). 상세는 Core Services 표의 `vworld_analyzer.py` 참조. 남은 보류: ③ SketchUp MCP 3D 매스 — 사용자가 자료 줄 때 재개.

## 당면 TODO (2026-08-27 갱신)

**전략 방향 (2026-07-29 사용자 결정):** 큰 그림은 터읽기·site-model·law-graph 를 합친 통합 제안서지만, **임원이 통합 산출물을 이해 못 하고 특히 믿지 못하는 게 병목** → 통합보다 **각 앱 개별 산출물의 신뢰성 강화가 우선**. 렌즈: "임원이 이 숫자·판단의 출처를 즉시 믿을 수 있나". 관련: A층(지침서만으로 나온 사실·전략, 결정론) 우선 노출, 임원 발표 PPT(사실→배점→방향성 5안+권장) 순서가 기준 레퍼런스.

**'변수' 프로토타입 v1 구현 완료 (2026-07-29):** 변수 = 정답이 하나가 아닌 지점(변수-1 공공성 해석, 변수-2 관점·테마 부여)에서 **사용자가 LLM 과 대화를 반복하며 컨셉을 조종**하는 루프. v1 = propose 확장(steering 누적 지시 → 해석층만 재생성, A층 구조적 불변) + BriefMode "🎛 방향 지시" 입력창 UI. 상세는 brief_proposal/브리프 라우터/BriefMode 항목. **목표 재정의(2026-07-29 사용자):** 핵심 가치 = **실무자가 현상설계 초반 머릿속으로 생각하는 시간 단축** — 덱은 결론 먼저(cockpit 최상단) 유지가 맞음. 후속 로드맵: ~~P1 한 문서화~~ **✅ 완료(2026-07-29)** — 면적 스택 S8(`program_stack_html` 공용 헬퍼)+지침서 강조요소 S10(`_emphases_html`)을 제안서 덱에 이식(LLM 0, 문서 왕복 제거) → P2 변수 버전 비교(v2) → P3 변수-1/2 프리셋 버튼. ⚠**"임원 보고 모드"(덱 사실-먼저 재배열 별도 뷰)는 만들지 않기로 사용자 결정** — 재제안 금지. 메모리 `project_byeonsu_conversational_steering` 참조.

**대지 배치 다이어그램 재설계 완료** (2026-07-29 세션): 배치도 top-view(방위만, 층은 카드로 분리)·위성 오버레이+실측 필지경계(`parcel_norm`)·조닝 ALT 2안·"AI" 자기지칭 라벨 제거("제안")·재분석 자동 재렌더+주소 자동채움·`html_file_response` 다운로드. 전부 배포됨.

**대지·법 연동 대작업 완료** (2026-07-14 세션) — 아래 1~4 는 다 끝남:

1. ~~placement_strategy 부지별 다이어그램 분리~~ **✅** — zone 에 `site` 필드 + 프롬프트 규칙, 렌더러 부지별 블록(헤더+조닝/단면 쌍+카드) 분리(번호·색 통합). 단부지 불변.
2. ~~Phase 1 — 대지 실측을 배치 근거로~~ **✅ (전제 규명)** — 조사 결과 placement 메커니즘은 **이미 작동**(site_context 있으면 방위 근거 살아남, 0629 서측 저수지→W/SW 활용). "남북 쏠림"은 데이터 없을 때 증상이었음. 부수: **다부지 vision/measured 비대칭 해소**(전 부지 각각), **선택 대지 주소 입력**(`site_address`, 지침서 미추출/오추출 고정).
3. ~~Phase 2 — arch-law-diagnose 연동~~ **✅ prod 활성** — `arch_law_client` 되받기(정북·가로구역·envelope·심의) → 법적 골격. 공개 엔진 기본 URL·always-on·`deploy.yml` env 고정. **계약 버그 2건 수정**(applicable_reviews dict·envelope pass null)·라이브 검증 완료. 상세는 Core Services `arch_law_client.py`.
4. ~~Phase 3 — arch-law-graph 조문 원문 각주~~ **✅** — `law_refs`→graph `/api/lookup`→`law_texts`, 법적 골격 패널에 원문 `<details>` 각주(없으면 law.go.kr 링크만).
5. ~~수집↔해석 단절·자동 산출물 미표시~~ **✅** — `include_proposal` 토글(분석 한 방에 제안서까지)·체크리스트 html/md/xlsx 에 "대지·법적 골격" 섹션(제안서 없이도 대지·법 표시).

**남은 것:**

- **컴플라이언스 매트릭스 ✅ (2026-08-27)** — kunwon-ops `benchmark-2026-siblings.md §6` 이 우리 앱에 지목한 상용 갭 3개 중 첫째. 조사 결과 **매트릭스 자체는 이미 있었다**(진단 `requirement_mapping` 표) — 진짜 갭은 **완결성**이었다: 그 목록을 LLM 이 고르므로 지침서 요구가 빠져도 표는 멀쩡해 보인다. `requirement_coverage.py`(LLM 0)가 분모×분자를 대조해 「요구 N개 중 M개 응답」과 누락 목록을 낸다. 요구 인벤토리 자체는 체크리스트 4절에 이미 있어 새로 만들지 않았다. ⏸ **Go/No-Go 는 보류** — kunwon-ops 판단대로 "참여할지 말지를 남에게 권하는 기능"이라 설문으로 본인 외 실사용자가 확인된 뒤.
- **발표 장표 PPTX ✅ (2026-08-27)** — `POST /brief/{id}/deck` → 터읽기 `POST /deck/render`(`deck_render/1.0`) → **A3 편집가능 PPTX 14장**. 임원이 통합 산출물을 못 믿는 병목("출처를 즉시 믿을 수 있나")에 대한 첫 조치 — 덱이 임원 발표 순서(사실→배점→5안→권장)를 그대로 따르고 슬라이드마다 근거가 캡션 밴드에 찍힌다. LLM 0 · API 키 불필요 · 형제앱 수정 0(그쪽이 이미 배포한 엔드포인트). 라이브 검증: 52.5KB · 네이티브 표 6개. 다음 후보는 같은 경로의 **HWPX 내보내기**(터읽기 `/board/hwp` 가 쓰는 kordoc `markdownToHwpx`, 우리 `to_markdown` 이 이미 재료).

- **개념 매스 다이어그램 ✅ (2026-07-29~30)** — `brief_massing.py` 부지별 **가로 바**(용적 봉투 vs 지상 프로그램 vs 지하 + 용적 상한 세로 점선, 초과 시 지하 재검토 신호), 제안서 덱 '개념 매스·용적 봉투' 섹션. 실무자 표준 2D(NYC 용량 스터디) — 아이소메트릭 3D·세로 타워 거부(비표준·여백 과다, 사용자 확인). 건폐·용적·높이한도 결정론, LLM 0. ⚠지상/지하 분리 한계(시설 소계 혼재) 정직 고지. 정북 계단컷 미반영.
- **Phase 4(보류) — SketchUp MCP 3D 매스**. 근거(placement·법적 골격) 풍부해진 뒤 형태화. 사용자: 지금은 HTML 다이어그램까지면 충분(개념 매스는 2D로 이식됨).
- **내재적 한계**(수정 불가/외부 앱 소관): 터읽기 measured=시군구 평균(대지 고유 방위 없음, 방위는 VWorld vision), law mode A(층수 추정·건폐/용적 pass 항상 통과), 외부 엔진 지연(진단 부지당 65~110초·graceful).
- **시퀀스 E 후폴로우**: 섹션별 takeaway 한 줄·본문 축약(project_proposal_magazine_deck 메모리).
- **feasibility 백필**: `tools/backfill_feasibility.py` — 옛 brief(기능 도입 전) 재빌드로 주소·envelope 확보(prod 14건 완료).

### 형제앱에서 가져올 것 — D:\APPS 조사 (2026-08-27)

D:\APPS 30개 폴더 중 **2026-08 이후 활발한 12개**를 CLAUDE.md·코드까지 읽고 뽑은 목록.
근거·상세는 `kunwon-ops/docs/benchmark-2026-siblings.md`(사내 앱 × 상용 비교, 우리 앱은 §6)와
`kunwon-ops/docs/benchmark-2026.md §3`(훔칠 것 7개). 형제앱 위치는 `kunwon-ops/docs/app-registry.md`.

**이미 가져온 것 (2026-08-27)** — 넷 다 **형제앱 코드 수정 0**, 그쪽이 이미 배포해둔 계약을 소비만 했다:
발표 장표 PPTX(터읽기 `/deck/render`) · 요구 완결성 감사(kunwon-ops 벤치마크) ·
법조문 시행일(arch-law-graph F-1·F-4) · 근거 안 밝힌 수치 구조 검사(concept-studio `render/numbers.py`).

⚠️ **착수하면 전제가 다를 수 있다** — 오늘 세 번 겪었다. 「컴플라이언스 매트릭스」는 **이미 있었고**
(진짜 갭은 그 목록을 LLM 이 고른다는 것), 「하드 게이트」는 우리에겐 **틀린 설계**였다(지침서 수치를
산문에 인용하는 자리가 정당하게 많다). **벤치마크 항목은 착수 전에 우리 코드부터 열어볼 것.**

**A. 반나절 이하 · LLM 0**

- [x] ~~**앱 boot 회귀**~~ ✅ 2026-08-28 — `tests/test_app_boot.py`(12). 계기: 형제앱 arch-law-diagnose 가 **테스트 340건 전부 초록인데 앱이 안 뜨는** 상태를 라이브에서야 발견(`main` 을 import 하는 테스트가 0건이었다). 우리는 `pip check` 깨끗·`mcp` 미설치라 무사했지만 boot 보장이 **우연**이었다(다른 걸 보러 온 김에 import 하는 테스트 6개). ⚠**C-1(MCP provider) 착수 시 이 테스트가 먼저 깨질 것** — `mcp` 가 `sse-starlette`→`starlette>=0.49.1` 을 끌고 와 fastapi 핀을 깬다. 그때 답은 핀을 푸는 게 아니라 **서비스 분리**(`kunwon-ops/docs/plan-mcp-gateway.md §9`).

- [x] ~~**A-1 arch-law-diagnose 역방향 소비 경로 문서화**~~ ✅ 2026-08-27 — Backend Routers 앞에 「형제앱이 우리를 읽는 경로」 블록 + BriefMode 「📈 사업성 분석」 버튼(딥링크 없음을 title 에 명시). **곁가지로 문서 오류 하나를 잡았다** — `feasibility_export` 를 「연동 앱 arch-law-diagnose 용」이라 적어 왔는데 **그쪽은 안 쓴다**(raw 필드 재파싱, 주소 분해 로직이 두 레포에 중복). 실제 소비자는 우리 자신. 상세는 Core Services `feasibility_export.py` 행. 남은 것: **그쪽에 갈아타기 제안**(아래 원문) + 그쪽 TODO 2건(민간·다부지 샘플 · 시설용도 매핑표)에 우리 DB 로 답하기.
- [x] ~~**A-2 시행일 백필 도구**~~ ✅ 2026-08-27 — `tools/backfill_law_ef.py`(LLM 0 · **진단 재실행 0** · graph `/api/lookup` 만). dry-run 기본 · `--apply` 저장(`_atomic_write`) · `--force` 재조회 · **멱등**(시행일 키가 다 있으면 네트워크도 안 탄다). ⚠**병합만 한다**(`arch_law_client.merge_law_texts`) — `fetch_law_texts` 는 found+본문 있는 것만 돌려주므로 통째로 갈아끼우면 graph 가 잠깐 죽거나 조문을 못 찾게 됐을 때 **이미 갖고 있던 원문이 사라진다**. `ef_yd: ""` 는 「미보유」라는 **사실**이라 빈 값도 보존(안 그러면 매번 대상으로 잡힌다). 합성 브리프로 라이브 검증(dry→apply→멱등).

  🚨 **그런데 백필할 데이터가 없다** — prod 21건 전수 확인 결과 **`law_diagnosis` 보유 0건**(`_site_context` 자체가 없음 19건 · 대지는 있으나 법 진단 없음 2건). **법적 골격(2026-07-14 대작업)이 저장된 브리프에 한 번도 안 돌았다.** 최신 브리프가 2026-07-14 045034 인데 그날 법 연동이 배포되기 **전**에 만들어졌고, 그 뒤로 새 분석이 없다. 즉 지금 prod 의 어떤 제안서·체크리스트에도 법적 골격 패널·조문 각주·시행일이 **하나도 안 보인다**(전부 graceful skip 이라 눈에 안 띈다). 도구가 이 원인을 출력한다(「0건을 0건이라고만 말하면 아무도 원인을 모른다」).
  → **실제 병목은 시행일이 아니라 `POST /brief/{id}/site-analyze` 를 아무도 안 돌린 것.** 부지당 65~110초 + vision·VWorld 과금이라 **일괄 실행은 사용자 결정**. 돌리고 나면 이 백필 도구는 그때부터 의미가 생긴다(그 경로는 애초에 시행일을 채워 오므로 백필도 사실상 불필요 — 도구는 **graph 재빌드 후 갱신**(`--force`)용으로 남는다).

- [x] ~~**A-3 `/analyze` coverage**~~ ❌ **안 만든다 (2026-08-28, 실측으로 폐기).** 착수해서 prod 21건을 전수로 재보니 **전제가 세 겹으로 틀렸다**:
      ① 「분류는 됐는데 추출이 빈손」 케이스가 **0건** — 분류된 타입은 전부 추출된다(그 지점의 파이프라인은 일관됨).
      ② 빈 블록은 **전부 「분류 0장」**(`brief_site` 빈 9건 모두 1차·2차 분류 0장).
      ③ 그런데 그 9건에 **대지 정보가 다 있다** — `feasibility_export` 부지 1개씩(주소·면적 보유). `brief_project_info.sites` 로 들어왔을 뿐이다.
      `brief_site`(대지 현황 **서술**)와 `brief_project_info.sites`(부지 **제원**)는 다른 것이고, 사업개요 표에 다 적는 지침서는 전자가 비는 게 **정상**이다.
      → 「43%가 설명 없이 비어 있다」는 관측 자체가 **블록을 잘못 읽은 것**이었다. 만들면 gap 0건을 보고하는 기능이 된다.
      ⚠**재제안 금지** — 다시 하려면 먼저 「분류 0장인데 문서엔 있었다」를 실제 사례로 하나 보여야 한다(그건 LLM 재판독이 필요해 「LLM 0」 전제가 깨진다).

**B. 1~2일 · 정확도·신뢰**

- [x] ~~**B-1 멀티파일 충돌**~~ ✅ 2026-08-27 — `services/brief_merge_conflicts.py`. **first_wins 는 유지하고 조용함만 없앴다**(값 수정 0). concept-studio 의 자동 해소는 **안 가져왔다** — 그쪽은 권위 서열(`gazette > guideline`)이 실재하는 문서군이고 우리는 아니다. 상세는 Core Services 행. 남은 것: 실제 멀티파일 지침서로 라이브 확인(현재 prod 에 복수 파일 brief 없음).
- [ ] **B-2 모순 탐지**(ContraVault) — kunwon-ops 가 우리 앱에 지목한 상용 갭 3개 중 **마지막 미착수**
      (①매트릭스 ✅ ②Go/No-Go 보류 ③모순). 지침서 내부 모순 + 우리 제안 내부 모순.
      ⚠**착수 전 확인** — `quant_validator` 가 정량 모순은 이미 본다. **서술 모순**이 진짜 갭인지 먼저 볼 것
      (A-1 과 같은 「이미 있었다」 위험). 참고: concept-studio `guards/factcheck.py` 는 LLM 0 대조 3종
      (기각값 재등장 · 단위 같은데 값 다름 · 남의 목록 시설)에 오탐 교훈 3개까지 있다.
- [ ] **B-3 kordoc HWPX 내보내기** — 심의·조합·발주처 제출은 HWP 가 사실상 표준인데 우리는 html/md/xlsx뿐.
      우리 `brief_checklist_exporter.to_markdown` 이 이미 재료고, 터읽기가 `POST /board/hwp` 로 **Dockerfile
      배선까지 실빌드 검증**해뒀다(`app/deck/board_report_md.py` + `services/kordoc_client.py` subprocess).
      ⚠**버전은 `kordoc@3.4.1` 고정**(검증본) — latest 아님. `--omit=optional` 로 무거운 OCR/PDF 의존성 제외.

**C. 큼 / 조건부**

- [ ] **C-1 MCP provider 전환** — 사내 5개 앱(arch-law-graph·arch-site-model·터읽기·law-qa·arch-law-diagnose)이
      MCP 를 열었는데 **우리만 빠져 있다**. `archive_search`·`list_briefs`·`get_brief` 는 전부 읽기 전용이라
      `arch-law-graph-mcp` 패턴(**별도 Cloud Run 서비스**) 그대로. 함정 5개는 `kunwon-ops/docs/plan-mcp-gateway.md §9`
      에 문서화돼 있다(Starlette Mount 트레일링슬래시 · **mcp 2.0.0 이 `mcp.server.fastmcp` 제거 → 버전 상한 먼저** ·
      Secret Manager 개행 · FastMCP DNS 리바인딩 · **백엔드 venv 에 `mcp` 넣으면 starlette 가 fastapi 핀을 깨므로
      서비스 분리 필수**). ⚠ 이건 **우리가 provider 가 되는 방향** — 서버간 REST 호출을 MCP 로 바꾸는 것은
      kunwon-ops 가 코드까지 읽고 "이득 없음" 결론냈다(E 참조).
- [ ] **C-2 `/deck/glb`·`/deck/dxf` + `/board {model:}`** — 보류한 Phase 4 3D 매스의 **실질적 대체**.
      터읽기가 대지계획도 DXF(실제 미터·대지=원점)·건물 GLB 를 낸다. `/board {model:...}` 은 **우리가
      assembler 로서** arch-site-model `/api/generate` 출력을 넘겨야 물리 3D 요약 + 축측 매싱이 온다
      (터읽기는 arch-site-model 을 스스로 안 부른다 — provider 경계). ⚠`plan_radius`(도면 범위 ≤2000)와
      `radius`(데이터 반경)는 **다른 축**.
- [ ] **C-3 세 개의 언어** — concept-studio `guards/translate.py`(심의/총회/분양)를 우리 맥락으로
      (심사위원용/발주처 보고용/내부 착수용). '변수' 로드맵 P3(프리셋)과 묶는다.
      규율 한 줄: **세 문장이 다른 숫자를 들면 그건 번역이 아니라 세 개의 안이다.**
- [ ] **C-4 `/context-pack` 총량제·걸침** — 주거·재개발 지침서일 때만. 조사범위 걸침 인구·세대(면적비율 합산)
      + 주민공동시설 총량제 부족/충족 판정이 제안서에 실측 근거로 붙는다.

**D. 작은 이식 (각 2~3시간)**

- [ ] **D-1 `render/qa.py`** — SVG 겹침·잘림·대비·**빈 영역**을 **브라우저 없이**("크롬이 필요하면 CI 에서
      skip 되고, skip 되는 검사는 없는 검사다"). 글자 폭은 모노 메트릭(라틴 0.6em·한글 1em), **재는 자와
      놓는 자가 같은 자를 쓴다**. 만들자마자 6건 적발했다 → 우리 `brief_massing`·조닝 SVG 에 바로.
- [ ] **D-2 `usage.Clock`** — 어디에 시간이 갔나(단계별). ⚠`ok`(돌았나)와 `changed_doc`(바꿨나)을 **가른다**
      — 0건은 실패가 아니라 맞는 답이다. 앱은 이 로그를 **안 읽는다**(읽으면 로그가 아니라 상태).
- [ ] **D-3 kunwon-ui `--kw-*` 토큰 통일** — 사내 공통 셸(`AppShell.tsx`·`theme.css`). 우리 `kunwon-tokens.css`
      와 이름이 다르다(`--color-accent` vs `--kw-primary`). ⚠ 자체완결 리포트는 `report_theme.py` 유지.
- [ ] **D-4 승인 맥락 기록**(EU AI Act Art.12·13) — 우리 `_steering_log` 는 지시·시각만 남긴다.
      **그때 무엇을 제치고 이걸 골랐는지**가 없다. "맥락 없는 승인 태그는 증거로서 실패한다."
      심의·발주처 질의가 요구하는 게 감사와 같은 성격이다.

**E. 보류 — 재제안 금지**

| 항목 | 왜 |
| --- | --- |
| **Go/No-Go** | kunwon-ops 판단(2026-08-27) — "참여할지 말지를 **남에게 권하는** 기능"이라 **설문으로 본인 외 실사용자가 확인된 뒤**. 컴플라이언스 매트릭스와 **같이 붙이지 말 것**도 그쪽 결론 |
| **임원 보고 모드** | 사용자 결정 — 만들지 않는다(메모리 `project_byeonsu_conversational_steering`) |
| **SketchUp MCP 3D 매스** | 근거 풍부해진 뒤. 당분간 C-2 가 대체 |
| **서버간 REST → MCP 전환** | kunwon-ops 가 우리 `teoilgi_client.py`·`arch_law_client.py` 를 직접 읽고 "이미 env override·버전 명시 계약·graceful degrade 를 갖춘 잘 만들어진 연동" + "결정론 파이프라인 호출엔 MCP 가 안 맞는다" 결론. 국면 3 후보에서 제외됨 |


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

## New Machine Setup (새 로컬 환경)

### 1. 필수 소프트웨어 설치

- Git, Python 3.10+, Node.js 18+

### 2. 코드 가져오기

```powershell
git clone https://github.com/DaDaDiRaRa/competition_comparison.git
cd competition_comparison
```

### 3. 백엔드 셋업

```powershell
cd backend
python -m venv venv
venv/Scripts/activate
pip install -r requirements.txt
```

### 4. 프론트엔드 셋업

```powershell
cd ../frontend
npm install
```

### 5. 민감 파일 복사 (git에 없음 — USB로 이동)

- `service.yaml` — 프로젝트 루트에 복사 후 `ANTHROPIC_API_KEY` 값을 실제 키로 교체
- `.env` — 프로젝트 루트에 복사 (또는 앱 설정 탭에서 직접 입력)

### 6. 앱 실행 후 설정 탭에서 입력

- **Anthropic API 키** — [console.anthropic.com](https://console.anthropic.com) 에서 확인
- **DB 경로** — 로컬 개발이면 비워두면 `~/CompetitionAnalyzerDB` 자동 생성

> DB 데이터는 GCS 버킷(`kunwon-competition-db`)에 있으므로 Cloud Run 배포 환경에서는 별도로 옮길 필요 없음.

**PaddleOCR (선택):** `pip install -r requirements-ocr.txt`. 기본 파이프라인은 PyMuPDF + Claude vision 으로 동작하므로 불필요.

**테스트:** `cd backend && venv/Scripts/python.exe -m pytest tests/ -v` (현재 768 passed, suite = `backend/tests/`). 부지별 개념 매스(`brief_massing` 파생·렌더) 수정 시 `tests/test_brief_massing.py` 17 케이스(봉투 항등식·다부지 프로그램 귀속·지하 분리·가로 렌더·범례·graceful·escape). '변수' steering(`brief_proposal` steering 파라미터·propose 라우터 로그) 수정 시 `tests/test_brief_proposal_steering.py` 14 케이스. 발표 장표(`proposal_deck` 매핑·`/deck` 라우터) 수정 시 `tests/test_proposal_deck.py` 25 + `tests/test_proposal_deck_route.py` 9 케이스(한 장 상한·5안 미유실·사업비 미유실·근거 sources·ASCII filename·헤더 latin-1·502). ⚠**터읽기 `render_slides.py` 상한이 바뀌면 `MAX_KPI`/`MAX_CARDS`/`MAX_ROWS` 도 같이** — 우리 상수는 그쪽 계약의 사본이다. `vworld_analyzer.py`(bbox 기하·필지 투영) 수정 시 `tests/test_vworld_analyzer.py` 13 케이스. HTML 리포트 서빙(`utils.html_file_response`) 수정 시 `tests/test_brief_export_serving.py` 6 케이스. 신규(성숙도 로드맵·리뷰): `test_citation_check`·`test_report_theme`·`test_report_badges`·`test_dashboard_readability`·`test_cross_compare_brief`·`test_cross_compare_data`·`test_cross_compare_overflow`·`test_archive_bm25`·`test_archive_build`·`test_comparator_core`·`test_myproject_quant`·`test_myproject_deep`·`test_run_compare`·`test_delete_project`·`test_delete_brief`·`test_brief_export_serving`. `arch_law_client.py`(건축법 진단 되받기·계약·Phase 3 graph) 수정 시 `tests/test_arch_law_client.py` 20 케이스 + 시행일 표기(`effective_label`·각주·md 근거 조문) 수정 시 `tests/test_law_effective_date.py` 21 케이스(⚠**mock 은 실제 응답 형태로** — applicable_reviews dict·높이_일조.pass null·law_refs. 형태 틀린 mock 은 계약 버그를 통과시킴). 대지·법적 골격 렌더(`_law_diagnosis_html`·체크리스트 대지·법 섹션·조문 각주) 수정 시 `tests/test_brief_proposal_report.py`(법적 골격 패널·다부지·법조문 각주) + `tests/test_brief_pipeline.py`(TestSiteLawSection·TestSiteLawXlsx). `brief_proposal_report_generator.py`(매거진 덱·cockpit·권장종합안·입찰2층·placement·법적 골격) 수정 시 `tests/test_brief_proposal_report.py`. `brief_genre.py`(장르 판별) 수정 시 `tests/test_brief_genre.py` 7 케이스. `bid_structure.py`(입찰 2층 배점·다중표 병합) 수정 시 `tests/test_bid_structure.py` 14 케이스. `_extract_docx_eval_from_table` (배점표 파싱) 수정 시 `tests/test_eval_table_multilevel.py` 4 케이스(다단계 PQ 표 points_col·이름 귀속·합계). `brief_playbook.py` / `brief_playbook_report_generator.py` 수정 시 `tests/test_brief_playbook.py` 7 케이스 (무료 게이트·결정론 덮어쓰기·렌더 escape, LLM monkeypatch). HWP/HWPX 코드 추가 시 `tests/test_hwpx_loader.py` 회귀 보호 필수 (22 케이스, rhwp monkeypatch — rhwp 미설치 환경도 통과). `tests/test_normalize_design_grouped.py` 13 케이스, `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스도 동일. `quant_validator.py` / `pattern_builder._build_quant_stats` / `merge_extracted_data` 의 `_quantitative_flags` 훅 수정 시 `tests/test_quant_validator.py` 19 케이스. 요구 완결성 감사(`requirement_coverage` 매칭 문턱·진단 훅·렌더) 수정 시 `tests/test_requirement_coverage.py` 20 케이스(관대함·중복 요구·축 문턱·escape). `feasibility_export.py` 수정 시 `tests/test_feasibility_export.py` 55 케이스 + 무료 검증 `tools/feasibility_verify.py`. ⚠️ DOCX 회귀 `test_docx_extractor.py` (10 케이스) 는 repo-root `tests/` 에 있어 backend 기준 suite(393)에 **미포함** — DOCX 수정 시 별도 실행 (repo-root cwd): `backend/venv/Scripts/python.exe -m pytest tests/test_docx_extractor.py`. repo-root `tests/` 엔 conftest 없음 — 테스트 파일이 직접 `services.utils` 등을 sys.modules 스텁(`types.ModuleType`)하므로, `data_extractor` 가 `services.utils` 에서 새 심볼을 import 하면 **스텁 함수 목록도 갱신 필수** (안 하면 collection 단계 `cannot import name ... (unknown location)`). 현재 상태: 9 pass / 1 사전실패 `test_force_cut_31_paragraphs` (docx_loader F3 force-cut 미발동, **미해결·brief 전용**).

## Deployment

- `main` push → GitHub Actions (`.github/workflows/deploy.yml`) → Docker 빌드 → Cloud Run.
- 수동 fallback: `gcloud run deploy competition-analyzer --source . --region asia-northeast3`.
- 로그: `gcloud logging read "resource.type=cloud_run_revision" --limit=50`.
- 상세는 `DEPLOYMENT.md`.
- **리소스(진실원본=`deploy.yml`)**: `--memory 8Gi --concurrency 8 --cpu 2 --timeout 3600 --max-instances 1`. ⚠**메모리는 deploy.yml 에 박아야 영구** — `gcloud run services update --memory` 로 올려도 다음 배포가 되돌림. 8Gi 이유: 다중 PDF 청크 업로드가 `/tmp`(Cloud Run tmpfs=**RAM**)에 쌓임 + 비전 추출 메모리 → 2Gi 로는 추출 중 **OOM → 503**("connection to instance had an error"). concurrency 8 로 한 인스턴스 동시 추출 폭주 차단.
- 기능·정확도 성숙도 로드맵·부채는 **`MATURITY.md`** 참조(지침서 분석 기준 5개 기능 진단 + 8항목 수정 완료).

Cloud Run 청크 업로드 (`/api/upload`) 가 32MB 한도 우회. 파이프라인은 multipart 대신 `file_ref` 받음.
