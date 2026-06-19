"""
test_design_chunking.py — BRIEF_DESIGN_* 연속 페이지 청크 분할 단위 테스트

대상:
  data_extractor.py::extract_pdf() 내부 청크 생성 로직 (CLAUDE.md 시퀀스 D).

목적:
  같은 type의 연속 페이지가 _DESIGN_STACK_CHUNK 이하로 묶이고,
  타입 경계·비연속 지점에서 청크가 정확히 분리되는지 검증.

실행:
  cd <repo-root>
  backend/venv/Scripts/python.exe -m pytest tests/test_design_chunking.py -v

LLM/네트워크 의존 없음.
"""

_DESIGN_BRIEF_TYPES = {
    "BRIEF_DESIGN_MASSING", "BRIEF_DESIGN_GUIDE", "BRIEF_DESIGN_FACADE",
    "BRIEF_DESIGN_SUSTAIN", "BRIEF_DESIGN_SPECIAL",
}
_DESIGN_STACK_CHUNK = 3


def _chunk(type_by_page: dict[int, str]) -> list[list[int]]:
    """data_extractor.extract_pdf의 청크 생성 로직 복제 (테스트용)."""
    sorted_design = sorted(pg for pg, pt in type_by_page.items() if pt in _DESIGN_BRIEF_TYPES)
    chunks: list[list[int]] = []
    current: list[int] = []
    current_type: str | None = None
    for pg in sorted_design:
        pt = type_by_page.get(pg)
        if (
            current
            and pt == current_type
            and pg == current[-1] + 1
            and len(current) < _DESIGN_STACK_CHUNK
        ):
            current.append(pg)
        else:
            if len(current) >= 2:
                chunks.append(current)
            current = [pg]
            current_type = pt
    if len(current) >= 2:
        chunks.append(current)
    return chunks


def test_empty_input():
    assert _chunk({}) == []


def test_single_page_no_chunk():
    assert _chunk({45: "BRIEF_DESIGN_GUIDE"}) == []


def test_two_consecutive_pages():
    assert _chunk({45: "BRIEF_DESIGN_GUIDE", 46: "BRIEF_DESIGN_GUIDE"}) == [[45, 46]]


def test_yeongdeungpo_45_46_47():
    """영등포구 통합 신청사 PDF 핵심 케이스: p.45+46+47 직무공간 섹션 연속."""
    type_by_page = {45: "BRIEF_DESIGN_GUIDE", 46: "BRIEF_DESIGN_GUIDE", 47: "BRIEF_DESIGN_GUIDE"}
    assert _chunk(type_by_page) == [[45, 46, 47]]


def test_chunk_max_size():
    """4페이지 연속 → 3+1로 분할 (singleton은 청크 안 됨)."""
    type_by_page = {p: "BRIEF_DESIGN_GUIDE" for p in [45, 46, 47, 48]}
    # 48은 singleton으로 제외
    assert _chunk(type_by_page) == [[45, 46, 47]]


def test_non_contiguous_split():
    type_by_page = {28: "BRIEF_DESIGN_GUIDE", 29: "BRIEF_DESIGN_GUIDE",
                    45: "BRIEF_DESIGN_GUIDE", 46: "BRIEF_DESIGN_GUIDE"}
    assert _chunk(type_by_page) == [[28, 29], [45, 46]]


def test_type_boundary_split():
    """같은 페이지 번호 연속이라도 타입이 다르면 분리."""
    type_by_page = {66: "BRIEF_DESIGN_GUIDE", 67: "BRIEF_DESIGN_MASSING", 68: "BRIEF_DESIGN_MASSING"}
    # 66은 singleton, 67-68은 청크
    assert _chunk(type_by_page) == [[67, 68]]


def test_yeongdeungpo_full_distribution():
    """영등포 PDF 전체 BRIEF_DESIGN_* 분포 → 예상 청크."""
    type_by_page = {}
    for p in [28, 29, 45, 46, 47, 49, 50, 51, 52, 53, 61, 62, 63, 64, 65, 66, 69, 70, 73]:
        type_by_page[p] = "BRIEF_DESIGN_GUIDE"
    for p in [67, 68]:
        type_by_page[p] = "BRIEF_DESIGN_MASSING"
    for p in [34, 48, 71, 72]:
        type_by_page[p] = "BRIEF_DESIGN_SPECIAL"
    chunks = _chunk(type_by_page)
    assert chunks == [
        [28, 29],
        [45, 46, 47],
        [49, 50, 51],
        [52, 53],
        [61, 62, 63],
        [64, 65, 66],
        [67, 68],
        [69, 70],
        [71, 72],
    ]
    # 영등포 핵심 케이스 — p.45+46 같은 청크 보장
    target = next(c for c in chunks if 45 in c)
    assert 46 in target


def test_chunk_resets_on_max_then_continues():
    """3페이지 청크 후 다음 연속 페이지는 새 청크 시작 (4번째부터)."""
    type_by_page = {p: "BRIEF_DESIGN_GUIDE" for p in [45, 46, 47, 48, 49]}
    # 청크 [45,46,47] 만들고 48부터 새 청크. 48-49가 청크 [48,49].
    chunks = _chunk(type_by_page)
    assert chunks == [[45, 46, 47], [48, 49]]
