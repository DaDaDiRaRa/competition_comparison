# -*- coding: utf-8 -*-
"""brief_massing 회귀 — 부지별 개념 매스(적층 + 용량 핏) 결정론 파생·렌더 (LLM 0).

용량 모델 항등식(footprint·봉투층·cap·지상 추정·초과), 다부지/단일부지 프로그램
귀속, 지하 표기 분리, graceful skip, html.escape 를 고정한다.
"""

import math

from services.brief_massing import (
    build_massing_sites, massing_html, _is_under, _per_site_programs, _site_geometry,
)


# ── 영등포 통합신청사 축소 fixture (2부지) ──
def _multisite_brief():
    return {
        "feasibility_export": {
            "sites": [
                {"site_id": "부지1", "site_area_sqm": 7498, "building_coverage_pct": 60,
                 "floor_area_ratio_pct": 460, "max_height_m": 100},
                {"site_id": "부지2", "site_area_sqm": 2940, "building_coverage_pct": 50,
                 "floor_area_ratio_pct": 400, "max_height_m": 50},
            ],
        },
        "brief_program": [{"area_rows": [
            {"row_type": "site_total", "name": "부지1(청사동 385) 합계", "subtotal_area": 56189.72},
            {"row_type": "facility", "name": "구청", "subtotal_area": 36019.86},
            {"row_type": "facility", "name": "구의회", "subtotal_area": 2961.0},
            {"row_type": "facility", "name": "어린이집", "subtotal_area": 1297.17},
            {"row_type": "facility", "name": "부속 주차장(지하)", "subtotal_area": 15911.69},
            {"row_type": "site_total", "name": "부지2(보건동 370-4) 합계", "subtotal_area": 13438.47},
            {"row_type": "facility", "name": "보건소", "subtotal_area": 8594.84},
            {"row_type": "facility", "name": "공공커뮤니티", "subtotal_area": 3577.13},
            {"row_type": "facility", "name": "부속 주차장(지하)", "subtotal_area": 1266.5},
            # 재집계 헤더 — 섹션 안 엶
            {"row_type": "site_total", "name": "총 합계 (본+별)", "subtotal_area": 69628.19},
            {"row_type": "facility", "name": "본관 상세", "subtotal_area": 99999.0},
        ]}],
    }


class TestGeometry:
    def test_extracts_valid_sites(self):
        g = _site_geometry(_multisite_brief())
        assert len(g) == 2
        assert g[0]["area"] == 7498 and g[0]["bcr"] == 60 and g[0]["far"] == 460
        assert g[0]["h_limit"] == 100

    def test_skips_site_missing_bcr_or_far(self):
        b = {"feasibility_export": {"sites": [
            {"site_id": "부지1", "site_area_sqm": 5000, "building_coverage_pct": 60},   # far 없음
            {"site_id": "부지2", "site_area_sqm": 3000, "building_coverage_pct": 50,
             "floor_area_ratio_pct": 300},
        ]}}
        g = _site_geometry(b)
        assert len(g) == 1 and g[0]["site_id"] == "부지2"

    def test_no_feasibility_empty(self):
        assert _site_geometry({}) == []


class TestUnderDetection:
    def test_jiha_marked(self):
        assert _is_under("부속 주차장(지하)")
        assert _is_under("지하주차장")

    def test_ground_not_under(self):
        assert not _is_under("구청")
        assert not _is_under("어린이집")


class TestPerSitePrograms:
    def test_multisite_buckets_scoped_and_resummary_excluded(self):
        a = {"area_rows": _multisite_brief()["brief_program"][0]["area_rows"]}
        buckets = _per_site_programs(a)
        assert len(buckets) == 2                       # 재집계 헤더는 버킷 안 만듦
        names0 = {n for n, _ in buckets[0]}
        assert names0 == {"구청", "구의회", "어린이집", "부속 주차장(지하)"}
        names1 = {n for n, _ in buckets[1]}
        assert names1 == {"보건소", "공공커뮤니티", "부속 주차장(지하)"}
        assert "본관 상세" not in names0 and "본관 상세" not in names1

    def test_single_site_collects_top_facilities(self):
        a = {"area_rows": [
            {"row_type": "facility", "name": "본관", "subtotal_area": 5000.0},
            {"row_type": "facility", "name": "지하주차장", "subtotal_area": 2000.0},
            {"row_type": "space", "name": "사무실", "area": 100.0},   # 상세는 무시
        ]}
        buckets = _per_site_programs(a)
        assert len(buckets) == 1
        assert {n for n, _ in buckets[0]} == {"본관", "지하주차장"}


