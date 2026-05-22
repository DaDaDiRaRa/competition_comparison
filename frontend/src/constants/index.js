export const COMPLIANCE_COLOR = {
  yes: 'var(--color-success)', partial: 'var(--color-grade-d)', no: 'var(--color-danger)', unclear: 'var(--color-text-faint)',
}

export const GRADE_COLOR = {
  A: 'var(--color-success)',
  B: 'var(--color-info)',
  C: 'var(--color-warning)',
  D: 'var(--color-grade-d)',
  E: 'var(--color-danger)',
}

export const GRADE_BG = {
  A: 'var(--color-success-bg)',
  B: 'var(--color-info-bg)',
  C: 'var(--color-warning-bg)',
  D: '#fed7aa',
  E: 'var(--color-danger-bg)',
}

const _LEGACY = { '상': 'B', '중': 'C', '하': 'D' }

// 구 데이터(상/중/하 or 0-10 score) → A-E 자동 변환
export function toGrade(d) {
  if (!d || typeof d !== 'object') return null
  const g = d.grade ?? d.overall_grade
  if (g === 'A' || g === 'B' || g === 'C' || g === 'D' || g === 'E') return g
  if (_LEGACY[g]) return _LEGACY[g]
  const s = d.score ?? d.overall_score
  if (s == null) return null
  const n = Number(s)
  if (!Number.isFinite(n)) return null
  if (n >= 8.5) return 'A'
  if (n >= 7.0) return 'B'
  if (n >= 5.0) return 'C'
  if (n >= 3.0) return 'D'
  return 'E'
}
