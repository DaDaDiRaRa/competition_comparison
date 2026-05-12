"""
테마 색상 일괄 교체 도구.

사용법:
    python tools/change_theme.py navy         # 기본 (네이비 + 골드)
    python tools/change_theme.py charcoal     # 차콜 + 틸
    python tools/change_theme.py forest       # 포레스트 + 앰버
    python tools/change_theme.py burgundy     # 버건디 + 골드
    python tools/change_theme.py indigo       # 인디고 + 마젠타
    python tools/change_theme.py blackgold    # 블랙 + 골드 (미니멀 럭셔리)

직접 색을 지정하려면:
    python tools/change_theme.py custom --accent #2563eb --hover #1d4ed8 --highlight #f59e0b

수정 대상:
    frontend/src/**/*.{jsx,js}            (인라인 스타일 색)
    backend/services/report_generator.py  (HTML CSS 변수)
    backend/services/submission_report_generator.py
    backend/services/diagnosis_report_generator.py
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONTEND = ROOT / "competition-analyzer" / "frontend" / "src"
BACKEND_SERVICES = ROOT / "competition-analyzer" / "backend" / "services"

# 현재 사용 중인 (네이비) 액센트 색상들 — 모든 프리셋에서 이걸 새 액센트로 치환.
CURRENT_ACCENT_KEYS = {
    "accent": "#1e3a8a",      # 메인 액센트 (버튼, 헤더, 활성 탭)
    "accent_hover": "#1e40af", # 호버/액티브
    "accent_light": "#3b82f6", # 밝은 액센트 (서브 강조)
    "accent_soft": "#dbeafe",  # 가장 옅은 배경 강조
    "highlight": "#b8860b",    # 골드 강조 (리포트 테두리, 특별 강조)
    "highlight_soft": "rgba(184,134,11,0.10)",  # 골드 소프트 BG
    "highlight_strong": "rgba(184,134,11,0.30)", # 골드 테두리 강조
}

PRESETS = {
    "navy": {
        "name": "네이비 + 골드 (Classic Professional)",
        "accent": "#1e3a8a",
        "accent_hover": "#1e40af",
        "accent_light": "#3b82f6",
        "accent_soft": "#dbeafe",
        "highlight": "#b8860b",
        "highlight_soft": "rgba(184,134,11,0.10)",
        "highlight_strong": "rgba(184,134,11,0.30)",
    },
    "charcoal": {
        "name": "차콜 + 틸 (Modern Sophisticated)",
        "accent": "#334155",
        "accent_hover": "#475569",
        "accent_light": "#64748b",
        "accent_soft": "#f1f5f9",
        "highlight": "#0d9488",
        "highlight_soft": "rgba(13,148,136,0.10)",
        "highlight_strong": "rgba(13,148,136,0.30)",
    },
    "forest": {
        "name": "포레스트 + 앰버 (Organic Warm)",
        "accent": "#15803d",
        "accent_hover": "#16a34a",
        "accent_light": "#22c55e",
        "accent_soft": "#dcfce7",
        "highlight": "#d97706",
        "highlight_soft": "rgba(217,119,6,0.10)",
        "highlight_strong": "rgba(217,119,6,0.30)",
    },
    "burgundy": {
        "name": "버건디 + 골드 (Luxury)",
        "accent": "#7f1d1d",
        "accent_hover": "#991b1b",
        "accent_light": "#dc2626",
        "accent_soft": "#fee2e2",
        "highlight": "#fbbf24",
        "highlight_soft": "rgba(251,191,36,0.10)",
        "highlight_strong": "rgba(251,191,36,0.30)",
    },
    "indigo": {
        "name": "인디고 + 마젠타 (Tech Vibrant)",
        "accent": "#4f46e5",
        "accent_hover": "#4338ca",
        "accent_light": "#818cf8",
        "accent_soft": "#e0e7ff",
        "highlight": "#ec4899",
        "highlight_soft": "rgba(236,72,153,0.10)",
        "highlight_strong": "rgba(236,72,153,0.30)",
    },
    "blackgold": {
        "name": "블랙 + 골드 (Minimal Luxury)",
        "accent": "#171717",
        "accent_hover": "#262626",
        "accent_light": "#525252",
        "accent_soft": "#f5f5f5",
        "highlight": "#d4af37",
        "highlight_soft": "rgba(212,175,55,0.10)",
        "highlight_strong": "rgba(212,175,55,0.30)",
    },
}


def build_color_map(target: dict) -> dict:
    """현재 색 → 타겟 색 매핑 생성."""
    return {
        CURRENT_ACCENT_KEYS["accent"]:           target["accent"],
        CURRENT_ACCENT_KEYS["accent_hover"]:     target["accent_hover"],
        CURRENT_ACCENT_KEYS["accent_light"]:     target["accent_light"],
        CURRENT_ACCENT_KEYS["accent_soft"]:      target["accent_soft"],
        CURRENT_ACCENT_KEYS["highlight"]:        target["highlight"],
        CURRENT_ACCENT_KEYS["highlight_soft"]:   target["highlight_soft"],
        CURRENT_ACCENT_KEYS["highlight_strong"]: target["highlight_strong"],
    }


def transform(text: str, mapping: dict) -> tuple[str, int]:
    count = 0
    for old, new in mapping.items():
        if old.startswith("#"):
            pattern = re.compile(re.escape(old) + r"(?![0-9a-fA-F])", re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(old))
        new_text, n = pattern.subn(new, text)
        if n > 0:
            text = new_text
            count += n
    return text, count


def main():
    parser = argparse.ArgumentParser(description="Competition Analyzer 테마 색 일괄 교체")
    parser.add_argument("preset", choices=list(PRESETS.keys()) + ["custom"],
                        help="프리셋 이름 (또는 'custom')")
    parser.add_argument("--accent")
    parser.add_argument("--hover")
    parser.add_argument("--light")
    parser.add_argument("--soft")
    parser.add_argument("--highlight")
    args = parser.parse_args()

    if args.preset == "custom":
        if not args.accent:
            print("custom 모드는 최소 --accent 가 필요합니다.")
            sys.exit(1)
        target = {
            "accent": args.accent,
            "accent_hover": args.hover or args.accent,
            "accent_light": args.light or args.accent,
            "accent_soft": args.soft or "#f5f5f5",
            "highlight": args.highlight or "#b8860b",
            "highlight_soft": "rgba(184,134,11,0.10)",
            "highlight_strong": "rgba(184,134,11,0.30)",
        }
        name = "Custom"
    else:
        target = PRESETS[args.preset]
        name = target["name"]

    mapping = build_color_map(target)

    print(f"테마 적용: {name}")
    print(f"  accent:    {CURRENT_ACCENT_KEYS['accent']}  →  {target['accent']}")
    print(f"  hover:     {CURRENT_ACCENT_KEYS['accent_hover']}  →  {target['accent_hover']}")
    print(f"  highlight: {CURRENT_ACCENT_KEYS['highlight']}  →  {target['highlight']}")
    print()

    # 대상 파일 수집
    targets = []
    if FRONTEND.exists():
        targets += [f for f in FRONTEND.rglob("*.jsx") if "node_modules" not in str(f)]
        targets += [f for f in FRONTEND.rglob("*.js") if "node_modules" not in str(f)]
    for fname in ("report_generator.py", "submission_report_generator.py", "diagnosis_report_generator.py"):
        f = BACKEND_SERVICES / fname
        if f.exists():
            targets.append(f)

    total = 0
    changed = 0
    for f in targets:
        original = f.read_text(encoding="utf-8")
        new, n = transform(original, mapping)
        if n > 0:
            f.write_text(new, encoding="utf-8")
            print(f"  {n:4d} edits  {f.relative_to(ROOT)}")
            total += n
            changed += 1

    print(f"\n총 {changed}개 파일, {total}개 색상 치환 완료.")
    print("\n다음 단계:")
    print("  1. cd competition-analyzer/frontend && npm run build")
    print("  2. cd ../backend && python -m PyInstaller competition_analyzer.spec --noconfirm")
    print("     (또는 .\\build.ps1)")


if __name__ == "__main__":
    main()
