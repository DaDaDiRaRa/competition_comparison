"""tests/test_eval_table_multilevel.py — 다단계 사업수행능력(PQ) 배점표 파싱 회귀.

대치미도 설계자 입찰지침서(HWP)에서 재현된 버그:
  헤더가 '… | 배점 | 점수 계산 방법 | 점수 계산 방법 | …' 처럼 '점수 계산 방법'을
  여러 번 포함하면, points_col 식별 정규식(비중|배점|점수|가중)이 마지막 매칭인
  '점수 계산 방법'(등급별 산출점수 컬럼)으로 덮어써져 배점 대신 등급점수·세대수
  임계값을 배점으로 오추출 → total 989.8 (정상 100).

수정: ① '계산/산출/방법' 컬럼은 배점 후보에서 배제, '배점/비중/가중' 우선(동점 최좌)
      ② 다단계 세로병합에서 상위 카테고리 셀(col0)이 빈 하위 행을 name_groups(merge_info)
         로 복원 → 유사용역실적/신용도 귀속 교정.

이 테스트는 실제 표 구조(3레벨 col0 병합 + 배점 col 병합 + 점수계산방법 트랩 + 합계행)를
압축 재현한다.
"""
import sys
from pathlib import Path
from collections import OrderedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.data_extractor import _extract_docx_eval_from_table


# 대치미도 PQ 배점표 압축 재현 —
#   참여기술자(50) = 경력25 + 실적25 (col0 4행 세로병합, 배점 col 2행씩 병합)
#   유사용역실적(40) = 40 (col0 2행 병합)
#   신용도(10) = 10 (단일 행)
#   합계 = 100
# merge_info.row 는 원본 rows(헤더=row0) 기준.
_PQ_BLOCK = {
    "table_rows_raw": [
        ["평가항목", "평가항목", "평가 방법", "배점", "점수 계산 방법", "점수 계산 방법"],  # row0 헤더
        ["참여기술자(50)", "경력",       "절대평가", "25", "15년 이상", "12년 이상"],          # row1
        ["",              "",           "",        "",   "25",        "24"],                # row2 (배점 병합·col0 병합 → blank)
        ["",              "유사용역 실적", "절대평가", "25", "5건 이상",  "3건 이상"],          # row3 (col0 여전히 참여기술자 병합)
        ["",              "",           "",        "",   "25",        "24"],                # row4
        ["유사용역 실적(40)", "실적건수", "절대평가", "40", "5건 이상",  "3건 이상"],          # row5
        ["",              "",           "",        "",   "40",        "38"],                # row6
        ["신용도(10)",      "지정기간",   "절대평가", "10", "예시",      "예시"],              # row7
        ["합 계",          "",           "",        "100", "",         ""],                 # row8
    ],
    "merge_info": [
        {"row": 1, "col": 0, "merged_rows": 4, "value": "참여기술자(50)"},   # rows1-4
        {"row": 1, "col": 3, "merged_rows": 2, "value": "25"},
        {"row": 3, "col": 3, "merged_rows": 2, "value": "25"},
        {"row": 5, "col": 0, "merged_rows": 2, "value": "유사용역 실적(40)"},  # rows5-6
        {"row": 5, "col": 3, "merged_rows": 2, "value": "40"},
    ],
}


def _agg(res):
    agg = OrderedDict()
    for c in res["evaluation_categories"]:
        agg.setdefault(c["name"], 0.0)
        if isinstance(c["points"], (int, float)):
            agg[c["name"]] += c["points"]
    return agg


class TestMultiLevelPQTable:
    def test_total_is_100_not_summed_garbage(self):
        """배점 컬럼(합계 100)을 잡아야 한다 — '점수 계산 방법' 컬럼 오선택 금지."""
        res = _extract_docx_eval_from_table(_PQ_BLOCK)
        assert res["total_points"] == 100.0

    def test_no_grade_score_or_threshold_leak(self):
        """등급점수(24·38)·임계값(세대수 등)이 배점으로 새면 안 됨 — 최대 단일 배점 ≤ 50."""
        res = _extract_docx_eval_from_table(_PQ_BLOCK)
        pts = [c["points"] for c in res["evaluation_categories"] if isinstance(c["points"], (int, float))]
        assert pts, "배점이 하나도 안 잡히면 실패"
        assert max(pts) <= 50, f"과대 배점 누출: {max(pts)}"

    def test_category_names_attributed_via_merge(self):
        """다단계 병합에서 이름이 ''로 새지 않고 상위 카테고리로 귀속돼야 한다."""
        res = _extract_docx_eval_from_table(_PQ_BLOCK)
        agg = _agg(res)
        assert "" not in agg, f"빈 이름 카테고리 발생: {list(agg)}"
        assert agg.get("참여기술자(50)") == 50.0
        assert agg.get("유사용역 실적(40)") == 40.0
        assert agg.get("신용도(10)") == 10.0
        # 합계행은 카테고리에서 제외
        assert not any("합" in n and "계" in n for n in agg)

    def test_points_sum_equals_total(self):
        res = _extract_docx_eval_from_table(_PQ_BLOCK)
        s = sum(c["points"] for c in res["evaluation_categories"] if isinstance(c["points"], (int, float)))
        assert s == 100.0
