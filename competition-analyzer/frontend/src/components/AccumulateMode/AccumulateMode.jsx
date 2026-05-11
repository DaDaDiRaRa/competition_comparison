import { useState, useEffect } from 'react'
import { getFacilityTypes, runAccumulatePipeline } from '../../api/client'
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
            placeholder="예: kunwon" />
        </div>
        <div style={s.group}>
          <label style={s.label}>결과</label>
          <select style={s.select} value={result}
            onChange={e => { setResult(e.target.value); update(company, e.target.value, file) }}>
            <option value="win">당선</option>
            <option value="contracted">수의계약</option>
            <option value="lose">낙선</option>
          </select>
        </div>
      </div>
      <DropZone label="제안서 PDF" onFiles={f => { setFile(f); update(company, result, f) }} />
      {file && <div style={{ fontSize: 12, color: '#68d391', marginTop: 4 }}>✓ {file.name}</div>}
      {(result === 'win' || result === 'contracted') && (
        <div style={{ ...s.tag, display: 'inline-block', marginTop: 8,
          background: result === 'contracted' ? '#2b6cb0' : '#2f855a' }}>
          {result === 'win' ? '당선작' : '수의계약'}
        </div>
      )}
    </div>
  )
}

export default function AccumulateMode() {
  const [facilityTypes, setFacilityTypes] = useState({})
  const [form, setForm] = useState({
    competition_name: '', facility_type: 'public',
    project_number: '', client: '', location: '',
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

  const canRun = form.competition_name && form.project_number
    && submissions.every(s => s.company && s.file) && !running

  const runPipeline = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)

    const fd = new FormData()
    fd.append('competition_name', form.competition_name)
    fd.append('facility_type', form.facility_type)
    fd.append('project_number', form.project_number)
    fd.append('client', form.client)
    fd.append('location', form.location)
    if (briefFile) fd.append('brief_pdf', briefFile)

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
      <div style={s.title}>경쟁 공모 등록</div>
      <div style={{ fontSize: 13, color: '#718096', lineHeight: 1.6, marginBottom: 20 }}>
        <strong style={{ color: '#e2e8f0' }}>한 공모에 참여한 여러 회사의 제안서</strong>를 한꺼번에 등록합니다.<br />
        PDF를 분석해 구조화된 데이터로 저장하며, <strong style={{ color: '#90cdf4' }}>비교분석·리포트</strong>는
        저장 후 상단 목록의 "비교분석 실행" 버튼으로 별도 실행합니다.<br />
        <span style={{ color: '#4a5568', fontSize: 12 }}>
          * 우리 회사 단독 등록은 상단 "내 프로젝트 등록" 탭을 이용하세요.
        </span>
      </div>

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>프로젝트번호</label>
          <input style={s.input} value={form.project_number}
            onChange={e => setFormField('project_number', e.target.value)}
            placeholder="예: 26014C" />
        </div>
        <div style={s.group}>
          <label style={s.label}>프로젝트명</label>
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
          <label style={s.label}>
            발주처
            <span style={{ fontSize: 11, color: '#4a5568', marginLeft: 4 }}>(선택 사항)</span>
          </label>
          <input style={s.input} value={form.client}
            onChange={e => setFormField('client', e.target.value)} />
        </div>
      </div>

      <div style={s.group}>
        <label style={s.label}>
          대지위치
          <span style={{ fontSize: 11, color: '#4a5568', marginLeft: 4 }}>(선택 사항)</span>
        </label>
        <input style={s.input} value={form.location}
          onChange={e => setFormField('location', e.target.value)}
          placeholder="예: 서울시 영등포구 당산동" />
      </div>

      <div style={s.section}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
          <div style={s.sectionTitle}>지침서 PDF</div>
          <span style={{ fontSize: 11, color: '#4a5568' }}>(선택 사항)</span>
        </div>
        <DropZone label="지침서 PDF 드래그 또는 클릭 (없으면 건너뜀)" onFiles={setBriefFile} />
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
        {running ? '추출 중...' : '데이터 추출 시작'}
      </button>

      {(events.length > 0) && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <div style={{
            background: '#0d1f17', border: '1px solid #276749', borderRadius: 10,
            padding: '14px 18px', marginBottom: 20,
            display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <span style={{ fontSize: 22, color: '#68d391' }}>✓</span>
            <div>
              <div style={{ fontWeight: 700, color: '#68d391', fontSize: 14, marginBottom: 3 }}>
                추출 완료 — 상단 목록에서 "비교분석 실행"을 눌러주세요
              </div>
              <div style={{ fontSize: 12, color: '#a0aec0' }}>
                프로젝트가 상단 저장 목록에 추가됐습니다. 비교분석·리포트는 목록 카드의 버튼으로 별도 실행합니다.
              </div>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={s.sectionTitle}>추출 결과</div>
          </div>
          {result.submissions?.map(sub => (
            <div key={sub.company} style={s.subCard}>
              <div style={s.subHeader}>
                <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{sub.company}</span>
                <span style={{
                  ...s.tag,
                  ...(sub.result === 'lose' ? s.tagLose : {}),
                  ...(sub.result === 'contracted' ? { background: '#2b6cb0' } : {}),
                }}>
                  {sub.result === 'win' ? '당선' : sub.result === 'contracted' ? '수의계약' : '낙선'}
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
