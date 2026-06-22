"""
hwpx_loader.py — HWP/HWPX 지침서를 블록 단위로 분할/파싱

rhwp-python(Rust 바이너리) 사용. PDF/DOCX 흐름과 완전 독립 모듈.

설계 결정:
  - 반환 스키마는 docx_loader.split_docx_to_blocks() 와 **동일** (block_num/header_text/
    paragraphs/table_markdown/table_rows_raw/merge_info) — classify_all_blocks_brief /
    extract_hwpx / BRIEF_* 추출 헬퍼가 docx 와 동일하게 재사용한다.
  - merge_info 스키마는 docx 와 동일하게 {row, col, merged_rows, value} (세로 병합만).
    data_extractor._extract_docx_eval_from_table 가 이 키들을 소비하므로 필수.
    가로 병합(colspan)은 docx 동작과 동일하게 셀 텍스트를 반복(empty 가 아님).
  - 블록 분할: R3(섹션번호)/R4(캡션)/R5(표 단독) + F1(TOC 압축)/F3(force-cut) + 빈단락 경계.

rhwp 는 split_hwpx_to_blocks 내부에서 lazy import — 라이브러리 미설치 시에도
모듈 import 자체는 실패하지 않는다 (PDF/DOCX 분석 무영향).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ── 설정 상수 (docx_loader 와 동일 값) ────────────────────────────────────────
_FORCE_CUT_PARAS     = 60       # F3: 단락 수
_FORCE_CUT_CHARS     = 12000    # F3: 글자 수
_HEADER_FALLBACK_LEN = 60       # header_text 폴백 최대 길이
_HEADING_MAX_LEN     = 60       # B 폴백: 짧은 첫 단락 기준
_TABLE_CELL_MAX      = 60       # 표 셀 텍스트 최대 길이 (마크다운)
_EMPTY_RUN_BOUNDARY  = 3        # 빈 단락 연속 N개 → 블록 경계

# 정규식 (docx_loader 와 동등)
_RE_SECTION_NUM = re.compile(r'^(제\d+장|\d+(\.\d+)*)\s')   # R3
_RE_CAPTION     = re.compile(r'\[\s*(표|양식|서식|별표)\s*\d+')  # R4
_RE_TOC         = re.compile(r'\t\d+\s*$')                  # F1: 탭+페이지번호
_RE_FIGURE      = re.compile(r'^(그림\s*\d+|Fig\.)')
_RE_CONTINUE    = re.compile(r'\(\s*계속\s*\)')


# ══════════════════════════════════════════════════════════════════════════════
# rhwp IR 접근 계층 (방어적 — 설치된 rhwp 버전에 따라 속성명이 다를 수 있어
# 여러 후보를 순차 탐색한다. 동작 안 하면 이 헬퍼만 조정하면 됨.)
# ══════════════════════════════════════════════════════════════════════════════
def _block_kind(block) -> str:
    """IR 블록 종류: 'paragraph' | 'table'. kind 속성 없으면 표 HTML 유무로 추론."""
    k = getattr(block, "kind", None)
    if k:
        return str(k).lower()
    return "table" if _block_table_html(block) else "paragraph"


def _block_text(block) -> str:
    """문단/리스트 블록의 텍스트. .text 속성 우선, get_text()/to_text() 폴백.

    ListItemBlock 은 글머리(marker)가 .text 와 분리돼 있어 prepend — docx 가 본문에
    글머리 기호를 포함하는 것과 맞춰 design_guidelines_grouped 라벨 힌트를 보존한다.
    """
    v = getattr(block, "text", None)
    if isinstance(v, str):
        marker = getattr(block, "marker", None)
        if isinstance(marker, str) and marker.strip():
            return f"{marker.strip()} {v}".strip()
        return v
    if callable(v):
        try:
            r = v()
            if isinstance(r, str):
                return r
        except Exception:
            pass
    for m in ("get_text", "to_text"):
        fn = getattr(block, m, None)
        if callable(fn):
            try:
                r = fn()
                if isinstance(r, str):
                    return r
            except Exception:
                pass
    return ""


def _block_table_html(block) -> str | None:
    """표 블록의 HTML. .html/.table_html 속성 우선, to_html()/as_html() 폴백."""
    for attr in ("html", "table_html"):
        v = getattr(block, attr, None)
        if isinstance(v, str) and "<" in v:
            return v
    for m in ("to_html", "as_html"):
        fn = getattr(block, m, None)
        if callable(fn):
            try:
                r = fn()
                if isinstance(r, str) and "<" in r:
                    return r
            except Exception:
                pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# HTML 표 파싱 (BeautifulSoup 없이 stdlib html.parser)
# ══════════════════════════════════════════════════════════════════════════════
class _TableHTMLParser(HTMLParser):
    """<table> HTML → 셀 그리드. 각 셀 = (text, rowspan, colspan)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self._cur: list[tuple[str, int, int]] | None = None
        self._buf: list[str] | None = None
        self._span: tuple[int, int] = (1, 1)

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "tr":
            self._cur = []
        elif t in ("td", "th"):
            d = dict(attrs)

            def _ival(v):
                try:
                    return max(1, int(str(v)))
                except (TypeError, ValueError):
                    return 1

            self._span = (_ival(d.get("rowspan")), _ival(d.get("colspan")))
            self._buf = []
        elif self._buf is not None and t in ("br", "p", "div", "li"):
            # 셀 내부 줄바꿈/블록 경계 → 공백 (태그 자체는 데이터 미발생)
            self._buf.append(" ")

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("td", "th") and self._buf is not None and self._cur is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._cur.append((text, self._span[0], self._span[1]))
            self._buf = None
        elif t == "tr" and self._cur is not None:
            self.rows.append(self._cur)
            self._cur = None


