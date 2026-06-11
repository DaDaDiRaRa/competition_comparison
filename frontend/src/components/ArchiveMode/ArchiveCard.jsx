import { useMeta } from '../../hooks/useMeta'

const ALIGNMENT_META = {
  high:    { label: '높음',   color: 'var(--color-success)' },
  partial: { label: '부분',   color: 'var(--color-warning)' },
  low:     { label: '낮음',   color: 'var(--color-danger)' },
  unknown: { label: '미상',   color: 'var(--color-text-faint)' },
}

const s = {
  card: {
    background: 'var(--color-bg-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 8,
    padding: '14px 16px',
    marginBottom: 10,
    cursor: 'pointer',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  },
  header: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' },
  title: {
    fontWeight: 'var(--font-weight-bold)',
    color: 'var(--color-text-body)',
    fontSize: 'var(--font-size-base)',
    flex: 1,
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  facilityBadge: {
    fontSize: 'var(--font-size-xs)',
    padding: '2px 8px',
    borderRadius: 20,
    background: 'var(--color-accent-soft)',
    color: 'var(--color-accent)',
    fontWeight: 'var(--font-weight-semibold)',
    border: '1px solid var(--color-accent-border)',
    flexShrink: 0,
  },
  alignmentBadge: (color) => ({
    fontSize: 'var(--font-size-xs)',
    padding: '2px 8px',
    borderRadius: 20,
    background: 'var(--color-bg-surface-alt)',
    color,
    fontWeight: 'var(--font-weight-semibold)',
    border: `1px solid ${color}`,
    flexShrink: 0,
  }),
  rankingRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 'var(--font-size-sm)',
    color: 'var(--color-text-muted)',
    marginBottom: 8,
  },
  rankingLabel: { color: 'var(--color-text-faint)' },
  rankingValue: { color: 'var(--color-text-body)', fontWeight: 'var(--font-weight-semibold)' },
  tagRow: { display: 'flex', gap: 6, flexWrap: 'wrap' },
  tag: {
    fontSize: 'var(--font-size-xs)',
    padding: '3px 9px',
    borderRadius: 12,
    background: 'var(--color-bg-surface-alt)',
    color: 'var(--color-text-muted)',
    border: '1px solid var(--color-border)',
  },
}

export default function ArchiveCard({ card, onSelect }) {
  const { facilityLabel } = useMeta()
  if (!card) return null

  const {
    competition_id,
    facility_type,
    ranking = [],
    gap_analysis = {},
    key_differentiators = [],
    meta = {},
  } = card

  const alignment = gap_analysis.alignment || 'unknown'
  const alignMeta = ALIGNMENT_META[alignment] || ALIGNMENT_META.unknown
  const winner = ranking[0]
  const diffs = (key_differentiators || []).slice(0, 3)
  const title = meta.competition_name || competition_id

  const handleClick = () => {
    if (onSelect) onSelect(competition_id, facility_type)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      style={s.card}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <div style={s.header}>
        <div style={s.title} title={title}>{title}</div>
        <span style={s.facilityBadge}>{facilityLabel(facility_type)}</span>
        <span style={s.alignmentBadge(alignMeta.color)}>정합도 {alignMeta.label}</span>
      </div>

      <div style={s.rankingRow}>
        <span style={s.rankingLabel}>1위</span>
        <span style={s.rankingValue}>{winner || '—'}</span>
      </div>

      {diffs.length > 0 && (
        <div style={s.tagRow}>
          {diffs.map((d, i) => (
            <span key={i} style={s.tag}>{typeof d === 'string' ? d : JSON.stringify(d)}</span>
          ))}
        </div>
      )}
    </div>
  )
}
