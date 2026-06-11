import { useEffect, useState } from 'react'
import { GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'
import { useMeta } from '../../hooks/useMeta'

const TRANSITION_MS = 240

const ALIGNMENT_META = {
  high:    { label: '정렬 일치도 높음', color: 'var(--color-success)' },
  partial: { label: '부분 일치',        color: 'var(--color-warning)' },
  low:     { label: '낮은 일치',        color: 'var(--color-danger)' },
  unknown: { label: '미상',             color: 'var(--color-text-faint)' },
}

const s = {
  overlay: (open) => ({
    position: 'fixed', inset: 0,
    background: 'var(--color-overlay)',
    zIndex: 1000,
    opacity: open ? 1 : 0,
    pointerEvents: open ? 'auto' : 'none',
    transition: `opacity ${TRANSITION_MS}ms ease`,
  }),
  panel: (open) => ({
    position: 'fixed', top: 0, right: 0, height: '100vh',
    width: 580, maxWidth: '100vw',
    background: 'var(--color-bg-surface)',
    boxShadow: '-12px 0 32px rgba(0,0,0,0.15)',
    zIndex: 1001,
    transform: open ? 'translateX(0)' : 'translateX(100%)',
    transition: `transform ${TRANSITION_MS}ms ease`,
    display: 'flex', flexDirection: 'column',
  }),
  header: {
    padding: '16px 20px',
    borderBottom: '1px solid var(--color-border)',
    display: 'flex', alignItems: 'flex-start', gap: 12,
    flexShrink: 0,
  },
  headerText: { flex: 1, minWidth: 0 },
  title: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 'var(--font-weight-bold)',
    color: 'var(--color-text-body)',
    marginBottom: 6,
    wordBreak: 'break-word',
  },
  facilityBadge: {
    fontSize: 'var(--font-size-xs)',
    padding: '2px 8px', borderRadius: 20,
    background: 'var(--color-accent-soft)',
    color: 'var(--color-accent)',
    fontWeight: 'var(--font-weight-semibold)',
    border: '1px solid var(--color-accent-border)',
    display: 'inline-block',
  },
  closeBtn: {
    background: 'none', border: 'none',
    color: 'var(--color-text-subtle)',
    fontSize: 'var(--font-size-xl)', lineHeight: 1,
    cursor: 'pointer', padding: '2px 6px', borderRadius: 4,
  },
  body: {
    flex: 1, overflowY: 'auto',
    padding: '16px 20px',
  },
  section: { marginBottom: 20 },
  sectionTitle: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 'var(--font-weight-semibold)',
    color: 'var(--color-accent)',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  rankRow: {
    display: 'flex', alignItems: 'center', gap: 10,
    flexWrap: 'wrap', marginBottom: 8,
  },
  rankLabel: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)' },
  rankValue: {
    fontSize: 'var(--font-size-base)',
    fontWeight: 'var(--font-weight-bold)',
    color: 'var(--color-text-body)',
  },
  alignBadge: (color) => ({
    fontSize: 'var(--font-size-xs)',
    padding: '3px 10px', borderRadius: 20,
    border: `1px solid ${color}`,
    color,
    background: 'var(--color-bg-surface-alt)',
    fontWeight: 'var(--font-weight-semibold)',
  }),
  notes: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--color-text-muted)',
    lineHeight: 1.6,
    padding: '8px 12px',
    background: 'var(--color-bg-surface-alt)',
    borderRadius: 6,
    marginTop: 4,
  },
  list: { margin: 0, padding: 0, listStyle: 'none' },
  listItem: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--color-text-body)',
    padding: '6px 0',
    borderBottom: '1px solid var(--color-border)',
    lineHeight: 1.5,
  },
  listBullet: {
    color: 'var(--color-accent)',
    marginRight: 6,
    fontWeight: 'var(--font-weight-bold)',
  },
  empty: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--color-text-faint)',
    fontStyle: 'italic',
  },
  subBlock: {
    background: 'var(--color-bg-surface-alt)',
    border: '1px solid var(--color-border)',
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  subName: {
    fontSize: 'var(--font-size-base)',
    fontWeight: 'var(--font-weight-semibold)',
    color: 'var(--color-text-body)',
    marginBottom: 8,
  },
  axisList: { display: 'flex', flexDirection: 'column', gap: 4 },
  axisRow: (expanded) => ({
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: 8, padding: '6px 8px',
    background: expanded ? 'var(--color-bg-surface-alt)' : 'var(--color-bg-surface)',
    borderRadius: expanded ? '4px 4px 0 0' : 4,
    fontSize: 'var(--font-size-xs)',
    cursor: 'pointer',
    userSelect: 'none',
    border: `1px solid ${expanded ? 'var(--color-accent-border)' : 'var(--color-border)'}`,
    transition: 'background 0.15s',
  }),
  axisName: {
    color: 'var(--color-text-muted)',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
    flex: 1,
  },
  gradeBadge: (grade) => ({
    minWidth: 22,
    padding: '1px 7px',
    borderRadius: 10,
    background: grade ? GRADE_BG[grade] : 'var(--color-bg-surface-alt)',
    color: grade ? GRADE_COLOR[grade] : 'var(--color-text-faint)',
    fontWeight: 'var(--font-weight-bold)',
    fontSize: 'var(--font-size-xs)',
    textAlign: 'center',
    letterSpacing: 0.5,
    flexShrink: 0,
  }),
  chevron: (expanded) => ({
    fontSize: 9, color: 'var(--color-text-faint)',
    marginLeft: 4, flexShrink: 0,
    transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
    transition: 'transform 0.15s',
  }),
  axisDetail: {
    background: 'var(--color-bg-surface-alt)',
    border: '1px solid var(--color-accent-border)',
    borderTop: 'none',
    borderRadius: '0 0 4px 4px',
    padding: '8px 10px',
    fontSize: 'var(--font-size-xs)',
    lineHeight: 1.6,
  },
  detailGroup: { marginBottom: 6 },
  detailLabel: (color) => ({
    fontSize: 10, fontWeight: 'var(--font-weight-bold)',
    color, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2,
  }),
  detailItem: { color: 'var(--color-text-body)', paddingLeft: 8 },
  detailNotes: {
    color: 'var(--color-text-muted)', fontStyle: 'italic',
    paddingLeft: 8,
  },
}

