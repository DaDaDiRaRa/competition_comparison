import { useMeta } from '../../hooks/useMeta'

const COLORS = [
  '#64748b','var(--color-success)','#ea580c','var(--color-danger)','#a78bfa',
  '#22d3ee','#fef08a','var(--color-danger-bg)','#bbf7d0','var(--color-accent-soft)',
  '#ede9fe','#fed7aa','#fbcfe8','#bbf7d0','var(--color-text-body)',
  'var(--color-info)','#ec4899',
]

export default function PageDistChart({ distribution, total, title }) {
  const { pageTypeLabel } = useMeta()
  if (!distribution || !total) return null
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1])

  return (
    <div style={{ marginTop: 16 }}>
      {title && <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>{title}</div>}
      {entries.map(([type, count], i) => {
        const pct = Math.round((count / total) * 100)
        return (
          <div key={type} style={{ display: 'flex', alignItems: 'center', marginBottom: 5, gap: 'var(--gap-sm)' }}>
            <div style={{ width: 90, fontSize: 'var(--font-size-sm)', color: '#374151', textAlign: 'right', flexShrink: 0 }}>
              {pageTypeLabel(type)}
            </div>
            <div style={{ flex: 1, background: 'var(--color-border)', borderRadius: 4, height: 16, overflow: 'hidden' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: COLORS[i % COLORS.length],
                borderRadius: 4, transition: 'width 0.4s',
              }} />
            </div>
            <div style={{ width: 50, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)' }}>
              {count}p ({pct}%)
            </div>
          </div>
        )
      })}
    </div>
  )
}
