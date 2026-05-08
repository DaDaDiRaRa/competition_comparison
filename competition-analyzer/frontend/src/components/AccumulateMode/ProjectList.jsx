import { useState, useEffect } from 'react'
import { getProjects, rerunCompare, rerenderReport, getReportUrl, getSubmissionReportUrl, addSubmission } from '../../api/client'
import ProgressLog from '../common/ProgressLog'
import DropZone from '../common/DropZone'

const FACILITY_KR = {
  public: '공공청사', residential: '공동주택', office: '업무시설',
  culture: '문화시설', education: '교육시설', medical: '의료시설',
  sports: '체육시설', religious: '종교시설', commercial: '상업시설',
  industrial: '산업시설', mixed: '복합시설', other: '기타',
  reconstruction: '재건축사업', alternative: '대안설계',
}

const RESULT_OPTIONS = [
  { value: 'win', label: '당선', color: '#d4af37', bg: '#2d2410' },
  { value: 'contracted', label: '수의계약', color: '#68d391', bg: '#1a2e1a' },
  { value: 'lose', label: '낙선', color: '#718096', bg: '#1a1f2e' },
]

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
  actions: { display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' },
  rerunBtn: {
    background: '#2f855a', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  addBtn: {
    background: '#2b6cb0', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  reportBtn: {
    background: '#44337a', color: '#e9d8fd', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
    textDecoration: 'none', display: 'inline-block',
  },
  rerenderBtn: {
    background: 'transparent', color: '#a0aec0',
    border: '1px solid #4a5568', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  subReportBtn: {
    background: '#1a2e40', color: '#90cdf4', border: '1px solid #2c5282', borderRadius: 6,
    padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600,
    textDecoration: 'none', display: 'inline-block',
  },
  disabledBtn: { opacity: 0.5, cursor: 'not-allowed' },
  logWrap: { marginTop: 10 },
  addForm: {
    marginTop: 12, padding: 14, background: '#111827',
    border: '1px solid #2d3748', borderRadius: 8,
  },
  addFormTitle: { fontSize: 13, fontWeight: 600, color: '#90cdf4', marginBottom: 10 },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 },
  label: { fontSize: 12, color: '#a0aec0', marginBottom: 4, display: 'block' },
  input: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '7px 10px', color: '#e2e8f0', fontSize: 13,
    boxSizing: 'border-box',
  },
  resultPicker: { display: 'flex', gap: 6 },
  resultBtn: (opt, selected) => ({
    flex: 1, padding: '6px 0', borderRadius: 6, cursor: 'pointer', fontSize: 12,
    fontWeight: 600, textAlign: 'center',
    border: selected ? `2px solid ${opt.color}` : '2px solid #2d3748',
    background: selected ? opt.bg : '#0d1117',
    color: selected ? opt.color : '#4a5568',
  }),
  submitBtn: (active) => ({
    width: '100%', marginTop: 10, padding: '9px 0', borderRadius: 6,
    border: 'none', cursor: active ? 'pointer' : 'not-allowed', fontSize: 13,
    fontWeight: 700, background: active ? '#2b6cb0' : '#1a2535', color: active ? '#fff' : '#4a5568',
  }),
  cancelBtn: {
    background: 'none', border: 'none', color: '#718096', cursor: 'pointer',
    fontSize: 12, marginLeft: 'auto',
  },
}

function AddSubmissionForm({ project, onDone, onCancel }) {
  const [company, setCompany] = useState('')
  const [result, setResult] = useState('lose')
  const [file, setFile] = useState(null)
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(false)

  const canSubmit = company && file && !running && !done

  const handleSubmit = async () => {
    setRunning(true)
    setEvents([])
    const fd = new FormData()
    fd.append('company', company)
    fd.append('result', result)
    fd.append('submission_pdf', file)

    try {
      for await (const ev of addSubmission(project.facility_type, project.competition_id, fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') { setDone(true); onDone?.() }
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  return (
    <div style={s.addForm}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
        <span style={s.addFormTitle}>제안서 추가</span>
        {!running && <button style={s.cancelBtn} onClick={onCancel}>✕ 닫기</button>}
      </div>

      {!done && (
        <>
          <div style={s.row}>
            <div>
              <label style={s.label}>회사명</label>
              <input style={s.input} value={company}
                onChange={e => setCompany(e.target.value)}
                placeholder="예: 군원건축" disabled={running} />
            </div>
            <div>
              <label style={s.label}>결과</label>
              <div style={s.resultPicker}>
                {RESULT_OPTIONS.map(opt => (
                  <div key={opt.value} style={s.resultBtn(opt, result === opt.value)}
                    onClick={() => !running && setResult(opt.value)}>
                    {opt.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DropZone label="제안서 PDF 드래그 또는 클릭" onFiles={setFile} />
          {file && <div style={{ fontSize: 11, color: '#68d391', marginTop: 4 }}>✓ {file.name}</div>}
          <button style={s.submitBtn(canSubmit)} onClick={canSubmit ? handleSubmit : undefined}>
            {running ? '처리 중...' : '추출 시작'}
          </button>
        </>
      )}

      {events.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <ProgressLog events={events} />
        </div>
      )}

      {done && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#68d391' }}>
          ✓ {company} 제안서 저장 완료. 비교분석 재실행 버튼으로 분석을 갱신하세요.
        </div>
      )}
    </div>
  )
}

function ProjectCard({ project, onRerunDone }) {
  const [running, setRunning] = useState(false)
  const [rerendering, setRerendering] = useState(false)
  const [rerenderMsg, setRerenderMsg] = useState('')
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

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

  const handleRerender = async () => {
    setRerendering(true)
    setRerenderMsg('')
    try {
      const r = await rerenderReport(project.facility_type, project.competition_id)
      setRerenderMsg(`✓ 리포트 재생성 완료 (개별 ${r.submission_reports_regenerated}개)`)
      onRerunDone?.()
    } catch (e) {
      setRerenderMsg(`✗ ${e.message}`)
    }
    setRerendering(false)
    setTimeout(() => setRerenderMsg(''), 4000)
  }

  const subs = project.submissions || []
  const winCount = subs.filter(s => s.result === 'win' || s.result === 'contracted').length
  const RESULT_KR = { win: '★ 당선', contracted: '◆ 수의계약', lose: '낙선' }
  const RESULT_COLOR = { win: '#d4af37', contracted: '#68d391', lose: '#718096' }

  return (
    <div style={s.card}>
      <div style={s.cardHeader}>
        <span style={s.badge}>{FACILITY_KR[project.facility_type] || project.facility_type}</span>
        <span style={s.cardName}>{project.competition_name || project.competition_id}</span>
      </div>
      <div style={s.meta}>
        {project.year}년 · {project.client || '-'} · 제안서 {subs.length}개 (당선 {winCount}개)
      </div>

      {subs.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {subs.map(sub => (
            <div key={sub.company} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 12, color: RESULT_COLOR[sub.result] || '#a0aec0' }}>
                {RESULT_KR[sub.result] || sub.result}
              </span>
              <span style={{ fontSize: 12, color: '#e2e8f0' }}>{sub.company}</span>
              {sub.has_sub_report && (
                <a
                  href={getSubmissionReportUrl(project.facility_type, project.competition_id, sub.company)}
                  target="_blank"
                  rel="noreferrer"
                  style={s.subReportBtn}
                >
                  리포트
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={s.actions}>
        <button
          style={{ ...s.rerunBtn, ...(running ? s.disabledBtn : {}) }}
          onClick={running ? undefined : handleRerun}
          disabled={running}
        >
          {running ? '분석 중...' : '비교분석 실행'}
        </button>
        <button
          style={{ ...s.addBtn, ...(running ? s.disabledBtn : {}) }}
          onClick={running ? undefined : () => setShowAdd(v => !v)}
          disabled={running}
        >
          {showAdd ? '추가 닫기' : '+ 제안서 추가'}
        </button>
        {(hasReport || done) && (
          <>
            <a
              href={getReportUrl(project.facility_type, project.competition_id)}
              target="_blank"
              rel="noreferrer"
              style={s.reportBtn}
            >
              비교 리포트 열기
            </a>
            <button
              style={{ ...s.rerenderBtn, ...(rerendering || running ? s.disabledBtn : {}) }}
              onClick={(rerendering || running) ? undefined : handleRerender}
              disabled={rerendering || running}
              title="LLM 재호출 없이 HTML만 재생성 (토큰 0)"
            >
              {rerendering ? '재생성 중...' : '리포트만 재생성'}
            </button>
          </>
        )}
      </div>
      {rerenderMsg && (
        <div style={{ marginTop: 8, fontSize: 12,
                      color: rerenderMsg.startsWith('✓') ? '#68d391' : '#fc8181' }}>
          {rerenderMsg}
        </div>
      )}

      {showAdd && (
        <AddSubmissionForm
          project={project}
          onDone={() => { onRerunDone?.() }}
          onCancel={() => setShowAdd(false)}
        />
      )}

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
  const [selectedType, setSelectedType] = useState(null)

  const load = () => {
    setLoading(true)
    getProjects().then(p => { setProjects(p); setLoading(false) })
  }

  useEffect(() => { load() }, [])

  // 실제 존재하는 시설 유형만 추출 (순서 유지)
  const facilityTypes = [...new Set(projects.map(p => p.facility_type))]
  const activeType = selectedType && facilityTypes.includes(selectedType)
    ? selectedType
    : facilityTypes[0] ?? null

  const filtered = projects.filter(p => p.facility_type === activeType)

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
          : <>
              {/* 시설 유형 탭 */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                {facilityTypes.map(ft => (
                  <button
                    key={ft}
                    onClick={() => setSelectedType(ft)}
                    style={{
                      padding: '5px 14px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                      cursor: 'pointer', border: 'none',
                      background: ft === activeType ? '#90cdf4' : '#2d3748',
                      color: ft === activeType ? '#0d1117' : '#a0aec0',
                    }}
                  >
                    {FACILITY_KR[ft] || ft}
                    <span style={{ marginLeft: 5, opacity: 0.7 }}>
                      {projects.filter(p => p.facility_type === ft).length}
                    </span>
                  </button>
                ))}
              </div>

              {/* 선택된 시설 유형의 프로젝트 목록 */}
              {filtered.map(p => (
                <ProjectCard key={p.competition_id} project={p} onRerunDone={load} />
              ))}
            </>
      }
    </div>
  )
}
