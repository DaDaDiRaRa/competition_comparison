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

// ── 3단계 표시 라벨 (내부는 A~E 유지, 임원용 표시만 단어) ──────────────
// 백엔드 grade_helpers.GRADE_LABEL_3 와 동일. 순위·차별화는 A~E 로 계산, 뱃지에만 3단계.
// 같은 단어에 다른 색이 붙지 않게 색도 3단계로 collapse (우수=A색·보통=C색·미흡=E색).
export const GRADE_LABEL = { A: '우수', B: '우수', C: '보통', D: '미흡', E: '미흡' }
const _LABEL_KEY = { A: 'A', B: 'A', C: 'C', D: 'E', E: 'E' }
export function gradeLabel(g) { return GRADE_LABEL[g] ?? '' }
export function gradeLabelColor(g) { return GRADE_COLOR[_LABEL_KEY[g]] ?? 'var(--color-text-faint)' }
export function gradeLabelBg(g) { return GRADE_BG[_LABEL_KEY[g]] ?? 'var(--color-bg-surface-alt)' }

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