class TestBuildMassing:
    def test_envelope_identities_and_overflow(self):
        sites = build_massing_sites(_multisite_brief())
        assert len(sites) == 2
        s = sites[0]
        assert math.isclose(s["footprint"], 7498 * 0.60, rel_tol=1e-6)      # 4498.8
        # 봉투 층수 = min(용적/건폐, 높이한도/4.3) = min(7.667, 23.3) = 7.667
        assert math.isclose(s["fl_env"], 460 / 60, rel_tol=1e-6)
        assert s["binding"] == "용적률"
        assert math.isclose(s["cap"], 4498.8 * (460 / 60), rel_tol=1e-6)    # 34490.8
        # 지상 추정 = 구청+구의회+어린이집 (주차장 지하 제외)
        assert math.isclose(s["ground_est"], 36019.86 + 2961.0 + 1297.17, rel_tol=1e-6)
        assert math.isclose(s["under_sum"], 15911.69, rel_tol=1e-6)
        assert s["over"] > 5000                                             # 초과 ~5787
        assert s["fill"] > 1.0                                              # 117%

    def test_height_binding_site(self):
        # 높이한도가 용적보다 빡빡하면 binding=높이한도
        b = {"feasibility_export": {"sites": [
            {"site_id": "부지1", "site_area_sqm": 5000, "building_coverage_pct": 50,
             "floor_area_ratio_pct": 800, "max_height_m": 20}]},
             "brief_program": [{"area_rows": [
                 {"row_type": "facility", "name": "본관", "subtotal_area": 8000.0}]}]}
        s = build_massing_sites(b)[0]
        # 용적층=800/50=16, 높이층=20/4.3=4.65 → 높이한도 binding
        assert s["binding"] == "높이한도"
        assert math.isclose(s["fl_env"], 20 / 4.3, rel_tol=1e-6)

    def test_within_envelope_no_overflow(self):
        b = {"feasibility_export": {"sites": [
            {"site_id": "부지1", "site_area_sqm": 5000, "building_coverage_pct": 60,
             "floor_area_ratio_pct": 400, "max_height_m": 60}]},
             "brief_program": [{"area_rows": [
                 {"row_type": "facility", "name": "본관", "subtotal_area": 3000.0}]}]}
        s = build_massing_sites(b)[0]
        assert s["over"] == 0 and s["fill"] < 1.0

    def test_no_data_empty(self):
        assert build_massing_sites({}) == []
        assert build_massing_sites({"feasibility_export": {"sites": []}}) == []


class TestMassingHtml:
    def test_renders_both_sites(self):
        h = massing_html(_multisite_brief())
        assert "부지1" in h and "부지2" in h
        assert "용적 봉투" in h and "지상 프로그램" in h
        assert "용적 상한" in h                       # 세로 점선 라벨
        assert "지하 배분" in h                       # 초과 verdict
        # 캡션의 정직성 고지
        assert "지상 추정은 과대 가능" in h
        assert "실측/인허가 아님" in h

    def test_legend_lists_facilities(self):
        h = massing_html(_multisite_brief())
        assert "구청" in h and "보건소" in h          # 범례 시설명
        assert "지하" in h                            # 지하 바/범례

    def test_graceful_empty(self):
        assert massing_html({}) == ""

    def test_html_escape(self):
        b = {"feasibility_export": {"sites": [
            {"site_id": "<img src=x>", "site_area_sqm": 5000, "building_coverage_pct": 60,
             "floor_area_ratio_pct": 400, "max_height_m": 60}]},
             "brief_program": [{"area_rows": [
                 {"row_type": "facility", "name": "<b>본관</b>", "subtotal_area": 3000.0}]}]}
        h = massing_html(b)
        assert "<img src=x>" not in h and "&lt;img src=x&gt;" in h
        assert "<b>본관</b>" not in h and "&lt;b&gt;" in h
