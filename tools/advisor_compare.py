"""
advisor_compare.py — AI 종합 해설(brief_advisor) 모델 A/B 비교 (추출 고정, 해설만 재생성)

같은 `_brief.json`(= 추출 결과 고정)으로 interpret_brief 를 두 모델로 각각 1콜씩
돌려 두 해설을 나란히 비교한다. "Opus 가 양이 적다"가 *군더더기를 줄인 것*인지
*핵심을 빠뜨린 것*인지를 항목 단위 diff 로 가린다.

핵심 출력:
  1. 필드별 분량 표 (요약 글자수 / 각 리스트 항목 수 / 총 글자수)
  2. 빠진 항목 diff — 한 모델엔 있고 다른 모델엔 없는 강조주제·필수항목·숨은제약
     (정규화 부분일치로 매칭 → 표현만 다른 동일 항목은 같은 것으로 봄)
  3. 한 줄 판정 휴리스틱: B가 A의 주제를 다 덮으면 "패딩만 축소", 아니면 "X 누락"

LLM 콜: 모델당 1콜 (총 2콜). 추출 재처리 0. 캐싱 없음(서로 다른 모델이라 무의미).
파일 수정/생성 없음 — stdout 리포트만. (--save-md 주면 비교 md 1개만 기록)

usage:
    set ANTHROPIC_API_KEY=sk-ant-...   (또는 PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-...")
    backend\\venv\\Scripts\\python.exe tools\\advisor_compare.py <_brief.json 경로> [--a MODEL] [--b MODEL]
    # 기본: --a claude-sonnet-4-6  --b claude-opus-4-8
    # 브리프 경로 대신 --db-path + --brief-id 도 가능
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config import settings  # noqa: E402
from services.brief_advisor import interpret_brief  # noqa: E402

# 비교할 리스트형 필드 + 각 항목의 "정체성" 텍스트를 뽑는 키 우선순위
_LIST_FIELDS = {
    "key_emphases":       ("topic",),
    "must_not_miss":      ("item",),
    "hidden_constraints": ("issue",),
    "reading_guide":      (None,),   # 항목이 문자열
    "caveats":            (None,),   # 항목이 문자열
}


def _norm(s: str) -> str:
    """매칭용 정규화: 공백/문장부호 제거 + 소문자. 표현 차이 흡수."""
    return re.sub(r"[\s·,.\-()\[\]'\"]+", "", str(s)).lower()


_TOK_SPLIT = re.compile(r"[\s·,./()\[\]'\"~:;|]+")


def _tokens(s: str) -> list:
    """len>=2 토큰 목록. 한국어 조사/어미는 부분일치로 흡수하므로 stemming 불필요."""
    return [t.lower() for t in _TOK_SPLIT.split(str(s)) if len(t) >= 2]


def _similar(x: str, y: str) -> bool:
    """두 항목이 사실상 같은 주제인가 (표현·어순·추가설명 차이 흡수).

    ① 정규화 후 한쪽이 다른 쪽을 포함하면 동일.
    ② 짧은 쪽 토큰의 50%+ 가 다른 쪽에 부분일치(포함)로 매칭되면 동일.
       (예: '심의로'⊂'심의 결정', '결정되는'⊃'결정' → 어미 차이 흡수)
    """
    nx, ny = _norm(x), _norm(y)
    if nx and ny and (nx in ny or ny in nx):
        return True
    tx, ty = _tokens(x), _tokens(y)
    if not tx or not ty:
        return False
    short, long = (tx, ty) if len(tx) <= len(ty) else (ty, tx)
    matched = sum(1 for t in short if any(t in u or u in t for u in long))
    return matched / len(short) >= 0.5


def _item_key(item, keys) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for k in keys:
            if k and (item.get(k) or "").strip():
                return str(item[k]).strip()
        return json.dumps(item, ensure_ascii=False)[:80]
    return str(item)


def _insight_chars(ins: dict) -> int:
    """해설 전체를 JSON 직렬화한 글자수(분량 프록시). scoring_focus 는 결정론이라 제외."""
    clone = {k: v for k, v in (ins or {}).items()
             if k not in ("scoring_focus", "schema_version", "model_id",
                          "facility_type", "generated_at")}
    return len(json.dumps(clone, ensure_ascii=False))


def _counts(ins: dict) -> dict:
    ins = ins or {}
    out = {
        "synthesis_chars": len((ins.get("synthesis_summary") or "").strip()),
        "total_chars": _insight_chars(ins),
        "data_confidence": ins.get("data_confidence"),
    }
    for f in _LIST_FIELDS:
        v = ins.get(f) or []
        out[f] = len(v) if isinstance(v, list) else 0
    return out


def _list_keys(ins: dict, field: str) -> list:
    keys = _LIST_FIELDS[field]
    items = (ins or {}).get(field) or []
    if not isinstance(items, list):
        return []
    return [_item_key(it, keys) for it in items if _item_key(it, keys).strip()]


def _diff(a_keys: list, b_keys: list) -> tuple:
    """a 에만 있는 / b 에만 있는 항목. 표현·어순·추가설명 차이는 _similar 로 흡수."""
    only_a = [x for x in a_keys if not any(_similar(x, y) for y in b_keys)]
    only_b = [y for y in b_keys if not any(_similar(y, x) for x in a_keys)]
    return only_a, only_b


async def _run_one(brief_data: dict, facility_type: str, model_id: str) -> dict:
    settings._data["model_id_advisor"] = model_id  # interpret_brief 가 이 값을 읽음
    try:
        return await interpret_brief(brief_data, facility_type)
    except Exception as e:  # noqa: BLE001
        print(f"  [!] {model_id} 해설 생성 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return {}


def _resolve_brief_path(args) -> Path:
    if args.brief_path:
        return Path(args.brief_path)
    db = Path(args.db_path) if args.db_path else settings.db_path
    return db / "_briefs" / f"{args.brief_id}.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 종합 해설 모델 A/B 비교 (추출 고정)")
    ap.add_argument("brief_path", nargs="?", help="_brief.json 경로")
    ap.add_argument("--db-path", help="brief_path 대신 DB 경로 + --brief-id")
    ap.add_argument("--brief-id", help="_briefs/{id}.json")
    ap.add_argument("--a", default="claude-sonnet-4-6", help="모델 A (기본 Sonnet)")
    ap.add_argument("--b", default="claude-opus-4-8", help="모델 B (기본 Opus)")
    ap.add_argument("--save-md", help="비교 결과를 이 경로에 md 로 저장")
    args = ap.parse_args()

    if not settings.has_api_key():
        print("[X] API 키 없음. ANTHROPIC_API_KEY 환경변수를 설정하세요.", file=sys.stderr)
        return 2

    path = _resolve_brief_path(args)
    if not path.exists():
        print(f"[X] 브리프 파일 없음: {path}", file=sys.stderr)
        return 2

    brief_data = json.loads(path.read_text(encoding="utf-8"))
    facility_type = (brief_data.get("_brief_meta") or {}).get("facility_type", "")
    title = ((brief_data.get("brief_project_info") or {}) if isinstance(
        brief_data.get("brief_project_info"), dict) else {}).get("competition_name", "") \
        or (brief_data.get("_brief_meta") or {}).get("brief_name", path.stem)

    print(f"\n=== 해설 A/B 비교 ===")
    print(f"브리프 : {title}")
    print(f"파일   : {path.name}  (시설유형: {facility_type or '미상'})")
    print(f"A      : {args.a}")
    print(f"B      : {args.b}")
    print("추출 고정 · 해설만 각 1콜 (총 2콜)\n")

    ins_a, ins_b = asyncio.run(_both(brief_data, facility_type, args.a, args.b))

    ca, cb = _counts(ins_a), _counts(ins_b)

    # ── 1. 분량 표 ──────────────────────────────────────────────────────────
    rows = [
        ("종합요약 글자수", ca["synthesis_chars"], cb["synthesis_chars"]),
        ("강조하는 것 (개)", ca["key_emphases"], cb["key_emphases"]),
        ("놓치면안되는것 (개)", ca["must_not_miss"], cb["must_not_miss"]),
        ("숨은제약 (개)", ca["hidden_constraints"], cb["hidden_constraints"]),
        ("읽는법 (개)", ca["reading_guide"], cb["reading_guide"]),
        ("한계 (개)", ca["caveats"], cb["caveats"]),
        ("총 글자수", ca["total_chars"], cb["total_chars"]),
    ]
    print("── 분량 ─────────────────────────────────────────────")
    print(f"{'항목':<22}{'A':>10}{'B':>10}{'B-A':>8}")
    for name, av, bv in rows:
        try:
            delta = f"{bv - av:+d}"
        except TypeError:
            delta = "-"
        print(f"{name:<22}{str(av):>10}{str(bv):>10}{delta:>8}")
    print(f"data_confidence        A={ca['data_confidence']}  B={cb['data_confidence']}")

    # ── 2. 빠진 항목 diff ───────────────────────────────────────────────────
    print("\n── 빠진 항목 (표현차이는 동일 취급) ─────────────────")
    dropped_by_b = 0
    for field in ("key_emphases", "must_not_miss", "hidden_constraints"):
        only_a, only_b = _diff(_list_keys(ins_a, field), _list_keys(ins_b, field))
        dropped_by_b += len(only_a)
        label = {"key_emphases": "강조주제", "must_not_miss": "필수항목",
                 "hidden_constraints": "숨은제약"}[field]
        print(f"\n[{label}]")
        if only_a:
            print(f"  A에만 있음 (B가 누락): {len(only_a)}")
            for x in only_a:
                print(f"    - {x}")
        if only_b:
            print(f"  B에만 있음 (B가 추가): {len(only_b)}")
            for x in only_b:
                print(f"    + {x}")
        if not only_a and not only_b:
            print("  (동일 — 양쪽 같은 주제 커버)")

    # ── 3. 판정 ─────────────────────────────────────────────────────────────
    print("\n── 판정 ─────────────────────────────────────────────")
    shorter = cb["total_chars"] < ca["total_chars"]
    if dropped_by_b == 0:
        verdict = ("B가 더 짧지만(또는 같지만) A의 핵심 주제를 모두 덮음 → "
                   "**패딩만 축소, 내용 손실 없음**") if shorter else \
            "B가 A를 모두 덮고 분량도 같거나 많음"
    else:
        verdict = (f"B가 A에 있는 항목 {dropped_by_b}건을 누락 → "
                   "위 'A에만 있음' 목록이 실제로 중요한지 사람이 판단 필요")
    print(verdict)
    print("\n주의: scoring_focus(배점·랭킹)는 결정론이라 모델 무관·비교 제외. "
          "본문(면적표·요구사항)은 추출 결과라 이 비교와 무관(고정).")

    if args.save_md:
        _save_md(Path(args.save_md), title, args, ca, cb, rows, ins_a, ins_b, verdict)
        print(f"\n비교 md 저장: {args.save_md}")
    return 0


async def _both(brief_data, facility_type, a, b):
    ia = await _run_one(brief_data, facility_type, a)
    ib = await _run_one(brief_data, facility_type, b)
    return ia, ib


def _save_md(out: Path, title, args, ca, cb, rows, ins_a, ins_b, verdict):
    L = [f"# 해설 A/B 비교 — {title}", "",
         f"- A: `{args.a}`", f"- B: `{args.b}`", "",
         "## 분량", "", "| 항목 | A | B |", "|---|---|---|"]
    for name, av, bv in rows:
        L.append(f"| {name} | {av} | {bv} |")
    L += ["", "## 판정", "", verdict, "",
          "## A 해설(JSON)", "```json",
          json.dumps(ins_a, ensure_ascii=False, indent=2), "```",
          "## B 해설(JSON)", "```json",
          json.dumps(ins_b, ensure_ascii=False, indent=2), "```"]
    out.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
