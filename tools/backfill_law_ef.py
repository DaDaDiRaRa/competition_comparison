"""
backfill_law_ef.py — 기존 _brief.json 의 `law_texts` 에 **시행일**(ef_yd·law_ef_yd) 백필

동기: 법조문 시행일 표기(2026-08-27)는 arch-law-graph 가 2026-08-24 에 낸 F-1·F-4 필드를
쓴다. 우리가 그 전에 저장한 `_site_context.law_texts` 엔 그 키가 아예 없어서, 옛 브리프의
법적 골격은 「건폐 60% / 용적 460%」를 보여주면서 **언제 판본인지는 말하지 못한다**
(graceful 하게 배지가 안 붙을 뿐이라 눈에 안 띈다).

**진단을 다시 돌리지 않는다.** 필요한 건 graph `/api/lookup` 재호출뿐이다 —
LLM 0 · arch-law-diagnose 호출 0 · 부지당 수 초. `law_refs` 는 이미 저장돼 있다.

⚠ **지우지 않는다** — `merge_law_texts` 로 병합만 한다. `fetch_law_texts` 는 found+본문
있는 것만 돌려주므로, graph 가 그 사이 조문을 못 찾게 되거나 잠깐 죽으면 통째로 갈아끼울 때
이미 갖고 있던 원문이 사라진다.

**멱등**: 이미 시행일 키가 다 있는 brief 는 네트워크도 안 탄다(--force 로 강제).

usage (PowerShell):
    $env:PYTHONUTF8 = "1"
    backend\\venv\\Scripts\\python.exe tools\\backfill_law_ef.py                    # dry-run, 기본 DB
    backend\\venv\\Scripts\\python.exe tools\\backfill_law_ef.py --dir <path>        # 지정 폴더
    backend\\venv\\Scripts\\python.exe tools\\backfill_law_ef.py --dir <path> --apply

prod DB 는 GCS(`gs://kunwon-competition-db`)다 — gcsfuse 마운트 경로를 --dir 로 주거나,
`gcloud storage rsync` 로 `_briefs/` 를 내려받아 돌리고 다시 올린다.
GRAPH_API_URL 로 graph 주소 override 가능(기본=배포본).
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.arch_law_client import (  # noqa: E402
    effective_label,
    fetch_law_texts,
    graph_url,
    law_ref_names,
    merge_law_texts,
)
from services.db_manager import _atomic_write  # noqa: E402  (GCSFUSE fsync 저장)

_EF_KEYS = ("ef_yd", "law_ef_yd")


def _needs_backfill(law_texts: dict, names: list[str]) -> bool:
    """시행일 키가 하나라도 없거나, 아예 못 받아온 조문이 있으면 대상."""
    for nm in names:
        tx = (law_texts or {}).get(nm)
        if not isinstance(tx, dict):
            return True                      # 원문 자체를 못 받았던 조문
        if any(k not in tx for k in _EF_KEYS):
            return True
    return False


def _dated(law_texts: dict, names: list[str]) -> int:
    return sum(1 for nm in names if effective_label((law_texts or {}).get(nm)))


async def _run(root: Path, apply: bool, force: bool) -> int:
    files = sorted(glob.glob(str(root / "**" / "*.json"), recursive=True))
    print(f"대상 폴더: {root}  (json {len(files)}개 스캔)")
    print(f"graph    : {graph_url()}")
    print(f"모드     : {'APPLY (저장)' if apply else 'DRY-RUN (읽기 전용)'}")
    print("=" * 78)

    # 「0건」의 **원인**을 가른다 — 대상이 없는 것과 못 찾은 것은 다르다.
    # 대상 0 을 0 이라고만 말하면 백필이 필요 없는 건지 파이프라인이 안 돌았던 건지 모른다.
    all_briefs = no_sc = no_lawdiag = 0
    briefs = targeted = updated = errs = 0
    for p in files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or not (
                "brief_project_info" in d or "brief_site" in d
                or (d.get("_brief_meta") or {}).get("facility_type")):
            continue
        all_briefs += 1
        sc = d.get("_site_context")
        if not isinstance(sc, dict):
            no_sc += 1
            continue
        names = law_ref_names(sc)
        if not names:
            no_lawdiag += 1
            continue
        briefs += 1

        old_texts = sc.get("law_texts") if isinstance(sc.get("law_texts"), dict) else {}
        if not force and not _needs_backfill(old_texts, names):
            continue
        targeted += 1

        try:
            fresh = await fetch_law_texts(names)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 배치를 막지 않게
            errs += 1
            print(f"[ERR ] {Path(p).name}  lookup 실패: {e}")
            continue
        if not fresh:
            print(f"[SKIP] {Path(p).name}  graph 가 {len(names)}건 중 0건 반환 (미보유·일시장애)")
            continue

        merged = merge_law_texts(old_texts, fresh)
        before, after = _dated(old_texts, names), _dated(merged, names)
        if after <= before and not force:
            print(f"[SAME] {Path(p).name}  시행일 {before}/{len(names)} — 변화 없음")
            continue

        updated += 1
        sample = next((f"{nm} → {effective_label(merged.get(nm))}"
                       for nm in names if effective_label(merged.get(nm))), "")
        print(f"[{'UPD ' if apply else 'WILL'}] {Path(p).name}  "
              f"시행일 {before}→{after}/{len(names)}  {sample}")
        if apply:
            sc["law_texts"] = merged
            d["_site_context"] = sc
            _atomic_write(Path(p), d)

    print("=" * 78)
    print(f"brief {all_briefs}개 | 법조문 보유 {briefs} | 대상 {targeted} | "
          f"갱신{'(저장)' if apply else '(예정)'} {updated} | lookup오류 {errs}")
    if all_briefs and not briefs:
        # 백필할 게 없다 ≠ 백필이 필요 없다. 어느 쪽인지 말한다.
        print(f"  └ 대지 분석 없음(_site_context 자체가 없음) {no_sc}건 "
              f"· 대지는 있으나 법 진단 없음 {no_lawdiag}건")
        print("  ⚠ 백필할 시행일이 없는 게 아니라 **법 진단이 한 번도 안 돌았다**. "
              "이 도구가 아니라 `POST /brief/{id}/site-analyze` 가 먼저다 "
              "(부지당 65~110초 · vision·VWorld 과금).")
    if not apply and updated:
        print("→ 실제 저장하려면 --apply 붙여 재실행.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="law_texts 시행일 백필 (LLM 0 · 진단 재실행 0)")
    ap.add_argument("--dir", default=None, help="brief JSON 폴더 (기본: settings.db_path). 재귀 glob.")
    ap.add_argument("--apply", action="store_true", help="실제 저장(_atomic_write). 없으면 dry-run.")
    ap.add_argument("--force", action="store_true",
                    help="시행일이 이미 있어도 다시 조회 (graph 재빌드 후 갱신용).")
    args = ap.parse_args()

    if args.dir:
        root = Path(args.dir)
    else:
        from config import settings
        root = Path(settings.db_path)
    if not root.exists():
        print(f"FATAL: 경로 없음 — {root}")
        return 1
    return asyncio.run(_run(root, args.apply, args.force))


if __name__ == "__main__":
    sys.exit(main())
