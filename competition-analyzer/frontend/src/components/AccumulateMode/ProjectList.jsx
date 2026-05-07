import { useState, useEffect } from 'react'
import { getProjects, rerunCompare, getReportUrl } from '../../api/client'
import ProgressLog from '../common/ProgressLog'

const FACILITY_KR = {
  public: '공공청사', residential: '공동주택', office: '업무시설',
  culture: '문화시설', education: '교육시설', medical: '의료시설',
  sports: '체육시설', religious: '종교시설', commercial: '상업시설',
  industrial: '산업시설', mixed: '복합시설', other: '기타',
}

const s = {
  panel: { background: '#1a1f2e', borderRadius: 12, padding: 24, marginBottom: 16 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  title: { fontSize: 16, fontWeight: 600, color: '#90cdf4' },
  refreshBtn: {
    background: 'none', border: '1px solid #2d3748', borderRadius: 6,
    color: '#a0aec0', padding: '4px 12px', cursor: 'pointer', fontSize: 12,
  },
  empty: { color: '#4a5568', fontSize: 13, textAlign: 'center', padding: '20px 0' },
  card: {
    background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8,
    padding: '14px 16px', marginBottom: 10,
  },
  cardHeader: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 },
  cardName: { fontWeight: 600, color: '#e2e8f0', fontSize: 14 },
  badge: {
    fontSize: 11, padding: '2px 8px', borderRadius: 20,
    background: '#2b4c7e', color: '#90cdf4', fontWeight: 600,
  },
  meta: { fontSize: 12, color: '#718096' },
  actions: { display: 'flex', gap: 8, marginTop: 10 },
  rerunBtn: {
    background: '#2f855a', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  reportBtn: {
    background: '#2b6cb0', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
    textDecoration: 'none', display: 'inline-block',
  },
  disabledBtn: { opacity: 0.5, cursor: 'not-allowed' },
  logWrap: { marginTop: 10 },
}

function ProjectCard({ project, onRerunDone }) {
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(false)

  const hasReport = project.report_available

  const handleRerun = async () => {
    setRunning(true)
    setEvents([])
    setDone(false)
    const startTime = Date.now()
    try {
      for await (const ev of rerunCompare(project.facility_type, project.competition_id)) {
        setEvents(prev => [...prev, { ...ev, _timestamp: startTime }])
        if (ev.type === 'complete') { setDone(true); onRerunDone?.() }
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message, _timestamp: startTime }])
    }
    setRunning(false)
  }

  const subs = project.submissions || []
  const winCount = subs.filter(s => s.result === 'win').length

  return (
    <div style={s.card}>
      <div style={s.cardHeader}>
        <span style={s.badge}>{FACILITY_KR[project.facility_type] || project.facility_type}</span>
        <span style={s.cardName}>{project.competition_name || project.competition_id}</span>
      </div>
      <div style={s.meta}>
        {project.year}년 · {project.client || '-'} · 제안서 {subs.length}개 (당선 {winCount}개)
      </div>
      <div style={s.actions}>
        <button
          style={{ ...s.rerunBtn, ...(running ? s.disabledBtn : {}) }}
          onClick={running ? undefined : handleRerun}
          disabled={running}
        >
          {running ? '분석 중...' : '비교분석 재실행'}
        </button>
        {(hasReport || done) && (
          <a
            href={getReportUrl(project.facility_type, project.competition_id)}
            target="_blank"
            rel="noreferrer"
            style={s.reportBtn}
          >
            HTML 리포트 열기
          </a>
        )}
      </div>
      {events.length > 0 && (
        <div style={s.logWrap}>
          <ProgressLog events={events} />
        </div>
      )}
    </div>
  )
}

export default function ProjectList() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    getProjects().then(p => { setProjects(p); setLoading(false) })
  }

  useEffect(() => { load() }, [])

  return (
    <div style={s.panel}>
      <div style={s.header}>
        <div style={s.title}>저장된 프로젝트</div>
        <button style={s.refreshBtn} onClick={load}>새로고침</button>
      </div>
      {loading
        ? <div style={s.empty}>로딩 중...</div>
        : projects.length === 0
          ? <div style={s.empty}>저장된 프로젝트가 없습니다.</div>
          : projects.map(p => (
              <ProjectCard key={p.competition_id} project={p} onRerunDone={load} />
            ))
      }
    </div>
  )
}
