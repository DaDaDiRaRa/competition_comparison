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

# ── 지침서(Brief) 전용 페이지 분류 ──────────────────────────────────────────
# 제안서(27개)와 별도 taxonomy. 지침서는 구조가 달라 억지 매핑 불필요.
# B-plan: 숫자 면적표가 있으면 BRIEF_PROGRAM 우선; 텍스트 지침만이면 BRIEF_DESIGN_GUIDE.
BRIEF_PAGE_TYPES = [
    "BRIEF_OVERVIEW",         # 공모개요 (목적·일정·조건 요약)
    "BRIEF_PROJECT_INFO",     # 사업 개요 (건축 규모 수치 표·사업비·기간)
    "BRIEF_SITE",             # 대상지 현황 (위치·현황도·지적도)
    "BRIEF_PROGRAM",          # 면적 프로그램 (실별 면적표·층별 용도·주차 수량)
    "BRIEF_DESIGN_MASSING",   # 배치·매싱·동선 지침
    "BRIEF_DESIGN_FACADE",    # 입면·재료·경관 지침
    "BRIEF_DESIGN_SUSTAIN",   # 친환경·에너지·인증 지침
    "BRIEF_DESIGN_SPECIAL",   # 특수·보안·안전 지침
    "BRIEF_DESIGN_GUIDE",     # 기타 설계 지침 (폴백)
    "BRIEF_TECHNICAL",        # 기술 기준 (구조·설비·법규 기술 사항)
    "BRIEF_REGULATIONS",      # 법규 기준 (용도지역·건폐율·용적률·높이제한 조문)
    "BRIEF_EVALUATION",       # 심사 기준 (배점표·평가 항목·심사위원)
    "BRIEF_SUBMISSION",       # 제출 기준 (도서 목록·파일 형식·제출 방법)
    "BRIEF_ADMIN",            # 행정 절차 (Q&A·일정·문의처 — 추출 불필요)
]

BRIEF_PAGE_TYPES_META = {
    "BRIEF_OVERVIEW":        "공모개요",
    "BRIEF_PROJECT_INFO":    "사업개요",
    "BRIEF_SITE":            "대상지현황",
    "BRIEF_PROGRAM":         "면적프로그램",
    "BRIEF_DESIGN_MASSING":  "배치·매싱지침",
    "BRIEF_DESIGN_FACADE":   "입면·재료지침",
    "BRIEF_DESIGN_SUSTAIN":  "친환경·인증",
    "BRIEF_DESIGN_SPECIAL":  "특수·보안지침",
    "BRIEF_DESIGN_GUIDE":    "기타설계지침",
    "BRIEF_TECHNICAL":       "기술기준",
    "BRIEF_REGULATIONS":     "법규기준",
    "BRIEF_EVALUATION":      "심사기준",
    "BRIEF_SUBMISSION":      "제출기준",
    "BRIEF_ADMIN":           "행정절차",
}

