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


# ── 백필 병합 (tools/backfill_law_ef.py) ────────────────────────────────────


def test_merge_never_deletes_what_we_already_had():
    """graph 가 잠깐 죽거나 조문을 못 찾게 되면, 통째로 갈아끼울 때 원문이 사라진다."""
    from services.arch_law_client import merge_law_texts
    old = {"건축법/제42조": {"content": "제42조 본문", "source_url": "u"},
           "사라진 조문/제1조": {"content": "옛 본문"}}
    new = {"건축법/제42조": {"content": "제42조 본문", "ef_yd": "20260227",
                             "law_ef_yd": "20260227"}}
    out = merge_law_texts(old, new)
    assert out["사라진 조문/제1조"]["content"] == "옛 본문", "안 온 조문을 지웠다"
    assert out["건축법/제42조"]["ef_yd"] == "20260227"
    assert out["건축법/제42조"]["source_url"] == "u", "새 응답에 없는 옛 필드를 잃었다"


def test_merge_keeps_empty_effective_date_because_it_is_a_fact():
    """`ef_yd: ""` 는 「이 조문은 시행일 미보유」라는 **사실**이다 — 빈 값이라고 버리면
    다음 백필이 매번 대상으로 잡는다."""
    from services.arch_law_client import merge_law_texts
    out = merge_law_texts({"조례/제55조": {"content": "본문"}},
                          {"조례/제55조": {"ef_yd": "", "law_ef_yd": "20260713"}})
    assert out["조례/제55조"]["ef_yd"] == ""
    assert effective_label(out["조례/제55조"]) == "법규 시행 2026-07-13"


def test_merge_adds_articles_we_never_had():
    from services.arch_law_client import merge_law_texts
    out = merge_law_texts({}, {"건축법/제42조": {"content": "본문", "ef_yd": "20260227"}})
    assert "건축법/제42조" in out


@pytest.mark.parametrize("old,new", [(None, None), ({}, None), (None, {}), ("x", "y")])
def test_merge_garbage_is_safe(old, new):
    from services.arch_law_client import merge_law_texts
    assert isinstance(merge_law_texts(old, new), dict)


def test_law_ref_names_dedup_across_sites():
    from services.arch_law_client import law_ref_names
    sc = {"law_diagnosis": [
        {"site_id": "부지1", "law_refs": [{"name": "건축법/제42조"}, {"name": "조례/제55조"}]},
        {"site_id": "부지2", "law_refs": [{"name": "건축법/제42조"}, {"name": ""}, None]},
    ]}
    assert law_ref_names(sc) == ["건축법/제42조", "조례/제55조"]
    assert law_ref_names(None) == [] and law_ref_names({}) == []


def test_backfill_target_detection_is_idempotent():
    """이미 시행일 키가 다 있으면 네트워크를 안 탄다."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "backfill_law_ef",
        Path(__file__).resolve().parent.parent.parent / "tools" / "backfill_law_ef.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    names = ["건축법/제42조"]
    done = {"건축법/제42조": {"content": "본문", "ef_yd": "20260227", "law_ef_yd": "20260227"}}
    assert mod._needs_backfill(done, names) is False
    old = {"건축법/제42조": {"content": "본문"}}                 # 키 없음 = 백필 대상
    assert mod._needs_backfill(old, names) is True
    assert mod._needs_backfill({}, names) is True               # 원문조차 못 받았던 조문
