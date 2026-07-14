# MATURITY.md — 기능별 성숙도 진단 & 수정 로드맵

> 작성 2026-07-14. 기준선 = **지침서 분석 파이프라인**(BriefMode).
> 목적: 지침서 분석만큼 "날카롭고·정확도 높고·활용도 높은" 상태로 나머지 기능을 끌어올리기 위한 진단과 수정 순위.

## 기준선 — 지침서 분석이 날카로운 이유 (6축)

LLM을 잘 써서가 아니라 **LLM 주변을 결정론으로 감쌌기** 때문. 이 6축이 평가 잣대다.

1. **결정론 백본** — `quant_validator` · `scoring_focus` · `feasibility_export` · `bid_structure` · `brief_genre` (LLM 0콜로 사실 고정)
2. **환각 방어 다중** — BRIEF_EVALUATION 5중 방어, `proposal_number_check`(근거 없는 수치 검산)
3. **사실/해석 2층 분리** — 사실엔 근거 인용 강제, 추론엔 "AI 해석" 배지 + `basis` 앵커
4. **인용 강제** — `(p.N)`
5. **자체완결 다포맷 산출물** — html / xlsx / md
6. **두터운 회귀 테스트** — 기능별 수십 케이스

## 스코어카드 (● 충족 / ○ 미흡)

| 축 | 지침서 | 진단 | 공모등록+비교 | 아카이브 | 교차비교 | 내프로젝트 |
|---|---|---|---|---|---|---|
| 결정론 백본 | ●●● | ●●○ | ●●○ | ●○○ | ●○○ | ○○○ |
| 환각 방어 | ●●● | ●●○ | ●●○ | ●○○ | ●●○ | ○○○ |
| 사실/해석 2층 | ●●● | ●○○ | ●●○ | —(검색) | ●●○ | ●○○ |
| 인용 강제(사후검증) | ●●○ | ●○○ | ●○○ | ○○○ | ●○○ | ●○○ |
| 산출물 풍부도 | ●●● | ●●● | ●●○ | ●●○ | ●●○ | ●●○ |
| 회귀 테스트 | ●●● | ●●○¹ | ●○○¹ | ○○○ | ○○○ | ○○○ |

¹ 진단·비교는 공유하는 `quant_validator` 테스트만 존재. **자기 고유 로직(`diagnose_submission` / `comparator` 2-pass) 테스트는 0.**

## 기능별 진단 (근접 순)

### 1. 제안서 진단 (Diagnose) — 기준선의 ~70%, 가장 근접
- **강점**: 백본 상당 공유 — `quant_validator`, `loser_stats`(당선/낙선 이원 비교), 패턴편차 자동계산, `grade_justification` 형식, `(p.N)` 인용 강제. 지침서에 없는 **낙선 안티패턴 비교**가 오히려 강점.
- **약점**: 1-pass(사후검증 없음) · `(p.N)`가 프롬프트에만 있고 **사후 정규식 검증 없음** · `diagnose_submission` 자기 회귀 테스트 부재 · 패턴편차 계산이 LLM 프롬프트 내부에 숨어 역산 불가.
- 근거: `routers/diagnose.py`, `services/comparator.py::diagnose_submission`, `services/diagnosis_report_generator.py`.

### 2. 공모등록 + 비교 (Accumulate + Compare) — 축에 따라 오히려 더 성숙
- **강점**: `comparator`의 **2-pass blind-reveal**(익명 채점 → 리빌 사후분석)은 지침서에도 없는 정교한 구조. `_compute_gap_analysis()` 결정론 계산, `concept_comparison`(축별 컨셉 나란히 비교)이 실무 핵심. `quant_validator`가 패턴 집계 오염 차단.
- **약점**: **비교/리포트 로직 회귀 테스트 0** · `concept_comparison`이 프롬프트 규약만 있고 "모든 회사 인용했는지" 자동 검증 없음.
- 근거: `routers/accumulate.py`, `services/comparator.py`, `services/report_generator.py`, `services/pattern_builder.py`.

