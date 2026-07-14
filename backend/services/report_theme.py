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
