import { useState, useEffect } from 'react'
import { getProjects, crossCompare, getCrossCompareReportUrl, listCrossCompareReports } from '../../api/client'
import ProgressLog from '../common/ProgressLog'
import ComparisonDashboard from '../AccumulateMode/ComparisonDashboard'
import { useMeta } from '../../hooks/useMeta'

const RESULT_COLOR = {
  win: { color: 'var(--color-success)', bg: 'var(--color-success-bg)', label: '당선' },
  contracted: { color: 'var(--color-success)', bg: 'var(--color-success-bg)', label: '수의계약' },
  lose: { color: 'var(--color-text-faint)', bg: 'var(--color-bg-surface)', label: '낙선' },
}

const s = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24 },
  title: { fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 6 },
  desc: { fontSize: 13, color: 'var(--color-text-faint)', lineHeight: 1.6, marginBottom: 20 },
  typeTab: (active) => ({
    padding: '5px 14px', borderRadius: 20, fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
    cursor: 'pointer', border: 'none',
    background: active ? 'var(--color-accent)' : 'var(--color-border)',
    color: active ? 'var(--color-bg-surface)' : 'var(--color-text-muted)',
  }),
  card: {
    background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 8, marginBottom: 8,
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '12px 14px', cursor: 'pointer', userSelect: 'none',
  },
  cardName: { fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)', flex: 1 },
  badge: {
    fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20,
    background: 'var(--color-accent-hover)', color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-semibold)',
  },
  chevron: (open) => ({
    color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)', transform: open ? 'rotate(180deg)' : 'none',
    transition: 'transform 0.15s',
  }),
  subList: { borderTop: '1px solid var(--color-border)', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 },
  subRow: (checked) => ({
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
    borderRadius: 6, cursor: 'pointer',
    background: checked ? 'var(--color-bg-surface-alt)' : 'transparent',
    border: checked ? '1px solid var(--color-accent)' : '1px solid transparent',
    transition: 'all 0.1s',
  }),
  checkbox: (checked) => ({
    width: 16, height: 16, borderRadius: 4, flexShrink: 0,
    border: checked ? '2px solid var(--color-accent)' : '2px solid var(--color-text-muted)',
    background: checked ? 'var(--color-accent)' : 'transparent',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 10, color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-bold)',
  }),
  subName: { fontSize: 13, color: 'var(--color-text-body)', flex: 1 },
  resultTag: (result) => ({
    fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20, fontWeight: 'var(--font-weight-semibold)',
    color: RESULT_COLOR[result]?.color || 'var(--color-text-faint)',
    background: RESULT_COLOR[result]?.bg || 'var(--color-bg-surface)',
  }),
  projectMeta: { fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)' },
  selBar: {
    display: 'flex', alignItems: 'center', gap: 'var(--gap-md)',
    padding: '14px 20px', background: 'var(--color-bg-surface)',
    border: '1px solid var(--color-border)', borderRadius: 10, marginBottom: 4,
  },
  selCount: { fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', flex: 1 },
  selChip: {
    fontSize: 'var(--font-size-xs)', padding: '3px 10px', borderRadius: 20,
    background: 'var(--color-bg-surface-alt)', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)',
    display: 'flex', alignItems: 'center', gap: 5,
  },
  clearBtn: {
    background: 'none', border: 'none', color: 'var(--color-danger)',
    cursor: 'pointer', fontSize: 'var(--font-size-xs)', padding: 0,
  },
  runBtn: (active) => ({
    background: active ? 'var(--color-success)' : 'var(--color-success-bg)',
    color: active ? '#fff' : 'var(--color-text-muted)',
    border: 'none', borderRadius: 8, padding: '10px 24px',
    cursor: active ? 'pointer' : 'not-allowed',
    fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-bold)', transition: 'all 0.15s', whiteSpace: 'nowrap',
  }),
  empty: { color: 'var(--color-text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' },
}