COMPARISON_AXES_BY_GROUP = {
    "redev": {
        "business_viability": {
            "label_ko":    "사업성",
            "label_dash":  "사업성·자산가치",
            "description": "조합원 자산가치 증가·분담금·일반분양 세대수·평당분양가·용적률 인센티브",
            "icon":        "₩",
            "signals": [
                "자산가치 증가액(억원) 또는 배수(×) 명시",
                "조합원 분담금 변화량(원) 또는 변화율(%)",
                "일반분양 세대수, 평당분양가",
                "용적률 base/incentive/final % 명시",
                "공사비 절감액, 공기 단축 개월수",
            ],
            "rubric": {
                "A": "자산가치 증가·분담금 변화·일반분양 세대수·평당분양가가 모두 정량으로 명시되고 경쟁안 대비 우위 근거 제시",
                "B": "주요 지표 4~5개 정량 명시, 일부 항목은 정성만",
                "C": "정량 지표 2~3개 + 일반적 사업 메시지 위주",
                "D": "정량 지표 1개 이하 또는 추정값·범위만 제시",
                "E": "사업성 지표 부재 또는 디자인 설명만"
            }
        },
        "member_benefit": {
            "label_ko":    "조합원 혜택",
            "label_dash":  "조합원 혜택·실수요",
            "description": "남향배치율·조망권 확보율·실사용면적 증가율·조합원동 위치",
            "icon":        "⊙",
            "signals": [
                "남향 배치율 %",
                "조망(한강/공원/산) 확보율 %",
                "실사용면적 증가율 % 또는 평형 증가폭",
                "조합원동의 위치(랜드마크/조망 우위) 명시",
            ],
            "rubric": {
                "A": "남향 80%+·조망 70%+·실사용면적 증가 명확. 조합원동 우월 배치 + 다이어그램 근거",
                "B": "주요 지표 3~4개 충족, 그래프·다이어그램으로 시각화",
                "C": "지표 1~2개 명시. 조합원동 배치는 평이",
                "D": "정량 지표 거의 없음. 일반론 위주",
                "E": "조합원 혜택 측면 미언급 또는 불리한 배치"
            }
        },
        "product_competitiveness": {
            "label_ko":    "상품 경쟁력",
            "label_dash":  "상품 경쟁력·특화",
            "description": "평형 다양성·단위세대 차별화(3면개방·5BAY)·펜트하우스 특화·천장고",
            "icon":        "□",
            "signals": [
                "평형 다양성(3~5종 이상)",
                "3면 개방·5BAY 등 차별화 요소",
                "천장고 2.6m+ 또는 펜트하우스 2.7m+",
                "펜트하우스 테라스 면적·infinity pool 등",
            ],
            "rubric": {
                "A": "5종+ 평형, 3면개방·5BAY·특화 발코니 명시, 펜트하우스 luxury 패키지 풀세트",
                "B": "3~4종 평형, 차별화 요소 2~3개. 펜트하우스는 기본 사양",
                "C": "평형 2~3종, 일반적 단위세대",
                "D": "단일 평형 위주, 차별화 부재",
                "E": "단위세대 정보 거의 없음"
            }
        },
        "site_planning": {
            "label_ko":    "단지 계획",
            "label_dash":  "단지 계획·배치",
            "description": "배치 전략·보행차량분리·동간거리·데크 활용·랜드마크성",
            "icon":        "⊞",
            "signals": [
                "보행/차량 동선 완전 분리 (단지 진입~동 진입)",
                "동간거리 18m+ 또는 법정 이상",
                "1·2층 데크화로 지하주차 통합",
                "랜드마크 동의 위치·높이 차별화",
            ],
            "rubric": {
                "A": "보차분리 완전·동간거리 충분·데크 활용·랜드마크 명시. 배치 다이어그램 3장+",
                "B": "주요 전략 3~4개 명확. 일부 다이어그램",
                "C": "기본 배치만, 전략 1~2개",
                "D": "배치도만 있고 전략 설명 부재",
                "E": "배치 부적절·동선 충돌"
            }
        },
        "community": {
            "label_ko":    "커뮤니티",
            "label_dash":  "커뮤니티·프로그램",
            "description": "세대당 면적·프로그램 수·스카이 커뮤니티·차별화 시설",
            "icon":        "◎",
            "signals": [
                "세대당 커뮤니티 면적(평/세대)",
                "총 프로그램 수 (10+ 풍부)",
                "스카이 라운지·인피니티풀·호텔식 컨시어지 등",
                "차별화된 시그니처 시설",
            ],
            "rubric": {
                "A": "세대당 1평+, 프로그램 15+, 스카이 커뮤니티·호텔식 시설 풀패키지",
                "B": "세대당 0.7평+, 프로그램 10+, 특화 시설 2~3개",
                "C": "법정 + α, 프로그램 5~7개",
                "D": "법정 수준만, 일반적 시설",
                "E": "커뮤니티 정보 부재 또는 미달"
            }
        },
        "design_brand": {
            "label_ko":    "디자인·브랜드",
            "label_dash":  "디자인·브랜드 아이덴티티",
            "description": "브랜드 아이덴티티·매스 독창성·외관 마감재·랜드마크 디자인",
            "icon":        "◧",
            "signals": [
                "브랜드 슬로건·아이덴티티 명확",
                "매스 컨셉 독창성 (스토리텔링)",
                "외관 마감재 grade (석재·금속·유리 조합)",
                "랜드마크 매스 (스카이라인 차별화)",
            ],
            "rubric": {
                "A": "브랜드 스토리 완성, 독창적 매스, 프리미엄 마감재, 랜드마크급 디자인",
                "B": "브랜드 명확, 매스 정돈, 마감재 좋음",
                "C": "기본 브랜드, 평이한 매스",
                "D": "브랜드 약함, 매스 일반적",
                "E": "디자인 아이덴티티 부재"
            }
        },
        "constructability": {
            "label_ko":    "시공성",
            "label_dash":  "시공성·공사비",
            "description": "공기 단축·공사비 절감·지하주차 효율·공법 리스크",
            "icon":        "⚙",
            "signals": [
                "공기 단축 개월수",
                "공사비 절감액 (억원)",
                "지하주차 굴착깊이·층수 최적화",
                "공법 리스크 분석 + 대안",
            ],
            "rubric": {
                "A": "공기 6개월+ 단축, 공사비 100억+ 절감, 지하 최적화, 리스크 대응안",
                "B": "공기 3~5개월 단축, 절감 50~100억",
                "C": "공기·비용 일부 개선",
                "D": "정량 효과 미명시",
                "E": "시공 리스크 큼 또는 미언급"
            }
        },
        "firm_capability": {
            "label_ko":    "회사 역량",
            "label_dash":  "회사 역량·실적",
            "description": "정비사업 실적·유사 프로젝트·재무안정성·디자인 어워드",
            "icon":        "⊕",
            "signals": [
                "정비사업 실적 5건+ (이름·연도·규모)",
                "유사 시설유형 프로젝트 풍부",
                "재무 안정성 (매출·신용등급)",
                "수상실적·해외 어워드",
            ],
            "rubric": {
                "A": "정비사업 10건+, 유사 프로젝트 다수, 신용 A+, 국내외 수상",
                "B": "정비사업 5~9건, 실적 명확, 안정 재무",
                "C": "정비사업 2~4건, 일반 실적",
                "D": "정비사업 1건 이하 또는 일반 건축 실적만",
                "E": "포트폴리오 부재"
            }
        },
    },
    "general": {
        "concept_clarity": {
            "label_ko":    "컨셉·아이덴티티",
            "label_dash":  "컨셉·아이덴티티",
            "description": "설계 컨셉의 명확성·독창성·일관성",
            "icon":        "◆",
            "signals": [
                "컨셉 키워드·메타포 명확 (한 문장 요약 가능)",
                "독창성 (전형적 키워드 회피)",
                "전 페이지 일관 적용 (배치→매스→파사드→공간)",
                "스토리텔링 구조 (다이어그램·텍스트 연결)",
            ],
            "rubric": {
                "A": "컨셉 한 단어/문장 명확, 독창적 메타포, 배치~파사드~공간 모두 일관 적용",
                "B": "컨셉 명확, 일반적이지만 적용 충실",
                "C": "컨셉 존재 (전형적: '소통의 공간' 등), 적용 평이",
                "D": "키워드 나열만, 디자인과 연결 약함",
                "E": "컨셉 부재 또는 슬로건 수준"
            }
        },
        "site_response": {
            "label_ko":    "대지 대응·맥락",
            "label_dash":  "대지 대응·맥락",
            "description": "대지 분석·주변 맥락 반응·배치 전략",
            "icon":        "⊞",
            "signals": [
                "대지 분석 (방위·소음·바람·맥락) 정량 또는 정성",
                "주변 건물/녹지/도로와의 관계 다이어그램",
                "배치 전략과 분석 결과의 명시적 정합",
                "보행/차량/공공동선 명확",
            ],
            "rubric": {
                "A": "대지 분석 구체적·정량, 배치 전략이 분석과 명시적으로 정합, 동선 분리 명확",
                "B": "대지 분석 충실, 배치 전략 명확, 일부 일반론",
                "C": "대지 분석은 있으나 배치 전략과 약하게 연결",
                "D": "대지 분석 또는 배치 전략 중 하나 부재",
                "E": "둘 다 부재 또는 컨셉과 불일치"
            }
        },
        "program_planning": {
            "label_ko":    "프로그램·기능",
            "label_dash":  "프로그램·기능",
            "description": "기능 구성·동선 체계·공간 관계",
            "icon":        "□",
            "signals": [
                "기능 zoning 명확 (공공/업무/지원 등)",
                "동선 체계 (이용자별·시간대별)",
                "핵심 공간(로비·메인홀·아트리움) 차별화",
                "유연성·확장성 고려",
            ],
            "rubric": {
                "A": "zoning·동선·핵심공간 모두 명확, 이용자별 시나리오 다이어그램, 유연성 명시",
                "B": "zoning·동선 명확, 핵심공간 잘 계획",
                "C": "기본 zoning, 동선 평이",
                "D": "기능 배분만, 동선 설명 부재",
                "E": "기능 충돌 또는 동선 미해결"
            }
        },
        "architectural_form": {
            "label_ko":    "건축 형태·매스",
            "label_dash":  "건축 형태·매스",
            "description": "매스 구성·파사드 디자인·비례·조형성",
            "icon":        "◧",
            "signals": [
                "매스 컨셉 (수평/수직/스택/하이브리드) 명확",
                "파사드 시스템 (커튼월·PC·석재·메탈) 일관",
                "비례·리듬 (입면 균형)",
                "랜드마크성 또는 주변 맥락 조응",
            ],
            "rubric": {
                "A": "매스 독창적·컨셉 일치, 파사드 디테일·재료 위계 명확, 랜드마크급",
                "B": "매스 정돈, 파사드 일관성 좋음",
                "C": "매스 평이, 파사드 표준",
                "D": "매스 일반적, 파사드 단조",
                "E": "조형성 부재 또는 컨셉 불일치"
            }
        },
        "public_value": {
            "label_ko":    "공공성·이용자",
            "label_dash":  "공공성·이용자",
            "description": "공공공간·접근성·이용자 경험·지역 기여",
            "icon":        "◎",
            "signals": [
                "공공공간(광장·필로티·옥상정원) 명확",
                "접근성 (BF·다국어·노약자 동선)",
                "이용자 경험 시나리오",
                "지역사회 연계 (오픈 프로그램·야간 활용)",
            ],
            "rubric": {
                "A": "공공공간 풍부, BF·다국어 완비, 시나리오 다이어그램, 지역 기여 프로그램",
                "B": "공공공간 명확, BF 충실, 일부 시나리오",
                "C": "법정 수준 공공공간·접근성",
                "D": "공공성 약함 또는 폐쇄적 배치",
                "E": "공공성 미고려"
            }
        },
        "sustainability": {
            "label_ko":    "지속가능성",
            "label_dash":  "지속가능성",
            "description": "친환경 계획·에너지 효율·녹지·자연채광",
            "icon":        "✿",
            "signals": [
                "녹색건축 인증 등급 (G-SEED 우수+, LEED Gold+)",
                "에너지 효율 등급 (1++ 이상)",
                "재생에너지 (태양광·지열) 정량",
                "녹지율 %, 자연채광·자연환기 전략",
            ],
            "rubric": {
                "A": "녹색건축 최우수+에너지 1++, 재생에너지 정량, 녹지율 30%+, 통합 전략",
                "B": "녹색건축 우수, 에너지 1+, 재생E 명시",
                "C": "법정 수준 친환경 + 일부 전략",
                "D": "친환경 키워드만, 정량 부재",
                "E": "지속가능성 미고려"
            }
        },
        "technical_feasibility": {
            "label_ko":    "기술·시공",
            "label_dash":  "기술·시공",
            "description": "구조 계획·설비·기술 혁신·시공성",
            "icon":        "⚙",
            "signals": [
                "구조 시스템 (PC·SRC·메가구조) 명확",
                "MEP 계획 (HVAC·소방·전기) 다이어그램",
                "스마트빌딩·BIM·모듈러 등 혁신",
                "시공 단계·공기 계획",
            ],
            "rubric": {
                "A": "구조·MEP·혁신기술·시공성 모두 다이어그램+설명, 공기·비용 정량",
                "B": "구조·MEP 명확, 일부 혁신 요소",
                "C": "구조 시스템 + 기본 MEP만",
                "D": "기술 내용 표면적",
                "E": "기술 검토 부재"
            }
        },
        "brief_compliance_quant": {
            "label_ko":    "지침 충족·정량",
            "label_dash":  "지침 충족·정량",
            "description": "지침 요구사항 충족도·면적·층수 등 정량 기준",
            "icon":        "⊕",
            "signals": [
                "지침 요구 면적·층수·주차 100% 충족",
                "용적률·건폐율 법정 이내",
                "필수 실 누락 없음 (지침 대조표)",
                "특수 요구사항 (BF·친환경 등급 등) 명시 충족",
            ],
            "rubric": {
                "A": "지침 100% 충족 + 대조표·근거 명시, 특수 요구사항 추가 만족",
                "B": "지침 모두 충족, 일부 항목 마진 적음",
                "C": "주요 항목 충족, 일부 항목 불명확",
                "D": "1~2개 요구 미달 또는 마진 부족",
                "E": "지침 미달 또는 정량 정보 부재"
            }
        },
    },
}