def _grid_from_rows(
    parsed_rows: list[list[tuple[str, int, int]]],
) -> tuple[list[list[str]], list[dict]]:
    """(text, rowspan, colspan) 행 리스트 → (rows_raw, merge_info).

    rows_raw  : 2D 텍스트. 세로병합 continue=빈칸, 가로병합=텍스트 반복 (docx 동작).
    merge_info: [{row, col, merged_rows, value}] — 세로병합(rowspan>1)만 (docx 호환).
                row 는 헤더 포함 그리드 행 인덱스 (docx merge_info 와 동일 좌표계).
    """
    rows_raw: list[list[str]] = []
    merge_info: list[dict] = []
    carry: dict[int, dict] = {}   # col -> {"remaining": int, "text": str}

    for r, cells in enumerate(parsed_rows):
        row: list[str] = []
        c = 0
        it = iter(cells)
        cell = next(it, None)
        while True:
            # 위 행에서 내려온 세로병합 continue → 빈 칸
            if c in carry:
                row.append("")
                carry[c]["remaining"] -= 1
                if carry[c]["remaining"] <= 0:
                    del carry[c]
                c += 1
                continue
            if cell is None:
                break
            text, rs, cs = cell
            for _ in range(cs):                 # 가로병합 → 텍스트 반복
                row.append(text)
                if rs > 1:                      # 세로병합 시작 → continue 예약 + merge_info
                    carry[c] = {"remaining": rs - 1, "text": text}
                    merge_info.append({"row": r, "col": c, "merged_rows": rs, "value": text})
                c += 1
            cell = next(it, None)
        # 행 셀 소진 후 오른쪽 끝에 남은 세로병합 continue 처리
        while c in carry:
            row.append("")
            carry[c]["remaining"] -= 1
            if carry[c]["remaining"] <= 0:
                del carry[c]
            c += 1
        rows_raw.append(row)

    return rows_raw, merge_info


def _rows_to_markdown(rows_raw: list[list[str]]) -> str:
    """rows_raw → 파이프 마크다운. 셀 60자 컷 + '…', 셀 안 | → &#124;."""
    if not rows_raw:
        return ""
    n_cols = max((len(r) for r in rows_raw), default=0)
    if n_cols == 0:
        return ""

    def _cell(t: str) -> str:
        s = re.sub(r"\s*\n+\s*", " ", t or "").strip().replace("|", "&#124;")
        if len(s) > _TABLE_CELL_MAX:
            s = s[: _TABLE_CELL_MAX - 1] + "…"
        return s

    def _pad(r: list[str]) -> list[str]:
        return [_cell(x) for x in r] + [""] * (n_cols - len(r))

    lines = ["| " + " | ".join(_pad(rows_raw[0])) + " |",
             "| " + " | ".join(["---"] * n_cols) + " |"]
    for r in rows_raw[1:]:
        lines.append("| " + " | ".join(_pad(r)) + " |")
    return "\n".join(lines)


