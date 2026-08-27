"""멀티파일 병합 충돌 탐지 회귀 — LLM 0 · 값 수정 0.

시퀀스 C 잔여("충돌해소는 업로드 순서뿐, 도메인 규칙 없음")의 절반을 푼다:
**해소는 그대로 first_wins 지만 조용하지 않게** 한다. 진 값이 어디에도 안 남으면
두 문서가 대지면적을 다르게 적어도 사람은 그 사실을 모르고, 그 값이
feasibility_export → 법적 골격까지 흘러간다.

⚠ **자동 판정을 안 한다** — 지침서·과업지시서는 전부 같은 발주처 문서라
권위 서열이 실재하지 않는다(concept-studio 의 `gazette > guideline` 과 다른 점).
"""
import pytest

from services.brief_merge_conflicts import (
    band_html,
    detect_conflicts,
    md_lines,
    summary_line,
)


def F(quant=None, sites=None, **top):
    d = dict(top)
    if quant is not None:
        d["_quantitative"] = quant
    if sites is not None:
        d["brief_project_info"] = {"sites": sites}
    return d


def _keys(flags):
    return {f["key"] for f in flags}


# ── 없어야 할 때 없다 ───────────────────────────────────────────────────────


@pytest.mark.parametrize("data", [
    [], [F(quant={"site_area_sqm": 100})], None, "문자열", [None, "x"],
])
def test_single_or_garbage_gives_nothing(data):
    assert detect_conflicts(data) == []


def test_same_values_are_not_a_conflict():
    a = F(quant={"site_area_sqm": 12345.0})
    b = F(quant={"site_area_sqm": 12345})       # 12345 == 12345.0
    assert detect_conflicts([a, b]) == []


def test_missing_in_one_file_is_not_a_conflict():
    """뒤 파일이 값을 안 가진 건 충돌이 아니라 그냥 없는 것이다."""
    a = F(quant={"site_area_sqm": 12345, "floors_above": 10})
    b = F(quant={"site_area_sqm": 12345})
    assert detect_conflicts([a, b]) == []


# ── 정량 ────────────────────────────────────────────────────────────────────


def test_quantitative_conflict_is_named():
    a = F(quant={"site_area_sqm": 12345})
    b = F(quant={"site_area_sqm": 12500})
    flags = detect_conflicts([a, b], ["지침서.pdf", "과업지시서.pdf"])
    assert len(flags) == 1
    f = flags[0]
    assert f["kind"] == "quantitative" and f["key"] == "site_area_sqm"
    assert f["chosen"] == 12345 and f["chosen_from"] == "지침서.pdf"
    assert f["others"] == [{"value": 12500, "from": "과업지시서.pdf"}]


def test_first_wins_is_preserved_we_only_report():
    """값을 고치지 않는다 — 채택값은 여전히 첫 파일 것이다."""
    flags = detect_conflicts([F(quant={"far_pct": 460}), F(quant={"far_pct": 400})])
    assert flags[0]["chosen"] == 460


def test_three_files_report_every_loser():
    flags = detect_conflicts(
        [F(quant={"x": 1}), F(quant={"x": 2}), F(quant={"x": 3})],
        ["a.pdf", "b.pdf", "c.pdf"])
    assert [o["value"] for o in flags[0]["others"]] == [2, 3]


def test_first_null_does_not_become_the_winner():
    """first **non-null** wins — 앞 파일이 비었으면 뒤 파일이 채택값이다."""
    flags = detect_conflicts(
        [F(quant={"x": None}), F(quant={"x": 2}), F(quant={"x": 3})],
        ["a.pdf", "b.pdf", "c.pdf"])
    assert flags[0]["chosen"] == 2 and flags[0]["chosen_from"] == "b.pdf"


# ── 부지 (feasibility_export 입력 → 법적 골격까지 간다) ─────────────────────