# ── 시설유형별 평가축 override ───────────────────────────────────────────────
# base axes의 signals/rubric에 facility-specific 보강을 더한다.
# 형식: FACILITY_AXIS_OVERRIDES[facility_type][axis_key] = {
#         "signals_extra": [...추가 신호],
#         "rubric_hint": "이 시설유형에서 특별히 보는 포인트 1~2문장"
#     }
# 없는 시설유형/축은 base를 그대로 사용. 점진적으로 채워나감.
FACILITY_AXIS_OVERRIDES: dict[str, dict[str, dict]] = {
    "medical": {
        "program_planning": {
            "signals_extra": [
                "응급/외래/입원/수술/검사 zoning 명확",
                "환자 동선과 의료진/물품 동선 완전 분리",
                "간호 스테이션 시야 확보(병동)",
                "감염 관리 zoning (격리병동·음압)",
            ],
            "rubric_hint": "의료시설은 zoning·교차감염 분리·간호 visibility가 핵심. 일반 zoning만으로는 B 이상 받기 어려움.",
        },
        "technical_feasibility": {
            "signals_extra": [
                "공조 분리 (감염·수술실 양압/음압)",
                "비상발전·UPS·의료가스 라인",
                "방사선 차폐(영상의학과)",
            ],
            "rubric_hint": "의료 MEP는 일반 사무용과 다름. 양압/음압·의료가스·차폐 명시되어야 A.",
        },
    },
    "residential": {
        "site_response": {
            "signals_extra": [
                "남향 배치율 % 명시",
                "동간거리 (법정 + α)",
                "조망 (한강·공원·산) 확보율",
                "소음원(도로·철도) 차단 전략",
            ],
            "rubric_hint": "주거시설은 남향·조망·소음이 곧 매수자 평가. 정량 없으면 C 이하.",
        },
        "program_planning": {
            "signals_extra": [
                "평형 다양성 (3종+ 권장)",
                "LDK 배치 (4BAY·판상/타워)",
                "공용 커뮤니티 면적(세대당)",
                "지하주차 세대당 대수",
            ],
            "rubric_hint": "주거 program은 평형/LDK/커뮤니티/주차의 4축. 하나라도 빠지면 B 이하.",
        },
    },
    "public": {
        "public_value": {
            "signals_extra": [
                "광장·로비의 시민 개방시간",
                "다국적·다세대 이용자 시나리오",
                "야간/주말 활용 프로그램",
                "지역 행사·축제 수용 가능성",
            ],
            "rubric_hint": "공공시설은 시민 개방성·다이용자 시나리오가 핵심. 운영 시간/프로그램 미명시면 B 이하.",
        },
        "brief_compliance_quant": {
            "signals_extra": [
                "BF 인증 등급 (장애물 없는 생활환경)",
                "장애인·고령자·다국적 대응 정량",
                "친환경 인증 등급 (G-SEED 우수+ 권장)",
            ],
            "rubric_hint": "공공시설은 BF·친환경 등급이 사실상 필수. 둘 다 명시 + 등급이면 A.",
        },
    },
    "education": {
        "program_planning": {
            "signals_extra": [
                "학습공간 유형 다양성 (강의실·세미나·실험·아틀리에)",
                "비공식 학습공간 (라운지·복도형)",
                "교사/학생/방문객 동선 분리",
                "스마트 캠퍼스·ICT 인프라",
            ],
            "rubric_hint": "교육시설은 학습공간 유형성과 비공식 공간이 핵심. 단순 강의실 배치면 C.",
        },
    },
    "transport": {
        "program_planning": {
            "signals_extra": [
                "환승 동선 시간·거리 정량",
                "보행·자전거·차량·대중교통 연결",
                "Wayfinding·다국어 사인 시스템",
                "혼잡시 cap·여유 폭 확보",
            ],
            "rubric_hint": "교통시설은 환승 효율 정량이 사실상 평가축. 시간 단축/거리 명시 없으면 B 이하.",
        },
    },
    "commercial": {
        "program_planning": {
            "signals_extra": [
                "앵커 매장·MD믹스 (층별 카테고리 구성)",
                "체류시간 유도 (F&B·문화·체험존)",
                "매장 가시성·정면 노출 (frontage)",
                "에스컬레이터·아트리움 중심 수직동선",
            ],
            "rubric_hint": "상업시설은 MD믹스·체류시간·가시성이 매출과 직결. 단순 zoning만으로는 C.",
        },
        "site_response": {
            "signals_extra": [
                "보행 유입 동선 (역세권·버스정류장 연결)",
                "주차 진입·차량 회전 반경",
                "외부 광장·캐노피·저층부 활성화",
                "배송·서비스 동선 분리",
            ],
            "rubric_hint": "상업시설은 보행 유입이 곧 집객. 차량/배송 동선 분리도 필수.",
        },
    },
    "cultural": {
        "public_value": {
            "signals_extra": [
                "공연·전시 운영 시나리오 (관객·출연자·VIP 분리)",
                "로비 가변성 (다목적 활용·이벤트)",
                "야간·비행사 시간대 오픈 프로그램",
                "장애인·다국적 관객 접근성",
            ],
            "rubric_hint": "문화시설은 운영 시나리오와 가변성이 핵심. 단순 박스형 공연장은 C 이하.",
        },
        "architectural_form": {
            "signals_extra": [
                "도시 표상·랜드마크성 (스카이라인 차별화)",
                "시그니처 매스 (지역 정체성·메타포)",
                "야간 조명 계획·표피 미디어",
                "주변 컨텍스트와 스케일 조응",
            ],
            "rubric_hint": "문화시설은 도시 아이콘 역할. 랜드마크 의도 없으면 B 이하.",
        },
        "program_planning": {
            "signals_extra": [
                "전시·공연·교육 zoning 명확",
                "백스테이지·리허설 동선 완전 분리",
                "수장고·하역 동선 (대형 작품 반입)",
                "교육·창작·체험 프로그램",
            ],
            "rubric_hint": "문화시설 program은 백스테이지·하역동선 누락이 흔한 감점 요인.",
        },
    },
    "hospitality": {
        "program_planning": {
            "signals_extra": [
                "객실 유형 다양성 (스탠다드·스위트·풀빌라)",
                "객실 뷰 분포 (오션·시티·가든)",
                "F&B·연회·스파 동선 분리",
                "투숙객·연회객·직원 동선 layered",
            ],
            "rubric_hint": "숙박시설은 객실 다양성·뷰·F&B 동선의 3박자. 동선 미분리는 운영 비용 증가로 직결.",
        },
        "site_response": {
            "signals_extra": [
                "주요 뷰 (오션·산·강) 객실 노출 %",
                "자연 활용 (수목·암반·물길)",
                "외부 소음 차단 (도로·시설)",
                "공항·관광지 접근성·픽업 동선",
            ],
            "rubric_hint": "숙박시설은 조망과 자연이 곧 가격대. 뷰 % 정량 없으면 C 이하.",
        },
    },
    "office": {
        "program_planning": {
            "signals_extra": [
                "기준층 평면 효율 (개방형·구획·혼합)",
                "코어 위치·개수 (center/side/distributed)",
                "전용률 % (NLA/GFA)",
                "공용시설 (라운지·카페·피트니스·옥상정원)",
            ],
            "rubric_hint": "업무시설은 전용률·코어 효율이 임대료 직결. 전용률 75%+ 명시되어야 A.",
        },
        "brief_compliance_quant": {
            "signals_extra": [
                "NLA(Net Leasable Area) 비율 명시",
                "기준층 층고 4.2m+ (스마트오피스 표준)",
                "구획 가변성 (1실/N실 분할)",
                "Tech 인프라 (광케이블·UPS·전력여유)",
            ],
            "rubric_hint": "업무시설 정량은 NLA·층고·tech 인프라. 셋 중 하나라도 미명시면 B 이하.",
        },
    },
    "industrial": {
        "technical_feasibility": {
            "signals_extra": [
                "층고·바닥 하중 (kg/m²) 정량",
                "전력·용수·압축공기 인프라",
                "생산동선과 일반·검사동선 분리",
                "확장성·라인 변경 대응 모듈러",
            ],
            "rubric_hint": "산업시설은 하중·전력·동선이 곧 생산성. 정량 미명시는 자동 C 이하.",
        },
        "program_planning": {
            "signals_extra": [
                "원료/생산/검사/포장/물류 zone 분리",
                "물류 동선 (트럭 회전·dock 수)",
                "클린룸·항온항습 영역 분리",
                "직원 후생 (식당·휴게·탈의)",
            ],
            "rubric_hint": "산업시설 zoning은 흐름 효율과 안전이 직결. 5개 zone 분리 명시되어야 A.",
        },
    },
    "mixed_use": {
        "program_planning": {
            "signals_extra": [
                "용도 간 간섭 차단 (소음·진동·동선)",
                "공용 share 동선 (코어·주차 공유)",
                "층별 zoning (저층 상업·중층 업무·상층 주거)",
                "각 용도 전용 entrance 분리",
            ],
            "rubric_hint": "복합시설은 간섭 차단과 동선 share의 균형이 핵심. 한쪽 미흡 시 B 이하.",
        },
        "site_response": {
            "signals_extra": [
                "저층부 활성화 (가로 활기·공공공간)",
                "각 용도별 진입 분리 + sub-entrance",
                "보행·차량·서비스 3종 동선 정리",
                "도시 스케일 매스 분절",
            ],
            "rubric_hint": "복합시설은 저층부가 도시와의 접점. 가로 활성화 전략 없으면 C 이하.",
        },
    },
    "masterplan": {
        "site_response": {
            "signals_extra": [
                "도시 스케일 맥락 (축선·green network·blue network)",
                "단지 내 동선 위계 (간선·집분배·블록)",
                "필지 분할·블록 사이즈 다양성",
                "기존 인프라 (지하철·도로) 활용",
            ],
            "rubric_hint": "마스터플랜은 도시 스케일 사고가 본질. 축선·네트워크 다이어그램 없으면 B 이하.",
        },
        "public_value": {
            "signals_extra": [
                "오픈스페이스 네트워크 (선형·면적 연결)",
                "단지 내 시민 동선 (보행·자전거)",
                "커뮤니티 hub 위치·접근성",
                "단계별 개발 계획",
            ],
            "rubric_hint": "마스터플랜의 공공성은 오픈스페이스 연속성과 단계별 개발 두 축.",
        },
        "concept_clarity": {
            "signals_extra": [
                "전체를 관통하는 single big idea",
                "단지·블록·필지 3단계 일관성",
                "이름·정체성 (place identity)",
                "주변 도시와의 통합 전략",
            ],
            "rubric_hint": "마스터플랜은 단일 컨셉이 단지~필지까지 일관 적용되어야 A.",
        },
    },
    "reconstruction": {
        "business_viability": {
            "signals_extra": [
                "자산가치 증가 배수 1.5×+ (정량 임계)",
                "분담금 감소율 % 또는 환급액 명시",
                "일반분양 세대수 비율 (조합원 대비)",
                "평당분양가 시장가 대비 우위",
            ],
            "rubric_hint": "재건축 사업성 정량 임계값: 자산가치 1.5×+ + 분담금 감소가 사실상 A의 기준선.",
        },
        "member_benefit": {
            "signals_extra": [
                "남향 배치율 80%+ (정량 임계)",
                "한강/공원 조망 확보율 60%+",
                "실사용면적 증가율 % 또는 평형 증가",
                "조합원동 우월 배치 (랜드마크·뷰)",
            ],
            "rubric_hint": "재건축 조합원 혜택의 임계값: 남향 80%+ 또는 조망 60%+ 둘 중 하나는 A 기준선.",
        },
    },
    "alternative": {
        "business_viability": {
            "signals_extra": [
                "기존안 대비 사업성 향상치 (정량 비교)",
                "공기·공사비 절감 정량",
                "조합원 환원 추가분 명시",
                "용적률 인센티브 추가 확보",
            ],
            "rubric_hint": "대안설계는 기존안 대비 비교가 본질. 향상치 정량 미명시면 자동 C 이하.",
        },
        "design_brand": {
            "signals_extra": [
                "기존안과 차별화 포인트 (매스·외관·평면)",
                "동일 사업성 유지 + 디자인 업그레이드",
                "리스크 (변경 영향·인허가) 분석",
            ],
            "rubric_hint": "대안설계는 '왜 이 대안인가' 차별화 스토리가 핵심.",
        },
    },
}