def _parse_html_table(html: str) -> tuple[list[list[str]], list[dict]]:
    """HTML <table> → (rows_raw, merge_info). 파싱 실패 시 ([], [])."""
    parser = _TableHTMLParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return [], []
    return _grid_from_rows(parser.rows)


def _html_table_to_markdown(html: str) -> tuple[str, list[dict]]:
    """HTML <table> → (파이프 마크다운, merge_info).

    merge_info 는 docx 호환 {row, col, merged_rows, value} (세로병합).
    독립 테스트용 공개 함수 — split_hwpx_to_blocks 는 동일 결과를
    _parse_html_table + _rows_to_markdown 으로 1회 파싱해 얻는다.
    """
    rows_raw, merge_info = _parse_html_table(html)
    return _rows_to_markdown(rows_raw), merge_info


# ══════════════════════════════════════════════════════════════════════════════
# header_text 폴백 (A → B → C → D → E)
# ══════════════════════════════════════════════════════════════════════════════
def _clean_header(text: str) -> str:
    return (text or "").strip()[:_HEADER_FALLBACK_LEN]


def _decide_header(paragraphs: list[str], table_markdown: str | None, block_num: int) -> str:
    """page_header_text 폴백 A→B→C→D→E.

    A. 첫 R3/R4 패턴 단락
    B. 짧은 첫 단락 (60자 미만)  — rhwp IR 에 bold 정보가 없어 길이 기준만 사용
    C. 표 첫 행 텍스트 60자
    D. 첫 비어있지 않은 단락 60자
    E. "(블록 N)" 디폴트
    """
    # A
    for p in paragraphs:
        if _RE_SECTION_NUM.search(p) or _RE_CAPTION.search(p):
            return _clean_header(p)
    # B
    if paragraphs:
        first = paragraphs[0].strip()
        if first and len(first) < _HEADING_MAX_LEN and not _RE_FIGURE.match(first):
            return _clean_header(first)
    # C
    if table_markdown:
        first_line = table_markdown.split("\n", 1)[0]
        cells = [c.strip() for c in first_line.strip("|").split("|") if c.strip()]
        if cells:
            return _clean_header(" · ".join(cells))
    # D
    for p in paragraphs:
        t = p.strip()
        if t and not _RE_FIGURE.match(t) and not _RE_CONTINUE.search(t):
            return _clean_header(t)
    # E
    return f"(블록 {block_num})"


