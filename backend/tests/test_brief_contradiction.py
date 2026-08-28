"""지침서 내부 모순 탐지 회귀 — LLM 0 · 값 수정 0.

계기(2026-08-28): `_quantitative.site_area_sqm` 이 대지면적이 아니라 **부지1의 연면적
합계**(56,189.72)를 들고 있었고, 체크리스트 핵심수치 카드의 폴백 사슬 끝이 그 값이라
**5.4배 틀린 대지면적**이 리포트 첫 화면에 떴다(실제 10,438㎡ · prod 21건 중 7건).
같은 지침서 안에 옳은 값도 있었는데(`feasibility_export.sites[]`) 아무도 안 물었다.

⚠ **자동 판정 안 함** — 어느 소스가 맞는지는 원문을 봐야 안다. 값과 출처를 나란히 놓을 뿐.
"""
import pytest

from services.brief_contradiction import (
    band_html,
    detect_contradictions,
    md_lines,
    summary_line,
)


def B(quant=None, fe_sites=None, bpi_sites=None, program=None):
    d = {}
    if quant is not None:
        d["_quantitative"] = quant
    if fe_sites is not None:
        d["feasibility_export"] = {"schema_version": 2, "sites": fe_sites}
    if bpi_sites is not None:
        d["brief_project_info"] = {"sites": bpi_sites}
    if program is not None:
        d["brief_program"] = program
    return d


# ── 실제 사고 재현 ──────────────────────────────────────────────────────────


def test_the_real_incident_is_caught():
    """영등포: _quantitative 가 연면적(56,189.72)을 대지면적 자리에 들고 있었다."""
    d = B(quant={"site_area_sqm": 56189.72, "total_floor_area_sqm": 69628.19},
          fe_sites=[{"site_id": "부지1", "site_area_sqm": 7498.0},
                    {"site_id": "부지2", "site_area_sqm": 2940.0}])
    flags = detect_contradictions(d)
    assert len(flags) == 1
    f = flags[0]
    assert f["quantity"] == "site_area_sqm"
    assert f["spread_ratio"] == 5.38
    wheres = {s["where"] for s in f["sources"]}
    assert wheres == {"feasibility_export.sites 합", "_quantitative.site_area_sqm"}
    assert {s["value"] for s in f["sources"]} == {10438.0, 56189.72}


def test_multi_site_sums_are_the_comparison_unit():
    """다부지면 **합**이 총 대지면적이다 — 부지 하나와 견주면 헛경고가 난다."""
    d = B(quant={"site_area_sqm": 10438.0},
          fe_sites=[{"site_area_sqm": 7498.0}, {"site_area_sqm": 2940.0}])
    assert detect_contradictions(d) == []


# ── 헛경고 방지 ─────────────────────────────────────────────────────────────


def test_rounding_is_tolerated():
    """추출은 반올림 표기를 섞어 온다."""
    d = B(quant={"site_area_sqm": 56190.0}, fe_sites=[{"site_area_sqm": 56189.72}])
    assert detect_contradictions(d) == []


def test_one_source_is_never_a_contradiction():
    assert detect_contradictions(B(quant={"site_area_sqm": 7498.0})) == []
    assert detect_contradictions(B(fe_sites=[{"site_area_sqm": 7498.0}])) == []


def test_missing_values_are_not_zero():
    """부지에 면적이 하나도 없으면 「0」이 아니라 「없음」이다 — 0 과 비교하면 전부 걸린다."""
    d = B(quant={"site_area_sqm": 7498.0},
          fe_sites=[{"site_id": "부지1"}, {"site_id": "부지2"}])
    assert detect_contradictions(d) == []


def test_program_total_repeated_across_pages_is_read_once():
    """면적표는 페이지마다 같은 총계를 반복한다 — 여러 번 세면 자기와 충돌한다."""
    d = B(quant={"total_floor_area_sqm": 69628.19},
          program=[{"total_required_floor_area_sqm": 69628.19},
                   {"total_required_floor_area_sqm": 69628.19},
                   {"total_required_floor_area_sqm": 69628.19}])
    assert detect_contradictions(d) == []