# ── 시설유형 충돌 키워드 (LLM 환각 검증) ──────────────────────────────────────
# 지침서 추출 결과(예: brief_evaluation.evaluation_categories[*].sub_items)에
# 시설유형과 충돌하는 키워드가 나오면 LLM 환각 가능성 — brief_validator에서 경고.
#
# 영등포구 청사(public) 케이스: 페이지 18 심사기준이 정상 추출되어야 하는데
# LLM이 "본 연구원의 특성에 맞는...", "연구원의 전체성 표현" 같은
# 학습 데이터의 연구원 공모 패턴을 환각으로 섞어넣음. 청사 공모에 "연구원"
# 단어가 평가항목에 나올 수 없으므로 충돌 키워드로 감지 가능.
#
# 값은 정규식 패턴 문자열. 한국어 단어 경계가 모호하므로 부분 일치(\b 미사용).
# 경계 모호 단어("학교"가 "유학교"에 매치 등)는 명확한 형태로 좁힘.
FACILITY_CONFLICT_KEYWORDS: dict[str, list[str]] = {
    "public":         ["연구원", "연구소", "병원", "공장", "산업단지", "리조트", "오피스텔", "백화점"],
    "residential":    ["청사", "연구원", "병원", "공장", "학교", "호텔"],
    "office":         ["청사", "연구원", "병원", "학교", "호텔"],
    "transport":      ["청사", "연구원", "병원", "공장", "학교", "호텔"],
    "commercial":     ["청사", "연구원", "병원", "공장", "학교"],
    "cultural":       ["청사", "연구원", "병원", "공장"],
    "hospitality":    ["청사", "연구원", "병원", "공장"],
    "education":      ["청사", "병원", "공장", "호텔", "백화점"],
    "industrial":     ["청사", "연구원", "병원", "학교", "호텔"],
    "medical":        ["청사", "연구원", "공장", "학교", "호텔"],
    "reconstruction": ["청사", "연구원", "공장", "학교", "호텔"],
    "alternative":    ["청사", "연구원", "공장", "학교", "호텔"],
    # masterplan / mixed_use 는 거의 모든 시설을 포함할 수 있어 충돌 키워드 없음
    "masterplan":     [],
    "mixed_use":      [],
}


