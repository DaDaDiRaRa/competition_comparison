"""Phase 0 — design_guidelines_grouped 계층 문제 정량화.

영향 범위를 측정해서 정규화 규칙 (R3 다중 depth 처리 등) 을 결정한다.
출력: 페이지·entry 통계 + 잠재 문제 케이스 샘플.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def audit_brief(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped = data.get("design_guidelines_grouped") or []

    depth_counter: Counter[int] = Counter()
    path_counter: Counter[tuple[str, str, str]] = Counter()
    by_scope_first_seg: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    text_in_group: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for entry in grouped:
        sp = (entry.get("section_path") or "").strip()
        fs = entry.get("facility_scope") or ""
        ss = entry.get("space_scope") or ""

        # depth = number of '>' separators + 1 (0 if blank)
        if not sp:
            depth = 0
        else:
            depth = len([s for s in sp.split(">") if s.strip()])
        depth_counter[depth] += 1

        key = (fs, ss, sp)
        path_counter[key] += 1

        # group by first segment for sub-parent inference
        first_seg = sp.split(">")[0].strip() if sp else ""
        scope_key = (fs, ss, first_seg)
        by_scope_first_seg[scope_key].append(sp)
        for it in entry.get("items") or []:
            txt = (it.get("text") or "").strip()
            if txt:
                text_in_group[scope_key].append(txt)

    # R1: exact duplicate section_path within same (fs, ss)
    dup_paths = [k for k, n in path_counter.items() if n >= 2]

    # R2: parent-child where child path starts with parent + " > "
    parent_child_pairs = []
    all_paths_by_scope: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (fs, ss, sp) in path_counter:
        all_paths_by_scope[(fs, ss)].add(sp)
    for (fs, ss), paths in all_paths_by_scope.items():
        for sp in paths:
            if " > " in sp:
                parent_candidate = sp.rsplit(" > ", 1)[0].strip()
                if parent_candidate in paths and parent_candidate:
                    parent_child_pairs.append((fs, ss, parent_candidate, sp))

    # R4: orphan - sp has " > " but parent (prefix before last ">") not present in same scope
    orphan_paths = []
    for (fs, ss, sp) in path_counter:
        if " > " in sp:
            parent_candidate = sp.rsplit(" > ", 1)[0].strip()
            if parent_candidate not in all_paths_by_scope[(fs, ss)]:
                orphan_paths.append((fs, ss, sp))

    # R5: identical item text within same scope+first_seg appearing more than once
    dup_items = []
    for scope_key, texts in text_in_group.items():
        c = Counter(texts)
        for t, n in c.items():
            if n >= 2:
                dup_items.append((scope_key, t[:80], n))

    return {
        "file": str(path),
        "total_entries": len(grouped),
        "depth_distribution": dict(depth_counter),
        "exact_dup_paths": len(dup_paths),
        "exact_dup_sample": dup_paths[:5],
        "parent_child_pairs": len(parent_child_pairs),
        "parent_child_sample": parent_child_pairs[:8],
        "orphan_paths": len(orphan_paths),
        "orphan_sample": orphan_paths[:8],
        "dup_item_text": len(dup_items),
        "dup_item_sample": dup_items[:5],
    }


def main():
    targets = [
        Path("C:/Users/20260102/Downloads/_brief.json"),
        Path("C:/Users/20260102/Desktop/_brief.json"),
        Path("D:/EVAL_DB/medical/24009C_가톨릭대학교_의정부병원_증축_및_리모델링_설계용역/_brief.json"),
        Path("D:/EVAL_DB/public/25035_영등포구_통합_신청사/_brief.json"),
        Path("D:/temp_brief.json"),
        Path("D:/temp_brief_0604.json"),
    ]
    results = []
    for p in targets:
        if not p.exists():
            continue
        try:
            results.append(audit_brief(p))
        except Exception as e:
            print(f"!! {p}: {e}", file=sys.stderr)

    for r in results:
        print("=" * 80)
        print(f"FILE: {r['file']}")
        print(f"  total entries:        {r['total_entries']}")
        print(f"  depth distribution:   {r['depth_distribution']}")
        print(f"  exact dup paths:      {r['exact_dup_paths']}")
        for s in r["exact_dup_sample"]:
            print(f"    - {s}")
        print(f"  parent-child pairs:   {r['parent_child_pairs']}")
        for fs, ss, par, ch in r["parent_child_sample"]:
            print(f"    - [{fs}/{ss}] {par}  <==  {ch}")
        print(f"  orphan paths:         {r['orphan_paths']}")
        for fs, ss, sp in r["orphan_sample"]:
            print(f"    - [{fs}/{ss}] {sp}")
        print(f"  dup item text count:  {r['dup_item_text']}")
        for scope_key, t, n in r["dup_item_sample"]:
            print(f"    - {scope_key} x{n}: {t}")
    print("=" * 80)
    print(f"Files analyzed: {len(results)}")


if __name__ == "__main__":
    main()
