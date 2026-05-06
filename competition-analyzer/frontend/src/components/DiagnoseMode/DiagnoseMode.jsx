import { useState, useEffect } from 'react'
import { getFacilityTypes, runDiagnosePipeline, getPattern } from '../../api/client'
import DropZone from '../common/DropZone'
import ProgressLog from '../common/ProgressLog'
import DiagnosisResult from './DiagnosisResult'

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
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  btn: {
    background: '#553c9a', color: '#fff', border: 'none', borderRadius: 6,
    padding: '12px 28px', cursor: 'pointer', fontSize: 15, fontWeight: 600,
    marginTop: 16, width: '100%',
  },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  patternBadge: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: '#1a2a3a', border: '1px solid #2c5282',
    borderRadius: 20, padding: '4px 12px', fontSize: 12, color: '#90cdf4',
    marginTop: 8,
  },
  noPattern: {
    background: '#2d1515', border: '1px solid #742a2a',
    borderRadius: 8, padding: 12, fontSize: 13, color: '#fc8181', marginTop: 8,
  },
}

export default function DiagnoseMode() {
  const [facilityTypes, setFacilityTypes] = useState({})
  const [facilityType, setFacilityType] = useState('public')
  const [competitionName, setCompetitionName] = useState('')
  const [briefFile, setBriefFile] = useState(null)
  const [submissionFile, setSubmissionFile] = useState(null)
  const [pattern, setPattern] = useState(null)
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)

  useEffect(() => {
    getFacilityTypes().then(setFacilityTypes)
  }, [])

  useEffect(() => {
    getPattern(facilityType).then(p => setPattern(p && p.win_count > 0 ? p : null))
  }, [facilityType])

  const canRun = briefFile && submissionFile && !running

  const run = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)

    const fd = new FormData()
    fd.append('facility_type', facilityType)
    fd.append('competition_name', competitionName)
    fd.append('brief_pdf', briefFile)
    fd.append('submission_pdf', submissionFile)

    try {
      for await (const ev of runDiagnosePipeline(fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') setResult(ev.result)
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  return (
    <div style={s.panel}>
      <div style={s.title}>신규 진단 모드</div>

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>시설유형</label>
          <select style={s.select} value={facilityType}
            onChange={e => setFacilityType(e.target.value)}>
            {Object.entries(facilityTypes).map(([k, v]) => (
              <option key={k} value={k}>{v} ({k})</option>
            ))}
          </select>
          {pattern
            ? <div style={s.patternBadge}>✓ DB 패턴: 당선작 {pattern.win_count}개 보유</div>
            : <div style={s.noPattern}>⚠ 해당 유형 당선 데이터 없음 (데이터 축적 필요)</div>
          }
        </div>

        <div style={s.group}>
          <label style={s.label}>공모명 (선택)</label>
          <input style={s.input} value={competitionName}
            onChange={e => setCompetitionName(e.target.value)}
            placeholder="예: 영등포구 신청사 건립" />
        </div>
      </div>

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>지침서 PDF</label>
          <DropZone label="지침서 PDF" onFiles={setBriefFile} />
        </div>
        <div style={s.group}>
          <label style={s.label}>자사 제안서 PDF</label>
          <DropZone label="자사 제안서 PDF" onFiles={setSubmissionFile} />
        </div>
      </div>

      <button
        style={{ ...s.btn, ...(canRun ? {} : s.btnDisabled) }}
        onClick={canRun ? run : undefined}
        disabled={!canRun}
      >
        {running ? '진단 중...' : '진단 시작'}
      </button>

      {events.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {result && <DiagnosisResult data={result} />}
    </div>
  )
}