def facility_conflict_keywords(facility_type: str) -> list[str]:
    """시설유형에 충돌하는 키워드 목록 (없으면 빈 리스트)."""
    return FACILITY_CONFLICT_KEYWORDS.get(facility_type, [])


# ── Rubric 버전 관리 ──────────────────────────────────────────────────────────
# rubric 개정 시 버전을 올리고 아래에 변경 이력을 남긴다.
# comparison.json / deep.json / diagnosis.json에 rubric_version 필드로 기록되어
# 기존 데이터의 재평가 필요 여부 판단 기준이 된다.
#
# 버전 이력:
#   v1 (2026-06-15) — initial rubric seed: 8축×2그룹 + 14개 시설유형 override
RUBRIC_VERSION = "v1"


def axis_rubric_for(facility_type: str, axis_key: str) -> dict:
    """시설유형 + 평가축에 적용되는 최종 rubric.

    base = COMPARISON_AXES_BY_GROUP[group][axis] (signals, rubric, description)
    override = FACILITY_AXIS_OVERRIDES[facility_type][axis] (있을 때만 signals_extra, rubric_hint)
    Returns: {label_ko, description, signals[], rubric{A..E}, rubric_hint}
    """
    axes = axes_for(facility_type)
    base = axes.get(axis_key, {})
    out = {
        "label_ko":    base.get("label_ko", axis_key),
        "description": base.get("description", ""),
        "signals":     list(base.get("signals", [])),
        "rubric":      dict(base.get("rubric", {})),
        "rubric_hint": "",
        "version":     RUBRIC_VERSION,
    }
    override = FACILITY_AXIS_OVERRIDES.get(facility_type, {}).get(axis_key)
    if override:
        out["signals"].extend(override.get("signals_extra", []))
        if override.get("rubric_hint"):
            out["rubric_hint"] = override["rubric_hint"]
    return out