def test_total_floor_area_disagreement_is_caught():
    d = B(quant={"total_floor_area_sqm": 69628.19},
          program=[{"total_required_floor_area_sqm": 46250.0}])
    flags = detect_contradictions(d)
    assert [f["quantity"] for f in flags] == ["total_floor_area_sqm"]


def test_percentages_are_not_checked():
    """건폐율·용적률은 다부지에서 **정당하게 다르다** — 단일값과 대조하면 헛경고."""
    d = B(quant={"floor_area_ratio_pct": 460},
          fe_sites=[{"floor_area_ratio_pct": 460}, {"floor_area_ratio_pct": 400}])
    assert detect_contradictions(d) == []


@pytest.mark.parametrize("d", [None, {}, "문자열", {"_quantitative": "x"},
                               {"feasibility_export": {"sites": "x"}},
                               {"brief_program": [None, 3]}])
def test_garbage_is_safe(d):
    assert detect_contradictions(d) == []


# ── 렌더 ────────────────────────────────────────────────────────────────────


def _flags():
    return detect_contradictions(B(
        quant={"site_area_sqm": 56189.72},
        fe_sites=[{"site_area_sqm": 7498.0}, {"site_area_sqm": 2940.0}]))


def test_band_says_it_does_not_judge():
    out = band_html(_flags())
    assert "자동 판정 안 함" in out
    assert "5.38배" in out
    assert "56,189.7" in out and "10,438" in out


def test_band_and_md_empty_when_clean():
    assert band_html([]) == "" and band_html(None) == ""
    assert md_lines([]) == [] and md_lines(None) == []


def test_md_carries_the_same_fact():
    md = "\n".join(md_lines(_flags()))
    assert "지침서 내부 모순" in md and "자동 판정하지 않았으며" in md
    assert "5.38배" in md


def test_summary_line():
    assert summary_line(_flags()) == "지침서 내부 모순 총 대지면적 5.38배"


def test_band_escapes_source_labels():
    flags = [{"label": "<script>x</script>", "spread_ratio": 2.0,
              "sources": [{"where": "<b>a</b>", "value": 1.0},
                          {"where": "b", "value": 2.0}]}]
    out = band_html(flags)
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<b>a</b>" not in out


# ── 파이프라인 배선 ─────────────────────────────────────────────────────────


def test_checklist_html_shows_the_band():
    from services.brief_checklist_exporter import to_html
    d = B(quant={"site_area_sqm": 56189.72},
          fe_sites=[{"site_area_sqm": 7498.0}, {"site_area_sqm": 2940.0}])
    d["_contradictions"] = detect_contradictions(d)
    d["_brief_meta"] = {"facility_type": "public", "brief_name": "모순 회귀"}
    html = to_html(d, {"flags": [], "summary": {}, "checked_rules": []})
    assert "5.38배" in html


def test_checklist_md_shows_the_block():
    from services.brief_checklist_exporter import to_markdown
    d = B(quant={"site_area_sqm": 56189.72},
          fe_sites=[{"site_area_sqm": 7498.0}, {"site_area_sqm": 2940.0}])
    d["_contradictions"] = detect_contradictions(d)
    md = to_markdown(d, {"flags": [], "summary": {}, "checked_rules": []})
    assert "0.3 지침서 내부 모순" in md


def test_site_area_fallback_prefers_normalized_sites():
    """폴백 사슬 수정 회귀 — `_quantitative` 의 오결합 값이 이기면 안 된다."""
    from services.brief_checklist_exporter import _extract_sections
    d = B(quant={"site_area_sqm": 56189.72, "total_floor_area_sqm": 69628.19},
          fe_sites=[{"site_area_sqm": 7498.0}, {"site_area_sqm": 2940.0}])
    assert _extract_sections(d)["area"]["site_area"] == 10438.0
