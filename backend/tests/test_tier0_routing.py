"""
E-3 검증 — Tier 0 디지털텍스트 fast-path 회귀 테스트.

실제 PDF·API 호출 없이:
  1. _extract_digital_text_only() 단위 테스트 (get_page_text + call_messages 모킹)
  2. DIGITAL_TEXT_EXCLUDE_TYPES 상수 검증
  3. _source 필드 / 이미지 토큰 0 / Haiku 모델 검증

정확도 측정은 시퀀스 B 하네스(tools/eval/run_harness.py)로 별도 진행.
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from services.data_extractor import (
    _extract_digital_text_only,
    DIGITAL_TEXT_EXCLUDE_TYPES,
    TILE_PAGE_TYPES,
    OCR_FIRST_TYPES,
    OCR_MIN_CHARS,
)
from config import settings

_DUMMY_PDF = Path("dummy.pdf")
_PROMPT_CFG = {"instruction": "extract JSON", "priority": 1}

# 충분한 임베딩 텍스트 (디지털 PDF 산문 페이지 시뮬레이션)
_RICH_TEXT = (
    "건폐율 45.6%\n용적률 180.0%\n연면적 12,456.78㎡\n"
    "층수 지상 15층 / 지하 2층\n주차 대수 120대\n"
    + "설계 개념 서술 텍스트 " * 10
)

# 이미지 기반 PDF (스캔본 / PPT 플래튼) — get_text() 거의 비어있음
_SCAN_TEXT = "그림"   # len < OCR_MIN_CHARS


# ══════════════════════════════════════════════════════════════════════════════
# 상수 검증 — DIGITAL_TEXT_EXCLUDE_TYPES
# ══════════════════════════════════════════════════════════════════════════════

class TestDigitalTextExcludeTypes:

    def test_submission_table_types_excluded(self):
        # 제안서 표 타입 5개 — 열 순서 왜곡 위험
        expected_submission = {
            "AREA_TABLE", "TECHNICAL", "INCENTIVE_TABLE",
            "BUSINESS_VIABILITY", "AREA_INCREASE",
        }
        assert expected_submission <= DIGITAL_TEXT_EXCLUDE_TYPES

    def test_brief_table_types_excluded(self):
        # 지침서 표 타입 2개 — 실별 면적표·법규 수치 열 왜곡 위험
        assert "BRIEF_PROGRAM" in DIGITAL_TEXT_EXCLUDE_TYPES
        assert "BRIEF_REGULATIONS" in DIGITAL_TEXT_EXCLUDE_TYPES

    def test_tile_page_types_subset_of_exclude(self):
        # TILE_PAGE_TYPES는 DIGITAL_TEXT_EXCLUDE_TYPES의 부분집합
        # (BRIEF_* 타입이 추가되어 등호 관계는 아님)
        assert TILE_PAGE_TYPES <= DIGITAL_TEXT_EXCLUDE_TYPES

    @pytest.mark.parametrize("prose_type", [
        "CONCEPT", "FLOOR_PLAN", "SECTION", "SITE_PLAN",
        "SUSTAINABILITY", "COMPANY_PORTFOLIO", "CONSTRUCTION_PLAN",
        "COMMUNITY_PROGRAM", "UNIT_PLAN", "BRANDING",
    ])
    def test_prose_types_not_excluded(self, prose_type):
        assert prose_type not in DIGITAL_TEXT_EXCLUDE_TYPES

    @pytest.mark.parametrize("table_type", sorted(DIGITAL_TEXT_EXCLUDE_TYPES))
    def test_table_types_excluded(self, table_type):
        # routing 조건: effective_type not in DIGITAL_TEXT_EXCLUDE_TYPES → Tier 0 적용
        # 표 타입은 이 조건에서 제외 → Tier 1(OCR) / tiled / vision으로 직행
        assert table_type in DIGITAL_TEXT_EXCLUDE_TYPES


# ══════════════════════════════════════════════════════════════════════════════
# _extract_digital_text_only() — 정상 경로
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractDigitalSuccess:

    def test_source_tag_is_digital_haiku(self):
        """디지털 PDF 산문 페이지 → _source: digital_haiku."""
        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", return_value='{"concept_keywords": ["저층주거"]}'),
        ):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        assert result is not None
        assert result["_source"] == "digital_haiku"

    def test_return_fields_complete(self):
        """반환 dict에 page / type / data / _source 포함."""
        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", return_value='{"x": 1}'),
        ):
            result = _extract_digital_text_only(_DUMMY_PDF, 2, 3, "SECTION", _PROMPT_CFG)

        assert result["page"] == 3
        assert result["type"] == "SECTION"
        assert isinstance(result["data"], dict)
        assert result["_source"] == "digital_haiku"

    def test_uses_haiku_model_not_sonnet(self):
        """이미지 토큰 0 경로: Haiku 사용 확인 (Sonnet 사용 시 비용 낭비)."""
        captured: dict = {}

        def fake_call(**kwargs):
            captured["model"] = kwargs.get("model")
            return '{"x": 1}'

        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", side_effect=fake_call),
        ):
            _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        assert captured["model"] == settings.model_id_classify  # Haiku

    def test_no_image_block_in_content(self):
        """content에 image 블록 없음 → 이미지 토큰 = 0 보장."""
        captured: dict = {}

        def fake_call(**kwargs):
            captured["messages"] = kwargs.get("messages", [])
            return '{"x": 1}'

        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", side_effect=fake_call),
        ):
            _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        content = captured["messages"][0]["content"]
        block_types = [b.get("type") for b in content]
        assert "image" not in block_types
        assert "text" in block_types

    def test_temperature_zero(self):
        """재현성을 위해 temperature=0 사용."""
        captured: dict = {}

        def fake_call(**kwargs):
            captured["temperature"] = kwargs.get("temperature")
            return '{"x": 1}'

        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", side_effect=fake_call),
        ):
            _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        assert captured["temperature"] == 0

    def test_page_text_and_instruction_in_prompt(self):
        """추출된 텍스트와 prompt_cfg instruction이 LLM content에 포함되는지."""
        captured: dict = {}

        def fake_call(**kwargs):
            captured["messages"] = kwargs.get("messages", [])
            return '{"x": 1}'

        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", side_effect=fake_call),
        ):
            _extract_digital_text_only(_DUMMY_PDF, 0, 1, "SITE_PLAN", _PROMPT_CFG)

        user_text = captured["messages"][0]["content"][0]["text"]
        assert "건폐율" in user_text            # _RICH_TEXT 포함 확인
        assert "extract JSON" in user_text     # instruction 포함 확인


# ══════════════════════════════════════════════════════════════════════════════
# _extract_digital_text_only() — fallback 경로 (None 반환)
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractDigitalFallback:

    def test_scan_pdf_empty_text_returns_none(self):
        """스캔 PDF: get_page_text() 빈 문자열 → None → OCR/vision으로 폴백."""
        with patch("services.data_extractor.get_page_text", return_value=""):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "FLOOR_PLAN", _PROMPT_CFG)
        assert result is None

    def test_sparse_text_returns_none(self):
        """< OCR_MIN_CHARS 텍스트 → None."""
        with patch("services.data_extractor.get_page_text", return_value=_SCAN_TEXT):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)
        assert result is None

    def test_boundary_exactly_ocr_min_chars_passes(self):
        """len == OCR_MIN_CHARS (경계값) → 통과 (>= 조건)."""
        boundary = "가" * OCR_MIN_CHARS
        with (
            patch("services.data_extractor.get_page_text", return_value=boundary),
            patch("services.data_extractor.call_messages", return_value='{"x": 1}'),
        ):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "SECTION", _PROMPT_CFG)
        assert result is not None

    def test_one_below_boundary_returns_none(self):
        """len == OCR_MIN_CHARS - 1 → None."""
        below = "가" * (OCR_MIN_CHARS - 1)
        with patch("services.data_extractor.get_page_text", return_value=below):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "SECTION", _PROMPT_CFG)
        assert result is None

    def test_whitespace_only_returns_none(self):
        """공백만 있는 텍스트 → strip 후 < OCR_MIN_CHARS → None."""
        whitespace = " \n\t" * 50
        with patch("services.data_extractor.get_page_text", return_value=whitespace):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 오류 처리 — LLM 실패 시 _source 태깅 유지
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractDigitalErrorHandling:

    def test_llm_error_returns_error_dict_not_none(self):
        """LLM 호출 실패 시 None이 아닌 {"error": ...} 반환 (소스 태깅 유지)."""
        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", side_effect=Exception("502 Bad Gateway")),
        ):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        assert result is not None
        assert result["_source"] == "digital_haiku"
        assert "error" in result["data"]
        assert "502" in result["data"]["error"]

    def test_invalid_json_response_has_error(self):
        """LLM이 유효하지 않은 JSON 반환 → parse_json_response가 예외 → error 필드."""
        with (
            patch("services.data_extractor.get_page_text", return_value=_RICH_TEXT),
            patch("services.data_extractor.call_messages", return_value="이것은 JSON이 아닙니다"),
        ):
            result = _extract_digital_text_only(_DUMMY_PDF, 0, 1, "CONCEPT", _PROMPT_CFG)

        assert result is not None
        assert "error" in result["data"]