def build_axis_rubric_block(facility_type: str, axes_keys: list[str] | None = None) -> str:
    """평가축별 rubric을 LLM 프롬프트용 문자열로 직렬화 (공유 헬퍼).

    각 축마다: label · description · 핵심 신호(signals) · A~E 등급 정의 · 시설특화 hint.
    "왜 이 등급인지" LLM이 자기검증 가능한 수준의 룰북.

    Args:
        facility_type: 시설유형 키 (FACILITY_TYPES의 키)
        axes_keys: 직렬화할 축 목록. None이면 시설유형 그룹의 전체 축 사용.

    Returns:
        프롬프트에 그대로 삽입 가능한 multi-line 문자열.
    """
    if axes_keys is None:
        axes_keys = axes_keys_for(facility_type)
    lines = []
    for k in axes_keys:
        r = axis_rubric_for(facility_type, k)
        lines.append(f"\n■ {k} — {r['label_ko']}")
        if r.get("description"):
            lines.append(f"  설명: {r['description']}")
        signals = r.get("signals") or []
        if signals:
            sig_lines = "\n".join(f"   · {s}" for s in signals)
            lines.append(f"  PDF에서 볼 신호:\n{sig_lines}")
        rubric = r.get("rubric") or {}
        if rubric:
            rub_lines = "\n".join(
                f"   {g}: {rubric[g]}" for g in ("A", "B", "C", "D", "E") if g in rubric
            )
            lines.append(f"  등급 기준:\n{rub_lines}")
        if r.get("rubric_hint"):
            lines.append(f"  시설특화 hint: {r['rubric_hint']}")
    return "\n".join(lines)

