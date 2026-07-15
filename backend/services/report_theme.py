"""
report_theme.py — 자체완결 리포트 HTML 공유 디자인 토큰 (단일 소스, LLM 0).

지침서 "수주 제안서"(brief_proposal_report_generator) 의 매거진 덱 디자인이 가장
다듬어져 있어 이를 기준으로 삼는다. 모든 리포트 generator 가 THEME_VARS 를 자기
`<style>` 안에 주입해 팔레트·타이포(건원 RED + 명조/Montserrat)를 통일한다.

각 리포트는 자체완결 문서라 외부 CSS(kunwon-tokens.css)를 못 쓴다 → Python 상수로 공유.
레이아웃 CSS 는 각 generator 가 유지하되, 색/폰트는 이 변수(var(--accent) 등)로 참조.

⚠ 값을 바꾸면 모든 리포트에 반영 — 회귀: tests/test_report_theme.py.
"""
from __future__ import annotations

# 건원 RED + 명조(본문)/Montserrat(제목). 제안서 :root 와 동일 팔레트.
# 폰트는 이름 참조만(웹폰트 미로드) — 로컬 미설치 시 시스템 폴백까지 제안서와 일치.
THEME_VARS = (
    ":root{"
    "--ink:#141414;--text:#3a3a3a;--muted:#6f6b66;--faint:#a9a5a0;--line:#dcdad6;"
    "--soft:#f6f4f1;--paper:#ffffff;--canvas:#eceae7;--accent:#e60012;"
    "--high:#c0202a;--med:#b7791f;--low:#4e7d3e;--ai:#2a6496;"
    "--serif:'Noto Serif KR','Nanum Myeongjo',Georgia,'Batang',serif;"
    "--sans:'Montserrat','Pretendard','Malgun Gothic',system-ui,-apple-system,'Segoe UI',sans-serif;"
    "}"
)

# 본문/제목 폰트 스택 (인라인 스타일에서 직접 참조용).
SANS = "'Montserrat','Pretendard','Malgun Gothic',system-ui,-apple-system,'Segoe UI',sans-serif"
SERIF = "'Noto Serif KR','Nanum Myeongjo',Georgia,'Batang',serif"
ACCENT = "#e60012"


def theme_style_block() -> str:
    """`<style>` 태그로 감싼 토큰 블록 — 자체 <style> 이 없는 리포트가 head 에 삽입."""
    return f"<style>{THEME_VARS}</style>"


_THEME_MARKER = "/*__THEME__*/"


def inject_theme(css: str) -> str:
    """CSS 안 `/*__THEME__*/` 마커를 THEME_VARS 로 치환. 마커가 없으면 예외.

    각 generator 가 `_CSS.replace(marker, THEME_VARS)` 를 직접 하면 마커를 실수로 지웠을 때
    조용히 no-op → THEME 미주입인데 에러·테스트 실패도 없어 브랜딩이 소리없이 깨진다.
    이 헬퍼는 그 드리프트를 로드타임 실패로 바꾼다.
    """
    if _THEME_MARKER not in css:
        raise ValueError(f"THEME 마커({_THEME_MARKER})가 CSS 에 없습니다 — THEME_VARS 미주입")
    return css.replace(_THEME_MARKER, THEME_VARS)


def warning_band(title_html: str, rows_html: str) -> str:
    """경고 밴드 공용 shell (빨강 계열, 인라인 스타일 자체완결).

    citation_check·quant_validator 의 flags_band_html 이 공유 — 바이트 동일하던 outer
    chrome 을 한 곳으로 통합(스타일 드리프트 방지). title/rows 는 호출측이 escape 완료해 전달.
    """
    return (
        '<section style="border:1px solid #f0b6b6;background:#fff6f6;border-radius:8px;'
        'padding:14px 18px;margin:18px 0">'
        f'<div style="font-weight:700;color:#c0392b;font-size:14px;margin-bottom:8px">{title_html}</div>'
        f'<ul style="margin:0;padding-left:20px;font-size:13px;color:#333">{rows_html}</ul>'
        '</section>'
    )
