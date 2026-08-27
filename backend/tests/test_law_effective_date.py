"""법조문 **시행일** 표기 회귀 — arch-law-graph F-1(`ef_yd`)·F-4(`law_ef_yd`) 소비.

"이 한도 언제 기준이냐"에 리포트만 보고 답하게 하는 게 목적이다.

⚠ 두 필드는 **의미가 다르다**(graph `doc/API.md` §ef_yd):
  · `ef_yd`     = 그 **조문**이 시행된 날 — 중앙법령 조문에만 값
  · `law_ef_yd` = 그 조문이 속한 **법규 판본** 시행일 — 조례·고시·별표는 이쪽만
섞으면 "조례 조문이 2026-02-27 에 시행됐다" 같은 거짓말이 된다.
"""
import pytest

from services.arch_law_client import _fmt_ef, effective_label


# ── 포맷 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expect", [
    ("20260227", "2026-02-27"),
    ("20260713", "2026-07-13"),
    ("", ""),
    (None, ""),
    ("2026-02-27", ""),      # 이미 포맷된 값은 raw 가 아니다 — 추측하지 않는다
    ("202602", ""),
    ("2026022X", ""),
    (20260227, "2026-02-27"),
])
def test_fmt_ef(raw, expect):
    assert _fmt_ef(raw) == expect


# ── 라벨 규칙 (graph 웹앱 `data.js efInfo` 와 같은 규칙) ─────────────────────


def test_statute_article_uses_article_date():
    tx = {"ef_yd": "20260227", "law_ef_yd": "20260227"}
    assert effective_label(tx) == "시행 2026-02-27"


def test_ordinance_falls_back_to_law_date_and_says_so():
    """조례·고시·별표는 조문시행일이 없다 — **법규임을 라벨에 밝힌다**."""
    assert effective_label({"ef_yd": "", "law_ef_yd": "20260713"}) == "법규 시행 2026-07-13"
    assert effective_label({"ef_yd": "", "law_ef_yd": "20260708"}) == "법규 시행 2026-07-08"


def test_precedent_has_no_effective_date():
    """판례·해석례는 시행일 개념이 없다(`law_ef_yd: null`) — 아무것도 안 쓴다."""
    assert effective_label({"ef_yd": "", "law_ef_yd": None}) == ""


def test_article_date_wins_over_law_date():
    """조문 시행일이 있으면 그것이 더 정확하다 — 법규 판본 날짜로 덮지 않는다."""
    assert effective_label({"ef_yd": "20260227", "law_ef_yd": "20260713"}) == "시행 2026-02-27"


@pytest.mark.parametrize("tx", [None, {}, "문자열", {"ef_yd": None, "law_ef_yd": None}])
def test_missing_keys_are_silent(tx):
    """옛 브리프의 `law_texts` 엔 이 키가 아예 없다 — graceful."""
    assert effective_label(tx) == ""


# ── 클라이언트가 키를 보존하는가 ────────────────────────────────────────────


def test_fetch_preserves_both_date_fields(monkeypatch):
    """graph 는 **키를 항상 준다** — 빈 문자열과 키 없음의 구분이 소비자 정보다."""
    import asyncio

    import services.arch_law_client as alc

    payload = {"results": [{
        "query": "서울특별시 도시계획 조례/제55조", "found": True,
        "title": "건폐율", "content": "제55조(건폐율) …", "source_url": "https://law.go.kr/x",
        "law_nm": "서울특별시 도시계획 조례", "article_no": "55",
        "ef_yd": "", "law_ef_yd": "20260713",
    }]}

    class _R:
        status_code = 200

        def json(self):
            return payload

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _R()

    monkeypatch.setattr(alc.httpx, "AsyncClient", _C)
    got = asyncio.run(alc.fetch_law_texts(["서울특별시 도시계획 조례/제55조"]))
    tx = got["서울특별시 도시계획 조례/제55조"]
    assert tx["ef_yd"] == "" and tx["law_ef_yd"] == "20260713"
    assert effective_label(tx) == "법규 시행 2026-07-13"


# ── 렌더 ────────────────────────────────────────────────────────────────────


def _sc(law_texts):
    return {
        "law_diagnosis": [{
            "site_id": "부지1", "envelope": {"bcr_limit_pct": 60, "far_limit_pct": 460},
            "law_refs": [{"name": "서울특별시 도시계획 조례/제55조", "url": "https://law.go.kr/x"},
                         {"name": "건축법/제42조", "url": "https://law.go.kr/y"}],
        }],
        "law_texts": law_texts,
    }


def test_html_footnote_shows_effective_date():
    from services.brief_proposal_report_generator import _law_diagnosis_html
    out = _law_diagnosis_html(_sc({
        "서울특별시 도시계획 조례/제55조": {"ef_yd": "", "law_ef_yd": "20260713",
                                            "content": "제55조(건폐율) 본문"},
        "건축법/제42조": {"ef_yd": "20260227", "law_ef_yd": "20260227",
                          "content": "제42조(대지의 조경) 본문"},
    }))
    assert "법규 시행 2026-07-13" in out
    assert "시행 2026-02-27" in out


def test_html_footnote_without_dates_is_unchanged():
    """옛 브리프(시행일 키 없음)에서 빈 배지가 붙지 않는다."""
    from services.brief_proposal_report_generator import _law_diagnosis_html
    out = _law_diagnosis_html(_sc({"건축법/제42조": {"content": "본문"}}))
    assert "law-ef" not in out
    assert "건축법/제42조" in out


def test_markdown_carries_the_same_provenance():
    """md·HWPX 로도 같은 출처가 따라간다 — 「언제 기준이냐」는 문서 종류를 안 가린다."""
    from services.brief_checklist_exporter import _md_site_law_block
    L: list[str] = []
    _md_site_law_block(L, {"_site_context": _sc({
        "건축법/제42조": {"ef_yd": "20260227", "law_ef_yd": "20260227"},
        "서울특별시 도시계획 조례/제55조": {"ef_yd": "", "law_ef_yd": "20260713"},
    })})
    md = "\n".join(L)
    assert "**근거 조문**" in md
    assert "건축법/제42조" in md and "— 시행 2026-02-27" in md
    assert "— 법규 시행 2026-07-13" in md


def test_markdown_refs_are_deduped_across_sites():
    from services.brief_checklist_exporter import _md_site_law_block
    sc = _sc({})
    sc["law_diagnosis"].append(dict(sc["law_diagnosis"][0], site_id="부지2"))
    L: list[str] = []
    _md_site_law_block(L, {"_site_context": sc})
    md = "\n".join(L)
    assert md.count("건축법/제42조") == 1
