import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

# PyInstaller로 패키징된 경우 번들 내부는 읽기 전용/임시 디렉터리이므로
# 사용자 홈에 영구 저장 위치를 둠. 개발 모드에선 backend/app_settings.json 그대로.
def _resolve_settings_file() -> Path:
    if getattr(sys, "frozen", False):
        user_dir = Path.home() / ".competition-analyzer"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / "app_settings.json"
    return BASE_DIR / "app_settings.json"

SETTINGS_FILE = _resolve_settings_file()

DEFAULT_DB_PATH = Path(
    os.environ.get("DB_PATH")
    or r"M:\06_설계사업6본부\설계사업6본부 1소\01 개인폴더\16 김정현\KUNWON_COMPETITION_DB"
)

FACILITY_TYPES = {
    "public":         {"label_ko": "공공시설",       "group": "general"},
    "residential":    {"label_ko": "주거시설",       "group": "general"},
    "office":         {"label_ko": "업무시설",       "group": "general"},
    "transport":      {"label_ko": "교통시설",       "group": "general"},
    "commercial":     {"label_ko": "상업시설",       "group": "general"},
    "cultural":       {"label_ko": "문화·집회시설",  "group": "general"},
    "hospitality":    {"label_ko": "숙박·위락시설",  "group": "general"},
    "education":      {"label_ko": "교육·연구시설",  "group": "general"},
    "masterplan":     {"label_ko": "마스터플랜",     "group": "general"},
    "industrial":     {"label_ko": "산업시설",       "group": "general"},
    "medical":        {"label_ko": "의료시설",       "group": "general"},
    "mixed_use":      {"label_ko": "복합시설",       "group": "general"},
    "reconstruction": {"label_ko": "재건축사업",     "group": "redev"},
    "alternative":    {"label_ko": "대안설계",       "group": "redev"},
}

def facility_label(facility_type: str) -> str:
    return FACILITY_TYPES.get(facility_type, {}).get("label_ko", facility_type)

FACILITY_GROUP = {k: v["group"] for k, v in FACILITY_TYPES.items()}

PAGE_TYPES = [
    "COVER", "TOC_HERO", "SITE_CONTEXT", "CONCEPT", "SPECIAL_SPACE",
    "RENDERING_EXT", "RENDERING_INT", "SITE_PLAN", "LANDSCAPE",
    "FLOOR_PLAN", "SECTION", "ELEVATION", "CIRCULATION",
    "HEALTH_CENTER", "TECHNICAL", "AREA_TABLE", "SUSTAINABILITY",
    "UNIT_PLAN", "INCENTIVE_TABLE", "BRANDING",
    "BUSINESS_VIABILITY", "AREA_INCREASE", "VIEW_ANALYSIS",
    "COMMUNITY_PROGRAM", "COMPANY_PORTFOLIO", "CONSTRUCTION_PLAN",
    "UNIT_PLAN_PENTHOUSE",
]

PAGE_TYPES_META = {
    "COVER":              "표지",
    "TOC_HERO":           "목차",
    "SITE_CONTEXT":       "위치도",
    "CONCEPT":            "컨셉",
    "SPECIAL_SPACE":      "핵심공간",
    "RENDERING_EXT":      "외부투시도",
    "RENDERING_INT":      "내부투시도",
    "SITE_PLAN":          "배치도",
    "LANDSCAPE":          "조경",
    "FLOOR_PLAN":         "평면도",
    "SECTION":            "단면도",
    "ELEVATION":          "입면도",
    "CIRCULATION":        "동선도",
    "HEALTH_CENTER":      "방재",
    "TECHNICAL":          "구조·설비",
    "AREA_TABLE":         "면적표",
    "SUSTAINABILITY":     "친환경",
    "UNIT_PLAN":          "단위세대",
    "INCENTIVE_TABLE":    "인센티브표",
    "BRANDING":           "브랜딩",
    "BUSINESS_VIABILITY": "사업성",
    "AREA_INCREASE":      "면적증가",
    "VIEW_ANALYSIS":      "조망분석",
    "COMMUNITY_PROGRAM":  "커뮤니티",
    "COMPANY_PORTFOLIO":  "회사실적",
    "CONSTRUCTION_PLAN":  "시공계획",
    "UNIT_PLAN_PENTHOUSE":"펜트하우스",
}