function SelectionBar({ selected, onRemove, onClear, onRun, running }) {
  const canRun = selected.length >= 2 && !running
  return (
    <div style={s.selBar}>
      <div style={s.selCount}>
        선택된 제안서 <span style={{ color: selected.length >= 2 ? 'var(--color-success)' : 'var(--color-danger)' }}>{selected.length}</span>개
        {selected.length < 2 && <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', fontWeight: 'var(--font-weight-regular)', marginLeft: 6 }}>(최소 2개 필요)</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 3 }}>
        {selected.map(item => (
          <div key={`${item.competition_id}__${item.company}`} style={s.selChip}>
            <span style={{ color: 'var(--color-text-faint)' }}>{item.competition_name}</span>
            <span>·</span>
            <span>{item.company}</span>
            <button style={s.clearBtn} onClick={() => onRemove(item)}>✕</button>
          </div>
        ))}
      </div>
      {selected.length > 0 && (
        <button style={{ ...s.clearBtn, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)' }} onClick={onClear}>전체 해제</button>
      )}
      <button style={s.runBtn(canRun)} onClick={canRun ? onRun : undefined} disabled={!canRun}>
        {running ? '분석 중...' : '비교분석 실행'}
      </button>
    </div>
  )
}

function ProjectCard({ project, selected, onToggle }) {
  const { facilityLabel } = useMeta()
  const [open, setOpen] = useState(false)
  const subs = project.submissions || []

  return (
    <div style={s.card}>
      <div style={s.cardHeader} onClick={() => setOpen(v => !v)}>
        <span style={s.badge}>{facilityLabel(project.facility_type)}</span>
        <span style={s.cardName}>{project.competition_name || project.competition_id}</span>
        <span style={s.projectMeta}>{project.year}년 · 제안서 {subs.length}개</span>
        <span style={s.chevron(open)}>▼</span>
      </div>
      {open && (
        <div style={s.subList}>
          {subs.length === 0
            ? <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>제안서 없음</div>
            : subs.map(sub => {
                const key = `${project.competition_id}__${sub.company}`
                const checked = selected.some(s => s.competition_id === project.competition_id && s.company === sub.company)
                return (
                  <div key={key} style={s.subRow(checked)}
                    onClick={() => onToggle({
                      facility_type: project.facility_type,
                      competition_id: project.competition_id,
                      competition_name: project.competition_name || project.competition_id,
                      company: sub.company,
                      result: sub.result,
                    })}>
                    <div style={s.checkbox(checked)}>{checked ? '✓' : ''}</div>
                    <span style={s.subName}>{sub.company}</span>
                    <span style={s.resultTag(sub.result)}>
                      {RESULT_COLOR[sub.result]?.label || sub.result}
                    </span>
                  </div>
                )
              })
          }
        </div>
      )}
    </div>
  )
}

export default function CrossCompareMode() {
  const { facilityLabel } = useMeta()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeType, setActiveType] = useState(null)
  const [selected, setSelected] = useState([])
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)
  const [pastReports, setPastReports] = useState([])

  const loadPastReports = () => listCrossCompareReports().then(setPastReports).catch(() => {})

  useEffect(() => {
    getProjects().then(p => { setProjects(p); setLoading(false) })
    loadPastReports()
  }, [])

  const facilityTypes = [...new Set(projects.map(p => p.facility_type))]
  const currentType = activeType && facilityTypes.includes(activeType)
    ? activeType : facilityTypes[0] ?? null
  const filtered = projects.filter(p => p.facility_type === currentType)

  const toggle = (item) => {
    const key = `${item.competition_id}__${item.company}`
    setSelected(prev =>
      prev.some(s => `${s.competition_id}__${s.company}` === key)
        ? prev.filter(s => `${s.competition_id}__${s.company}` !== key)
        : [...prev, item]
    )
  }

  const run = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)
    try {
      for await (const ev of crossCompare(selected.map(({ facility_type, competition_id, company }) => ({ facility_type, competition_id, company })))) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') { setResult(ev); loadPastReports() }
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  return (
    <div style={s.wrap}>
      <div style={s.panel}>
        <div style={s.title}>프로젝트 교차 비교</div>
        <div style={s.desc}>
          저장된 프로젝트에서 제안서를 자유롭게 골라 비교분석합니다.<br />
          공모가 달라도 선택 가능합니다. 최소 2개 이상 선택 후 실행하세요.
        </div>

        <SelectionBar
          selected={selected}
          onRemove={item => toggle(item)}
          onClear={() => setSelected([])}
          onRun={run}
          running={running}
        />

        {loading ? (
          <div style={s.empty}>로딩 중...</div>
        ) : projects.length === 0 ? (
          <div style={s.empty}>저장된 프로젝트가 없습니다. 먼저 데이터 축적 탭에서 프로젝트를 추가하세요.</div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16, marginTop: 16 }}>
              {facilityTypes.map(ft => (
                <button key={ft} style={s.typeTab(ft === currentType)} onClick={() => setActiveType(ft)}>
                  {facilityLabel(ft)}
                  <span style={{ marginLeft: 5, opacity: 0.7 }}>
                    {projects.filter(p => p.facility_type === ft).length}
                  </span>
                </button>
              ))}
            </div>
            {filtered.map(p => (
              <ProjectCard key={p.competition_id} project={p} selected={selected} onToggle={toggle} />
            ))}
          </>
        )}
      </div>

      {events.length > 0 && (
        <div style={s.panel}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {pastReports.length > 0 && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', flex: 1 }}>
              저장된 교차비교 리포트 <span style={{ color: 'var(--color-text-muted)', fontWeight: 'var(--font-weight-regular)', fontSize: 'var(--font-size-sm)' }}>({pastReports.length})</span>
            </div>
            <button
              onClick={loadPastReports}
              style={{
                background: 'none', border: '1px solid var(--color-border)', borderRadius: 6,
                color: 'var(--color-text-muted)', padding: '4px 12px', cursor: 'pointer', fontSize: 'var(--font-size-sm)',
              }}
            >새로고침</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {pastReports.map(rep => (
              <a
                key={rep.filename}
                href={getCrossCompareReportUrl(rep.filename)}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--gap-md)',
                  padding: '10px 14px', background: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)', borderRadius: 6,
                  textDecoration: 'none', transition: 'all 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--color-accent-hover)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--color-border)'}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: 'var(--color-text-body)', fontWeight: 'var(--font-weight-medium)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {rep.labels.join('  vs  ')}
                  </div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginTop: 3 }}>
                    {rep.created_at}
                  </div>
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-accent)' }}>열기 →</div>
              </a>
            ))}
          </div>
        </div>
      )}

      {result?.comparison && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 'var(--gap-md)' }}>
            <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', flex: 1 }}>비교분석 결과</div>
            {result.report_filename && (
              <a
                href={getCrossCompareReportUrl(result.report_filename)}
                target="_blank"
                rel="noreferrer"
                style={{
                  background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', borderRadius: 6,
                  padding: '6px 14px', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
                  textDecoration: 'none',
                }}
              >
                HTML 리포트 열기
              </a>
            )}
          </div>
          <ComparisonDashboard
            comparison={result.comparison}
            submissionMeta={selected.map(s => ({ company: s.company, result: s.result }))}
          />
        </div>
      )}
    </div>
  )
}