### 3. 아카이브 검색 (Archive) — 목적엔 충분하나 얇음
- **강점**: FTS5(trigram) + LLM 키워드 추출 + 자동 재인덱싱(`rebuild_index`, 비교분석 후 즉시 반영). 예외 처리(LLM 실패 시 FTS5 폴백).
- **약점**: **랭킹 없음**(FTS5 OR 매칭 → 관련도 정렬 불가, 50건 컷) · 한글 형태소 없음(동의어 하드코딩) · 검색 결과에 "왜 매칭됐는지" 근거 미표시 · 테스트 0.
- 근거: `routers/archive.py`, `services/archive_search.py`, `main.py`(시작 시 `build_index`).

### 4. 교차비교 (CrossCompare) — 프로토타입 수준
- `compare_submissions()`를 거의 그대로 재사용한 껍데기. 치명적 약점 3개:
  - ① **지침서 통합 없음** — 첫 프로젝트 지침서만 로드, 나머지 무시 → 요구사항 기반 비교 불가. (기능이 반쯤 틀린 버그성 문제)
  - ② **결과 저장 안 함** — `comparison.json` 미저장 → 재조회 불가, 같은 조합 재비교마다 LLM 재호출.
  - ③ **다중 제출물 토큰 오버플로우** — 제출물 5개↑ × 축 8개에서 Pass 2가 32K 캡 도달 → 컨셉비교 잘림 위험.
- 테스트 0.
- 근거: `routers/accumulate.py`(`/cross-compare`), `services/comparator.py`, `services/db_manager.py`(`_cross_reports/`).

### 5. 내 프로젝트 등록 (MyProject) — 검증이 가장 얇음
- 단일 LLM 1콜(temp 0.3)로 끝. **결정론 검증·환각 방어·인용 사후검증 전무.** LLM 출력을 거의 그대로 신뢰(`setdefault` 폴백만). 결과 라벨 공개 전 추출이 끝나 사후 학습 없음.
- 산출물 HTML은 깔끔하나 내용 신뢰도를 보증하는 장치가 없음.
- 근거: `services/myproject_analyzer.py::deep_analyze`, `services/myproject_report_generator.py`.

## 관통하는 공통 격차 (5개 전부 해당)

- **(A) 인용 사후검증 부재** — 어디서도 LLM이 뱉은 `(p.N)`이 실재 페이지인지 검증하지 않음. 프롬프트로만 강제.
- **(B) 자기 고유 로직 회귀 테스트 부재** — 공유 `quant_validator`만 테스트 존재. 진단·비교·교차·아카이브·내프로젝트의 고유 로직은 테스트 0.
- **(C) 사실/해석 2층 분리 미적용** — "AI 해석" 배지 + `basis` 앵커는 지침서 제안서·플레이북만의 장치. 진단·비교 서술은 사실과 추론이 섞임.

---

# 수정 로드맵 (실행 순위)

impact(정확도·활용도 개선폭) ÷ effort 로 정렬. 위에서부터 순서대로 실행.

| 순위 | 작업 | 대상 기능 | 성격 | 노력 | 임팩트 |
|---|---|---|---|---|---|
| **1** | 교차비교 **지침서 통합 버그** 수정 — 프로젝트별 각자의 `_brief.json` 로드해 비교에 반영 | 교차비교 | 버그(기능 반오작동) | 소 | 대 |
| **2** | **인용 사후검증 공용 유틸** `verify_citations(text, extracted)` — 프롬프트 강제→코드 검증 승격, 진단·비교·교차·내프로젝트에 주입 | 4개 공통 | 격차 (A) | 중 | 대 |
| **3** | 내프로젝트에 **`quant_validator` 연결** — 이미 있는 결정론 백본을 안 쓰는 상태 해소(`_quantitative_flags` 부착) | 내프로젝트 | 결정론 백본 | 소 | 중 |
| **4** | 교차비교 **결과 저장/재조회** — `comparison.json` persist → 재호출 없이 재열람·이력 | 교차비교 | 활용도 | 중 | 중 |
| **5** | 교차비교 **토큰 오버플로우 가드** — 제출물 수 상한/청킹 또는 축 단위 분할로 컨셉비교 잘림 방지 | 교차비교 | 견고성 | 소~중 | 중 |
| **6** | 아카이브 **BM25 랭킹 + 결과 정렬** — FTS5 `rank` 사용, 관련도 순 정렬(현재 무순 50건 컷) | 아카이브 | 활용도 | 중 | 중 |
| **7** | 진단·비교 **사실/해석 2층 분리** — 서술에 "AI 해석" 배지 + `basis` 앵커(지침서 제안서 패턴 이식) | 진단·비교 | 격차 (C) | 중~대 | 중 |
| **8** | **회귀 테스트 백필** — `comparator` 2-pass·`diagnose_submission`·`cross_compare`·`archive_search`·`myproject_analyzer`(LLM monkeypatch) | 5개 전부 | 격차 (B) | 대 | 대(장기) |

