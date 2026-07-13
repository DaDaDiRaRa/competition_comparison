# CLAUDE.md

Competition Analyzer — 건축 공모 제안서 추출·비교 풀스택 앱.

**Stack:** FastAPI + React 18/Vite + Anthropic Claude (추출·분류·비교·진단·대지분석 `claude-sonnet-4-6` / AI 종합 해설·수주 제안서만 `claude-opus-4-8`) + PyMuPDF. JSON-based DB. Docker + Cloud Run (gen2) + GCS 마운트 (`/data`). `main` push → GitHub Actions 자동 배포.

## Architecture

### Backend Routers (`/api/<name>`)

1. **`routers/accumulate.py`** — PDF → JSON 추출 + 개별 제출물 리포트. 비교분석은 별도 (`rerun-compare`). `add-submission`, `rerun-compare`, `rerender-report`, `cross-compare` 엔드포인트 포함.
2. **`routers/diagnose.py`** — 단일 제출물 진단. `/run` (DB 전체 패턴) + `/run-vs-projects` (사용자 선택). 완료 시 HTML 리포트 자동 생성.
3. **`routers/patterns.py`** — 시설유형별 패턴 관리 (당선 + 낙선 통계).
4. **`routers/settings.py`** — `app_settings.json` 관리. `GET /settings/meta` 가 프론트 `useMeta()` 단일 소스.
5. **`routers/upload.py`** — 청크 업로드 (Cloud Run 32MB 한도 우회). 25MB 청크 / 600MB 상한 / `/tmp/cc_uploads/` 누적.
6. **`routers/archive.py`** — FTS5 in-memory SQLite 자연어 검색.
7. **`routers/brief.py`** — 지침서 단독 분석 (PDF + DOCX + HWP/HWPX). 분류 → 추출 → 요구사항 → 검증 → (옵션) AI 종합 해설 → JSON/MD/xlsx/HTML 저장. HTML 은 `/exports/{name}.html` 에서 인라인(text/html, 보기용), md/xlsx 는 attachment. `analyze` 폼 `include_insight`(기본 ON) 가 같은 run 에서 종합 해설까지 한 방. `POST /{brief_id}/interpret` 는 해설만 재생성(추출 재처리 0, 분석 시 껐거나 프롬프트 개선 후 재적용용) 후 **파생 3종(html·md·xlsx) 모두 재렌더** — 셋 다 새 `_insight` 반영. `POST /{brief_id}/propose` 는 **프로젝트 수주 제안서** 생성(추출 재처리 0, LLM 1콜) → `_proposal` 임베드 + 별도 `{brief_id}_proposal.html` 렌더(`/exports` 인라인 서빙, `has_proposal` 노출). `POST /{brief_id}/playbook` 는 **경험 기반 처방** 생성(추출 재처리 0, LLM 최대 1콜) → `_playbook` 임베드 + 별도 `{brief_id}_playbook.html` 렌더(`has_playbook` 노출) — 같은 시설유형 과거 축적 데이터(`reference_cases`) 없으면 **LLM 미호출·`has_playbook:false`+`reason`** 반환(무료 게이트). `interpret`=사실 triage(해설가), `propose`=수주 전략 처방(전략가), `playbook`=과거 경험 기반 처방(과거 당락→이 지침서 적용) — **셋 다 별개 산출물**. 멀티파일: `analyze` 는 지침서+과업지시서 등 **복수 파일 동시 분석** 지원(`brief_pdf_refs` JSON 배열, `_merge_multi_brief_data` first_wins — 충돌해소는 업로드 순서뿐, 도메인 규칙 없음).

**MyProject 심층 분석:** 별도 라우터 없음. `accumulate.py` 가 단일 등록 시 `myproject_analyzer.deep_analyze()` 호출 → `_deep.json` + `_deep.html`. `GET /projects/{ft}/{cid}/submissions/{company}/deep-report` 로 서빙.

### Core Services

