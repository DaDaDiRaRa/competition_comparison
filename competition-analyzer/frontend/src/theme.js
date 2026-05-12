// 화이트 테마 — 네이비 액센트
// 색 변경 시 이 파일과 services/report_generator.py::_CSS의 :root 변수를 함께 수정.
export const theme = {
  // 배경
  bg: '#fafafa',          // 메인 배경
  panel: '#ffffff',       // 카드/패널
  panelAlt: '#f9fafb',    // 약한 강조 배경
  input: '#ffffff',       // 입력 필드
  inputReadonly: '#f3f4f6',

  // 테두리
  border: '#e5e7eb',
  borderStrong: '#d1d5db',

  // 액센트 (네이비)
  accent: '#334155',
  accentHover: '#475569',
  accentSoft: '#f1f5f9',
  accentText: '#ffffff',

  // 텍스트
  text: '#1f2937',
  textMuted: '#4b5563',
  textFaint: '#6b7280',
  textSubtle: '#9ca3af',

  // 등급 색상 (화이트 배경용)
  grade: {
    A: '#16a34a',
    B: '#0891b2',
    C: '#ca8a04',
    D: '#ea580c',
    E: '#dc2626',
  },
  gradeBg: {
    A: '#dcfce7',
    B: '#cffafe',
    C: '#fef3c7',
    D: '#fed7aa',
    E: '#fee2e2',
  },

  // 골드 (특별 강조)
  gold: '#0d9488',
}