COMPARISON_AXES_BY_GROUP = {
    "redev": {
        "business_viability": {
            "label_ko":    "사업성",
            "label_dash":  "사업성·자산가치",
            "description": "조합원 자산가치 증가·분담금·일반분양 세대수·평당분양가·용적률 인센티브",
            "icon":        "₩",
        },
        "member_benefit": {
            "label_ko":    "조합원 혜택",
            "label_dash":  "조합원 혜택·실수요",
            "description": "남향배치율·조망권 확보율·실사용면적 증가율·조합원동 위치",
            "icon":        "⊙",
        },
        "product_competitiveness": {
            "label_ko":    "상품 경쟁력",
            "label_dash":  "상품 경쟁력·특화",
            "description": "평형 다양성·단위세대 차별화(3면개방·5BAY)·펜트하우스 특화·천장고",
            "icon":        "□",
        },
        "site_planning": {
            "label_ko":    "단지 계획",
            "label_dash":  "단지 계획·배치",
            "description": "배치 전략·보행차량분리·동간거리·데크 활용·랜드마크성",
            "icon":        "⊞",
        },
        "community": {
            "label_ko":    "커뮤니티",
            "label_dash":  "커뮤니티·프로그램",
            "description": "세대당 면적·프로그램 수·스카이 커뮤니티·차별화 시설",
            "icon":        "◎",
        },
        "design_brand": {
            "label_ko":    "디자인·브랜드",
            "label_dash":  "디자인·브랜드 아이덴티티",
            "description": "브랜드 아이덴티티·매스 독창성·외관 마감재·랜드마크 디자인",
            "icon":        "◧",
        },
        "constructability": {
            "label_ko":    "시공성",
            "label_dash":  "시공성·공사비",
            "description": "공기 단축·공사비 절감·지하주차 효율·공법 리스크",
            "icon":        "⚙",
        },
        "firm_capability": {
            "label_ko":    "회사 역량",
            "label_dash":  "회사 역량·실적",
            "description": "정비사업 실적·유사 프로젝트·재무안정성·디자인 어워드",
            "icon":        "⊕",
        },
    },
    "general": {
        "concept_clarity": {
            "label_ko":    "컨셉·아이덴티티",
            "label_dash":  "컨셉·아이덴티티",
            "description": "설계 컨셉의 명확성·독창성·일관성",
            "icon":        "◆",
        },
        "site_response": {
            "label_ko":    "대지 대응·맥락",
            "label_dash":  "대지 대응·맥락",
            "description": "대지 분석·주변 맥락 반응·배치 전략",
            "icon":        "⊞",
        },
        "program_planning": {
            "label_ko":    "프로그램·기능",
            "label_dash":  "프로그램·기능",
            "description": "기능 구성·동선 체계·공간 관계",
            "icon":        "□",
        },
        "architectural_form": {
            "label_ko":    "건축 형태·매스",
            "label_dash":  "건축 형태·매스",
            "description": "매스 구성·파사드 디자인·비례·조형성",
            "icon":        "◧",
        },
        "public_value": {
            "label_ko":    "공공성·이용자",
            "label_dash":  "공공성·이용자",
            "description": "공공공간·접근성·이용자 경험·지역 기여",
            "icon":        "◎",
        },
        "sustainability": {
            "label_ko":    "지속가능성",
            "label_dash":  "지속가능성",
            "description": "친환경 계획·에너지 효율·녹지·자연채광",
            "icon":        "✿",
        },
        "technical_feasibility": {
            "label_ko":    "기술·시공",
            "label_dash":  "기술·시공",
            "description": "구조 계획·설비·기술 혁신·시공성",
            "icon":        "⚙",
        },
        "brief_compliance_quant": {
            "label_ko":    "지침 충족·정량",
            "label_dash":  "지침 충족·정량",
            "description": "지침 요구사항 충족도·면적·층수 등 정량 기준",
            "icon":        "⊕",
        },
    },
}

def axes_for(facility_type: str) -> dict:
    group = FACILITY_TYPES.get(facility_type, {}).get("group", "general")
    return COMPARISON_AXES_BY_GROUP[group]

def axes_keys_for(facility_type: str) -> list:
    return list(axes_for(facility_type).keys())

# Legacy aliases — backward compat for existing imports
COMPARISON_AXES_META = COMPARISON_AXES_BY_GROUP["redev"]
COMPARISON_AXES = list(COMPARISON_AXES_META.keys())

MODEL_ID = "claude-sonnet-4-6"
MODEL_ID_CLASSIFY = "claude-haiku-4-5-20251001"  # 분류는 단순 작업 → Haiku로 비용/속도 최적화

RASTER_DPI_CLASSIFY = 72
RASTER_DPI_EXTRACT = 120  # 150→120 (이미지 토큰 36% 절감, 도면 OCR 품질 유지선)


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
                data.pop("anthropic_api_key", None)  # API 키는 절대 파일에서 읽지 않음
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
        # API 키만 저장 제외 (보안). db_path는 저장함.
        safe = {k: v for k, v in self._data.items() if k != "anthropic_api_key"}
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2)

    @property
    def db_path(self) -> Path:
        p = self._data.get("db_path")
        return Path(p) if p else DEFAULT_DB_PATH

    @property
    def has_db_path(self) -> bool:
        """사용자가 명시적으로 DB 경로를 설정했는지 여부."""
        return bool(self._data.get("db_path"))

    def set_db_path(self, path: str):
        self._data["db_path"] = str(path)
        self.save()

    @property
    def api_key(self) -> str:
        # 메모리 우선, 없으면 환경변수
        return self._memory_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def set_api_key(self, key: str):
        """세션 메모리에만 저장. 디스크에 쓰지 않음."""
        key = (key or "").strip()
        # 셸 복붙 아티팩트 제거: echo -n "sk-ant-..." → sk-ant-...
        if key.startswith("-n "):
            key = key[3:].strip()
        key = key.strip('"').strip("'")
        self._memory_api_key = key

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
        return {
            **{k: v for k, v in self._data.items() if k != "anthropic_api_key"},
            "db_path": str(self.db_path),
            "has_db_path": self.has_db_path,
            "has_api_key": self.has_api_key(),
        }

    def update(self, data: dict):
        # anthropic_api_key는 전용 엔드포인트로만 변경. db_path는 set_db_path() 사용.
        clean = {k: v for k, v in data.items()
                 if k not in ("db_path", "anthropic_api_key") and v is not None}
        self._data.update(clean)
        self.save()


settings = AppSettings()
