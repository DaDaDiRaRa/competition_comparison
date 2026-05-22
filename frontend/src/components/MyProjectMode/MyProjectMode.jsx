import { useState, useEffect } from 'react'
import { getFacilityTypes, runMyProjectPipeline } from '../../api/client'
import DropZone from '../common/DropZone'
import ProgressLog from '../common/ProgressLog'
import PageDistChart from '../common/PageDistChart'
import { GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'

const RESULT_OPTIONS = [
  { value: 'win', label: '당선', color: 'var(--color-teal)', bg: 'var(--color-warning-bg)' },
  { value: 'contracted', label: '수의계약', color: 'var(--color-success)', bg: 'var(--color-success-bg)' },
  { value: 'lose', label: '참여 (낙선)', color: 'var(--color-text-faint)', bg: 'var(--color-bg-surface)' },
]

const AXIS_KR = {
  concept: '개념', mass: '매스', landscape: '조경',
  program: '프로그램', facade: '파사드', technical: '기술', quantitative: '정량',
}

const COMPLIANCE_COLOR = { yes: 'var(--color-success)', partial: 'var(--color-grade-d)', no: 'var(--color-danger)', unclear: 'var(--color-text-muted)' }
const COMPLIANCE_KR = { yes: '충족', partial: '부분', no: '미충족', unclear: '불명확' }

const s = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 'var(--gap-lg)' },
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24 },
  title: { fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 6 },
  desc: { fontSize: 13, color: 'var(--color-text-faint)', lineHeight: 1.6, marginBottom: 20 },
  label: { fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 6, display: 'block' },
  optLabel: { fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginLeft: 4 },
  input: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
    boxSizing: 'border-box',
  },
  select: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
  },
  group: { marginBottom: 14 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--gap-md)' },
  divider: { borderTop: '1px solid var(--color-border)', marginTop: 20, paddingTop: 20 },
  sectionTitle: { fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 12 },
  resultPicker: { display: 'flex', gap: 'var(--gap-sm)' },
  resultBtn: (opt, selected) => ({
    flex: 1, padding: '10px 0', borderRadius: 8, cursor: 'pointer', fontSize: 13,
    fontWeight: 'var(--font-weight-semibold)', textAlign: 'center', transition: 'all 0.15s',
    border: selected ? `2px solid ${opt.color}` : '2px solid var(--color-border)',
    background: selected ? opt.bg : 'var(--color-bg-surface)',
    color: selected ? opt.color : 'var(--color-text-muted)',
  }),
  btn: (active) => ({
    background: active ? 'var(--color-success)' : 'var(--color-success-bg)',
    color: active ? '#fff' : 'var(--color-text-muted)',
    border: 'none', borderRadius: 8, padding: '13px 0', cursor: active ? 'pointer' : 'not-allowed',
    fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-bold)', width: '100%', marginTop: 8, transition: 'all 0.15s',
  }),
  card: {
    background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 10, padding: 20,
  },
  badge: (color, bg) => ({
    display: 'inline-block', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-bold)',
    padding: '3px 10px', borderRadius: 20, color, background: bg,
  }),
  axisRow: {
    display: 'flex', alignItems: 'center', padding: '8px 0',
    borderBottom: '1px solid var(--color-bg-surface)', gap: 10,
  },
  gradePill: (grade) => ({
    display: 'inline-block', padding: '3px 12px', borderRadius: 14,
    background: GRADE_BG[grade] || 'var(--color-border)',
    color: GRADE_COLOR[grade] || 'var(--color-text-faint)',
    fontWeight: 'var(--font-weight-bold)', fontSize: 13, letterSpacing: 1,
  }),
  listItem: {
    fontSize: 13, color: '#374151', padding: '3px 0', lineHeight: 1.5,
  },
}

