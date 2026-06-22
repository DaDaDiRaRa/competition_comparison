"""
test_hwpx_loader.py — HWP/HWPX 블록 분할/표 파싱 단위 테스트

rhwp / LLM / 네트워크 의존 없음:
  - 순수 함수(_html_table_to_markdown / _parse_html_table / _rows_to_markdown /
    _decide_header)는 입력 dict/str 만으로 테스트.
  - split_hwpx_to_blocks 는 sys.modules["rhwp"] 를 가짜 모듈로 monkeypatch 해
    실제 rhwp 미설치 환경에서도 분할 오케스트레이션(R3/R4/R5/빈줄경계/F3/marker)을 검증.

대상 (cases):
  _html_table_to_markdown / _parse_html_table (6):
    1. 기본 표 → 마크다운 + merge_info 빈 배열
    2. rowspan → merge_info {row,col,merged_rows,value} (docx 호환 스키마) + continue 빈칸
    3. colspan → 셀 텍스트 반복 (docx 동작)
    4. 셀 이스케이프: | → &#124;, 60자 컷 + …
    5. 빈/깨진 html → ("", [])
    6. <td> 내부 태그 제거 + 공백 정규화
  _decide_header (5): A(섹션)/A(캡션)/B(짧은첫단락)/C(표첫행)/D(첫비어있지않음)/E(디폴트)
  split_hwpx_to_blocks (7): R3 / R4 / R5 표단독 / 빈줄3경계 / F3 "(계속)" /
                            list_item marker prepend / recurse=False 가드 + 스키마 키
  cross-module (1): hwpx 표 블록 → _extract_docx_eval_from_table 호환 (shared_with)
  get_hwpx_source_text (1): docx 구현 위임 결과 (헤더+단락 포함)

실행:
  cd backend
  venv/Scripts/python.exe -m pytest tests/test_hwpx_loader.py -v
"""
from __future__ import annotations

import sys
import types

import pytest

# conftest.py 가 backend/ 를 sys.path 에 추가 → services.* / config 직접 import
from services.hwpx_loader import (
    _html_table_to_markdown,
    _parse_html_table,
    _rows_to_markdown,
    _decide_header,
    split_hwpx_to_blocks,
    get_hwpx_source_text,
)
from services.data_extractor import _extract_docx_eval_from_table


# ── 가짜 rhwp IR (실제 rhwp 미설치 환경 대비) ────────────────────────────────
class _FakeBlock:
    """rhwp IR 블록 모사. kind/text/html/marker 속성만 제공."""
    def __init__(self, kind, text="", html="", marker=None):
        self.kind = kind
        self.text = text
        self.html = html
        if marker is not None:
            self.marker = marker


class _FakeIR:
    def __init__(self, blocks):
        self._blocks = blocks

    def iter_blocks(self, *, scope="body", recurse=True):
        # 회귀 가드: split 은 표 셀 재귀(중복 집계) 방지를 위해 recurse=False 필수
        assert recurse is False, "split_hwpx_to_blocks must call iter_blocks(recurse=False)"
        assert scope == "body"
        return iter(self._blocks)

    @property
    def body(self):
        return self._blocks


class _FakeDoc:
    def __init__(self, ir):
        self._ir = ir

    def to_ir(self):
        return self._ir


def _run_split(blocks, monkeypatch):
    """가짜 rhwp 모듈을 주입하고 split_hwpx_to_blocks 실행."""
    fake = types.ModuleType("rhwp")
    fake.parse = lambda path: _FakeDoc(_FakeIR(blocks))
    monkeypatch.setitem(sys.modules, "rhwp", fake)
    return split_hwpx_to_blocks("dummy.hwpx")


