"""MyProject 정량 검증 연결 회귀 테스트 (MATURITY 로드맵 #3).

이미 계산되던 `_quantitative_flags`(merge_extracted_data 부착)를 MyProject 가
① deep_analyze 프롬프트에 error 주입 ② 리포트 밴드로 노출하도록 연결한 것을 잠근다.
"""
from services.quant_validator import flags_band_html
from services.myproject_analyzer import _build_prompt


_ERR_FLAG = {"rule": "building_gt_site", "severity": "error",
             "fields": ["building_area_sqm", "site_area_sqm"],
             "detail": "건축면적 9,000 > 대지면적 8,000㎡ (불가)"}
_WARN_FLAG = {"rule": "coverage_gt_far", "severity": "warn",
              "fields": ["building_coverage_ratio_pct", "floor_area_ratio_pct"],
              "detail": "건폐율 60% > 용적률 50%"}


class TestQuantFlagsBand:
    def test_empty_returns_blank(self):
        assert flags_band_html([]) == ""
        assert flags_band_html(None) == ""

    def test_renders_error_and_warn(self):
        html = flags_band_html([_ERR_FLAG, _WARN_FLAG])
        assert "정량 데이터 정합성 경고" in html
        assert "모순" in html and "주의" in html
        assert "건축면적 9,000" in html

    def test_escapes_detail(self):
        html = flags_band_html([{"severity": "error", "detail": "a<b>&c"}])
        assert "a&lt;b&gt;&amp;c" in html
        assert "<b>" not in html

    def test_skips_flags_without_detail(self):
        assert flags_band_html([{"severity": "error"}]) == ""


class TestPromptInjection:
    def _prompt(self, flags):
        extracted = {"concept": {"_page": 1}, "_quantitative_flags": flags}
        return _build_prompt("residential", ["site", "mass"], extracted, None,
                             {}, "테스트사", "win")

    def test_error_flag_injected(self):
        p = self._prompt([_ERR_FLAG])
        assert "정량 데이터 경고" in p
        assert "건축면적 9,000" in p

    def test_warn_flag_not_injected(self):
        # warn 은 프롬프트에 넣지 않음 (error 만 강한 신호)
        p = self._prompt([_WARN_FLAG])
        assert "정량 데이터 경고" not in p

    def test_no_flags_no_caution(self):
        p = self._prompt([])
        assert "정량 데이터 경고" not in p
