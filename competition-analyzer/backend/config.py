import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
SETTINGS_FILE = BASE_DIR / "app_settings.json"

DEFAULT_DB_PATH = str(Path.home() / "competition_db")

FACILITY_TYPES = {
    "public": "공공시설",
    "residential": "주거시설",
    "office": "업무시설",
    "transport": "교통시설",
    "commercial": "상업시설",
    "cultural": "문화·집회시설",
    "hospitality": "숙박·위락시설",
    "education": "교육·연구시설",
    "masterplan": "마스터플랜",
    "industrial": "산업시설",
    "medical": "의료시설",
    "mixed_use": "복합시설",
}

PAGE_TYPES = [
    "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
    "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
    "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION",
    "HEALTH_CENTER", "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY",
]

COMPARISON_AXES = [
    "concept", "mass", "landscape", "program", "facade", "technical", "quantitative"
]

MODEL_ID = "claude-sonnet-4-6"

RASTER_DPI_CLASSIFY = 72
RASTER_DPI_EXTRACT = 150


class AppSettings:
    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f)
        return {
            "db_path": DEFAULT_DB_PATH,
            "anthropic_api_key": "",
            "raster_dpi_classify": RASTER_DPI_CLASSIFY,
            "raster_dpi_extract": RASTER_DPI_EXTRACT,
            "model_id": MODEL_ID,
        }

    def save(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @property
    def db_path(self) -> Path:
        return Path(self._data["db_path"])

    @property
    def api_key(self) -> str:
        return self._data.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def model_id(self) -> str:
        return self._data.get("model_id", MODEL_ID)

    @property
    def dpi_classify(self) -> int:
        return int(self._data.get("raster_dpi_classify", RASTER_DPI_CLASSIFY))

    @property
    def dpi_extract(self) -> int:
        return int(self._data.get("raster_dpi_extract", RASTER_DPI_EXTRACT))

    def to_dict(self) -> dict:
        return {**self._data, "anthropic_api_key": "***" if self._data.get("anthropic_api_key") else ""}

    def update(self, data: dict):
        self._data.update(data)
        self.save()


settings = AppSettings()