function DiagnosisPanel({ diagnosis }) {
  if (!diagnosis) return null
  const axes = diagnosis.axes || {}
  const overallGrade = toGrade(diagnosis)

  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ ...s.sectionTitle, color: 'var(--color-danger)', marginBottom: 16 }}>
        낙선 원인 분석
        {overallGrade && (
          <span style={{ fontSize: 13, fontWeight: 'var(--font-weight-regular)', color: 'var(--color-text-muted)', marginLeft: 10 }}>
            종합 등급: <span style={s.gradePill(overallGrade)}>{overallGrade}</span>
          </span>
        )}
      </div>

      {/* 7축 등급 */}
      <div style={s.card}>
        {Object.entries(axes).map(([axis, data]) => {
          const grade = toGrade(data)
          const compliance = diagnosis.brief_compliance?.[axis]
          return (
            <div key={axis} style={s.axisRow}>
              <div style={{ width: 56, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', flexShrink: 0 }}>
                {AXIS_KR[axis] || axis}
              </div>
              <div style={{ flex: 1 }}>
                {grade ? <span style={s.gradePill(grade)}>{grade}</span> : <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>-</span>}
              </div>
              {compliance && (
                <div style={{
                  ...s.badge(COMPLIANCE_COLOR[compliance] || 'var(--color-text-muted)', 'var(--color-bg-surface)'),
                  fontSize: 'var(--font-size-xs)', padding: '2px 7px', border: `1px solid ${COMPLIANCE_COLOR[compliance] || 'var(--color-text-muted)'}`,
                }}>
                  {COMPLIANCE_KR[compliance] || compliance}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ ...s.grid2, marginTop: 16, gap: 'var(--gap-md)' }}>
        {/* 부족했던 점 */}
        {diagnosis.weaknesses?.length > 0 && (
          <div style={s.card}>
            <div style={{ fontSize: 13, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-danger)', marginBottom: 10 }}>
              부족했던 점
            </div>
            {diagnosis.weaknesses.map((w, i) => (
              <div key={i} style={s.listItem}>• {w}</div>
            ))}
          </div>
        )}

        {/* 개선 방향 */}
        {diagnosis.recommendations?.length > 0 && (
          <div style={s.card}>
            <div style={{ fontSize: 13, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 10 }}>
              개선 방향
            </div>
            {diagnosis.recommendations.map((r, i) => (
              <div key={i} style={s.listItem}>• {r}</div>
            ))}
          </div>
        )}
      </div>

      {/* 패턴 대비 누락 페이지 */}
      {diagnosis.pattern_deviation?.missing_page_types?.length > 0 && (
        <div style={{ ...s.card, marginTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-grade-d)', marginBottom: 8 }}>
            당선작 대비 누락된 페이지 유형
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {diagnosis.pattern_deviation.missing_page_types.map((t, i) => (
              <span key={i} style={s.badge('var(--color-grade-d)', 'var(--color-warning-bg)')}>{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function MyProjectMode() {
  const [facilityTypes, setFacilityTypes] = useState({})
  const [form, setForm] = useState({
    competition_name: '', facility_type: 'public',
    project_number: '', client: '', location: '',
    company: '',
  })
  const [resultType, setResultType] = useState('win')
  const [briefFile, setBriefFile] = useState(null)
  const [submissionFile, setSubmissionFile] = useState(null)
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(null)

  useEffect(() => { getFacilityTypes().then(setFacilityTypes) }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const canRun = form.competition_name && form.project_number
    && form.company && submissionFile && !running

  const run = async () => {
    setRunning(true)
    setEvents([])
    setDone(null)

    const fd = new FormData()
    fd.append('competition_name', form.competition_name)
    fd.append('facility_type', form.facility_type)
    fd.append('project_number', form.project_number)
    fd.append('client', form.client)
    fd.append('location', form.location)
    fd.append('company', form.company)
    fd.append('result', resultType)
    if (briefFile) fd.append('brief_pdf', briefFile)
    fd.append('submission_pdf', submissionFile)

    try {
      for await (const ev of runMyProjectPipeline(fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'complete') setDone(ev)
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  const selectedOpt = RESULT_OPTIONS.find(o => o.value === resultType)

  return (
    <div style={s.wrap}>
      <div style={s.panel}>
        <div style={s.title}>내 프로젝트 등록</div>
        <div style={s.desc}>
          <strong style={{ color: 'var(--color-text-body)' }}>우리 회사가 과거에 제출한 제안서</strong>를 하나씩 등록하는 탭입니다.<br />
          당선·수의계약은 <span style={{ color: 'var(--color-success)' }}>패턴 DB에 자동 반영</span>되어 이후 진단의 기준이 됩니다.<br />
          낙선은 <span style={{ color: 'var(--color-danger)' }}>기존 당선 패턴 대비 원인 분석</span>을 바로 제공합니다.<br />
          <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
            * 경쟁사 제안서 없이 우리 것만 올리면 됩니다. 지침서(RFP)가 있으면 함께 올리면 더 정확합니다.
          </span>
        </div>

        <div style={s.grid2}>
          <div style={s.group}>
            <label style={s.label}>프로젝트번호</label>
            <input style={s.input} value={form.project_number}
              onChange={e => set('project_number', e.target.value)}
              placeholder="예: 26014C" />
          </div>
          <div style={s.group}>
            <label style={s.label}>프로젝트명</label>
            <input style={s.input} value={form.competition_name}
              onChange={e => set('competition_name', e.target.value)}
              placeholder="예: 영등포구 신청사 설계공모" />
          </div>
          <div style={s.group}>
            <label style={s.label}>시설유형</label>
            <select style={s.select} value={form.facility_type}
              onChange={e => set('facility_type', e.target.value)}>
              {Object.entries(facilityTypes).map(([k, v]) => (
                <option key={k} value={k}>{v} ({k})</option>
              ))}
            </select>
          </div>
          <div style={s.group}>
            <label style={s.label}>
              발주처
              <span style={s.optLabel}>(선택 사항)</span>
            </label>
            <input style={s.input} value={form.client}
              onChange={e => set('client', e.target.value)} />
          </div>
        </div>

        <div style={s.group}>
          <label style={s.label}>
            대지위치
            <span style={s.optLabel}>(선택 사항)</span>
          </label>
          <input style={s.input} value={form.location}
            onChange={e => set('location', e.target.value)}
            placeholder="예: 서울시 영등포구 당산동" />
        </div>

        <div style={s.divider}>
          <div style={s.sectionTitle}>우리 회사 정보</div>
          <div style={s.grid2}>
            <div style={s.group}>
              <label style={s.label}>회사명</label>
              <input style={s.input} value={form.company}
                onChange={e => set('company', e.target.value)}
                placeholder="예: kunwon" />
            </div>
            <div style={s.group}>
              <label style={s.label}>결과</label>
              <div style={s.resultPicker}>
                {RESULT_OPTIONS.map(opt => (
                  <div key={opt.value} style={s.resultBtn(opt, resultType === opt.value)}
                    onClick={() => setResultType(opt.value)}>
                    {opt.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div style={s.divider}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
            <div style={s.sectionTitle}>지침서 PDF</div>
            <span style={s.optLabel}>(선택 사항)</span>
          </div>
          <DropZone label="지침서 PDF 드래그 또는 클릭 (없으면 건너뜀)" onFiles={setBriefFile} />
        </div>

        <div style={s.divider}>
          <div style={s.sectionTitle}>제안서 PDF</div>
          <DropZone label="우리 회사 제안서 PDF 드래그 또는 클릭" onFiles={setSubmissionFile} />
        </div>

        <button style={s.btn(canRun)} onClick={canRun ? run : undefined} disabled={!canRun}>
          {running ? '처리 중...' : '등록 시작'}
        </button>
      </div>

      {events.length > 0 && (
        <div style={s.panel}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {done && (
        <div style={s.panel}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-md)', marginBottom: 16 }}>
            <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)' }}>등록 완료</div>
            <div style={s.badge(selectedOpt.color, selectedOpt.bg)}>{selectedOpt.label}</div>
            {(done.result === 'win' || done.result === 'contracted') && (
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-success)' }}>✓ 패턴 DB 반영됨</div>
            )}
          </div>

          <div style={s.card}>
            <div style={{ display: 'flex', gap: 24, marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)' }}>프로젝트명</div>
                <div style={{ fontSize: 'var(--font-size-base)', color: 'var(--color-text-body)' }}>{form.competition_name}</div>
              </div>
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)' }}>회사</div>
                <div style={{ fontSize: 'var(--font-size-base)', color: 'var(--color-text-body)' }}>{done.company}</div>
              </div>
              <div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)' }}>제안서</div>
                <div style={{ fontSize: 'var(--font-size-base)', color: 'var(--color-text-body)' }}>{done.total_pages}페이지</div>
              </div>
            </div>
            <PageDistChart
              distribution={done.page_distribution}
              total={done.total_pages}
              title="페이지 구성"
            />
          </div>

          {done.result === 'lose' && !done.diagnosis && (
            <div style={{ marginTop: 12, fontSize: 13, color: 'var(--color-text-faint)' }}>
              패턴 DB에 당선 데이터가 없어 낙선 원인 분석을 건너뜠습니다.
              당선 프로젝트를 먼저 등록하면 다음 낙선 분석부터 결과가 표시됩니다.
            </div>
          )}

          <DiagnosisPanel diagnosis={done.diagnosis} />
        </div>
      )}
    </div>
  )
}
