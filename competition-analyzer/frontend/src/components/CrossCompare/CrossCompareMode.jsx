import { useState, useEffect } from 'react'
import { getProjects, crossCompare, getCrossCompareReportUrl, listCrossCompareReports } from '../../api/client'
import ProgressLog from '../common/ProgressLog'
import ComparisonDashboard from '../AccumulateMode/ComparisonDashboard'
import { useMeta } from '../../hooks/useMeta'

const RESULT_COLOR = {
  win: { color: '#b8860b', bg: '#fef3c7', label: '당선' },
  contracted: { color: '#16a34a', bg: '#dcfce7', label: '수의계약' },
  lose: { color: '#6b7280', bg: '#ffffff', label: '낙선' },
}

const s = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  panel: { background: '#ffffff', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, color: '#1f2937', marginBottom: 6 },
  desc: { fontSize: 13, color: '#6b7280', lineHeight: 1.6, marginBottom: 20 },
  typeTab: (active) => ({
    padding: '5px 14px', borderRadius: 20, fontSize: 12, fontWeight: 600,
    cursor: 'pointer', border: 'none',
    background: active ? '#1e3a8a' : '#e5e7eb',
    color: active ? '#ffffff' : '#4b5563',
  }),
  card: {
    background: '#ffffff', border: '1px solid #e5e7eb',
    borderRadius: 8, marginBottom: 8,
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '12px 14px', cursor: 'pointer', userSelect: 'none',
  },
  cardName: { fontWeight: 600, color: '#1f2937', fontSize: 14, flex: 1 },
  badge: {
    fontSize: 11, padding: '2px 8px', borderRadius: 20,
    background: '#1e40af', color: '#1e3a8a', fontWeight: 600,
  },
  chevron: (open) => ({
    color: '#4a5568', fontSize: 12, transform: open ? 'rotate(180deg)' : 'none',
    transition: 'transform 0.15s',
  }),
  subList: { borderTop: '1px solid #e5e7eb', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 },
  subRow: (checked) => ({
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
    borderRadius: 6, cursor: 'pointer',
    background: checked ? '#f9fafb' : 'transparent',
    border: checked ? '1px solid #1e3a8a' : '1px solid transparent',
    transition: 'all 0.1s',
  }),
  checkbox: (checked) => ({
    width: 16, height: 16, borderRadius: 4, flexShrink: 0,
    border: checked ? '2px solid #1e3a8a' : '2px solid #4a5568',
    background: checked ? '#1e3a8a' : 'transparent',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 10, color: '#ffffff', fontWeight: 700,
  }),
  subName: { fontSize: 13, color: '#1f2937', flex: 1 },
  resultTag: (result) => ({
    fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600,
    color: RESULT_COLOR[result]?.color || '#6b7280',
    background: RESULT_COLOR[result]?.bg || '#ffffff',
  }),
  projectMeta: { fontSize: 11, color: '#4a5568' },
  selBar: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '14px 20px', background: '#ffffff',
    border: '1px solid #e5e7eb', borderRadius: 10, marginBottom: 4,
  },
  selCount: { fontSize: 14, fontWeight: 600, color: '#1e3a8a', flex: 1 },
  selChip: {
    fontSize: 11, padding: '3px 10px', borderRadius: 20,
    background: '#f9fafb', color: '#4b5563', border: '1px solid #e5e7eb',
    display: 'flex', alignItems: 'center', gap: 5,
  },
  clearBtn: {
    background: 'none', border: 'none', color: '#dc2626',
    cursor: 'pointer', fontSize: 11, padding: 0,
  },
  runBtn: (active) => ({
    background: active ? '#15803d' : '#dcfce7',
    color: active ? '#fff' : '#4a5568',
    border: 'none', borderRadius: 8, padding: '10px 24px',
    cursor: active ? 'pointer' : 'not-allowed',
    fontSize: 14, fontWeight: 700, transition: 'all 0.15s', whiteSpace: 'nowrap',
  }),
  empty: { color: '#4a5568', fontSize: 13, textAlign: 'center', padding: '20px 0' },
}

function SelectionBar({ selected, onRemove, onClear, onRun, running }) {
  const canRun = selected.length >= 2 && !running
  return (
    <div style={s.selBar}>
      <div style={s.selCount}>
        선택된 제안서 <span style={{ color: selected.length >= 2 ? '#16a34a' : '#dc2626' }}>{selected.length}</span>개
        {selected.length < 2 && <span style={{ fontSize: 12, color: '#4a5568', fontWeight: 400, marginLeft: 6 }}>(최소 2개 필요)</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 3 }}>
        {selected.map(item => (
          <div key={`${item.competition_id}__${item.company}`} style={s.selChip}>
            <span style={{ color: '#6b7280' }}>{item.competition_name}</span>
            <span>·</span>
            <span>{item.company}</span>
            <button style={s.clearBtn} onClick={() => onRemove(item)}>✕</button>
          </div>
        ))}
      </div>
      {selected.length > 0 && (
        <button style={{ ...s.clearBtn, fontSize: 12, color: '#6b7280' }} onClick={onClear}>전체 해제</button>
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
            ? <div style={{ fontSize: 12, color: '#4a5568' }}>제안서 없음</div>
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
          <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {pastReports.length > 0 && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#1f2937', flex: 1 }}>
              저장된 교차비교 리포트 <span style={{ color: '#4a5568', fontWeight: 400, fontSize: 12 }}>({pastReports.length})</span>
            </div>
            <button
              onClick={loadPastReports}
              style={{
                background: 'none', border: '1px solid #e5e7eb', borderRadius: 6,
                color: '#4b5563', padding: '4px 12px', cursor: 'pointer', fontSize: 12,
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
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 14px', background: '#ffffff',
                  border: '1px solid #e5e7eb', borderRadius: 6,
                  textDecoration: 'none', transition: 'all 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = '#1e40af'}
                onMouseLeave={e => e.currentTarget.style.borderColor = '#e5e7eb'}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: '#1f2937', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {rep.labels.join('  vs  ')}
                  </div>
                  <div style={{ fontSize: 11, color: '#4a5568', marginTop: 3 }}>
                    {rep.created_at}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: '#1e3a8a' }}>열기 →</div>
              </a>
            ))}
          </div>
        </div>
      )}

      {result?.comparison && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 12 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#1e3a8a', flex: 1 }}>비교분석 결과</div>
            {result.report_filename && (
              <a
                href={getCrossCompareReportUrl(result.report_filename)}
                target="_blank"
                rel="noreferrer"
                style={{
                  background: '#6d28d9', color: '#ede9fe', borderRadius: 6,
                  padding: '6px 14px', fontSize: 12, fontWeight: 600,
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
