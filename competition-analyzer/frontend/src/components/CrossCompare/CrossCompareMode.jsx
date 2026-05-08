import { useState, useEffect } from 'react'
import { getProjects, crossCompare, getCrossCompareReportUrl, listCrossCompareReports } from '../../api/client'
import ProgressLog from '../common/ProgressLog'
import ComparisonDashboard from '../AccumulateMode/ComparisonDashboard'

const FACILITY_KR = {
  public: '공공청사', residential: '공동주택', office: '업무시설',
  culture: '문화시설', education: '교육시설', medical: '의료시설',
  sports: '체육시설', religious: '종교시설', commercial: '상업시설',
  industrial: '산업시설', mixed: '복합시설', other: '기타',
  reconstruction: '재건축사업', alternative: '대안설계',
}

const RESULT_COLOR = {
  win: { color: '#d4af37', bg: '#2d2410', label: '당선' },
  contracted: { color: '#68d391', bg: '#1a2e1a', label: '수의계약' },
  lose: { color: '#718096', bg: '#1a1f2e', label: '낙선' },
}

const s = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  panel: { background: '#1a1f2e', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, color: '#e2e8f0', marginBottom: 6 },
  desc: { fontSize: 13, color: '#718096', lineHeight: 1.6, marginBottom: 20 },
  typeTab: (active) => ({
    padding: '5px 14px', borderRadius: 20, fontSize: 12, fontWeight: 600,
    cursor: 'pointer', border: 'none',
    background: active ? '#90cdf4' : '#2d3748',
    color: active ? '#0d1117' : '#a0aec0',
  }),
  card: {
    background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 8, marginBottom: 8,
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '12px 14px', cursor: 'pointer', userSelect: 'none',
  },
  cardName: { fontWeight: 600, color: '#e2e8f0', fontSize: 14, flex: 1 },
  badge: {
    fontSize: 11, padding: '2px 8px', borderRadius: 20,
    background: '#2b4c7e', color: '#90cdf4', fontWeight: 600,
  },
  chevron: (open) => ({
    color: '#4a5568', fontSize: 12, transform: open ? 'rotate(180deg)' : 'none',
    transition: 'transform 0.15s',
  }),
  subList: { borderTop: '1px solid #2d3748', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 },
  subRow: (checked) => ({
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
    borderRadius: 6, cursor: 'pointer',
    background: checked ? '#1a2535' : 'transparent',
    border: checked ? '1px solid #2b6cb0' : '1px solid transparent',
    transition: 'all 0.1s',
  }),
  checkbox: (checked) => ({
    width: 16, height: 16, borderRadius: 4, flexShrink: 0,
    border: checked ? '2px solid #90cdf4' : '2px solid #4a5568',
    background: checked ? '#90cdf4' : 'transparent',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 10, color: '#0d1117', fontWeight: 700,
  }),
  subName: { fontSize: 13, color: '#e2e8f0', flex: 1 },
  resultTag: (result) => ({
    fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600,
    color: RESULT_COLOR[result]?.color || '#718096',
    background: RESULT_COLOR[result]?.bg || '#1a1f2e',
  }),
  projectMeta: { fontSize: 11, color: '#4a5568' },
  selBar: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '14px 20px', background: '#0d1117',
    border: '1px solid #2d3748', borderRadius: 10, marginBottom: 4,
  },
  selCount: { fontSize: 14, fontWeight: 600, color: '#90cdf4', flex: 1 },
  selChip: {
    fontSize: 11, padding: '3px 10px', borderRadius: 20,
    background: '#1a2535', color: '#a0aec0', border: '1px solid #2d3748',
    display: 'flex', alignItems: 'center', gap: 5,
  },
  clearBtn: {
    background: 'none', border: 'none', color: '#fc8181',
    cursor: 'pointer', fontSize: 11, padding: 0,
  },
  runBtn: (active) => ({
    background: active ? '#2f855a' : '#1a2e1a',
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
        선택된 제안서 <span style={{ color: selected.length >= 2 ? '#68d391' : '#fc8181' }}>{selected.length}</span>개
        {selected.length < 2 && <span style={{ fontSize: 12, color: '#4a5568', fontWeight: 400, marginLeft: 6 }}>(최소 2개 필요)</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 3 }}>
        {selected.map(item => (
          <div key={`${item.competition_id}__${item.company}`} style={s.selChip}>
            <span style={{ color: '#718096' }}>{item.competition_name}</span>
            <span>·</span>
            <span>{item.company}</span>
            <button style={s.clearBtn} onClick={() => onRemove(item)}>✕</button>
          </div>
        ))}
      </div>
      {selected.length > 0 && (
        <button style={{ ...s.clearBtn, fontSize: 12, color: '#718096' }} onClick={onClear}>전체 해제</button>
      )}
      <button style={s.runBtn(canRun)} onClick={canRun ? onRun : undefined} disabled={!canRun}>
        {running ? '분석 중...' : '비교분석 실행'}
      </button>
    </div>
  )
}

function ProjectCard({ project, selected, onToggle }) {
  const [open, setOpen] = useState(false)
  const subs = project.submissions || []

  return (
    <div style={s.card}>
      <div style={s.cardHeader} onClick={() => setOpen(v => !v)}>
        <span style={s.badge}>{FACILITY_KR[project.facility_type] || project.facility_type}</span>
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
                  {FACILITY_KR[ft] || ft}
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
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {pastReports.length > 0 && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', flex: 1 }}>
              저장된 교차비교 리포트 <span style={{ color: '#4a5568', fontWeight: 400, fontSize: 12 }}>({pastReports.length})</span>
            </div>
            <button
              onClick={loadPastReports}
              style={{
                background: 'none', border: '1px solid #2d3748', borderRadius: 6,
                color: '#a0aec0', padding: '4px 12px', cursor: 'pointer', fontSize: 12,
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
                  padding: '10px 14px', background: '#0d1117',
                  border: '1px solid #2d3748', borderRadius: 6,
                  textDecoration: 'none', transition: 'all 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = '#2c5282'}
                onMouseLeave={e => e.currentTarget.style.borderColor = '#2d3748'}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: '#e2e8f0', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {rep.labels.join('  vs  ')}
                  </div>
                  <div style={{ fontSize: 11, color: '#4a5568', marginTop: 3 }}>
                    {rep.created_at}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: '#90cdf4' }}>열기 →</div>
              </a>
            ))}
          </div>
        </div>
      )}

      {result?.comparison && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 12 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#90cdf4', flex: 1 }}>비교분석 결과</div>
            {result.report_filename && (
              <a
                href={getCrossCompareReportUrl(result.report_filename)}
                target="_blank"
                rel="noreferrer"
                style={{
                  background: '#44337a', color: '#e9d8fd', borderRadius: 6,
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
