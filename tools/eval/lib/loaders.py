"""
loaders.py — GT JSON 디렉터리 스캔 + predicted 캐시 로드
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterator


def scan_ground_truth(
    gt_dir: Path,
    facility_type: str | None = None,
) -> Iterator[tuple[str, str, dict]]:
    """
    gt_dir 하위 *_gt.json 재귀 스캔.
    yields: (competition_id, slug, gt_dict)

    디렉터리 구조: gt_dir/{facility_type}/{competition_id}/{slug}_gt.json
    facility_type 필터 지정 시 해당 유형만 반환.
    """
    for gt_file in sorted(gt_dir.rglob("*_gt.json")):
        if gt_file.name.startswith("TEMPLATE"):
            continue
        try:
            gt = json.loads(gt_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] GT 로드 실패: {gt_file} — {e}")
            continue

        ft = gt.get("meta", {}).get("facility_type", "")
        if facility_type and ft != facility_type:
            continue

        slug = gt_file.stem.removesuffix("_gt")
        comp_id = gt_file.parent.name
        yield comp_id, slug, gt


def load_predicted_cache(cache_dir: Path, competition_id: str, slug: str) -> dict | None:
    p = cache_dir / f"{competition_id}_{slug}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 캐시 로드 실패: {p} — {e}")
        return None


def save_predicted_cache(cache_dir: Path, competition_id: str, slug: str, data: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{competition_id}_{slug}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tolerance(tolerance_file: Path) -> dict:
    try:
        return json.loads(tolerance_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] tolerance.json 로드 실패: {e} — 기본값 사용")
        return {"numeric": {}, "categorical": {}}
