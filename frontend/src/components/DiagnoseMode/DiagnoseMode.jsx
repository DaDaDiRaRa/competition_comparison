import { useState, useEffect } from 'react'
import {
  getFacilityTypes, runDiagnosePipeline, runDiagnoseVsProjects,
  getPattern, getProjects, getDiagnosisReportUrl,
} from '../../api/client'
import DropZone from '../common/DropZone'
import ProgressLog from '../common/ProgressLog'
import DiagnosisResult from './DiagnosisResult'

const s = {
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24 },
  title: { fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)', marginBottom: 20, color: 'var(--color-text-body)' },
  label: { fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
  },
  select: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
  },
  group: { marginBottom: 14 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  btn: {
    background: 'var(--color-purple)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '12px 28px', cursor: 'pointer', fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)',
    marginTop: 16, width: '100%',
  },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  patternBadge: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: 'var(--color-bg-surface-alt)', border: '1px solid var(--color-accent-hover)',
    borderRadius: 20, padding: '4px 12px', fontSize: 'var(--font-size-sm)', color: 'var(--color-accent)',
    marginTop: 8,
  },
  noPattern: {
    background: 'var(--color-danger-bg)', border: '1px solid var(--color-danger)',
    borderRadius: 8, padding: 12, fontSize: 13, color: 'var(--color-danger)', marginTop: 8,
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
  const [reportFilename, setReportFilename] = useState(null)
  // 진단 모드: 'pattern' (기본 — DB 패턴) | 'projects' (특정 공모 선택)
  const [refMode, setRefMode] = useState('pattern')
  const [allProjects, setAllProjects] = useState([])
  const [selectedRefs, setSelectedRefs] = useState([])  // [{facility_type, competition_id, company}]

  useEffect(() => {
    getFacilityTypes().then(setFacilityTypes)
  }, [])

  useEffect(() => {
    getPattern(facilityType).then(p => setPattern(p && p.win_count > 0 ? p : null))
  }, [facilityType])

  useEffect(() => {
    if (refMode === 'projects') {
      getProjects().then(setAllProjects).catch(() => {})
    }
  }, [refMode])

  const refKey = (item) => `${item.competition_id}__${item.company}`
  const toggleRef = (item) => {
    setSelectedRefs(prev =>
      prev.some(s => refKey(s) === refKey(item))
        ? prev.filter(s => refKey(s) !== refKey(item))
        : [...prev, item]
    )
  }
  const isRefSelected = (item) => selectedRefs.some(s => refKey(s) === refKey(item))

  const canRun = submissionFile && !running &&
    (refMode === 'pattern' || selectedRefs.length > 0)

  const run = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)
    setReportFilename(null)

    const fd = new FormData()
    fd.append('facility_type', facilityType)
    fd.append('competition_name', competitionName)
    fd.append('submission_pdf', submissionFile)
    if (briefFile) fd.append('brief_pdf', briefFile)

    const stream = refMode === 'projects'
      ? (() => {
          fd.append('reference_items_json', JSON.stringify(
            selectedRefs.map(({ facility_type, competition_id, company }) =>
              ({ facility_type, competition_id, company }))
          ))
          return runDiagnoseVsProjects(fd)
        })()
      : runDiagnosePipeline(fd)

    try {
      for await (const ev of stream) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') {
          setResult(ev.result)
          if (ev.report_filename) setReportFilename(ev.report_filename)
        }
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  const filteredProjects = allProjects.filter(p => p.facility_type === facilityType)

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
          {refMode === 'pattern' && (
            pattern
              ? <div style={s.patternBadge}>✓ DB 패턴: 당선작 {pattern.win_count}개 보유</div>
              : <div style={s.noPattern}>⚠ 해당 유형 당선 데이터 없음 (데이터 축적 필요)</div>
          )}
        </div>

        <div style={s.group}>
          <label style={s.label}>공모명 (선택)</label>
          <input style={s.input} value={competitionName}
            onChange={e => setCompetitionName(e.target.value)}
            placeholder="예: 영등포구 신청사 건립" />
        </div>
      </div>

      {/* 진단 기준 모드 토글 */}
      <div style={s.group}>
        <label style={s.label}>진단 기준</label>
        <div style={{ display: 'flex', gap: 'var(--gap-sm)' }}>
          {[
            { v: 'pattern', label: '전체 당선 패턴 (자동)' },
            { v: 'projects', label: '특정 공모 선택' },
          ].map(opt => (
            <button
              key={opt.v}
              onClick={() => setRefMode(opt.v)}
              style={{
                flex: 1, padding: '9px 0', borderRadius: 6, fontSize: 13,
                fontWeight: 'var(--font-weight-semibold)', cursor: 'pointer',
                border: refMode === opt.v ? '2px solid #a78bfa' : '2px solid var(--color-border)',
                background: refMode === opt.v ? 'var(--color-purple-bg)' : 'var(--color-bg-surface)',
                color: refMode === opt.v ? '#5b21b6' : 'var(--color-text-faint)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 특정 공모 선택 모드 — 프로젝트 리스트 */}
      {refMode === 'projects' && (
        <div style={s.group}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            <label style={{ ...s.label, marginBottom: 0, flex: 1 }}>
              참조할 공모 선택 ({facilityTypes[facilityType] || facilityType})
            </label>
            <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-accent)', fontWeight: 'var(--font-weight-semibold)' }}>
              {selectedRefs.length}개 선택됨
            </span>
          </div>
          <div style={{
            maxHeight: 240, overflowY: 'auto',
            background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
            borderRadius: 6, padding: 8,
          }}>
            {filteredProjects.length === 0 ? (
              <div style={{ padding: 12, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                해당 유형의 저장된 공모가 없습니다.
              </div>
            ) : filteredProjects.map(p => (
              <div key={p.competition_id} style={{ marginBottom: 6 }}>
                <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', padding: '6px 8px', fontWeight: 'var(--font-weight-semibold)' }}>
                  {p.competition_name || p.competition_id}
                  <span style={{ marginLeft: 6, fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', fontWeight: 'var(--font-weight-regular)' }}>
                    {p.year}
                  </span>
                </div>
                {(p.submissions || []).map(sub => {
                  const item = { facility_type: p.facility_type, competition_id: p.competition_id, company: sub.company }
                  const checked = isRefSelected(item)
                  return (
                    <div
                      key={sub.company}
                      onClick={() => toggleRef(item)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '6px 12px', marginLeft: 8, cursor: 'pointer',
                        borderRadius: 4,
                        background: checked ? 'var(--color-bg-surface-alt)' : 'transparent',
                        border: checked ? '1px solid var(--color-accent)' : '1px solid transparent',
                      }}
                    >
                      <div style={{
                        width: 14, height: 14, borderRadius: 3, flexShrink: 0,
                        border: checked ? '2px solid var(--color-accent)' : '2px solid var(--color-text-muted)',
                        background: checked ? 'var(--color-accent)' : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 9, color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-bold)',
                      }}>{checked ? '✓' : ''}</div>
                      <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)', flex: 1 }}>{sub.company}</span>
                      <span style={{
                        fontSize: 10, padding: '1px 6px', borderRadius: 10,
                        color: sub.result === 'win' || sub.result === 'contracted' ? 'var(--color-teal)' : 'var(--color-text-faint)',
                        background: 'var(--color-bg-surface)',
                      }}>
                        {sub.result === 'win' ? '당선' : sub.result === 'contracted' ? '수의계약' : '낙선'}
                      </span>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>
            지침서 PDF
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginLeft: 4 }}>(선택 사항)</span>
          </label>
          <DropZone label="지침서 PDF (선택)" onFiles={setBriefFile} />
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
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {reportFilename && (
        <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
          <a
            href={getDiagnosisReportUrl(reportFilename)}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-block', background: 'var(--color-purple)', color: 'var(--color-text-on-accent)',
              borderRadius: 6, padding: '8px 20px', fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)',
              textDecoration: 'none',
            }}
          >
            진단 리포트 열기
          </a>
        </div>
      )}

      {result && <DiagnosisResult data={result} pattern={pattern} />}
    </div>
  )
}
