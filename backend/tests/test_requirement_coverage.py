"""지침서 요구 완결성 감사 회귀 — LLM 0 · 매트릭스 수정 0.

`quant_validator`·`citation_check` 와 같은 성격: 진단 매트릭스를 고치지 않고,
**분모(지침서 요구)에 있는데 분자(매트릭스)에 안 나온 것**만 이름 대고 말한다.

헛경고 하나가 진짜 누락 열 개의 신뢰를 깎는다(영등포 교훈) — 관대함을 잠근다.
"""
import pytest

from services.requirement_coverage import (
    AXIS_MATCH_MIN,
    MATCH_MIN,
    band_html,
    check_coverage,
    check_diagnosis,
    summary_line,
)


def R(desc, axis="site_plan"):
    return {"axis": axis, "description": desc, "weight_pct": None}


def M(req, axis="site_plan", status="yes", ev="근거 (p.12)"):
    return {"requirement": req, "axis": axis, "status": status, "evidence": ev}


# ── 분모·분자 ───────────────────────────────────────────────────────────────


def test_counts_denominator_and_numerator():
    reqs = [R("보행자 전용 통로를 남측 도로에 접하여 계획할 것"),
            R("옥상 조경 면적을 대지면적의 10% 이상 확보할 것"),
            R("지하 주차장은 2개 층 이하로 계획할 것")]
    mapping = [M("보행자 전용 통로 남측 배치"), M("옥상 조경 10% 확보")]
    cov = check_coverage(reqs, mapping)
    assert cov["total"] == 3
    assert cov["mapped"] == 2
    assert cov["coverage_pct"] == 67
    assert len(cov["unmapped"]) == 1
    assert "지하 주차장" in cov["unmapped"][0]["description"]


def test_summary_line_is_the_exec_number():
    cov = check_coverage([R("가"), R("나")], [M("가")])
    assert summary_line(cov) == "지침서 요구 2개 중 1개 응답 (50%)"


def test_no_requirements_is_none_not_zero_percent():
    """잴 것이 없는 것과 못 맞춘 것은 다르다."""
    cov = check_coverage([], [])
    assert cov["total"] == 0
    assert cov["coverage_pct"] is None
    assert summary_line(cov) == ""
    assert band_html(cov) == ""


def test_blank_descriptions_leave_the_denominator():
    """글이 없으면 대조할 수 없다 — 분모에서 뺀다(0% 로 몰지 않는다)."""
    cov = check_coverage([R(""), R("   "), R("옥상 조경 확보")], [M("옥상 조경 확보")])
    assert cov["total"] == 1
    assert cov["coverage_pct"] == 100


# ── 관대함 (헛경고 방지) ────────────────────────────────────────────────────


def test_condensed_summary_still_matches():
    """LLM 요약(30자)과 지침서 원문(장문)은 길이가 비대칭이다 — Jaccard 면 놓친다."""
    long_req = R("통합민원실은 저층부에 배치하고 장애인 편의시설 기준을 충족하며 "
                 "주출입구에서 30m 이내에 계획할 것")
    cov = check_coverage([long_req], [M("통합민원실 저층부 배치")])
    assert cov["unmapped"] == []


def test_spacing_and_punctuation_do_not_break_matching():
    cov = check_coverage([R("옥상 조경 · 대지면적의 10%")], [M("옥상조경 대지면적 10%")])
    assert cov["unmapped"] == []


def test_same_axis_lowers_the_bar():
    """축이 같으면 문턱을 낮춘다 — 축이 같은데 겹침도 있으면 다른 요구일 확률이 낮다.

    실측 0.429 인 쌍(두 문턱 사이)으로 **기제 자체**를 잠근다.
    """
    from services.requirement_coverage import _overlap
    desc, summary = "옥상 조경 면적을 대지면적의 10% 이상 확보할 것", "조경 면적 기준 충족"
    assert AXIS_MATCH_MIN < _overlap(desc, summary) < MATCH_MIN, "픽스처가 두 문턱 사이를 벗어났다"

    same = check_coverage([R(desc, axis="landscape")], [M(summary, axis="landscape")])
    assert same["unmapped"] == [], "축이 같은데 놓쳤다"

    diff = check_coverage([R(desc, axis="landscape")], [M(summary, axis="site_plan")])
    assert len(diff["unmapped"]) == 1, "축이 다른데 확신 문턱 아래를 매칭했다"