def test_site_level_numeric_conflict():
    a = F(sites=[{"site_id": "부지1", "site_area_sqm": 7498, "building_coverage_pct": 60}])
    b = F(sites=[{"site_id": "부지1", "site_area_sqm": 7500, "building_coverage_pct": 60}])
    flags = detect_conflicts([a, b])
    assert _keys(flags) == {"부지1.site_area_sqm"}


def test_sites_are_matched_by_id_not_position():
    a = F(sites=[{"site_id": "부지1", "site_area_sqm": 100},
                 {"site_id": "부지2", "site_area_sqm": 200}])
    b = F(sites=[{"site_id": "부지2", "site_area_sqm": 999},   # 순서가 반대
                 {"site_id": "부지1", "site_area_sqm": 100}])
    flags = detect_conflicts([a, b])
    assert _keys(flags) == {"부지2.site_area_sqm"}


def test_site_without_id_falls_back_to_position():
    a = F(sites=[{"site_area_sqm": 100}])
    b = F(sites=[{"site_area_sqm": 200}])
    assert _keys(detect_conflicts([a, b])) == {"#1.site_area_sqm"}


# ── 블록 유실 ───────────────────────────────────────────────────────────────


def test_dropped_block_is_reported():
    """필드별 병합이 아니라 first_wins 라 뒤 파일 블록은 통째로 사라진다."""
    a = F(brief_evaluation={"items": [{"item": "배치", "points": 40}]})
    b = F(brief_evaluation={"items": [{"item": "배치", "points": 30}]})
    flags = detect_conflicts([a, b], ["지침서.pdf", "공고문.pdf"])
    blk = [f for f in flags if f["kind"] == "block"]
    assert blk and blk[0]["key"] == "brief_evaluation"
    assert blk[0]["others"][0]["from"] == "공고문.pdf"


def test_identical_block_is_not_reported():
    same = {"items": [{"item": "배치", "points": 40}]}
    flags = detect_conflicts([F(brief_evaluation=same), F(brief_evaluation=dict(same))])
    assert [f for f in flags if f["kind"] == "block"] == []


def test_specially_merged_keys_are_not_block_flagged():
    """page_map·design_guidelines_grouped 등은 합산·재정규화라 유실이 아니다."""
    a = F(page_map=[{"page": 1}], design_guidelines_grouped=[{"g": 1}], total_pages=1)
    b = F(page_map=[{"page": 2}], design_guidelines_grouped=[{"g": 2}], total_pages=1)
    assert [f for f in detect_conflicts([a, b]) if f["kind"] == "block"] == []


def test_empty_block_in_later_file_is_not_a_loss():
    assert detect_conflicts([F(brief_site=[{"address": "a"}]), F(brief_site=[])]) == []


# ── 파일 이름 날짜는 힌트지 판정이 아니다 ───────────────────────────────────


def test_later_dated_file_is_marked_but_does_not_win():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})],
                             ["260729_지침서.pdf", "260806_과업지시서.pdf"])
    assert flags[0]["later_differs"] is True
    assert flags[0]["chosen"] == 1, "날짜로 자동 판정하면 안 된다 — 표시만"


def test_earlier_dated_file_is_not_marked():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})],
                             ["260806_지침서.pdf", "260729_구버전.pdf"])
    assert flags[0]["later_differs"] is False


@pytest.mark.parametrize("names", [
    ["a.pdf", "b.pdf"],                       # 날짜 없음
    ["20260729_a.pdf", "20260806_b.pdf"],     # 8자리
])
def test_date_parsing_shapes(names):
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})], names)
    assert isinstance(flags[0]["later_differs"], bool)


def test_unnamed_files_get_positional_labels():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})])
    assert flags[0]["chosen_from"] == "파일1"
    assert flags[0]["others"][0]["from"] == "파일2"


# ── 렌더 ────────────────────────────────────────────────────────────────────


