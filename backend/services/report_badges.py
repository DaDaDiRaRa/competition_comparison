"""
report_badges.py — 사실/해석 2층 분리 렌더 헬퍼 (LLM 0 · 인라인 스타일 자체완결).

지침서 제안서/플레이북이 쓰는 "사실=근거 인용 vs AI 해석=추론" 시각 분리를
진단·비교 리포트에도 적용하기 위한 공용 배지·범례. 진단·비교의 데이터는 이미
2층(강점/약점/근거=인용 강제 사실 vs 보강/차별화/사후요약=추론)으로 나뉘어 있으나
렌더에서 구분이 없어 사실과 추론이 섞여 보였다 — 이 헬퍼가 그 경계를 노출한다.

(지침서 제안서 리포트는 자체 Phase 2 범례를 이미 보유 — 중복 이식하지 않음.)
"""
from __future__ import annotations

# AI 해석 강조색 = 테마 공유 토큰 --ai(#2a6496 파랑). 제안서·플레이북의 AI 칩과 통일
# (리포트가 THEME_VARS 주입 → var(--ai) 해석됨). 사실(중립 텍스트)과 구분.
_ACCENT = "var(--ai)"


def ai_badge(label: str = "해석") -> str:
    """추론 섹션·항목에 붙는 작은 인라인 배지."""
    return (
        f'<span style="display:inline-block;font-size:11px;font-weight:700;'
        f'color:#fff;background:{_ACCENT};border-radius:4px;padding:1px 7px;'
        f'margin-left:6px;vertical-align:middle">{label}</span>'
    )


def fact_interp_legend() -> str:
    """리포트 상단 범례 — 사실(근거 인용) vs AI 해석(추론) 구분 안내."""
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;'
        'border:1px solid #e5e5e5;background:#fafafa;border-radius:8px;'
        'padding:10px 16px;margin:12px 0;font-size:12px;color:#555">'
        '<span><b style="color:#333">사실</b> · 강점/약점/근거는 제출물에서 직접 관찰 '
        '(p.N 인용)</span>'
        f'<span>{ai_badge()} · 보강·차별화·사후 요약은 추론·조언 (참고용)</span>'
        '</div>'
    )
