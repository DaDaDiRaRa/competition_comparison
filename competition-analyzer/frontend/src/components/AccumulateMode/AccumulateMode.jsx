import { useState, useEffect } from 'react'
import { getFacilityTypes, runAccumulatePipeline, getReportUrl } from '../../api/client'
import DropZone from '../common/DropZone'
import ProgressLog from '../common/ProgressLog'
import PageDistChart from '../common/PageDistChart'
import ComparisonDashboard from './ComparisonDashboard'
import ProjectList from './ProjectList'

const s = {
  panel: { background: '#1a1f2e', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, marginBottom: 20, color: '#e2e8f0' },
  label: { fontSize: 13, color: '#a0aec0', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 14,
  },
  select: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 14,
  },
  group: { marginBottom: 14 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  btn: {
    background: '#2f855a', color: '#fff', border: 'none', borderRadius: 6,
    padding: '12px 28px', cursor: 'pointer', fontSize: 15, fontWeight: 600,
    marginTop: 16, width: '100%',
  },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  section: { marginTop: 20, borderTop: '1px solid #2d3748', paddingTop: 16 },
  sectionTitle: { fontSize: 15, fontWeight: 600, color: '#90cdf4', marginBottom: 12 },
  subCard: {
    background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8,
    padding: 16, marginBottom: 12,
  },
  subHeader: { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 10 },
  tag: {
    fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600,
    background: '#2f855a', color: '#fff',
  },
  tagLose: { background: '#742a2a' },
}

function SubmissionInput({ idx, onChange, onRemove }) {
  const [company, setCompany] = useState('')
  const [result, setResult] = useState('lose')
  const [file, setFile] = useState(null)

  const update = (c, r, f) => {
    onChange(idx, { company: c, result: r, file: f })
  }

  return (
    <div style={s.subCard}>
      <div style={s.subHeader}>
        <span style={{ color: '#a0aec0', fontSize: 13 }}>제안서 {idx + 1}</span>
        <button onClick={() => onRemove(idx)}
          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#fc8181', cursor: 'pointer', fontSize: 18 }}>
          ×
        </button>
      </div>
      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>회사명</label>
          <input style={s.input} value={company}
            onChange={e => { setCompany(e.target.value); update(e.target.value, result, file) }}
            placeholder="예: 군원건축" />
        </div>
        <div style={s.group}>
          <label style={s.label}>당선 여부</label>
          <select style={s.select} value={result}
            onChange={e => { setResult(e.target.value); update(company, e.target.value, file) }}>
            <option value="win">당선</option>
            <option value="lose">낙선</option>
          </select>
        </div>
      </div>
      <DropZone label="제안서 PDF" onFiles={f => { setFile(f); update(company, result, f) }} />
      {file && <div style={{ fontSize: 12, color: '#68d391', marginTop: 4 }}>✓ {file.name}</div>}
      {result === 'win' && (
        <div style={{ ...s.tag, display: 'inline-block', marginTop: 8 }}>당선작</div>
      )}
    </div>
  )
}