## 순위 결정 근거

- **1~3은 "저노력·고효과"** — 1은 정확도가 아니라 기능이 반쯤 틀린 것(첫 지침서만), 2는 한 번 만들어 4곳에 재사용(cross-cutting), 3은 이미 있는 백본을 배선만.
- **4~6은 활용도·견고성** — 교차비교를 실사용 가능 수준으로 마감(4·5) + 아카이브 검색 품질(6).
- **7은 품질 상향** — 사실/해석 분리는 임팩트 크나 서술 로직·렌더러를 함께 손대야 해 노력이 큼.
- **8은 마지막** — 테스트는 위 변경들이 안정화된 뒤 그 최종 형태에 맞춰 한 번에 까는 게 재작업이 적음. (단, 1~7 진행 중 회귀가 두려운 지점은 최소 스모크 테스트를 그때그때 추가)

## 진행 체크리스트

- [x] 1. 교차비교 지침서 통합 — 2026-07-14 완료 (제출물별 `_brief_context` 부착, comparator 추가절, 회귀 5케이스)
- [x] 2. 인용 사후검증 공용 유틸 — 2026-07-14 완료 (`citation_check.py`, compare·cross·diagnose·myproject 배선 + 3개 리포트 경고 밴드, 회귀 19케이스)
- [x] 3. 내프로젝트 quant_validator 연결 — 2026-07-14 완료 (이미 계산되던 `_quantitative_flags`를 deep_analyze 프롬프트 error 주입 + 리포트 밴드로 노출, `quant_validator.flags_band_html` 추가, 회귀 7케이스)
- [x] 4. 교차비교 결과 저장/재조회 — 2026-07-14 완료 (HTML 옆에 구조화 JSON 저장, `save/load_cross_compare_data`, `has_data` 플래그, `/rerender` 라우트(LLM 0), 프론트 재렌더 버튼, 회귀 5케이스)
- [x] 5. 교차비교 토큰 오버플로우 가드 — 2026-07-14 완료 (⚠재평가: 오버플로우 위험은 ~30제출물부터로 과대추정이었음. 진짜 latent 버그=Pass 2 실패 시 성공한 Pass 1 통째 유실. 방어 가드로 전환: Pass 2 비치명화(Pass 1 등급 보존)+concept 전축키 보장+capped/실패 시 `_coverage_note` 고지+리포트 렌더, 회귀 3케이스)
- [x] 6. 아카이브 BM25 랭킹 — 2026-07-14 완료 (FTS5 `ORDER BY bm25()` 관련도순 + 컬럼 가중치 `_BM25_WEIGHTS`(시설유형·컨셉키워드 우대), 무순 폴백, `_ranked_match` 공유 헬퍼로 keyword·natural 통일, 회귀 4케이스). 남은 무관 한계: trigram 2자 미만 미매칭(병원·시청)은 별개 이슈
- [x] 7. 진단·비교 사실/해석 2층 분리 — 2026-07-14 완료 (`report_badges.py` 공용 배지·범례. 진단=보강(recommendations) 배지, 비교=당선/낙선 사후요약 배지 + 상단 범례. 사실(강점/약점/근거·p.N)은 그대로. 프롬프트·스키마 불변(렌더만), 회귀 8케이스). 자연 확장: MyProject improvement_points·key_differentiators도 동일 배지 적용 가능(미적용)
- [ ] 8. 회귀 테스트 백필