def test_band_says_it_is_not_an_automatic_judgment():
    flags = detect_conflicts([F(quant={"site_area_sqm": 12345})],
                             ["a.pdf"]) or detect_conflicts(
        [F(quant={"site_area_sqm": 12345}), F(quant={"site_area_sqm": 12500})],
        ["지침서.pdf", "과업지시서.pdf"])
    out = band_html(flags)
    assert "자동 판정 아님" in out
    assert "site_area_sqm" in out and "12,500" in out


def test_band_and_md_are_empty_without_conflicts():
    assert band_html([]) == "" and band_html(None) == ""
    assert md_lines([]) == [] and md_lines(None) == []


def test_md_carries_the_same_fact():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})],
                             ["260729_a.pdf", "260806_b.pdf"])
    md = "\n".join(md_lines(flags))
    assert "파일 간 충돌" in md and "먼저 올린 파일 값을 채택" in md
    assert "나중 날짜 파일이 다름" in md


def test_band_escapes_filenames():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})],
                             ["<script>.pdf", "b.pdf"])
    out = band_html(flags)
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_summary_line_counts_later_differs():
    flags = detect_conflicts([F(quant={"x": 1}), F(quant={"x": 2})],
                             ["260729_a.pdf", "260806_b.pdf"])
    assert summary_line(flags) == "파일 간 충돌 1건 · 그중 1건은 나중 날짜 파일이 다르게 말함"


def test_precise_site_flags_suppress_the_coarse_block_notice():
    """같은 사실을 두 번 말하면 정확한 줄이 뭉뚱그린 줄에 묻힌다."""
    a = F(sites=[{"site_id": "부지1", "site_area_sqm": 7498}])
    b = F(sites=[{"site_id": "부지1", "site_area_sqm": 7500}])
    flags = detect_conflicts([a, b])
    assert _keys(flags) == {"부지1.site_area_sqm"}
    assert "brief_project_info" not in _keys(flags)


def test_block_notice_survives_when_the_difference_is_outside_site_numbers():
    """부지 수치는 같은데 다른 필드가 다르면 뭉뚱그린 통지라도 낸다(silent skip 0)."""
    a = F(sites=[{"site_id": "부지1", "site_area_sqm": 100}])
    a["brief_project_info"]["organizer"] = "영등포구"
    b = F(sites=[{"site_id": "부지1", "site_area_sqm": 100}])
    b["brief_project_info"]["organizer"] = "서울시"
    flags = detect_conflicts([a, b])
    assert _keys(flags) == {"brief_project_info"}


# ── 라우터 배선 ─────────────────────────────────────────────────────────────


def test_router_merge_keeps_first_wins_and_attaches_flags():
    """해소는 안 바뀐다 — 채택값은 그대로고 진 값만 기록된다."""
    from routers.brief import _merge_multi_brief_data
    a = F(quant={"site_area_sqm": 12345},
          sites=[{"site_id": "부지1", "site_area_sqm": 7498}], page_map=[{"page": 1}])
    b = F(quant={"site_area_sqm": 12500},
          sites=[{"site_id": "부지1", "site_area_sqm": 7500}], page_map=[{"page": 1}])
    m = _merge_multi_brief_data([a, b], ["260729_지침서.pdf", "260806_과업지시서.pdf"])
    assert m["_quantitative"]["site_area_sqm"] == 12345
    kinds = {f["kind"] for f in m["_merge_conflicts"]}
    assert kinds == {"quantitative", "site"}
    assert all(f["later_differs"] for f in m["_merge_conflicts"])


def test_router_merge_single_file_has_no_conflict_key():
    from routers.brief import _merge_multi_brief_data
    assert "_merge_conflicts" not in _merge_multi_brief_data([F(quant={"x": 1})])


def test_router_merge_without_names_still_works():
    """하위호환 — source_names 없이 부르던 옛 호출."""
    from routers.brief import _merge_multi_brief_data
    m = _merge_multi_brief_data([F(quant={"x": 1}), F(quant={"x": 2})])
    assert m["_merge_conflicts"][0]["chosen_from"] == "파일1"
