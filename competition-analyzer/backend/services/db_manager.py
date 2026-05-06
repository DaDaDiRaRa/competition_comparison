import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from config import settings, FACILITY_TYPES


def _atomic_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s가-힣-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text


def init_db():
    db = settings.db_path
    config_dir = db / "_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (db / "_patterns").mkdir(exist_ok=True)

    for ft in FACILITY_TYPES:
        (db / ft).mkdir(exist_ok=True)

    taxonomy_path = config_dir / "page_taxonomy.json"
    if not taxonomy_path.exists():
        _atomic_write(taxonomy_path, {
            "version": "1.0",
            "page_types": [
                "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
                "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
                "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION",
                "HEALTH_CENTER", "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY",
            ]
        })


def make_competition_id(year: int, name: str) -> str:
    return f"{year}_{_slugify(name)}"


def get_competition_dir(facility_type: str, competition_id: str) -> Path:
    return settings.db_path / facility_type / competition_id


def save_project_meta(
    competition_id: str,
    facility_type: str,
    competition_name: str,
    year: int,
    client: str,
    location: str,
) -> Path:
    comp_dir = get_competition_dir(facility_type, competition_id)
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "submissions").mkdir(exist_ok=True)

    meta = {
        "competition_id": competition_id,
        "competition_name": competition_name,
        "facility_type": facility_type,
        "year": year,
        "client": client,
        "location": location,
        "created_at": datetime.now().isoformat(),
        "submissions": [],
    }
    _atomic_write(comp_dir / "_meta.json", meta)
    return comp_dir


def load_project_meta(facility_type: str, competition_id: str) -> dict:
    path = get_competition_dir(facility_type, competition_id) / "_meta.json"
    return _read_json(path)


def save_brief(facility_type: str, competition_id: str, brief_data: dict):
    comp_dir = get_competition_dir(facility_type, competition_id)
    _atomic_write(comp_dir / "_brief.json", brief_data)


def load_brief(facility_type: str, competition_id: str) -> dict:
    path = get_competition_dir(facility_type, competition_id) / "_brief.json"
    return _read_json(path)


def save_submission(
    facility_type: str,
    competition_id: str,
    company: str,
    result: str,
    submission_data: dict,
) -> str:
    slug = _slugify(company)
    filename = f"{slug}_{result}.json"
    comp_dir = get_competition_dir(facility_type, competition_id)
    _atomic_write(comp_dir / "submissions" / filename, submission_data)

    meta = load_project_meta(facility_type, competition_id)
    entries = meta.get("submissions", [])
    existing = [e for e in entries if e.get("company") == company]
    if not existing:
        entries.append({"company": company, "result": result, "file": filename})
        meta["submissions"] = entries
        _atomic_write(comp_dir / "_meta.json", meta)

    return filename


def save_comparison(facility_type: str, competition_id: str, comparison: dict):
    comp_dir = get_competition_dir(facility_type, competition_id)
    _atomic_write(comp_dir / "_comparison.json", comparison)


def list_projects(facility_type: str | None = None) -> list[dict]:
    db = settings.db_path
    projects = []
    types = [facility_type] if facility_type else list(FACILITY_TYPES.keys())
    for ft in types:
        ft_dir = db / ft
        if not ft_dir.exists():
            continue
        for comp_dir in sorted(ft_dir.iterdir()):
            if comp_dir.is_dir():
                meta_path = comp_dir / "_meta.json"
                if meta_path.exists():
                    projects.append(_read_json(meta_path))
    return projects


def list_submissions(facility_type: str, competition_id: str) -> list[dict]:
    comp_dir = get_competition_dir(facility_type, competition_id)
    sub_dir = comp_dir / "submissions"
    result = []
    if sub_dir.exists():
        for f in sorted(sub_dir.glob("*.json")):
            data = _read_json(f)
            result.append(data)
    return result


def get_winning_submissions(facility_type: str) -> list[dict]:
    db = settings.db_path
    ft_dir = db / facility_type
    winners = []
    if not ft_dir.exists():
        return winners
    for comp_dir in ft_dir.iterdir():
        if not comp_dir.is_dir():
            continue
        sub_dir = comp_dir / "submissions"
        if not sub_dir.exists():
            continue
        for f in sub_dir.glob("*_win.json"):
            data = _read_json(f)
            if data:
                winners.append(data)
    return winners


def save_pattern(facility_type: str, pattern: dict):
    path = settings.db_path / "_patterns" / f"{facility_type}.json"
    _atomic_write(path, pattern)


def load_pattern(facility_type: str) -> dict:
    path = settings.db_path / "_patterns" / f"{facility_type}.json"
    return _read_json(path)


def all_patterns() -> dict:
    pattern_dir = settings.db_path / "_patterns"
    result = {}
    if pattern_dir.exists():
        for f in pattern_dir.glob("*.json"):
            result[f.stem] = _read_json(f)
    return result