def test_a_requirement_listed_twice_is_not_a_false_alarm():
    """중복 요구를 '하나만 답했다'로 세면 헛경고다 — 답한 요구는 답한 것이다.

    (일대일 매칭을 **의도적으로 안 한다.** 문턱이 있어 일반 문구가 서로 다른 요구를
    쓸어담지 못하고, 중복은 대개 추출 산물이다. 관대함 우선 — 영등포 교훈.)
    """
    reqs = [R("옥상 조경 면적 확보"), R("옥상 조경 면적 확보")]
    cov = check_coverage(reqs, [M("옥상 조경 면적 확보")])
    assert cov["unmapped"] == []
    assert cov["coverage_pct"] == 100


def test_truly_unrelated_is_flagged():
    cov = check_coverage([R("지하 주차장 2개 층 이하")], [M("옥상 조경 면적 확보")])
    assert len(cov["unmapped"]) == 1


# ── 상태 집계 · 대응 없는 항목 ──────────────────────────────────────────────


def test_status_tally():
    mapping = [M("가", status="yes"), M("나", status="no"),
               M("다", status="partial"), M("라", status="이상한값")]
    cov = check_coverage([], mapping)
    assert cov["by_status"]["yes"] == 1
    assert cov["by_status"]["no"] == 1
    assert cov["by_status"]["partial"] == 1
    assert cov["by_status"]["unclear"] == 1     # 모르는 값은 unclear 로


def test_unanchored_mapping_is_named_not_asserted():
    """지침서 요구에 안 붙는 매트릭스 항목 — 추출이 놓쳤을 수도 있어 단정하지 않는다."""
    cov = check_coverage([R("옥상 조경 확보")], [M("옥상 조경 확보"), M("전혀 다른 소방 피난 계획")])
    assert any("소방" in t for t in cov["unanchored"])


# ── 방어 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reqs,maps", [
    (None, None), ("문자열", {}), ([{"bad": 1}], [{"bad": 1}]), ({}, []),
])
def test_garbage_input_does_not_raise(reqs, maps):
    cov = check_coverage(reqs, maps)
    assert cov["total"] == 0 and cov["unmapped"] == []


def test_check_diagnosis_is_non_fatal():
    assert check_diagnosis({}, {})["total"] == 0
    assert check_diagnosis(None, None)["total"] == 0
    d = {"requirement_mapping": [M("옥상 조경")]}
    b = {"_requirements": {"requirements": [R("옥상 조경 면적 확보")]}}
    assert check_diagnosis(d, b)["mapped"] == 1


# ── 렌더 ────────────────────────────────────────────────────────────────────


def test_band_only_appears_when_something_is_missing():
    clean = check_coverage([R("옥상 조경 확보")], [M("옥상 조경 확보")])
    assert band_html(clean) == ""
    dirty = check_coverage([R("지하 주차장 2개 층 이하")], [M("옥상 조경 확보")])
    assert "지하 주차장" in band_html(dirty)
    assert "탈락은 누락에서 난다" in band_html(dirty)


def test_band_escapes_llm_text():
    cov = check_coverage([R("<script>alert(1)</script> 요구")], [M("무관한 항목")])
    out = band_html(cov)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_report_renders_band_even_without_a_table():
    """표가 통째로 비어도 요구는 있을 수 있다 — 경고만이라도 낸다(silent skip 0)."""
    from services.diagnosis_report_generator import _render_requirement_mapping
    cov = check_coverage([R("지하 주차장 2개 층 이하")], [])
    out = _render_requirement_mapping([], {}, cov)
    assert "지하 주차장" in out


def test_report_shows_the_count_next_to_the_title():
    from services.diagnosis_report_generator import _render_requirement_mapping
    cov = check_coverage([R("옥상 조경 확보"), R("지하 주차장 2층 이하")], [M("옥상 조경 확보")])
    out = _render_requirement_mapping([M("옥상 조경 확보")], {}, cov)
    assert "지침서 요구 2개 중 1개 응답 (50%)" in out
