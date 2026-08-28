"""SVG 글자 **겹침·잘림** 회귀 — 브라우저 없이, 런타임 코드 0.

기법은 concept-studio `render/qa.py` 에서 가져왔다(2026-08-28). 그쪽 원칙:
「크롬이 필요하면 CI 에서 skip 되고, **skip 되는 검사는 없는 검사다**」. 글자 폭은
모노 메트릭으로 잰다 — 라틴 0.6em · 한글 1em. 넉넉하게 잡아 애매하면 봐준다.

## 왜 런타임이 아니라 테스트인가

실측(2026-08-28, prod 21건): 우리 SVG 세 계열이 **전부 깨끗하다**(매스 19 텍스트 ·
면적 스택 12 · 제안서 16). 그쪽이 만들자마자 6건을 잡은 것과 다른 이유는 **구조가
달라서**다 — 우리 조닝 다이어그램은 라벨을 SVG 안이 아니라 **HTML 카드**(`pz-loc`·
범례)에 둔다. 겹칠 글자가 애초에 거의 없다.

그래서 「지금 뭔가를 찾아내는 기능」으로는 값이 없다. 대신 **회귀 가드**로는 값이 있다:
`brief_massing` 은 라벨 19개를 SVG 안에 그리고 아직 손대는 중이다(정북 계단컷 미반영).
라벨이 늘거나 좌표가 바뀌면 **조용히** 깨진다 — 그림은 나오는데 글자만 겹친다.

⚠ 이 검사가 **못 하는 것**: 도형끼리의 겹침, 글자와 도형의 겹침, 실제 폰트 메트릭
(우리는 모노 근사). 대비·빈 영역도 안 본다(그쪽은 본다 — 필요해지면 그때).
이름을 「레이아웃」으로 붙여 둔다, 나중에 과대평가되지 않도록.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: 모노 한 글자의 폭(em). 한글·한자는 라틴의 거의 두 배다.
LATIN_EM, WIDE_EM = 0.6, 1.0
#: 기준선(`y`)에서 위아래로 잡는 글자 상자.
ASCENT, DESCENT = 0.80, 0.25
#: 이만큼은 스쳐도 봐준다 — 모노 추정이라 오차가 있다.
SLACK = 1.5

_TEXT = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_VIEWBOX = re.compile(r'viewBox="([\d.\-]+) ([\d.\-]+) ([\d.]+) ([\d.]+)"')
_SVG = re.compile(r"<svg\b.*?</svg>", re.S)


def _attr(tag: str, name: str):
    m = re.search(name + r'="([^"]*)"', tag)
    return m.group(1) if m else None


def _advance(s: str) -> float:
    return sum(WIDE_EM if ord(c) >= 0x2E80 else LATIN_EM for c in s)


def _boxes(svg: str):
    """(x0, y0, x1, y1, 글자). 좌표·크기가 인라인 속성일 때만 — 우리 렌더러가 그렇다."""
    out = []
    for attrs, body in _TEXT.findall(svg):
        s = re.sub(r"<[^>]+>", "", body).strip()
        if not s:
            continue
        try:
            x = float(_attr(attrs, "x") or 0)
            y = float(_attr(attrs, "y") or 0)
            size = float(_attr(attrs, "font-size") or 12)
        except ValueError:
            continue
        w = _advance(s) * size
        left = {"middle": x - w / 2, "end": x - w}.get(_attr(attrs, "text-anchor") or "start", x)
        out.append((left, y - size * ASCENT, left + w, y + size * DESCENT, s))
    return out


def check_svg(svg: str, name: str = "") -> list[str]:
    """글자 겹침·도면 밖 이탈. 문제 없으면 []."""
    vb = _VIEWBOX.search(svg)
    if not vb:
        return [f"{name}: viewBox 가 없어 검사할 수 없다"]
    W, H = float(vb.group(3)), float(vb.group(4))
    boxes, out = _boxes(svg), []
    for i, (x0, y0, x1, y1, s) in enumerate(boxes):
        for (u0, v0, u1, v1, t) in boxes[i + 1:]:
            if x0 < u1 - SLACK and u0 < x1 - SLACK and y0 < v1 - SLACK and v0 < y1 - SLACK:
                out.append(f"{name}: 글자가 겹친다 — {s[:22]!r} × {t[:22]!r}")
        if x0 < -SLACK or x1 > W + SLACK:
            out.append(f"{name}: 글자가 가로로 넘쳤다 — {s[:24]!r} (x {x0:.0f}~{x1:.0f} / W={W:.0f})")
        if y0 < -SLACK or y1 > H + SLACK:
            out.append(f"{name}: 글자가 세로로 넘쳤다 — {s[:24]!r} (y {y0:.0f}~{y1:.0f} / H={H:.0f})")
    return out


def _all(html: str, label: str) -> tuple[list[str], int, int]:
    """(문제, svg 수, 글자 수) — **본 것의 수를 같이 돌려준다.**

    아무것도 안 본 검사기는 언제나 깨끗하다고 말한다. 이 세션에서 실제로 한 번
    그렇게 착각할 뻔했다 — 「0건」을 믿기 전에 분모를 본다.
    """
    issues, n_svg, n_txt = [], 0, 0
    for i, svg in enumerate(_SVG.findall(html or "")):
        n_svg += 1
        n_txt += len(_boxes(svg))
        issues += check_svg(svg, f"{label}#{i}")
    return issues, n_svg, n_txt


# ── 검사기 자체가 도는지 (자가 검증) ────────────────────────────────────────


def test_detects_a_real_overlap():
    svg = ('<svg viewBox="0 0 100 40">'
           '<text x="10" y="20" font-size="12">서울특별시</text>'
           '<text x="12" y="22" font-size="12">영등포구</text></svg>')
    assert any("겹친다" in i for i in check_svg(svg, "t"))


def test_detects_horizontal_clip():
    svg = '<svg viewBox="0 0 60 40"><text x="40" y="20" font-size="12">넘치는긴라벨</text></svg>'
    assert any("가로로 넘쳤다" in i for i in check_svg(svg, "t"))


def test_anchor_shifts_the_box():
    """`text-anchor="end"` 는 왼쪽으로 자란다 — 이걸 무시하면 헛경고가 난다."""
    svg = '<svg viewBox="0 0 200 40"><text x="195" y="20" text-anchor="end" font-size="10">합계</text></svg>'
    assert check_svg(svg, "t") == []


def test_clean_svg_is_clean():
    svg = ('<svg viewBox="0 0 300 40">'
           '<text x="5" y="20" font-size="10">왼쪽</text>'
           '<text x="200" y="20" font-size="10">오른쪽</text></svg>')
    assert check_svg(svg, "t") == []


# ── 실제 렌더러 ─────────────────────────────────────────────────────────────


@pytest.fixture
def brief():
    """면적표·부지 지오메트리를 갖춘 최소 지침서 — 매스와 스택 둘 다 그려진다."""
    return {
        "_brief_meta": {"facility_type": "public", "brief_name": "레이아웃 회귀"},
        "feasibility_export": {
            "schema_version": 2,
            "sites": [
                {"site_id": "부지1", "address": "서울특별시 영등포구 당산동3가 385",
                 "site_area_sqm": 7498.0, "building_coverage_pct": 60,
                 "floor_area_ratio_pct": 460, "max_height_m": 100.0,
                 "floor_area_sqm": 34490.0},
                {"site_id": "부지2", "address": "서울특별시 영등포구 양평동",
                 "site_area_sqm": 2940.0, "building_coverage_pct": 60,
                 "floor_area_ratio_pct": 400, "max_height_m": 40.0,
                 "floor_area_sqm": 11760.0},
            ],
        },
        # ⚠ 실제 추출 스키마 그대로 — `row_type`/`area`/`subtotal_area`/`is_subtotal`.
        #   («area_sqm»·«level» 로 지어냈다가 SVG 가 하나도 안 그려졌다. 아래 분모 가드가 잡았다.)
        "brief_program": [{"area_rows": [
            {"row_type": "site_total", "name": "총 합계 (①+②)", "area": None,
             "subtotal_area": 46250.0, "is_subtotal": True, "note": "", "dept": ""},
            {"row_type": "site_total", "name": "부지1(당산동3가 385) 합계 ①", "area": None,
             "subtotal_area": 34490.0, "is_subtotal": True, "note": "", "dept": ""},
            {"row_type": "facility", "name": "통합민원실·다목적 대강당·구민이용시설",
             "area": 12000.0, "subtotal_area": None, "is_subtotal": False},
            {"row_type": "facility", "name": "직무공간·업무지원공간",
             "area": 18000.0, "subtotal_area": None, "is_subtotal": False},
            {"row_type": "facility", "name": "지하주차장",
             "area": 4490.0, "subtotal_area": None, "is_subtotal": False},
            {"row_type": "site_total", "name": "부지2(양평동) 합계 ②", "area": None,
             "subtotal_area": 11760.0, "is_subtotal": True, "note": "", "dept": ""},
            {"row_type": "facility", "name": "보건소·공공커뮤니티지원센터",
             "area": 11760.0, "subtotal_area": None, "is_subtotal": False},
        ]}],
    }


def test_massing_svg_has_no_overlap_or_clip(brief):
    """라벨 19개를 SVG 안에 그리는 유일한 계열 — 여기가 제일 깨지기 쉽다."""
    from services.brief_massing import massing_html
    issues, n_svg, n_txt = _all(massing_html(brief), "매스")
    assert n_svg and n_txt, f"검사할 게 없다 (svg {n_svg} · 글자 {n_txt}) — 픽스처가 죽었다"
    assert not issues, "\n".join(issues)


def test_program_stack_svg_has_no_overlap_or_clip(brief):
    from services.brief_checklist_exporter import program_stack_html
    issues, n_svg, n_txt = _all(program_stack_html(brief), "스택")
    assert n_svg and n_txt, f"검사할 게 없다 (svg {n_svg} · 글자 {n_txt})"
    assert not issues, "\n".join(issues)


def test_long_korean_labels_do_not_overflow(brief):
    """실무 라벨은 길다 — 「공공커뮤니티지원센터(주민편의시설)」 같은 것."""
    from services.brief_checklist_exporter import program_stack_html
    b = json.loads(json.dumps(brief))
    b["brief_program"][0]["area_rows"][2]["name"] = (
        "통합민원실·다목적 대강당·구민이용시설 및 공공커뮤니티지원센터(주민편의시설)")
    issues, _, n_txt = _all(program_stack_html(b), "긴라벨")
    assert n_txt
    assert not issues, "\n".join(issues)