export default function AccumulateMode() {
  const [facilityTypes, setFacilityTypes] = useState({})
  const [form, setForm] = useState({
    competition_name: '', facility_type: 'public',
    year: new Date().getFullYear(), client: '', location: '',
  })
  const [briefFile, setBriefFile] = useState(null)
  const [submissions, setSubmissions] = useState([{ company: '', result: 'lose', file: null }])
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)

  useEffect(() => {
    getFacilityTypes().then(setFacilityTypes)
  }, [])

  const setFormField = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const updateSub = (idx, data) => {
    setSubmissions(prev => prev.map((s, i) => i === idx ? { ...s, ...data } : s))
  }
  const addSub = () => setSubmissions(prev => [...prev, { company: '', result: 'lose', file: null }])
  const removeSub = (idx) => setSubmissions(prev => prev.filter((_, i) => i !== idx))

  const canRun = briefFile && submissions.every(s => s.company && s.file) && !running

  const runPipeline = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)

    const fd = new FormData()
    fd.append('competition_name', form.competition_name)
    fd.append('facility_type', form.facility_type)
    fd.append('year', form.year)
    fd.append('client', form.client)
    fd.append('location', form.location)
    fd.append('brief_pdf', briefFile)
    fd.append('submissions_json', JSON.stringify(
      submissions.map(s => ({ company: s.company, result: s.result }))
    ))
    submissions.forEach(s => fd.append('submission_pdfs', s.file))

    try {
      for await (const ev of runAccumulatePipeline(fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') setResult(ev)
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  return (
    <>
    <ProjectList />
    <div style={s.panel}>
      <div style={s.title}>데이터 축적 모드</div>

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>공모명</label>
          <input style={s.input} value={form.competition_name}
            onChange={e => setFormField('competition_name', e.target.value)}
            placeholder="예: 영등포구 신청사 건립 설계공모" />
        </div>
        <div style={s.group}>
          <label style={s.label}>시설유형</label>
          <select style={s.select} value={form.facility_type}
            onChange={e => setFormField('facility_type', e.target.value)}>
            {Object.entries(facilityTypes).map(([k, v]) => (
              <option key={k} value={k}>{v} ({k})</option>
            ))}
          </select>
        </div>
        <div style={s.group}>
          <label style={s.label}>연도</label>
          <input style={s.input} type="number" value={form.year}
            onChange={e => setFormField('year', Number(e.target.value))} />
        </div>
        <div style={s.group}>
          <label style={s.label}>발주처</label>
          <input style={s.input} value={form.client}
            onChange={e => setFormField('client', e.target.value)} />
        </div>
      </div>

      <div style={s.group}>
        <label style={s.label}>대지위치</label>
        <input style={s.input} value={form.location}
          onChange={e => setFormField('location', e.target.value)}
          placeholder="예: 서울시 영등포구 당산동" />
      </div>

      <div style={s.section}>
        <div style={s.sectionTitle}>지침서 PDF</div>
        <DropZone label="지침서 PDF 드래그 또는 클릭" onFiles={setBriefFile} />
      </div>

      <div style={s.section}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
          <div style={s.sectionTitle}>제안서 PDF</div>
          <button onClick={addSub}
            style={{ marginLeft: 'auto', background: '#2b6cb0', color: '#fff', border: 'none',
              borderRadius: 6, padding: '6px 14px', cursor: 'pointer', fontSize: 13 }}>
            + 추가
          </button>
        </div>
        {submissions.map((sub, idx) => (
          <SubmissionInput key={idx} idx={idx} onChange={updateSub}
            onRemove={submissions.length > 1 ? removeSub : () => {}} />
        ))}
      </div>

      <button
        style={{ ...s.btn, ...(canRun ? {} : s.btnDisabled) }}
        onClick={canRun ? runPipeline : undefined}
        disabled={!canRun}
      >
        {running ? '분석 중...' : '분석 시작'}
      </button>

      {(events.length > 0) && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
            <div style={s.sectionTitle}>분석 결과</div>
            {result.report_available && (
              <a
                href={getReportUrl(result.facility_type, result.competition_id)}
                target="_blank"
                rel="noreferrer"
                style={{
                  marginLeft: 'auto', background: '#2b6cb0', color: '#fff',
                  borderRadius: 6, padding: '7px 16px', fontSize: 13, fontWeight: 600,
                  textDecoration: 'none', display: 'inline-block',
                }}
              >
                HTML 비교 리포트 열기
              </a>
            )}
          </div>
          {result.submissions?.map(sub => (
            <div key={sub.company} style={s.subCard}>
              <div style={s.subHeader}>
                <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{sub.company}</span>
                <span style={{ ...s.tag, ...(sub.result === 'lose' ? s.tagLose : {}) }}>
                  {sub.result === 'win' ? '당선' : '낙선'}
                </span>
                <span style={{ color: '#a0aec0', fontSize: 13 }}>{sub.total_pages}페이지</span>
              </div>
              <PageDistChart distribution={sub.page_distribution} total={sub.total_pages} />
            </div>
          ))}
          {result.comparison && (
            <ComparisonDashboard
              comparison={result.comparison}
              submissionMeta={result.submissions}
            />
          )}
        </div>
      )}
    </div>
    </>
  )
}
