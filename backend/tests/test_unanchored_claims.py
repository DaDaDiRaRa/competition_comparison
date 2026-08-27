"""근거를 안 밝힌 수치 주장 — 구조 검사 회귀 (LLM 0 · 텍스트 수정 0).

코퍼스 검사(`check_proposal_numbers`)와 **잡는 것이 다르다**:
  · 코퍼스 = 그 숫자가 지침서 어디에도 없다        → 지어냈다
  · 구조   = 숫자는 있는데 이 주장이 출처를 안 밝혔다 → 확인할 수 없다
섞으면 고칠 방법이 달라진다 — 앞은 「이 숫자 진짜냐」, 뒤는 「어느 쪽이냐」.

concept-studio `render/numbers.py` 의 원리를 우리 데이터 모델로 옮긴 것.
⚠ **빌드를 세우지 않는다** — 우리 제안서는 지침서 수치를 산문에 인용하는 자리가
정당하게 많아 렌더를 막으면 정당한 산출물이 안 나온다.
"""
import pytest

from services.proposal_number_check import check_unanchored_claims


def _fields(flags):
    return {f["field"] for f in flags}


# ── 앵커 유무 ───────────────────────────────────────────────────────────────


def test_claim_without_basis_is_flagged():
    p = {"design_directions": [
        {"direction": "안A", "narrative": "저층부 30%를 시민에게 내준다", "basis": []},
    ]}
    flags = check_unanchored_claims(p)
    assert len(flags) == 1
    assert flags[0]["value"] == "30"
    assert flags[0]["field"] == "design_directions[0].narrative"


def test_claim_with_basis_is_clean():
    p = {"design_directions": [
        {"direction": "안A", "narrative": "저층부 30%를 시민에게 내준다", "basis": ["p.12"]},
    ]}
    assert check_unanchored_claims(p) == []


def test_blank_basis_entries_do_not_count_as_anchored():
    p = {"win_themes": [{"theme": "저층 개방 40점", "basis": ["", "  "]}]}
    assert len(check_unanchored_claims(p)) == 1


def test_risks_basis_is_a_string_not_a_list():
    """⚠ `risks[].basis` 만 문자열이다 — 리스트로 보면 전부 미앵커로 샌다."""
    anchored = {"risks": [{"risk": "공사비 1,200억 초과", "mitigation": "대안", "basis": "p.30"}]}
    assert check_unanchored_claims(anchored) == []
    bare = {"risks": [{"risk": "공사비 1,200억 초과", "mitigation": "대안", "basis": ""}]}
    assert len(check_unanchored_claims(bare)) == 1


def test_placement_zones_are_checked():
    p = {"placement_strategy": {"zones": [
        {"program": "저층부", "why": "남측 20m 도로에 접한다", "basis": []},
        {"program": "업무동", "why": "북측 12m 이격", "basis": ["site_context.road_access"]},
    ]}}
    flags = check_unanchored_claims(p)
    assert _fields(flags) == {"placement_strategy.zones[0].why"}


# ── 없는 칸을 비었다고 나무라지 않는다 ──────────────────────────────────────


@pytest.mark.parametrize("key,val", [
    ("executive_summary", "배점 40점이 배치에 쏠려 있다"),
    ("kickoff_checklist", ["30일 내 현장 답사"]),
    ("caveats", ["표본 12건 기준"]),
    ("open_questions", ["주차 40대 기준이 모호하다"]),
])
def test_sections_without_a_basis_field_are_not_checked(key, val):
    """이 블록들은 스키마에 `basis` 칸 자체가 없다 — 검사하면 전부 헛경고다."""
    assert check_unanchored_claims({key: val}) == []


# ── 잡음 억제 ───────────────────────────────────────────────────────────────


def test_single_digit_structure_numbers_are_ignored():
    """1순위·5안 같은 한 자리 구조 숫자는 발명 위험이 낮다."""
    p = {"phasing": [{"claim": "1단계로 배치를 확정", "detail": "3개 안을 비교", "basis": []}]}
    assert check_unanchored_claims(p) == []


def test_single_digit_with_a_risky_unit_is_still_flagged():
    """'5억'은 한 자리라도 발명 위험 단위가 붙었다."""
    p = {"program_directions": [{"claim": "운영비 5억 절감", "detail": "", "basis": []}]}
    assert len(check_unanchored_claims(p)) == 1


def test_one_flag_per_field_keeps_the_list_readable():
    """목록이 길면 아무도 안 읽는다 — 항목당 하나."""
    p = {"massing_strategy": [
        {"claim": "30%·40%·50% 를 모두 언급", "detail": "", "basis": []},
    ]}
    assert len(check_unanchored_claims(p)) == 1


def test_prose_without_numbers_is_clean():
    p = {"design_directions": [{"direction": "안A", "narrative": "저층부를 시민에게 내준다",
                                "basis": []}]}
    assert check_unanchored_claims(p) == []


# ── 방어 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("p", [None, {}, "문자열", {"design_directions": "리스트아님"},
                               {"design_directions": [None, 3, "x"]}])
def test_garbage_input_does_not_raise(p):
    assert check_unanchored_claims(p) == []


def test_two_checks_are_independent():
    """지침서에 있는 숫자라도 출처를 안 밝히면 구조 검사엔 걸린다."""
    from services.proposal_number_check import check_proposal_numbers
    brief = {"brief_evaluation": {"items": [{"item": "배치계획", "points": 40}]}}
    p = {"design_directions": [{"direction": "안A", "narrative": "배치 40점을 정면으로",
                                "basis": []}]}
    assert check_proposal_numbers(p, brief) == []      # 코퍼스엔 있다
    assert len(check_unanchored_claims(p)) == 1        # 그래도 출처는 안 밝혔다


# ── 렌더 ────────────────────────────────────────────────────────────────────


def test_band_separates_the_two_meanings():
    from services.brief_proposal_report_generator import _number_flags_html
    out = _number_flags_html({
        "_number_flags": [{"value": "1,100", "field": "x", "context": "분양가 1,100만원"}],
        "_unanchored_flags": [{"value": "30", "field": "y", "context": "저층부 30%"}],
    })
    assert "확인되지 않았습니다" in out
    assert "근거를 밝히지 않았습니다" in out
    assert "틀렸다는 뜻이 아니라" in out, "두 뜻을 섞으면 고칠 방법이 달라진다"


def test_band_is_empty_when_both_are_clean():
    from services.brief_proposal_report_generator import _number_flags_html
    assert _number_flags_html({"_number_flags": [], "_unanchored_flags": []}) == ""


def test_deck_caveats_slide_reports_both():
    from services.proposal_deck import build_deck
    deck = build_deck({
        "executive_summary": "요약",
        "caveats": ["보장 없음"],
        "_number_flags": [{"value": "1,100", "field": "a"}],
        "_unanchored_flags": [{"value": "30", "field": "b"}],
    }, "X", "공공")
    txt = " ".join(" ".join(s.get("body", [])) for s in deck["slides"] if s["kind"] == "text")
    assert "근거 미확인 수치 1건" in txt
    assert "근거를 밝히지 않은 수치 주장 1건" in txt
