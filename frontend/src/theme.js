// 화이트 테마 — 네이비 액센트
// 색 변경 시 이 파일과 services/report_generator.py::_CSS의 :root 변수를 함께 수정.
export const theme = {
  // 배경
  bg: 'var(--color-bg-page)',          // 메인 배경
  panel: 'var(--color-bg-surface)',       // 카드/패널
  panelAlt: 'var(--color-bg-surface-alt)',    // 약한 강조 배경
  input: 'var(--color-bg-surface)',       // 입력 필드
  inputReadonly: 'var(--color-bg-input-disabled)',

  // 테두리
  border: 'var(--color-border)',
  borderStrong: 'var(--color-border-strong)',

  // 액센트 (네이비)
  accent: 'var(--color-accent)',
  accentHover: 'var(--color-accent-hover)',
  accentSoft: 'var(--color-accent-soft)',
  accentText: 'var(--color-bg-surface)',

  // 텍스트
  text: 'var(--color-text-body)',
  textMuted: 'var(--color-text-muted)',
  textFaint: 'var(--color-text-faint)',
  textSubtle: 'var(--color-text-subtle)',

  // 등급 색상 (화이트 배경용)
  grade: {
    A: 'var(--color-success)',
    B: 'var(--color-info)',
    C: 'var(--color-warning)',
    D: '#ea580c',
    E: 'var(--color-danger)',
  },
  gradeBg: {
    A: 'var(--color-success-bg)',
    B: 'var(--color-info-bg)',
    C: 'var(--color-warning-bg)',
    D: '#fed7aa',
    E: 'var(--color-danger-bg)',
  },

  // 골드 (특별 강조)
  gold: '#0d9488',
}