| 파일 | 책임 |
| --- | --- |
| `db_manager.py` | JSON DB. `_atomic_write` / `_sync_write` 는 GCSFUSE 플러시 위해 `fsync` 후 rename — 신규 파일 저장 함수 추가 시 반드시 사용. |
| `docx_loader.py` | DOCX 블록 분할 (PDF 와 완전 독립). `split_docx_to_blocks()` R1~R5 분할 + F1~F3 필터. vMerge 감지는 `_tc` identity + tcPr `w:vMerge` 두 시그널 조합 필수. |
| `hwpx_loader.py` | HWP/HWPX 블록 분할 (rhwp-python, PDF/DOCX 와 독립). `split_hwpx_to_blocks()` 반환 스키마가 docx_loader 와 **동일** → `classify_all_blocks_brief` / `extract_hwpx` / BRIEF_* 추출 헬퍼 그대로 재사용. `ir.iter_blocks(recurse=False)` 필수 (Critical Rules 참조). 표 HTML → 마크다운 + merge_info 는 docx 호환 `{row,col,merged_rows,value}`. `get_hwpx_source_text()` 는 docx 구현 위임. 회귀: `tests/test_hwpx_loader.py` (22, rhwp monkeypatch). |
| `page_classifier.py` | 페이지/블록 분류. `classify_all_pages_brief()` (PDF) / `classify_all_blocks_brief()` (DOCX/HWP/HWPX). `has_scoring_table=False` 면 BRIEF_EVALUATION → BRIEF_ADMIN 강등. |
| `data_extractor.py` | 페이지/블록 추출. `merge_extracted_data()` 가 `_quantitative` 자동 집계. DOCX BRIEF_EVALUATION 표는 `_extract_docx_eval_from_table()` 로 LLM 없이 파싱 (환각 차단). 제안서(브리프 제외) 결과엔 `quant_validator.validate_quantitative()` 로 `_quantitative_flags` 부착 (모순 시에만, 숫자 수정 안 함). brief 결과면 끝에서 `feasibility_export` 블록도 부착 (try/except, 실패해도 파이프라인 무중단). HWP/HWPX 는 `extract_hwpx()` (split_hwpx_to_blocks 로 파싱, extract_docx 가 python-docx 재파싱이라 hwpx 불가 → 병렬 함수. BRIEF_* 추출 헬퍼·merge_info 스키마 재사용). |
| `quant_validator.py` | `_quantitative` 내부 정합성 결정론 검증 (LLM 0 · 숫자 수정 0). 건폐율=건축/대지, 총연면적≥용적률×대지 등 항등식으로 추출 오류(필드 오결합·환각)를 flag 로만 표시 (`severity: error\|warn`). **단일 소스** — `merge_extracted_data`(추출 직후 `_quantitative_flags` 부착, 제안서만) · `pattern_builder`(error flag 필드 집계 제외) · `tools/data_health.py`(무료 감사) 가 공유. 관대(false positive 회피 — 영등포 교훈). 회귀: `tests/test_quant_validator.py`. |
| `feasibility_export.py` | `_brief.json` → `feasibility_export` 정규화 블록 (연동 앱 arch-law-diagnose 용, schema_version 2). **새 vision 추출 없음 · 기존 키 수정 없음 · 추가만.** 이미 추출된 값을 재배치·파싱: site_id 통일, brief_site "(부지N)" 주소 분해+접두 상속, 인증 코드화, facilities 괄호 건축법 용도, 사업 규모 노출(1차); 주차 서술→required_parking_count(부지N 마커 귀속), zoning→표준 용도지역명(불확실 시 raw), special_conditions 심의 문구→limits_determined_by(2차). 모두 후처리 파싱이라 BRIEF_* 추출 회귀 없음. 회귀: `tests/test_feasibility_export.py` (46). 무료 검증: `tools/feasibility_verify.py`. |
| `llm_client.py` | Claude API 래퍼 `call_messages()`. `system` 은 `str \| list` 모두 지원. 캐시 토큰 로깅. `_NO_SAMPLING_PREFIXES`(opus-4.7/4.8·fable·mythos) 로 시작하는 모델엔 `temperature`/`top_p`/`top_k` 를 body 에서 자동 생략 — 이 모델군은 샘플링 파라미터 전송 시 **400** (Sonnet/Haiku/Opus4.6 은 유지). |
| `comparator.py` | **2-pass blind-reveal.** Pass 1: 익명화 채점, Pass 2: 리빌 후 차별화·gap 분석 + `concept_comparison`(축별로 각 회사의 컨셉·설계방향을 (p.N) 인용과 함께 나란히 서술하는 비교 — Pass 1 결과의 strengths/weaknesses/notes 만 근거로 사용, 원본 재전송 없음) (Pass 1 결과만 재전송, 80%+ 토큰 절감). `_compute_gap_analysis()` 결정적 로직으로 alignment 산출 — **결과 화면엔 더 이상 렌더하지 않고 내부 QA 용으로만 comparison.json 에 보존**(2026-07-01, "누가 1등이냐"보다 컨텐츠 비교가 더 유용하다는 사용자 결정). Prompt caching ephemeral. `.replace()` 사용 (`.format()` 은 JSON 중괄호 충돌). |
| `pattern_builder.py` | 당선 패턴 + `loser_stats` (lose_count, page_distribution, quantitative, concept_keywords). `_build_quant_stats()` 는 `quant_validator` 가 error 로 지목한 필드를 **제출물별** 집계에서 제외 (환각 수치 패턴 유입 차단; warn 은 유지). 저장 `_quantitative_flags` 우선, 없으면(플래그 훅 이전 추출된 구 레코드) 집계 시점 `validate_quantitative()` 재검증. 회귀: `tests/test_quant_validator.py::TestPatternBuilderExcludesFlagged`. |
| `report_generator.py` | 비교 HTML 리포트 (LLM 호출 없음). `axes_for(facility_type)` 로 시설별 평가축. 종합 순위(`ranking`)·블라인드 정렬 분석(`gap_analysis`) 섹션은 미렌더 — `concept_comparison` 기반 "축별 컨셉·설계 방향 비교" 섹션이 그 자리를 대체(2026-07-01). |
| `submission_report_generator.py` | 개별 제출물 리포트. LLM 호출 없음. |
| `diagnosis_report_generator.py` | 진단 리포트. LLM 호출 없음. 종합점수 링 → 페이지바 → 패턴편차 → 충족도 → 요구사항 매핑 → 평가축 상세. |
| `myproject_analyzer.py` | MyProject 멀티패스 deep-analysis. narrative + deep evidence + 정량 + 키워드 + auto_meta. |
| `myproject_report_generator.py` | `_deep.json` → HTML. LLM 호출 없음. |
| `archive_search.py` | in-memory SQLite FTS5. `build_index()` 시작 시 1회, `rerun-compare` 후 `rebuild_index()`. `check_same_thread=False` 필수. |
| `brief_validator.py` | 지침서 검증. LLM 호출 없음. `requirements` 가 dict 아니면 `{}` 교체 (LLM 배열 반환 방어). `_check_points_mismatch` 는 `shared_with` non-empty 또는 합계가 만점과 일치 시 null 항목을 정성평가로 인정 (영등포 false positive 차단). |
| `brief_checklist_exporter.py` | 지침서 체크리스트 MD/xlsx/HTML. LLM 호출 금지. openpyxl lazy import. xlsx 시트: (`_insight` 있으면 맨 앞 "AI 종합 해설") / 1.면적·프로그램(사업개요 서브섹션 포함) / 2.심사기준 / 3.요구사항 / 4.검증경고 (+ area_rows 있으면 5.면적표상세). `to_markdown` 도 `_insight` 있으면 헤더 직후 `## 0. AI 종합 해설` 섹션 삽입(`_md_insight_block`). xlsx·md·html **3종 모두** insight 임베드(없으면 graceful skip). `to_html()` 은 `to_markdown` 과 동일한 `_extract_sections()` 데이터로 미니멀 자체완결 HTML (화이트 + 건원 RED, 5섹션, 상단 고정 nav + 핵심수치 카드 + 시설별 접기). `to_html()` 의 "AI 종합 해설" 섹션은 `insight._reference_cases` 있으면 "참고 사례" 서브섹션도 렌더(`_reference_cases_section_html`, html 전용 v1 — md/xlsx 는 미포함). 데이터는 `html.escape`. `_form_area_pages()` 가 '[서식 N] …면적표' 제출양식 오분류 페이지를 면적 집계에서 제외 (본문 면적표 중복 차단, 영등포 사례). 회귀: `tests/test_brief_pipeline.py::TestToHtml`. |
| `brief_advisor.py` | 지침서 "AI 종합 해설" (안전한 ②: 종합·번역 + 강조점 탐지, **외부 당락 예측 없음**). 결정론 백본 `compute_scoring_focus()`(배점 랭킹, null/shared_with 시맨틱=`brief_validator._check_points_mismatch` 와 동일) + `extract_emphasis_signals()`(강조어휘 문장 + category_weights, 강조문장 dedup) + `reference_cases.collect_reference_context()`(시설유형 기존 사례, 있을 때만) → 이 신호 위에서 `interpret_brief()`(LLM 1콜, comparator 패턴) 가 종합. **모델 = `settings.model_id_advisor`(기본 Opus `claude-opus-4-8`), `max_tokens=16000`** (해설은 지침서당 1콜뿐이라 Opus 비용 부담 작음; 추출·비교·진단은 Sonnet 유지). temperature=0 전송하나 Opus 는 `llm_client` 가 자동 생략. 가드 4: 근거한정·인용필수(페이지 추측 금지)·예측금지·중립탐지. `reference_cases` 는 `reading_guide` 배경 참고로만 — key_emphases/must_not_miss/hidden_constraints/scoring_focus 등 이 지침서 판단 근거로는 사용 금지(가드 강화). LLM 의 scoring_focus 환각은 결정론 값으로 덮어씀. 연료=`brief_evaluation`+`design_guidelines_grouped`. `interpret_brief()` 결과에 `_reference_cases` 부착(렌더러용). 회귀: `tests/test_brief_advisor.py`. |
| `brief_proposal.py` | 지침서 "프로젝트 수주 제안서" (**전략가**: `brief_advisor`가 사실 triage(해설가)라면 이쪽은 앞을 보는 처방). `propose_project()` (LLM 1콜, Opus `settings.model_id_advisor`, `max_tokens=16000`, comparator 패턴). 결정론 백본은 `brief_advisor._build_advisor_payload()`와 단일 소스 재사용 — `reference_cases`(시설유형 기존 사례 참고자료) 도 이 payload 를 통해 공유. 설계 계약·패턴 결합·AI 해석 확장층 상세는 표 아래 [파일별 상세](#core-services-상세-표에-담기엔-긴-항목) 참조. |
| `bid_structure.py` | 입찰(bid) **2층 배점 구조** 정규화(LLM 0, 결정론) — `build_bid_structure(brief_data)` → `_bid_structure`(genre=="bid" 일 때만, `routers/brief.py` 가 requirements 추출 **직후** 부착 — bid_structure 가 `_requirements` 를 소비하므로 merge 시점엔 불가). 상위(top_layer): 종합평점=사업수행능력%×w + 가격%×(100-w), w 는 **연면적 규모별 밴드**(8만/24만㎡→20/30/40% vs 80/70/60%). 하위(pq_detail): 사업수행능력 100점표(참여기술자50·유사용역실적40·신용도10, brief_evaluation 재집계). **다중표 병합**: `_find_eval_pages` 가 brief_evaluation 여러 페이지에서 상위층(사업수행능력+가격 2축) 페이지와 PQ상세(100점표) 페이지를 **분리 식별** — 각 층을 올바른 표에서 가져온다. **견고성(3소스 우선순위)**: ① 상위층 페이지 `evaluation_method` 서술(`_parse_bands_from_method`, "8만㎡미만(사업수행능력평가 20%, 가격평가 80%)…" — run 간 안정적, 최우선) ② evaluation_criteria 항목(`_parse_bands`) ③ requirements 범위(`_parse_range`, "가격 60~80% 차등"). axis 는 `bands`(정확) 또는 `weight_range`(범위). LLM 이 evaluation_criteria 밴드를 떨궈도 method 소스로 정확 밴드 복원. **정직성**: 밴드 기준=연면적인데 연면적 미추출이면 적용 밴드 단정 금지(대지면적 대체 추정 금지 — 21만㎡ 대지 ≠ 연면적), `applicable.note` 로 "확인 필요". 렌더: `brief_checklist_exporter._bid_structure_html` (심사기준 섹션), advisor payload 주입. 회귀: `tests/test_bid_structure.py` (14). |
| `brief_genre.py` | 지침서 **장르 판별**(LLM 0, 결정론) — `detect_brief_genre(brief_data)` → `_brief_genre` 부착. `competition`(설계공모: 배치·공간계획 등 설계축) vs `bid`(설계자 선정 입찰: 사업수행능력=참여기술자·유사용역실적·신용도 + 가격) vs `unknown`. 최강 판별자 = **평가 카테고리명 자체**(가중 3) + 본문 텍스트 마커(적격심사·낙찰 vs 심사위원·당선작, 가중 2). bare "공모"/"입찰"은 양쪽 혼재라 약신호. `merge_extracted_data`(brief)·`_merge_multi_brief_data`(합쳐진 eval 로 재판별)가 부착. 다운스트림 오인 차단: `brief_validator`(입찰은 건폐율·용적률 등 설계지표 누락 오경고 스킵), advisor/proposal/playbook 프롬프트에 genre 주입, exporter eyebrow·프론트 배지. 회귀: `tests/test_brief_genre.py` (7). |
| `reference_cases.py` | 시설유형별 "기존 사례 참고자료" 결정론 조회(LLM 0) — `brief_advisor`·`brief_proposal` 공유 단일 소스. `collect_reference_context(facility_type)` 가 세 서브키 반환: `pattern_summary`(기존 `pattern_builder` 집계 통계 이관), `case_excerpts`(당선 제출물 `concept.main_strategy` 실제 서술, 최근순 최대 3건, `get_winning_submissions`), `concept_comparison_excerpts`(과거 비교분석 `concept_comparison` 축별 서술, 최대 4건, `load_comparison`). 셋 다 비면 전체 `{}` 반환. 실패해도 `{}` (본 파이프라인 비차단). 소비 측이 반드시 "다른 공모 자료 — 이 지침서 사실 근거 아님" 가드레일을 프롬프트에 명시(브리프 자체 `basis` 에 섞이지 않게). 결과 리포트에 "참고 사례" 섹션으로 노출(2026-07-01 사용자 결정) — `brief_proposal_report_generator._reference_cases_html()` / `brief_checklist_exporter._reference_cases_section_html()`. 회귀: `tests/test_reference_cases.py`. |
| `brief_proposal_report_generator.py` | `_proposal` → 자체완결 HTML (LLM 0, Report Generation Rule). 화이트 + 건원 RED, 상단 nav. 히어로·팩트밴드·대지 섹션·AI 해석 확장층·"참고 사례"(`_reference_cases_html`, `_proposal._reference_cases` 있을 때만) 등 상세는 표 아래 [파일별 상세](#core-services-상세-표에-담기엔-긴-항목) 참조. |
| `brief_playbook.py` | 지침서 "경험 기반 처방"(experiential playbook, **세 번째 산출물** — `interpret`=해설가, `propose`=전략가에 이은 것). `build_playbook()` (LLM 최대 1콜, Opus `settings.model_id_advisor`, `max_tokens=16000`, comparator 패턴). **advisor/propose 와 정반대**: 저 둘은 `reference_cases`(같은 시설유형 과거 당선/낙선 축적)를 *배경 참고로만* 쓰고 이 지침서 판단 근거로는 못 쓰게 가드가 걸려 있음 — playbook 은 그 관계를 **뒤집어** reference_cases 를 *주연료*로 삼아 "과거엔 이래서 됐고/떨어졌으니 이 지침서에선 이걸 이렇게" 능동 처방. `_build_advisor_payload` 재사용. **무료 게이트: `collect_reference_context` 가 비면 LLM 미호출 sentinel(`has_accumulated_data=False`)** (연료 없는데 과금 방지). **오염 방지 — 교차 앵커**: `applications` 각 항목은 과거 교훈(`rooted_in`)+이 지침서 실제 사실(`basis`, p.N/항목명) **둘 다** 앵커, 못 달면 제외. 과거 공모 수치를 이 지침서 사실로 옮기기 금지·당락 예측 금지. 결정론 덮어씀: `data_basis`(표본 규모)·`scoring_focus`. 전제조건=DB에 같은 시설유형 과거 데이터 축적. 회귀: `tests/test_brief_playbook.py` (7). |
| `brief_playbook_report_generator.py` | `_playbook` → 자체완결 HTML (LLM 0, Report Generation Rule). 화이트 + 건원 RED. 2층 시각 분리: **과거·사실**(당선 교훈·낙선 함정·당락 축, 파란 `source` 칩=과거 공모명) vs **AI 해석**(`applications`, "AI 해석" 배지 + `rooted_in` 과거 앵커 + `basis` 이 지침서 앵커 동시 노출). 상단 표본 근거 밴드(win/lose/발췌 수)·범례·디스클레이머. `has_accumulated_data=False` 면 안내 카드만(graceful). `to_playbook_html()`. 데이터 `html.escape`. |
| `teoilgi_client.py` | **터읽기(arch-site-context) 형제앱 연동** (2026-07-09) — `POST /board {brief:true,synthesize:false}` 로 **실측** 대지 맥락(전국=100 인구지수·근접도·수급진단·재해·★지배 설계 드라이버) 취득. vision(vworld_analyzer)을 대체 않고 **보강**: 정량·사실은 measured 우선, vision 은 형상·조망 시각판독. `FACILITY_TO_USE_TYPE`(14종→주거/상업/의료), env `TEOILGI_BOARD_URL`(기본 Cloud Run). graceful(실패→None, 제안서는 vision 만으로). `routers/brief.py` 가 `_site_context.measured` 로 병합, `brief_proposal._measured_digest`가 프롬프트 주입(터읽기 ②AI판단·notes 제외 = 경계: 우리는 제안서 컨셉안 소유, 터읽기는 사실+드라이버까지). 회귀: `tests/test_teoilgi_client.py` (6). |
| `vworld_analyzer.py` | 지침서 "대지·맥락 분석" — 주소→지오코딩→VWorld 위성(WMTS)+지적도(WMS) 합성→Claude Sonnet vision 판독. 지침서 분석 완료 후 `feasibility_export.sites[0].address` 로 자동 실행 (키 있을 때만, 실패해도 비치명). 위성은 **WMTS 전용**(WMS GetMap 미지원), 지적도는 **WMS 전용**(WMTS 미제공) — 레이어명 `lp_pa_cbnd_bonbun,lp_pa_cbnd_bubun` (구 `lp_pa_cn_A` 는 오타, 확인은 GetCapabilities로). 광역 위성(zoom16, 3×3≈1.8km) **중앙**에 지적도를 고해상(900m@768px≈1.2m/px) 요청 후 비례 축소·합성 — 스케일 임계는 **절대 span 아닌 m/px**. `has_cadastral` 플래그가 `_site_context`·vision 프롬프트·제안서 썸네일 캡션까지 전파. 빈 타일·오프셋 이탈·PIL 에러는 위성 단독 폴백. `GET /brief/{id}/site-context` 로 서빙. 회귀: `tests/test_vworld_analyzer.py` (8, 네트워크 0 — bbox/m/px 기하만). |
| `proposal_number_check.py` | 제안서 prose **근거 없는 수치 검산** (LLM 0 · 숫자 수정 0, `quant_validator` 의 제안서판). `check_proposal_numbers(proposal, brief_data)` — `_proposal` 의 LLM 작성 서술에 나온 수치를 코퍼스(brief_data 전체 + 결정론 scoring_focus)와 대조해 원천에 없는 숫자만 flag (분양가·ROI 등 발명/일반지식 수치가 사실처럼 새는 것 차단). basis(근거 인용)·메타 제외. **2-pass:** ① **위험 단위 쌍**(억/만원/원/%/세대/가구/호)에 붙은 수치는 `(숫자,단위)` 쌍으로 대조 — 자릿수 무관, 소액 발명(공실률 12%·30억·480세대)까지 포착 ② 그 외 **bare 다자리** 수치는 코퍼스 막대조(한 자리 구조 숫자 1순위·5안 제외). 코퍼스는 over-permissive(false positive 회피), 단 위험 단위만 쌍 정밀도. 배점 비중 'N%'는 scoring_focus weight_pct 로 허용(오탐 방지). `_propose_sync` 가 `result["_number_flags"]` 부착(비치명), 렌더러가 "근거 미확인 수치" 경고 밴드로 노출. 회귀: `tests/test_proposal_number_check.py` (11). |
| `grade_helpers.py` | 등급 단일 소스. `GRADE_COLORS`, `GRADE_RING_COLORS`, `to_grade()`. 모든 리포트 generator 가 공통 import. |
| `utils.py` | PDF rasterizer (`rasterize_pdf` PyMuPDF), SSE helper, `parse_json_response()` 3단계 복구, 공유 dict 헬퍼 `_first()` / `_as_list()`, `user_error_msg()`, `normalize_design_guidelines_grouped()`. |
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

**패턴 결합(2026-06-26 추가):** `_pattern_signals(facility_type)` 가 `load_pattern()` 으로 동일 시설유형 당선·낙선 경향을 `payload["pattern_context"]` 로 주입.
사실 근거 인용 금지·전략 힌트 전용·N≤2 는 약신호 명시 — 지침서 우선 원칙 유지.

**AI 해석 확장층(시퀀스 E Phase 2, 2026-06-29):** `design_directions` 에 `scoring_play`(득점)·`site_rationale`(이 부지라서) + 신규 `program_directions`/`massing_strategy`/`phasing`(각 `{claim, basis}`).
1층 사실 위 추론을 펼치되 **각 claim 에 basis 앵커 강제**(앵커 못 달면 제외), **새 숫자를 사실로 만들기 금지**(가정은 open_questions/caveats).

#### `brief_proposal_report_generator.py`

`_proposal` → 자체완결 HTML (LLM 0, Report Generation Rule). 화이트 + 건원 RED, 상단 nav.

**시퀀스 E Phase 1(2026-06-29, 밀도 업그레이드):** 덱 최상단 **히어로**(위성+지적도 실측 이미지 + 대지 요약 — "상상 아닌 실측" 첫인상, `_hero_html`) + **사업 규모 팩트 밴드**(`feasibility_export` 실추출 수치 대형 숫자, `_facts_band_html` — 첨부물의 날조 분양가/ROI 정반대로 지침서 사실 숫자만).
히어로가 이미지 보이면 대지 섹션은 compact(필드·주의만, b64 중복 0). `to_proposal_html(site_image_b64=, feasibility=)`. brief.py propose 가 주입.

**시퀀스 E Phase 2(2026-06-29, AI 해석 확장층):** 상단 **명시적 범례**(근거 칩=사실 vs "AI 해석" 배지=추론, `_legend_html`) + 설계 5안 카드에 득점·이 부지라서 필드 + 신규 해석 섹션 **프로그램 방향·매스 전략·단계 접근**(`_interp_section`, 각 항목 근거 앵커 + "AI 해석" 배지) + 하단 **근거 미확인 수치** 경고 밴드(`_number_flags_html`, `_number_flags` 있을 때만).

섹션 순서: 전략요약 → **사업 규모**(옵션) → **대지·맥락 분석**(옵션, `_site_context` 있을 때만) → 배점 무게중심 카드(결정론 scoring_focus 상위) → 수주 핵심 테마 → 설계 접근 방향 → 착수 우선순위(rank 정렬) → 리스크·대응(severity 정렬) → 착수 체크리스트 → 발주처 확인 → 한계.

**대지 섹션:** `to_proposal_html(site_context=, site_image_b64=)` 받으면 전략요약 직후 삽입 — VWorld 위성 썸네일(base64 임베드, 자체완결 유지) + overall_summary + 5개 판독 필드(향/도로/주변/자연/특이) + "위성 AI 판독 기반·현장 확인 필요(추론 포함)" 라벨 고정.
brief.py propose 가 `_brief.json._site_context` + `{brief_id}_site.jpg` 로 주입. 데이터 `html.escape`. 빈 섹션 graceful skip.

상단에 "수주 전략 가설 · 당락 예측 아님" 디스클레이머 고정. 회귀: `tests/test_brief_proposal_report.py` (27).

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
7. **BriefMode** — 지침서 단독 분석. `accept=".pdf,.docx,.hwp,.hwpx"`. docx / hwp·hwpx 선택 시 "도면 포함 지침서는 PDF로" 안내. 블록 기반 포맷(docx/hwp/hwpx)일 때 flag location `p.N` → `블록 N` 치환 (`isBlockFormat`). "AI 종합 해설 포함" 체크박스(기본 ON)로 `include_insight` 토글, 결과에 포함 배지 / 미포함 시 재생성 버튼(`reinterpretBrief`). 결과·이력에 **프로젝트 수주 제안서** 생성/열기 버튼(`proposeBrief` → `{brief_id}_proposal.html` 새 탭, `has_proposal` 배지) — 요약·정리를 넘어선 수주 전략 제안. 결과·이력에 **경험 기반 처방** 생성/열기 버튼(`buildBriefPlaybook` → `{brief_id}_playbook.html` 새 탭, `has_playbook`/'경험 처방' 배지) — 같은 시설유형 과거 축적 데이터를 이 지침서에 적용한 처방(과거 데이터 없으면 안내 메시지, LLM 미호출).

**Key components:** `useMeta()` 훅이 시설유형·페이지타입·평가축 한국어 레이블 단일 소스 (`/settings/meta` 1회 fetch). 하드코딩 금지. `useMeta.jsx` JSX 포함하므로 `.jsx` 확장자 필수.

### Styling

- 화이트 테마 + 건원 RED `#e60012`. **단일 소스: [frontend/src/kunwon-tokens.css](frontend/src/kunwon-tokens.css)** — `main.jsx` 에서 전역 import.
- 컴포넌트는 인라인 스타일에서 `style={{ color: 'var(--color-accent)' }}` 패턴. hex 직접 사용 금지.
- 신규 색 필요 시 `kunwon-tokens.css` 에 추가 (단일 소스).
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
6. **AI 종합 해설 (옵션, `include_insight` 기본 ON)**: `brief_advisor.interpret_brief()` Opus 1콜(`settings.model_id_advisor`) → `brief_data["_insight"]` 임베드 (별도 파일 아님). 한 방 통합(diagnose 패턴), 실패해도 비치명적(추출 산출물 유지). `to_html`·`to_markdown`·`to_xlsx` **3종 모두** `_insight` 를 "AI 종합 해설" 섹션/시트로 렌더(LLM 0; html 은 핵심수치 카드 직후, md 는 `## 0`, xlsx 는 맨 앞 시트).
7. `_brief_meta.source_format` (`"pdf"` | `"docx"` | `"hwp"` | `"hwpx"`) 기록.
8. 저장: `_atomic_write(json)` + `_sync_write(md)` + `_sync_write(html)` + `_sync_write_bytes(xlsx)`. 위치: `{db_path}/_briefs/{stamp}_{facility_type}_{slug}.{json|md|html|xlsx}` (≤120자).
9. SSE `complete`: `{brief_id, md_filename, xlsx_filename, html_filename, validation_summary, source_format, has_insight}`. accumulate 의 `done`/`brief` 이벤트도 `html_filename` 포함.
10. 분석 후 별도 엔드포인트(추출 재처리 0): `POST /{brief_id}/interpret`(해설 재생성), `POST /{brief_id}/propose`(수주 제안서), `POST /{brief_id}/playbook`(경험 기반 처방 — `reference_cases` 없으면 무료 게이트로 LLM 미호출).

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
  submission_quantitative, rubric_version: "v1"
}
```

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
  win_themes: [{theme, rationale, scoring_link, basis: [...]}],          # 수주 핵심 테마
  design_directions: [{direction, narrative, addresses, scoring_play, tradeoffs, site_rationale, basis: [...]}],  # 설계 접근 5안 (Phase 2: narrative=2~4문장·득점·이 부지라서)
  program_directions: [{claim, detail, basis: [...]}],    # AI 해석층 — 프로그램 방향 (Phase 2, detail=2~4문장)
  massing_strategy:   [{claim, detail, basis: [...]}],    # AI 해석층 — 매스 전략 (Phase 2, detail=2~4문장)
  phasing:            [{claim, detail, basis: [...]}],    # AI 해석층 — 단계 접근 (Phase 2, detail=2~4문장)
  priorities: [{rank, focus, why, scoring_weight}],        # 배점 기반 착수 우선순위
  risks: [{risk, severity: "high|medium|low", mitigation, basis}],
  kickoff_checklist: [str], open_questions: [str],
  scoring_focus: [...],                                    # 결정론 (LLM 환각 차단용 덮어씀)
  _number_flags: [{value, field, context}],               # 근거 없는 수치 검산 (proposal_number_check, 숫자 수정 0)
  _reference_cases: {...},                                 # reference_cases.collect_reference_context() 원본, 없으면 {}
  data_confidence: "high|medium|low", caveats: [str]
}
```

`interpret`(=`_insight`, 해설가) 과 별개. 사실 주장엔 근거 인용 강제, 전략·접근은 제안으로 명시. **당락 보장 금지** — caveats 에 "실제 심사 결과 보장 못 함" 강제. 별도 `{brief_id}_proposal.html` 로 렌더. **2층 분리(Phase 2):** `program_directions`/`massing_strategy`/`phasing` = AI 해석 확장층 — 1층 사실(배점·강조·대지) 위 추론, 각 항목 `basis` 앵커 강제, 새 숫자를 사실로 만들지 않음(가정은 open_questions/caveats). 렌더는 명시적 범례 + "AI 해석" 배지로 사실과 구분.

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

`interpret`(해설가)·`propose`(전략가) 와 **별개인 세 번째 산출물**. advisor/propose 가 `reference_cases` 를 배경 참고로만 쓰는 것과 정반대 — playbook 은 그것을 **주연료**로 삼아 과거 당락→이 지침서 능동 처방. **핵심 오염 방지:** `applications` 각 항목은 과거 교훈(`rooted_in`)+이 지침서 실제 사실(`basis`, p.N/항목명) **둘 다** 앵커, 못 달면 제외 — 과거 공모 수치를 이 지침서 사실로 옮기기 금지. **무료 게이트:** `reference_cases` 비면 LLM 미호출·`has_accumulated_data=false` sentinel. 별도 `{brief_id}_playbook.html` 로 렌더(2층 시각 분리 + "AI 해석" 배지). 당락 예측·보장 없음. 전제조건=DB에 같은 시설유형 과거 데이터 축적.

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

- **Grading (5-level A/B/C/D/E):** 점수 숫자 아닌 문자열. 임원 검토 시 정밀도 논쟁 차단 + 환각 검증 부담 감소. 구 `score`(0-10) 자동 변환: ≥8.5=A / ≥7=B / ≥5=C / ≥3=D / else=E. 백엔드 `grade_helpers.py`, 프론트 `constants/index.js::GRADE_COLOR/GRADE_BG/toGrade()`.
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
- **시퀀스 C — 멀티파일 지침서 업로드:** ✅ 기본 구현 완료 (접근 A: `analyze` 가 `brief_pdf_refs` JSON 배열로 복수 파일 동시 분석, `_brief_meta.source_files: list[...]`, `_merge_multi_brief_data`). **남은 보류: 충돌 우선순위 = 현재 업로드 순서(first_wins)뿐, 도메인 규칙 없음** — 지침서 vs 과업지시서가 정량·스칼라 필드를 다르게 규정하면 먼저 올린 파일이 조용히 이김(설계지침은 additive 병합이라 무손실). 개선 방향: 충돌을 숨기지 말고 `_quantitative_flags` 처럼 경고로 노출해 사람이 판단.
- **시퀀스 D — 오프라인 / 제로-API 지침서 분석 (Claude Code 가 LLM 엔진):** API 토큰 절감용 **로컬·소량 전용** 경로. 동기: 파이프라인에서 LLM 필요 단계는 **classify / extract / requirements 3개뿐**이고 나머지(파싱·표 배점 파싱·`merge_extracted_data`·`validate_brief`·exporter)는 이미 결정론적 무료. DOCX/HWP/HWPX 는 **텍스트·표 기반(비전 불필요)** 이라 그 3단계가 "블록 텍스트 읽고 JSON 생성"에 불과 → **Claude Code(또는 claude.ai)가 직접 수행 가능**(구독 기반이면 API 미터 미사용, API 키 종량제면 과금됨). 구현안: `tools/analyze_brief_offline.py` — ① 결정론적 파싱 → 블록 + `source_text` + classify/extract 프롬프트를 파일로 출력, ② Claude Code 가 그 핸드오프를 읽고 classify/extract JSON 채움, ③ 다시 도구가 `merge_extracted_data` → `validate_brief` → 기존 exporter 로 **동일한 xlsx/html/md** 산출. 한계: **배포 앱엔 불가**(Cloud Run 서버는 구독 호출 불가, API 만 가능) · PDF 는 비전 필요로 핸드오프 무거움(DOCX/HWP/HWPX 가 최적) · 소량 수동 전용(배치 부적합). 같은 원리로 compare/diagnose 도 가능하나 제안서 PDF 는 비전+복잡해 손이 더 감.
- **시퀀스 E — 수주 제안서 비주얼 덱 출력 (`brief_proposal` 출력 고도화):** Phase 1(히어로+팩트밴드) ✅ / Phase 2(AI 해석 확장층·범례·근거 미확인 수치 밴드) ✅ / **Phase 3(PPT형 덱 전면 재설계) 미착수 → 당면 TODO 4번**. 현재 `brief_proposal_report_generator.to_proposal_html` 은 *보고서형*(스크롤 섹션). 사용자 피드백으로 **PPT형 스크롤 덱**이 더 낫다고 확정 — 향후 그 양식을 앱 기본 출력으로 이식. 디자인 계약(수동 검증 완료): ① **하나의 통일 캔버스**(섹션별 배경색 분리 금지 — "페이지 나눈 느낌" 역효과) ② 글을 줄일 땐 **삭제 말고 도식·아이콘으로 치환**(SVG: 맥락 개념도·100칸 와플 배점·매트릭스+상세카드·단면 긴장도·인허가 타임라인) ③ **밀도 높게**(나란히 배치) ④ 5안은 매트릭스(한눈) + **상세 카드**(공간전략/득점/포기/이 부지라서 + 매스 실루엣)로 — 이게 사용자가 "최종적으로 얻고 싶은" 산출물 ⑤ 매스는 *평면 만화 금지*(실무자 역효과), 측면 개념 실루엣까지만. 참고 산출물은 수동 생성본(시퀀스 D 경로) 존재. Phase 1 히어로는 사용자가 디자인·표현·이미지 해석 로직 불만족(2026-06-29) → Phase 3에서 히어로 재설계 포함.
- **시퀀스 F — 대지·맥락 분석 통합:** ✅ 구현·자동 파이프라인 통합 완료 (2026-06-26~29, 위성+지적도 하이브리드 단일 이미지). 상세는 Core Services 표의 `vworld_analyzer.py` 참조. 남은 보류: ③ SketchUp MCP 3D 매스 — 사용자가 자료 줄 때 재개.

## 당면 TODO (2026-07-01 기준)

VWorld 실동작 확인·대지분석 섹션·지적도 오버레이는 완료(시퀀스 F 참조). 남은 항목:

1. **시퀀스 E Phase 3 — PPT형 스크롤 덱 재설계** — `backend/brief_proposal_report_generator.py` → `to_proposal_html()` 전면 재작성. 기존 `_proposal` JSON 재사용(LLM 재호출 없음) — `POST /{brief_id}/propose` 재실행으로 HTML만 갱신. 디자인 계약 5조: ① 단일 통일 캔버스(섹션 배경색 분리 금지) ② 글 삭제 말고 SVG 도식으로 치환(100칸 와플 배점·5안 매트릭스·맥락 개념도·인허가 타임라인) ③ 밀도 높게·나란히 배치 ④ 5안 = 매트릭스(한눈) + 상세 카드(공간전략/득점/포기/이부지라서 + 측면 실루엣) ⑤ 평면 만화 금지·측면 개념 실루엣까지만. 히어로 재설계(위성 이미지 표현·주석 오버레이·판독 텍스트 카드화) 포함. 회귀: `tests/test_brief_proposal_report.py` (27케이스) 통과 필수.

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

**테스트:** `cd backend && venv/Scripts/python.exe -m pytest tests/ -v` (현재 431 passed, suite = `backend/tests/`). `brief_genre.py`(장르 판별) 수정 시 `tests/test_brief_genre.py` 7 케이스. `bid_structure.py`(입찰 2층 배점·다중표 병합) 수정 시 `tests/test_bid_structure.py` 14 케이스. `_extract_docx_eval_from_table` (배점표 파싱) 수정 시 `tests/test_eval_table_multilevel.py` 4 케이스(다단계 PQ 표 points_col·이름 귀속·합계). `brief_playbook.py` / `brief_playbook_report_generator.py` 수정 시 `tests/test_brief_playbook.py` 7 케이스 (무료 게이트·결정론 덮어쓰기·렌더 escape, LLM monkeypatch). HWP/HWPX 코드 추가 시 `tests/test_hwpx_loader.py` 회귀 보호 필수 (22 케이스, rhwp monkeypatch — rhwp 미설치 환경도 통과). `tests/test_normalize_design_grouped.py` 13 케이스, `tests/test_pure_functions.py::TestBriefValidatorPointsMismatch` 15 케이스도 동일. `quant_validator.py` / `pattern_builder._build_quant_stats` / `merge_extracted_data` 의 `_quantitative_flags` 훅 수정 시 `tests/test_quant_validator.py` 19 케이스. `feasibility_export.py` 수정 시 `tests/test_feasibility_export.py` 46 케이스 + 무료 검증 `tools/feasibility_verify.py`. ⚠️ DOCX 회귀 `test_docx_extractor.py` (10 케이스) 는 repo-root `tests/` 에 있어 backend 기준 suite(393)에 **미포함** — DOCX 수정 시 별도 실행 (repo-root cwd): `backend/venv/Scripts/python.exe -m pytest tests/test_docx_extractor.py`. repo-root `tests/` 엔 conftest 없음 — 테스트 파일이 직접 `services.utils` 등을 sys.modules 스텁(`types.ModuleType`)하므로, `data_extractor` 가 `services.utils` 에서 새 심볼을 import 하면 **스텁 함수 목록도 갱신 필수** (안 하면 collection 단계 `cannot import name ... (unknown location)`). 현재 상태: 9 pass / 1 사전실패 `test_force_cut_31_paragraphs` (docx_loader F3 force-cut 미발동, **미해결·brief 전용**).

## Deployment

- `main` push → GitHub Actions (`.github/workflows/deploy.yml`) → Docker 빌드 → Cloud Run.
- 수동 fallback: `gcloud run deploy competition-analyzer --source . --region asia-northeast3`.
- 로그: `gcloud logging read "resource.type=cloud_run_revision" --limit=50`.
- 상세는 `DEPLOYMENT.md`.

Cloud Run 청크 업로드 (`/api/upload`) 가 32MB 한도 우회. 파이프라인은 multipart 대신 `file_ref` 받음.