# ════════════════════════════════════════════════════════════════════════════
# _html_table_to_markdown / _parse_html_table / _rows_to_markdown
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlTable:

    def test_basic_table(self):
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        md, mi = _html_table_to_markdown(html)
        assert mi == []
        assert "| A | B |" in md
        assert "| 1 | 2 |" in md
        assert "| --- | --- |" in md

    def test_rowspan_merge_info_docx_schema(self):
        # 배점 셀(rowspan=2)이 두 행에 걸침 → docx 호환 merge_info
        html = ("<table><tr><th>구분</th><th>배점</th></tr>"
                "<tr><td>배치</td><td rowspan='2'>20</td></tr>"
                "<tr><td>공간</td></tr></table>")
        rows_raw, mi = _parse_html_table(html)
        assert len(mi) == 1
        # docx _extract_docx_eval_from_table 가 소비하는 정확한 키 집합
        assert set(mi[0].keys()) == {"row", "col", "merged_rows", "value"}
        assert mi[0]["merged_rows"] == 2
        assert mi[0]["value"] == "20"
        assert mi[0]["col"] == 1
        assert mi[0]["row"] == 1          # 헤더 포함 그리드 행 인덱스
        # 병합 continue 셀은 빈 칸
        assert rows_raw[2][1] == ""

    def test_colspan_repeats_text(self):
        html = "<table><tr><td colspan='3'>합계</td></tr><tr><td>A</td><td>B</td><td>C</td></tr></table>"
        rows_raw, mi = _parse_html_table(html)
        assert rows_raw[0] == ["합계", "합계", "합계"]   # 가로병합 텍스트 반복
        assert mi == []                                   # 가로병합은 merge_info 미기록

    def test_cell_escape_and_truncate(self):
        long = "가" * 80
        html = f"<table><tr><td>a|b</td><td>{long}</td></tr></table>"
        md = _rows_to_markdown(_parse_html_table(html)[0])
        assert "&#124;" in md          # 파이프 이스케이프
        assert "a|b" not in md
        assert "…" in md               # 60자 컷
        assert ("가" * 80) not in md

    def test_empty_and_malformed(self):
        assert _html_table_to_markdown("") == ("", [])
        assert _html_table_to_markdown("not html") == ("", [])
        assert _parse_html_table("<table></table>") == ([], [])

    def test_strips_inner_tags(self):
        html = "<table><tr><td><b>굵게</b> 텍스트</td><td>x</td></tr></table>"
        rows_raw, _ = _parse_html_table(html)
        assert rows_raw[0][0] == "굵게 텍스트"


# ════════════════════════════════════════════════════════════════════════════
# _decide_header (폴백 A→B→C→D→E)
# ════════════════════════════════════════════════════════════════════════════
class TestDecideHeader:

    def test_a_section_number(self):
        assert _decide_header(["3.2 계획지침", "본문"], None, 5) == "3.2 계획지침"

    def test_a_caption(self):
        assert _decide_header(["[표 1] 면적표", "..."], None, 5) == "[표 1] 면적표"

    def test_b_short_first_paragraph(self):
        assert _decide_header(["개요", "이것은 매우 긴 본문 문단입니다"], None, 5) == "개요"

    def test_c_table_first_row(self):
        # 단락 없음 + 표 있음 → 표 첫 행
        h = _decide_header([], "| 구분 | 배점 |\n| --- | --- |\n| 배치 | 20 |", 5)
        assert "구분" in h and "배점" in h

    def test_d_first_nonempty_when_first_is_figure(self):
        # 첫 단락이 그림 캡션(B 제외) + 섹션/캡션 없음 → D 폴백
        h = _decide_header(["그림 1 배치도", "실제 설명 문단입니다"], None, 5)
        assert h == "실제 설명 문단입니다"

    def test_e_default(self):
        assert _decide_header([], None, 7) == "(블록 7)"