# ══════════════════════════════════════════════════════════════════════════════
# 메인: split_hwpx_to_blocks
# ══════════════════════════════════════════════════════════════════════════════
def split_hwpx_to_blocks(path: str) -> list[dict]:
    """HWP/HWPX 파일을 의미 단위 블록으로 분할.

    각 블록 dict (docx_loader.split_docx_to_blocks 와 동일 스키마):
      {
        "block_num": int,
        "header_text": str,
        "paragraphs": [str],
        "table_markdown": str | None,
        "table_rows_raw": [[str]] | None,
        "merge_info": [{"row", "col", "merged_rows", "value"}],
      }
    """
    import rhwp   # lazy import — 미설치 시 이 함수 호출 시점에만 실패

    doc = rhwp.parse(path)
    ir = doc.to_ir()
    # 본문 최상위 블록만 순회. iter_blocks 기본값이 recurse=True 라 TableCell.blocks
    # (표 셀 내부 문단)까지 재귀해 표가 중복 집계되므로 recurse=False 필수.
    # (rhwp 0.7.0 검증: scope="body" 기본=RAG-safe 본문만, recurse=False=셀 미진입.
    #  docstring 도 구조 분할엔 doc.body 직접 접근을 권장.)
    try:
        ir_blocks = list(ir.iter_blocks(scope="body", recurse=False))
    except TypeError:
        ir_blocks = list(getattr(ir, "body", None) or [])

    # ── 1차: 선형 IR 스트림 → raw 블록 분할 ──────────────────────────────────
    raw_blocks: list[dict] = []   # {paragraphs:[str], table_html:str|None, is_toc, force_cut}
    current: dict | None = None
    toc_buffer: list[str] = []
    empty_run = 0

    def _new_block(first_para: str | None = None, force_cut: bool = False) -> dict:
        b = {"paragraphs": [], "table_html": None, "is_toc": False, "force_cut": force_cut}
        if first_para is not None:
            b["paragraphs"].append(first_para)
        return b

    def _flush_current():
        nonlocal current
        if current and (current["paragraphs"] or current["table_html"]):
            raw_blocks.append(current)
        current = None

    def _flush_toc():
        nonlocal current
        if toc_buffer:
            raw_blocks.append({
                "paragraphs": list(toc_buffer), "table_html": None,
                "is_toc": True, "force_cut": False,
            })
            toc_buffer.clear()
        current = None

    def _force_cut_needed(b: dict) -> bool:
        if len(b["paragraphs"]) >= _FORCE_CUT_PARAS:
            return True
        return sum(len(p) for p in b["paragraphs"]) >= _FORCE_CUT_CHARS

    for blk in ir_blocks:
        kind = _block_kind(blk)

        # R5: 표는 항상 단독 블록
        if kind == "table":
            if toc_buffer:
                _flush_toc()
            _flush_current()
            raw_blocks.append({
                "paragraphs": [], "table_html": _block_table_html(blk) or "",
                "is_toc": False, "force_cut": False,
            })
            empty_run = 0
            continue

        text = (_block_text(blk) or "").strip()

        # 빈 단락 연속 3개 이상 → 블록 경계
        if not text:
            empty_run += 1
            if empty_run >= _EMPTY_RUN_BOUNDARY:
                if toc_buffer:
                    _flush_toc()
                _flush_current()
                empty_run = 0
            continue
        empty_run = 0

        # F1: TOC 항목 누적
        if _RE_TOC.search(text):
            _flush_current()
            toc_buffer.append(text)
            continue
        if toc_buffer:
            _flush_toc()

        # R3/R4: 섹션번호 / 캡션 → 새 블록
        if _RE_CAPTION.search(text) or _RE_SECTION_NUM.search(text):
            _flush_current()
            current = _new_block(first_para=text)
        else:
            if current is None:
                current = _new_block(first_para=text)
            else:
                current["paragraphs"].append(text)
                # F3: force-cut
                if _force_cut_needed(current):
                    _flush_current()
                    current = _new_block(force_cut=True)

    if toc_buffer:
        _flush_toc()
    _flush_current()

    # ── 2차: dict 변환 (header_text + table_markdown + table_rows_raw + merge_info) ──
    result: list[dict] = []
    for idx, b in enumerate(raw_blocks, start=1):
        paras = [p for p in b["paragraphs"] if p.strip()]
        if b["table_html"]:
            rows_raw, merge_info = _parse_html_table(b["table_html"])
            table_md = _rows_to_markdown(rows_raw)
        else:
            rows_raw, merge_info, table_md = [], [], ""

        if b.get("is_toc"):
            header = "(목차)"
        else:
            header = _decide_header(paras, table_md or None, idx)
        if b.get("force_cut"):
            header = f"{header} (계속)"

        result.append({
            "block_num":      idx,
            "header_text":    header,
            "paragraphs":     paras,
            "table_markdown": table_md or None,
            "table_rows_raw": rows_raw or None,
            "merge_info":     merge_info,
        })

    return result


# ── source text (분류·추출 공통 입력) ────────────────────────────────────────
def get_hwpx_source_text(block: dict) -> str:
    """HWPX 블록의 헤더 + 단락 + 표 미리보기를 결합한 텍스트.

    HWPX 블록 스키마가 DOCX 와 완전히 동일하므로 docx_loader.get_block_source_text
    와 **동일 로직**을 그대로 재사용한다 (단일 소스, 드리프트 방지).
    6,000자 초과 시 앞 4,000 + 뒤 2,000 컷, 글머리 라벨 힌트 부착 등 docx 동작 동일.
    """
    from services.docx_loader import get_block_source_text
    return get_block_source_text(block)