function renderItem(item, i) {
  const text = typeof item === 'string' ? item : JSON.stringify(item)
  return (
    <li key={i} style={s.listItem}>
      <span style={s.listBullet}>·</span>{text}
    </li>
  )
}

function Section({ title, items }) {
  return (
    <div style={s.section}>
      <div style={s.sectionTitle}>{title}</div>
      {items?.length > 0
        ? <ul style={s.list}>{items.map(renderItem)}</ul>
        : <div style={s.empty}>—</div>}
    </div>
  )
}

function AxisAccordion({ axisKey, axisData, label }) {
  const [open, setOpen] = useState(false)
  const grade = toGrade(axisData)
  const strengths = axisData?.strengths || []
  const weaknesses = axisData?.weaknesses || []
  const notes = axisData?.notes
  const brief = axisData?.brief_compliance
  const hasDetail = strengths.length > 0 || weaknesses.length > 0 || notes || brief

  return (
    <div>
      <div
        style={s.axisRow(open)}
        onClick={() => hasDetail && setOpen(p => !p)}
        title={hasDetail ? '클릭하여 상세 보기' : undefined}
      >
        <span style={s.axisName} title={label}>{label}</span>
        <span style={s.gradeBadge(grade)}>{grade || '—'}</span>
        {hasDetail && <span style={s.chevron(open)}>▼</span>}
      </div>
      {open && hasDetail && (
        <div style={s.axisDetail}>
          {strengths.length > 0 && (
            <div style={s.detailGroup}>
              <div style={s.detailLabel('var(--color-success)')}>강점</div>
              {strengths.map((t, i) => (
                <div key={i} style={s.detailItem}>· {typeof t === 'string' ? t : JSON.stringify(t)}</div>
              ))}
            </div>
          )}
          {weaknesses.length > 0 && (
            <div style={s.detailGroup}>
              <div style={s.detailLabel('var(--color-danger)')}>약점</div>
              {weaknesses.map((t, i) => (
                <div key={i} style={s.detailItem}>· {typeof t === 'string' ? t : JSON.stringify(t)}</div>
              ))}
            </div>
          )}
          {brief && (
            <div style={s.detailGroup}>
              <div style={s.detailLabel('var(--color-info)')}>지침 충족</div>
              <div style={s.detailItem}>{brief}</div>
            </div>
          )}
          {notes && (
            <div style={s.detailGroup}>
              <div style={s.detailLabel('var(--color-text-muted)')}>노트</div>
              <div style={s.detailNotes}>{notes}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ArchiveDetail({ data, onClose }) {
  const { facilityLabel, axisLabel } = useMeta()
  const [displayData, setDisplayData] = useState(data)
  const isOpen = !!data

  // 닫는 애니메이션 끝난 뒤에 데이터 제거 (트랜지션 중 콘텐츠 유지)
  useEffect(() => {
    if (data) {
      setDisplayData(data)
      return
    }
    const t = setTimeout(() => setDisplayData(null), TRANSITION_MS)
    return () => clearTimeout(t)
  }, [data])

  // ESC 키로 닫기
  useEffect(() => {
    if (!isOpen) return
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!displayData && !isOpen) return null

  const d = displayData || {}
  const title = d.competition_name || d.competition_id || '—'
  const facilityType = d.facility_type
  const ranking = d.ranking || d.blind_ranking || []
  const gap = d.gap_analysis || {}
  const winner = ranking[0]
  const alignment = gap.alignment || 'unknown'
  const alignMeta = ALIGNMENT_META[alignment] || ALIGNMENT_META.unknown
  const submissions = d.submissions || {}

  return (
    <>
      <div style={s.overlay(isOpen)} onClick={onClose} />
      <aside
        style={s.panel(isOpen)}
        role="dialog"
        aria-modal="true"
        aria-label="비교분석 상세"
      >
        <div style={s.header}>
          <div style={s.headerText}>
            <div style={s.title}>{title}</div>
            {facilityType && (
              <span style={s.facilityBadge}>{facilityLabel(facilityType)}</span>
            )}
          </div>
          <button
            style={s.closeBtn}
            onClick={onClose}
            aria-label="닫기"
          >×</button>
        </div>

        <div style={s.body}>
          {/* 1. 순위 + 정합도 */}
          <div style={s.section}>
            <div style={s.sectionTitle}>순위 · 정합도</div>
            <div style={s.rankRow}>
              <span style={s.rankLabel}>1위</span>
              <span style={s.rankValue}>{winner || '—'}</span>
              <span style={s.alignBadge(alignMeta.color)}>{alignMeta.label}</span>
            </div>
            {gap.notes && <div style={s.notes}>{gap.notes}</div>}
          </div>

          {/* 2. 핵심 차별화 */}
          <Section title="핵심 차별화" items={d.key_differentiators} />

          {/* 3. 당선작 강점 */}
          <Section title="당선작 강점" items={d.winner_strengths} />

          {/* 4. 낙선작 약점 */}
          <Section title="낙선작 약점" items={d.loser_weaknesses} />

          {/* 5. 제출사별 평가 */}
          <div style={s.section}>
            <div style={s.sectionTitle}>제출사별 평가</div>
            {Object.keys(submissions).length === 0 && (
              <div style={s.empty}>—</div>
            )}
            {Object.entries(submissions).map(([company, axes]) => (
              <div key={company} style={s.subBlock}>
                <div style={s.subName}>{company}</div>
                <div style={s.axisList}>
                  {Object.entries(axes || {}).map(([axisKey, axisData]) => (
                    <AxisAccordion
                      key={axisKey}
                      axisKey={axisKey}
                      axisData={axisData}
                      label={facilityType ? axisLabel(facilityType, axisKey) : axisKey}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  )
}