# ════════════════════════════════════════════════════════════════════════════
# split_hwpx_to_blocks (가짜 rhwp 주입)
# ════════════════════════════════════════════════════════════════════════════
class TestSplitHwpxToBlocks:

    def test_schema_keys(self, monkeypatch):
        res = _run_split([_FakeBlock("paragraph", "1. 개요"), _FakeBlock("paragraph", "내용")], monkeypatch)
        assert len(res) == 1
        b = res[0]
        assert set(b.keys()) == {
            "block_num", "header_text", "paragraphs",
            "table_markdown", "table_rows_raw", "merge_info",
        }
        assert b["block_num"] == 1

    def test_r3_section_split(self, monkeypatch):
        # _RE_SECTION_NUM(docx 상속)은 일반 번호목록("1. 첫째")과 구분하려고
        # 다단계("1.1 ") 또는 점없음("1 ")만 섹션으로 인식. 단일레벨+점("1. ")은 제외.
        res = _run_split([
            _FakeBlock("paragraph", "1.1 개요"),
            _FakeBlock("paragraph", "본문 a"),
            _FakeBlock("paragraph", "2.1 지침"),   # R3 → 새 블록
            _FakeBlock("paragraph", "본문 b"),
        ], monkeypatch)
        assert len(res) == 2
        assert res[0]["header_text"] == "1.1 개요"
        assert res[1]["header_text"] == "2.1 지침"

    def test_r4_caption_split(self, monkeypatch):
        res = _run_split([
            _FakeBlock("paragraph", "본문"),
            _FakeBlock("paragraph", "[서식 3] 신청서"),  # R4 캡션 → 새 블록
        ], monkeypatch)
        assert len(res) == 2
        assert res[1]["header_text"] == "[서식 3] 신청서"

    def test_r5_table_standalone(self, monkeypatch):
        res = _run_split([
            _FakeBlock("paragraph", "앞 문단"),
            _FakeBlock("table", html="<table><tr><td>구분</td><td>값</td></tr></table>"),
            _FakeBlock("paragraph", "뒤 문단"),
        ], monkeypatch)
        # 표는 단독 블록 → 앞/표/뒤 3블록
        assert len(res) == 3
        assert res[0]["table_markdown"] is None
        assert res[1]["table_markdown"] is not None
        assert res[1]["paragraphs"] == []
        assert res[2]["table_markdown"] is None

    def test_empty_run_boundary(self, monkeypatch):
        res = _run_split([
            _FakeBlock("paragraph", "블록 A 문단"),
            _FakeBlock("paragraph", ""),
            _FakeBlock("paragraph", ""),
            _FakeBlock("paragraph", ""),         # 빈줄 3개 → 경계
            _FakeBlock("paragraph", "블록 B 문단"),
        ], monkeypatch)
        assert len(res) == 2

    def test_force_cut_suffix(self, monkeypatch):
        # 단락 70개(>=60) → F3 강제 컷, 이어지는 블록에 "(계속)"
        paras = [_FakeBlock("paragraph", "내용 없는 일반 문단")] + \
                [_FakeBlock("paragraph", f"문단 {i}") for i in range(70)]
        res = _run_split(paras, monkeypatch)
        assert len(res) >= 2
        assert any(b["header_text"].endswith("(계속)") for b in res)

    def test_list_item_marker_prepended(self, monkeypatch):
        res = _run_split([
            _FakeBlock("paragraph", "1. 설계지침"),
            _FakeBlock("list_item", "토지이용 배치", marker="가)"),
        ], monkeypatch)
        joined = " ".join(res[0]["paragraphs"])
        assert "가) 토지이용 배치" in joined

    def test_picture_dropped(self, monkeypatch):
        # picture 블록(.kind='picture', 텍스트 없음)은 내용에 안 들어감
        res = _run_split([
            _FakeBlock("paragraph", "문단"),
            _FakeBlock("picture"),
        ], monkeypatch)
        all_text = " ".join(p for b in res for p in b["paragraphs"])
        assert "문단" in all_text
        # picture 는 텍스트가 없으므로 블록 paragraphs 를 늘리지 않음
        assert sum(len(b["paragraphs"]) for b in res) == 1


# ════════════════════════════════════════════════════════════════════════════
# cross-module: hwpx 표 블록 → _extract_docx_eval_from_table 호환
# ════════════════════════════════════════════════════════════════════════════
class TestEvalTableCompatibility:

    def test_shared_points_via_rowspan(self):
        # 배점 셀 rowspan=2 → 배치/공간이 20점 공유 (shared_with), 친환경 10점
        html = ("<table><tr><th>구분</th><th>세부</th><th>배점</th></tr>"
                "<tr><td>배치</td><td>가로</td><td rowspan='2'>20</td></tr>"
                "<tr><td>공간</td><td>실배분</td></tr>"
                "<tr><td>친환경</td><td>에너지</td><td>10</td></tr></table>")
        md, mi = _html_table_to_markdown(html)
        rows_raw, _ = _parse_html_table(html)
        block = {"table_markdown": md, "table_rows_raw": rows_raw, "merge_info": mi}

        ev = _extract_docx_eval_from_table(block)
        assert ev["total_points"] == 30
        cats = ev["evaluation_categories"]
        배치 = next(c for c in cats if c["name"] == "배치")
        assert 배치["points"] == 20
        assert "공간" in 배치["shared_with"]
        친환경 = next(c for c in cats if c["name"] == "친환경")
        assert 친환경["points"] == 10
        assert 친환경["shared_with"] == []


# ════════════════════════════════════════════════════════════════════════════
# get_hwpx_source_text (docx 구현 위임)
# ════════════════════════════════════════════════════════════════════════════
class TestGetHwpxSourceText:

    def test_delegates_to_docx(self):
        block = {
            "block_num": 1,
            "header_text": "3.2 계획지침",
            "paragraphs": ["토지이용 배치계획", "동선계획"],
            "table_markdown": None,
            "table_rows_raw": None,
            "merge_info": [],
        }
        out = get_hwpx_source_text(block)
        assert "[HEADER]" in out
        assert "3.2 계획지침" in out
        assert "토지이용 배치계획" in out
