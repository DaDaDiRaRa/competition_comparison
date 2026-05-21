export const COMPLIANCE_COLOR = {
  yes: '#16a34a', partial: '#ea580c', no: '#dc2626', unclear: '#6b7280',
}

export const GRADE_COLOR = {
  A: '#16a34a',
  B: '#0891b2',
  C: '#ca8a04',
  D: '#ea580c',
  E: '#dc2626',
}

export const GRADE_BG = {
  A: '#dcfce7',
  B: '#cffafe',
  C: '#fef3c7',
  D: '#fed7aa',
  E: '#fee2e2',
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
