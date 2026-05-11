import { useMeta } from '../../hooks/useMeta'

const COLORS = [
  '#63b3ed','#68d391','#f6ad55','#fc8181','#b794f4',
  '#76e4f7','#faf089','#fed7d7','#c6f6d5','#bee3f8',
  '#e9d8fd','#feebc8','#fed7e2','#c6f6d5','#e2e8f0',
  '#4fd1c5','#f687b3',
]

export default function PageDistChart({ distribution, total, title }) {
  const { pageTypeLabel } = useMeta()
  if (!distribution || !total) return null
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1])

  return (
    <div style={{ marginTop: 16 }}>
      {title && <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 8 }}>{title}</div>}
      {entries.map(([type, count], i) => {
        const pct = Math.round((count / total) * 100)
        return (
          <div key={type} style={{ display: 'flex', alignItems: 'center', marginBottom: 5, gap: 8 }}>
            <div style={{ width: 90, fontSize: 12, color: '#cbd5e0', textAlign: 'right', flexShrink: 0 }}>
              {pageTypeLabel(type)}
            </div>
            <div style={{ flex: 1, background: '#2d3748', borderRadius: 4, height: 16, overflow: 'hidden' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: COLORS[i % COLORS.length],
                borderRadius: 4, transition: 'width 0.4s',
              }} />
            </div>
            <div style={{ width: 50, fontSize: 12, color: '#e2e8f0' }}>
              {count}p ({pct}%)
            </div>
          </div>
        )
      })}
    </div>
  )
}
