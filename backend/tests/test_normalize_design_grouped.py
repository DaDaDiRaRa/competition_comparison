"""normalize_design_guidelines_grouped — 단위 테스트.

Phase 0 측정에서 발견된 5가지 패턴 + edge cases 커버.
"""
from __future__ import annotations

import pytest

from services.utils import normalize_design_guidelines_grouped


def _entry(fs: str, ss: str, sp: str, items: list[tuple[str, str]], cat: str = "공간구성") -> dict:
    return {
        "facility_scope": fs,
        "space_scope": ss,
        "category": cat,
        "section_path": sp,
        "items": [{"label": lbl, "text": txt} for lbl, txt in items],
    }


def test_empty_input():
    assert normalize_design_guidelines_grouped(None) == []
    assert normalize_design_guidelines_grouped([]) == []


def test_R1_exact_duplicate_paths_merged():
    """동일 (fs, ss, section_path) 가 두 번 나오면 items 병합."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반 항목 A")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반 항목 B")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    assert out[0]["section_path"] == "직무공간 (부서 사무실)"
    assert out[0]["items_by_sub"] == [
        {"sub_path": "", "items": [
            {"label": "-", "text": "일반 항목 A"},
            {"label": "-", "text": "일반 항목 B"},
        ]}
    ]


def test_R2_parent_child_grouped():
    """직무공간 케이스 — parent + 두 child path 가 한 그룹으로.

    그룹 키 = (facility_scope, first_seg) — space_scope 다른 entry 도
    같은 그룹으로 통합 (LLM 의 space_scope 추출 불안정성 보정).
    """
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반")]),
        _entry("구청", "비품창고", "직무공간 (부서 사무실) > 비품창고", [("①", "비품창고 항목")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실) > 기타 부서별 요청사항",
               [("①", "감사담당관")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    # 셋 모두 같은 (fs, first_seg) → 한 그룹.
    assert len(out) == 1
    grp = out[0]
    assert grp["facility_scope"] == "구청"
    assert grp["section_path"] == "직무공간 (부서 사무실)"
    sub_paths = [x["sub_path"] for x in grp["items_by_sub"]]
    # 입력 순서: "" → "비품창고" → "기타 부서별 요청사항"
    assert sub_paths == ["", "비품창고", "기타 부서별 요청사항"]


def test_R2_same_space_scope_parent_child():
    """같은 space_scope 안에서 parent-child 관계."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실) > 비품창고",
               [("①", "비품창고 항목")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    grp = out[0]
    assert grp["section_path"] == "직무공간 (부서 사무실)"
    subs = {x["sub_path"]: x["items"] for x in grp["items_by_sub"]}
    assert subs[""] == [{"label": "-", "text": "일반"}]
    assert subs["비품창고"] == [{"label": "①", "text": "비품창고 항목"}]


def test_R3_three_level_depth_preserves_breadcrumb():
    """3단 depth — sub_path 에 'B > C' 형태로 breadcrumb 보존."""
    inp = [
        _entry("전체", "전체", "II. 설계지침 > 1. 설계 개요 > 1-1. 과업의 목적",
               [("•", "목적 항목")]),
        _entry("전체", "전체", "II. 설계지침 > 1. 설계 개요 > 1-2. 설계목표",
               [("•", "목표 항목")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    grp = out[0]
    assert grp["section_path"] == "II. 설계지침"
    sub_paths = [x["sub_path"] for x in grp["items_by_sub"]]
    assert sub_paths == [
        "1. 설계 개요 > 1-1. 과업의 목적",
        "1. 설계 개요 > 1-2. 설계목표",
    ]


def test_R4_orphan_grouped_by_first_seg():
    """parent entry 가 없어도 first_seg 으로 자연 그룹화."""
    inp = [
        _entry("전체", "전체", "A > B > C", [("•", "X")]),
        _entry("전체", "전체", "A > B > D", [("•", "Y")]),
        _entry("전체", "전체", "A > E", [("•", "Z")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    grp = out[0]
    assert grp["section_path"] == "A"
    sub_paths = [x["sub_path"] for x in grp["items_by_sub"]]
    assert sub_paths == ["B > C", "B > D", "E"]


def test_R5_item_text_dedup():
    """같은 그룹·sub 안에서 동일 label+text item 은 한 번만."""
    inp = [
        _entry("구청", "회의 및 행사공간", "회의 및 행사공간",
               [("-", "회의, 행사 등을 위한 공간으로 음향 등 장비조정실, 비품 창고를 배치한다.")]),
        _entry("구청", "회의 및 행사공간", "회의 및 행사공간",
               [("-", "회의, 행사 등을 위한 공간으로 음향 등 장비조정실, 비품 창고를 배치한다.")]),
        _entry("구청", "회의 및 행사공간", "회의 및 행사공간",
               [("-", "회의, 행사 등을 위한 공간으로 음향 등 장비조정실, 비품 창고를 배치한다.")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    grp = out[0]
    flat = grp["items_by_sub"][0]["items"]
    assert len(flat) == 1


def test_R3_breadcrumb_with_R5_dedup_combined():
    """3단 depth + 동일 sub_path 에 동일 item 중복 → dedup 정상."""
    inp = [
        _entry("전체", "전체", "A > B > C", [("•", "shared item")]),
        _entry("전체", "전체", "A > B > C", [("•", "shared item")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    grp = out[0]
    assert len(grp["items_by_sub"]) == 1
    assert grp["items_by_sub"][0]["sub_path"] == "B > C"
    assert len(grp["items_by_sub"][0]["items"]) == 1


def test_preserves_input_order_within_group():
    """그룹 안 sub_path 들은 입력 순서대로."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실) > 기타 부서별 요청사항",
               [("①", "감사담당관")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실) > 비품창고",
               [("①", "비품창고")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    sub_paths = [x["sub_path"] for x in out[0]["items_by_sub"]]
    # 입력 순서: 기타 부서별 요청사항 → "" → 비품창고
    assert sub_paths == ["기타 부서별 요청사항", "", "비품창고"]


def test_different_scopes_stay_separate():
    """facility_scope 다르면 별도 그룹."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "A")]),
        _entry("보건소", "직무공간", "직무공간 (부서 사무실)", [("-", "B")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 2
    facs = {o["facility_scope"] for o in out}
    assert facs == {"구청", "보건소"}


def test_empty_section_path_kept():
    """section_path 비어있는 entry 도 그대로 한 그룹 (first_seg = '')."""
    inp = [
        _entry("전체", "전체", "", [("•", "global item")]),
        _entry("전체", "전체", "", [("•", "another global")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
    assert out[0]["section_path"] == ""
    assert len(out[0]["items_by_sub"][0]["items"]) == 2


def test_items_field_backwards_compat():
    """items 필드 (sub_path '') 가 하위 호환을 위해 채워져야 함."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "일반")]),
        _entry("구청", "직무공간", "직무공간 (부서 사무실) > 비품창고", [("①", "x")]),
    ]
    out = normalize_design_guidelines_grouped(inp)
    grp = out[0]
    # items 는 sub_path == "" 인 항목들만
    assert grp["items"] == [{"label": "-", "text": "일반"}]


def test_skips_non_dict_entries():
    """list 안에 dict 아닌 게 섞여 있어도 크래시 없음."""
    inp = [
        _entry("구청", "직무공간", "직무공간 (부서 사무실)", [("-", "A")]),
        "garbage",
        None,
        42,
    ]
    out = normalize_design_guidelines_grouped(inp)
    assert len(out) == 1
