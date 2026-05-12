import { useMeta } from '../../hooks/useMeta'

const COLORS = [
  '#3b82f6','#16a34a','#ea580c','#dc2626','#a78bfa',
  '#22d3ee','#fef08a','#fee2e2','#bbf7d0','#dbeafe',
  '#ede9fe','#fed7aa','#fbcfe8','#bbf7d0','#1f2937',
  '#0891b2','#ec4899',
]

export default function PageDistChart({ distribution, total, title }) {
  const { pageTypeLabel } = useMeta()
  if (!distribution || !total) return null
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1])

  return (
    <div style={{ marginTop: 16 }}>
      {title && <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 8 }}>{title}</div>}
      {entries.map(([type, count], i) => {
        const pct = Math.round((count / total) * 100)
        return (
          <div key={type} style={{ display: 'flex', alignItems: 'center', marginBottom: 5, gap: 8 }}>
            <div style={{ width: 90, fontSize: 12, color: '#374151', textAlign: 'right', flexShrink: 0 }}>
              {pageTypeLabel(type)}
            </div>
            <div style={{ flex: 1, background: '#e5e7eb', borderRadius: 4, height: 16, overflow: 'hidden' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: COLORS[i % COLORS.length],
                borderRadius: 4, transition: 'width 0.4s',
              }} />
            </div>
            <div style={{ width: 50, fontSize: 12, color: '#1f2937' }}>
              {count}p ({pct}%)
            </div>
          </div>
        )
      })}
    </div>
  )
}
