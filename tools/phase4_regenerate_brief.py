"""Phase 4 — 영등포 brief JSON 으로 xlsx/md 재생성 후 직무공간 섹션 검증.

기존 _brief.json (정규화 안 된 옛 데이터) → exporter 의 lazy fallback 으로
정규화 후 렌더. 출력 파일을 d:/temp 에 생성하고 직무공간 섹션 dump 출력.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows cp949 콘솔에서도 한글·이모지 출력
sys.stdout.reconfigure(encoding="utf-8")

# 경로 우회: backend/ 를 sys.path 에 직접 추가 (백엔드 패키지 import 위해)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.brief_checklist_exporter import to_markdown, to_xlsx  # noqa: E402


def main():
    brief_path = Path(r"C:\Users\20260102\Downloads\_brief.json")
    if not brief_path.exists():
        print(f"!! brief not found: {brief_path}")
        return 1
    data = json.loads(brief_path.read_text(encoding="utf-8"))
    val = data.get("validation") or {}

    md = to_markdown(data, val)
    xlsx_bytes = to_xlsx(data, val)

    out_dir = Path("d:/temp")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "phase4_regen.md"
    xlsx_path = out_dir / "phase4_regen.xlsx"
    md_path.write_text(md, encoding="utf-8")
    xlsx_path.write_bytes(xlsx_bytes)
    print(f"wrote: {md_path}  ({len(md):,} chars)")
    print(f"wrote: {xlsx_path}  ({len(xlsx_bytes):,} bytes)")

    # ── 직무공간 섹션만 골라서 출력해 비교 용이하게 ─────────────────────────
    lines = md.splitlines()
    print("\n" + "=" * 80)
    print("DUMP: '직무공간 (부서 사무실)' 관련 MD 라인")
    print("=" * 80)
    in_section = False
    captured = 0
    for i, ln in enumerate(lines):
        if "직무공간 (부서 사무실)" in ln:
            in_section = True
        if in_section:
            print(f"L{i+1}: {ln}")
            captured += 1
            if captured > 60:
                print("... (truncated)")
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
