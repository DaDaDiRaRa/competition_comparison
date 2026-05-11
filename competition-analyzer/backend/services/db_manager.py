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
            "version": "1.1",
            "page_types": [
                "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
                "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
                "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION",
                "HEALTH_CENTER", "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY",
                "UNIT_PLAN", "INCENTIVE_TABLE", "BRANDING",
            ]
        })


def make_competition_id(project_number: str, name: str) -> str:
    pn = _slugify(str(project_number))
    return f"{pn}_{_slugify(name)}"


def get_competition_dir(facility_type: str, competition_id: str) -> Path:
    return settings.db_path / facility_type / competition_id


def save_project_meta(
    competition_id: str,
    facility_type: str,
    competition_name: str,
    project_number: str,
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
        "project_number": project_number,
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


def update_submission(
    facility_type: str,
    competition_id: str,
    company: str,
    new_result: str,
    new_extracted_data: dict,
    meta_overrides: dict | None = None,
) -> dict:
    """
    편집된 submission을 저장한다.
    - result 변경 시 파일명 변경 (old 삭제 + new 생성)
    - _meta.json submissions[].result 동기화
    - meta_overrides(client, location)는 project meta에 반영
    반환: {"old_file": str, "new_file": str, "result_changed": bool}
    """
    slug = _slugify(company)
    comp_dir = get_competition_dir(facility_type, competition_id)
    sub_dir = comp_dir / "submissions"

    # 현재 파일 탐색
    old_file: Path | None = None
    old_result: str = new_result
    for f in sub_dir.glob("*.json"):
        data = _read_json(f)
        if data.get("company") == company:
            old_file = f
            old_result = data.get("result", new_result)
            break

    new_filename = f"{slug}_{new_result}.json"
    new_path = sub_dir / new_filename

    # 기존 데이터에 수정 내용을 덮어쓴 완성본 생성
    base = _read_json(old_file) if old_file else {}
    base["extracted_data"] = new_extracted_data
    base["result"] = new_result
    base["company"] = company
    base["_edited_at"] = datetime.now().isoformat()

    if meta_overrides:
        base["client"] = meta_overrides.get("client", base.get("client", ""))
        base["location"] = meta_overrides.get("location", base.get("location", ""))

    # 새 파일 저장
    _atomic_write(new_path, base)

    result_changed = old_result != new_result
    if old_file and old_file != new_path:
        old_file.unlink(missing_ok=True)
        # 연결된 리포트 HTML도 이름 변경
        old_report = old_file.with_name(old_file.stem + "_report.html")
        new_report = new_path.with_name(new_path.stem + "_report.html")
        if old_report.exists():
            old_report.rename(new_report)

    # _meta.json 동기화
    meta = load_project_meta(facility_type, competition_id)
    for entry in meta.get("submissions", []):
        if entry.get("company") == company:
            entry["result"] = new_result
            entry["file"] = new_filename
            break

    if meta_overrides:
        if "client" in meta_overrides:
            meta["client"] = meta_overrides["client"]
        if "location" in meta_overrides:
            meta["location"] = meta_overrides["location"]

    _atomic_write(comp_dir / "_meta.json", meta)

    return {
        "old_file": old_file.name if old_file else None,
        "new_file": new_filename,
        "result_changed": result_changed,
        "submission": base,
    }


def has_comparison(facility_type: str, competition_id: str) -> bool:
    return (get_competition_dir(facility_type, competition_id) / "_comparison.json").exists()


def save_comparison(facility_type: str, competition_id: str, comparison: dict):
    comp_dir = get_competition_dir(facility_type, competition_id)
    _atomic_write(comp_dir / "_comparison.json", comparison)


def load_comparison(facility_type: str, competition_id: str) -> dict:
    comp_path = get_competition_dir(facility_type, competition_id) / "_comparison.json"
    if comp_path.exists():
        return _read_json(comp_path)
    return {}


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


def load_submission(facility_type: str, competition_id: str, company: str) -> dict:
    sub_dir = get_competition_dir(facility_type, competition_id) / "submissions"
    if sub_dir.exists():
        for f in sub_dir.glob("*.json"):
            data = _read_json(f)
            if data.get("company") == company:
                return data
    return {}


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
        for pattern in ("*_win.json", "*_contracted.json"):
            for f in sub_dir.glob(pattern):
                data = _read_json(f)
                if data:
                    winners.append(data)
    return winners


def get_losing_submissions(facility_type: str) -> list[dict]:
    db = settings.db_path
    ft_dir = db / facility_type
    losers = []
    if not ft_dir.exists():
        return losers
    for comp_dir in ft_dir.iterdir():
        if not comp_dir.is_dir():
            continue
        sub_dir = comp_dir / "submissions"
        if not sub_dir.exists():
            continue
        for f in sub_dir.glob("*_lose.json"):
            data = _read_json(f)
            if data:
                losers.append(data)
    return losers


def save_report(facility_type: str, competition_id: str, html: str):
    comp_dir = get_competition_dir(facility_type, competition_id)
    path = comp_dir / "_report.html"
    path.write_text(html, encoding="utf-8")


def get_report_path(facility_type: str, competition_id: str) -> Path:
    return get_competition_dir(facility_type, competition_id) / "_report.html"


def save_submission_report(facility_type: str, competition_id: str, company: str, html: str) -> bool:
    sub_dir = get_competition_dir(facility_type, competition_id) / "submissions"
    if not sub_dir.exists():
        return False
    for f in sub_dir.glob("*.json"):
        data = _read_json(f)
        if data.get("company") == company:
            report_path = f.with_name(f.stem + "_report.html")
            report_path.write_text(html, encoding="utf-8")
            _mark_sub_report(facility_type, competition_id, company)
            return True
    return False


def _mark_sub_report(facility_type: str, competition_id: str, company: str):
    comp_dir = get_competition_dir(facility_type, competition_id)
    meta = _read_json(comp_dir / "_meta.json")
    for entry in meta.get("submissions", []):
        if entry.get("company") == company:
            entry["has_sub_report"] = True
            break
    _atomic_write(comp_dir / "_meta.json", meta)


def get_submission_report_path(facility_type: str, competition_id: str, company: str) -> Path | None:
    sub_dir = get_competition_dir(facility_type, competition_id) / "submissions"
    if not sub_dir.exists():
        return None
    for f in sub_dir.glob("*.json"):
        data = _read_json(f)
        if data.get("company") == company:
            report_path = f.with_name(f.stem + "_report.html")
            return report_path
    return None


def save_cross_compare_report(filename: str, html: str) -> Path:
    cross_dir = settings.db_path / "_cross_reports"
    cross_dir.mkdir(parents=True, exist_ok=True)
    path = cross_dir / filename
    path.write_text(html, encoding="utf-8")
    return path


def get_cross_compare_report_path(filename: str) -> Path | None:
    path = settings.db_path / "_cross_reports" / filename
    return path if path.exists() else None


def list_cross_compare_reports() -> list[dict]:
    """저장된 교차비교 리포트 목록 (최신순)."""
    cross_dir = settings.db_path / "_cross_reports"
    if not cross_dir.exists():
        return []
    items = []
    for f in cross_dir.glob("*.html"):
        stem = f.stem  # 20260508_190203_proj_a_vs_proj_b
        # 파일명 = {YYYYMMDD}_{HHMMSS}_{label_segments}
        parts = stem.split("_", 2)
        if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 6:
            date_str, time_str, labels_part = parts
            ts = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            labels = labels_part.split("_vs_")
        else:
            ts = ""
            labels = [stem]
        items.append({
            "filename": f.name,
            "created_at": ts,
            "labels": labels,
            "size": f.stat().st_size,
        })
    return sorted(items, key=lambda x: x["filename"], reverse=True)


def save_diagnosis_report(filename: str, html: str) -> Path:
    diag_dir = settings.db_path / "_diagnosis_reports"
    diag_dir.mkdir(parents=True, exist_ok=True)
    path = diag_dir / filename
    path.write_text(html, encoding="utf-8")
    return path


def get_diagnosis_report_path(filename: str) -> Path | None:
    path = settings.db_path / "_diagnosis_reports" / filename
    return path if path.exists() else None


def list_diagnosis_reports() -> list[dict]:
    diag_dir = settings.db_path / "_diagnosis_reports"
    if not diag_dir.exists():
        return []
    items = []
    for f in diag_dir.glob("*.html"):
        stem = f.stem  # 20260511_103045_public_영등포구청사
        parts = stem.split("_", 3)
        if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 6:
            date_str, time_str = parts[0], parts[1]
            label = "_".join(parts[2:]) if len(parts) > 2 else stem
            ts = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
        else:
            ts = ""
            label = stem
        items.append({
            "filename": f.name,
            "created_at": ts,
            "label": label,
            "size": f.stat().st_size,
        })
    return sorted(items, key=lambda x: x["filename"], reverse=True)


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
