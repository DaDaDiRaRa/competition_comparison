import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
SETTINGS_FILE = BASE_DIR / "app_settings.json"

# DB 경로는 코드 상수로 고정. 변경하려면 이 값을 수정 후 새 버전 릴리즈.
HARDCODED_DB_PATH = r"M:\06_설계사업6본부\설계사업6본부 1소\01 개인폴더\16 김정현\KUNWON_COMPETITION_DB"

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
    "reconstruction": "재건축사업",
}

PAGE_TYPES = [
    "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
    "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
    "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION",
    "HEALTH_CENTER", "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY",
    "UNIT_PLAN", "INCENTIVE_TABLE", "BRANDING",
]

COMPARISON_AXES = [
    "concept", "mass", "landscape", "program", "facade", "technical", "quantitative"
]

MODEL_ID = "claude-sonnet-4-6"
MODEL_ID_CLASSIFY = "claude-haiku-4-5-20251001"  # 분류는 단순 작업 → Haiku로 비용/속도 최적화

RASTER_DPI_CLASSIFY = 72
RASTER_DPI_EXTRACT = 150


class AppSettings:
    """비민감 설정만 파일에 저장. API 키는 메모리에만 보관 (앱 종료 시 소멸)."""

    def __init__(self):
        self._data = self._load()
        self._memory_api_key: str = ""  # 세션 전용 — 디스크에 저장 안 함

    def _load(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                # 과거 버전과의 호환: 파일에 키가 남아있어도 무시
                data.pop("anthropic_api_key", None)
                data.pop("db_path", None)
                return data
            except Exception:
                pass
        return {
            "raster_dpi_classify": RASTER_DPI_CLASSIFY,
            "raster_dpi_extract": RASTER_DPI_EXTRACT,
            "model_id": MODEL_ID,
            "model_id_classify": MODEL_ID_CLASSIFY,
        }

    def save(self):
        # API 키와 DB 경로는 절대 저장하지 않음
        safe = {k: v for k, v in self._data.items()
                if k not in ("anthropic_api_key", "db_path")}
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2)

    @property
    def db_path(self) -> Path:
        return Path(HARDCODED_DB_PATH)

    @property
    def api_key(self) -> str:
        # 메모리 우선, 없으면 환경변수
        return self._memory_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def set_api_key(self, key: str):
        """세션 메모리에만 저장. 디스크에 쓰지 않음."""
        self._memory_api_key = (key or "").strip()

    def clear_api_key(self):
        self._memory_api_key = ""

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def model_id(self) -> str:
        return self._data.get("model_id", MODEL_ID)

    @property
    def model_id_classify(self) -> str:
        return self._data.get("model_id_classify", MODEL_ID_CLASSIFY)

    @property
    def dpi_classify(self) -> int:
        return int(self._data.get("raster_dpi_classify", RASTER_DPI_CLASSIFY))

    @property
    def dpi_extract(self) -> int:
        return int(self._data.get("raster_dpi_extract", RASTER_DPI_EXTRACT))

    @property
    def extraction_priority_limit(self) -> int:
        # 2 = priority<=2만 추출 (표지·렌더링 스킵). 3 = 모든 페이지 추출 (기존 동작).
        return int(self._data.get("extraction_priority_limit", 2))

    def to_dict(self) -> dict:
        # API 키 자체는 절대 노출하지 않고, 설정 여부만 표시
        return {
            **{k: v for k, v in self._data.items() if k != "anthropic_api_key"},
            "db_path": str(self.db_path),
            "has_api_key": self.has_api_key(),
        }

    def update(self, data: dict):
        # db_path와 anthropic_api_key는 update로 변경 불가 (각각 하드코딩 / 전용 엔드포인트 사용)
        clean = {k: v for k, v in data.items()
                 if k not in ("db_path", "anthropic_api_key") and v is not None}
        self._data.update(clean)
        self.save()


settings = AppSettings()
