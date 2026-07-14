"""
backfill_feasibility.py — 기존 _brief.json 에 feasibility_export 재빌드/백필 (API 0, 결정론)

동기: feasibility_export 기능 도입 *전*에 분석된 옛 brief 는 이 블록이 없거나 주소가 비어
있다. 하지만 주소·envelope 는 이미 brief_project_info.sites / brief_site 에 추출돼 있어,
결정론 함수 build_feasibility_export 를 다시 돌리면 채워진다 (LLM 0, 추출 재처리 0).

이 툴은 각 brief 의 feasibility_export 를 재빌드하고, **주소 있는 부지 수가 늘어나는(또는
블록이 새로 생기는) brief 만** 갱신 대상으로 잡는다. 기본 dry-run(읽기 전용) — 무엇이 바뀔지
출력만. --apply 시에만 _atomic_write(GCSFUSE fsync)로 저장. 다른 키는 절대 건드리지 않음(추가만).

usage (PowerShell):
    $env:PYTHONUTF8 = "1"
    backend\\venv\\Scripts\\python.exe tools\\backfill_feasibility.py                 # dry-run, 기본 DB
    backend\\venv\\Scripts\\python.exe tools\\backfill_feasibility.py --dir <path>     # 지정 폴더
    backend\\venv\\Scripts\\python.exe tools\\backfill_feasibility.py --dir <path> --apply
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.db_manager import _atomic_write  # noqa: E402  (GCSFUSE fsync 저장)
from services.feasibility_export import build_feasibility_export  # noqa: E402


def _is_brief(d: dict) -> bool:
    """brief 산출물인지 (다른 JSON _meta/_comparison 등 제외)."""
    return isinstance(d, dict) and (
        "brief_project_info" in d or "brief_site" in d
        or (d.get("_brief_meta") or {}).get("facility_type")
    )


def _addr_count(fe: dict | None) -> int:
    return sum(1 for s in ((fe or {}).get("sites") or []) if s.get("address"))


def main() -> int:
    ap = argparse.ArgumentParser(description="feasibility_export 재빌드/백필 (결정론)")
    ap.add_argument("--dir", default=None,
                    help="brief JSON 폴더 (기본: settings.db_path). 재귀 glob.")
    ap.add_argument("--apply", action="store_true",
                    help="실제 저장(_atomic_write). 없으면 dry-run.")
    args = ap.parse_args()

    if args.dir:
        root = Path(args.dir)
    else:
        from config import settings
        root = Path(settings.db_path)
    if not root.exists():
        print(f"FATAL: 경로 없음 — {root}")
        return 1

    files = sorted(glob.glob(str(root / "**" / "*.json"), recursive=True))
    print(f"대상 폴더: {root}  (json {len(files)}개 스캔)")
    print(f"모드: {'APPLY (저장)' if args.apply else 'DRY-RUN (읽기 전용)'}")
    print("=" * 78)

    scanned = briefs = updated = skipped_err = 0
    for p in files:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not _is_brief(d):
            continue
        briefs += 1
        old_fe = d.get("feasibility_export")
        try:
            new_fe = build_feasibility_export(d)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 배치를 막지 않게
            skipped_err += 1
            print(f"[ERR ] {Path(p).name}  build 실패: {e}")
            continue
        scanned += 1

        old_n, new_n = _addr_count(old_fe), _addr_count(new_fe)
        # 갱신 조건: 주소 있는 부지 수 증가, 또는 블록이 없었는데 부지가 생김
        block_new = old_fe is None and (new_fe.get("sites"))
        if new_n > old_n or block_new:
            updated += 1
            addrs = " | ".join(f"{s.get('site_id')}={s.get('address')}"
                               for s in (new_fe.get("sites") or []) if s.get("address"))
            tag = "블록신규" if old_fe is None else f"주소 {old_n}→{new_n}"
            print(f"[{'UPD ' if args.apply else 'WILL'}] {Path(p).name}  ({tag})  {addrs}")
            if args.apply:
                d["feasibility_export"] = new_fe
                _atomic_write(Path(p), d)

    print("=" * 78)
    print(f"brief {briefs}개 | 재빌드 {scanned} | 갱신{'(저장)' if args.apply else '(예정)'} {updated} "
          f"| build오류 {skipped_err}")
    if not args.apply and updated:
        print("→ 실제 저장하려면 --apply 붙여 재실행.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