def axes_for(facility_type: str) -> dict:
    group = FACILITY_TYPES.get(facility_type, {}).get("group", "general")
    return COMPARISON_AXES_BY_GROUP[group]

def axes_keys_for(facility_type: str) -> list:
    return list(axes_for(facility_type).keys())

# Legacy aliases — backward compat for existing imports
COMPARISON_AXES_META = COMPARISON_AXES_BY_GROUP["redev"]
COMPARISON_AXES = list(COMPARISON_AXES_META.keys())

MODEL_ID = "claude-sonnet-4-6"
# 분류 모델: Sonnet으로 통일. Haiku는 페이지 헤더 텍스트를 환각하는 케이스 다수 발견
# (영등포구 청사 케이스 — Haiku가 p.18 헤더를 "[표 06] 심사평가 주안점" 대신 "배점 표"로 일반화
# → 헤더 기반 후처리 강등 무력화 → BRIEF_EVALUATION 환각 카테고리 추출).
# 비용 증가는 페이지당 ~$0.004로 미미하며, 분류 오류로 인한 토큰 손실보다 작음.
MODEL_ID_CLASSIFY = "claude-sonnet-4-6"

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
        # 메모리 우선, 없으면 환경변수. 양쪽 모두 정제 적용.
        raw = self._memory_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return self._sanitize_api_key(raw)

    @staticmethod
    def _sanitize_api_key(key: str) -> str:
        """셸 복붙 아티팩트 제거: echo -n "sk-ant-..." → sk-ant-...

        UTF-8 BOM / zero-width 문자도 제거 — 메모장·일부 편집기로 키를 저장하면
        선두에 BOM(\\ufeff)이 붙어 httpx 헤더 인코딩(ascii)에서 UnicodeEncodeError
        발생. str.strip() 은 BOM 을 공백으로 보지 않으므로 명시적으로 제거.
        """
        key = key or ""
        for _zw in ("﻿", "​", "‌", "‍", "⁠"):
            key = key.replace(_zw, "")
        key = key.strip()
        if key.startswith("-n "):
            key = key[3:].strip()
        key = key.strip('"').strip("'")
        return key

    def set_api_key(self, key: str):
        """세션 메모리에만 저장. 디스크에 쓰지 않음."""
        self._memory_api_key = self._sanitize_api_key(key)

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
