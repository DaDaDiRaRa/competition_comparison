import { useState, useEffect } from 'react'
import { getProjects, rerunCompare, rerenderReport, getReportUrl, getSubmissionReportUrl, addSubmission } from '../../api/client'
import ProgressLog from '../common/ProgressLog'
import DropZone from '../common/DropZone'
import SubmissionEditor from '../SubmissionEditor/SubmissionEditor'
import { useMeta } from '../../hooks/useMeta'

const RESULT_OPTIONS = [
  { value: 'win', label: '당선', color: 'var(--color-teal)', bg: 'var(--color-warning-bg)' },
  { value: 'contracted', label: '수의계약', color: 'var(--color-success)', bg: 'var(--color-success-bg)' },
  { value: 'lose', label: '낙선', color: 'var(--color-text-faint)', bg: 'var(--color-bg-surface)' },
]

const s = {
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24, marginBottom: 16 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  title: { fontSize: 16, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)' },
  refreshBtn: {
    background: 'none', border: '1px solid var(--color-border)', borderRadius: 6,
    color: 'var(--color-text-muted)', padding: '4px 12px', cursor: 'pointer', fontSize: 'var(--font-size-sm)',
  },
  empty: { color: 'var(--color-text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' },
  card: {
    background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 8,
    padding: '14px 16px', marginBottom: 10,
  },
  cardHeader: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 },
  cardName: { fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)' },
  badge: {
    fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20,
    background: 'var(--color-accent-hover)', color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-semibold)',
  },
  meta: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)' },
  actions: { display: 'flex', gap: 'var(--gap-sm)', marginTop: 10, flexWrap: 'wrap' },
  rerunBtn: {
    background: 'var(--color-success)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
  },
  addBtn: {
    background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
  },
  reportBtn: {
    background: 'var(--color-purple)', color: 'var(--color-purple-bg)', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
    textDecoration: 'none', display: 'inline-block',
  },
  rerenderBtn: {
    background: 'transparent', color: 'var(--color-text-muted)',
    border: '1px solid var(--color-text-muted)', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
  },
  subReportBtn: {
    background: 'var(--color-accent)', color: 'var(--color-bg-surface)', border: '1px solid var(--color-accent-hover)', borderRadius: 6,
    padding: '4px 10px', cursor: 'pointer', fontSize: 'var(--font-size-xs)', fontWeight: 'var(--font-weight-semibold)',
    textDecoration: 'none', display: 'inline-block',
  },
  editBtn: {
    background: 'var(--color-border)', color: 'var(--color-text-muted)', border: '1px solid var(--color-text-muted)', borderRadius: 6,
    padding: '3px 9px', cursor: 'pointer', fontSize: 'var(--font-size-xs)', fontWeight: 'var(--font-weight-semibold)',
    textDecoration: 'none', display: 'inline-block',
  },
  staleBanner: {
    background: 'var(--color-warning-bg)', border: '1px solid var(--color-amber-dark)', borderRadius: 6,
    padding: '7px 12px', fontSize: 'var(--font-size-sm)', color: 'var(--color-grade-d)', marginTop: 8,
    display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)',
  },
  disabledBtn: { opacity: 0.5, cursor: 'not-allowed' },
  logWrap: { marginTop: 10 },
  addForm: {
    marginTop: 12, padding: 14, background: 'var(--color-border-strong)',
    border: '1px solid var(--color-border)', borderRadius: 8,
  },
  addFormTitle: { fontSize: 13, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 10 },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 },
  label: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' },
  input: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '7px 10px', color: 'var(--color-text-body)', fontSize: 13,
    boxSizing: 'border-box',
  },
  resultPicker: { display: 'flex', gap: 6 },
  resultBtn: (opt, selected) => ({
    flex: 1, padding: '6px 0', borderRadius: 6, cursor: 'pointer', fontSize: 'var(--font-size-sm)',
    fontWeight: 'var(--font-weight-semibold)', textAlign: 'center',
    border: selected ? `2px solid ${opt.color}` : '2px solid var(--color-border)',
    background: selected ? opt.bg : 'var(--color-bg-surface)',
    color: selected ? opt.color : 'var(--color-text-muted)',
  }),
  submitBtn: (active) => ({
    width: '100%', marginTop: 10, padding: '9px 0', borderRadius: 6,
    border: 'none', cursor: active ? 'pointer' : 'not-allowed', fontSize: 13,
    fontWeight: 'var(--font-weight-bold)', background: active ? 'var(--color-accent)' : 'var(--color-bg-surface-alt)', color: active ? '#fff' : 'var(--color-text-muted)',
  }),
  cancelBtn: {
    background: 'none', border: 'none', color: 'var(--color-text-faint)', cursor: 'pointer',
    fontSize: 'var(--font-size-sm)', marginLeft: 'auto',
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
          {file && <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-success)', marginTop: 4 }}>✓ {file.name}</div>}
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
        <div style={{ marginTop: 8, fontSize: 'var(--font-size-sm)', color: 'var(--color-success)' }}>
          ✓ {company} 제안서 저장 완료. 비교분석 재실행 버튼으로 분석을 갱신하세요.
        </div>
      )}
    </div>
  )
}

function ProjectCard({ project, onRerunDone }) {
  const { facilityLabel } = useMeta()
  const [running, setRunning] = useState(false)
  const [rerendering, setRerendering] = useState(false)
  const [rerenderMsg, setRerenderMsg] = useState('')
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingCompany, setEditingCompany] = useState(null)
  const [comparisonStale, setComparisonStale] = useState(false)
  const [reportTs, setReportTs] = useState(Date.now())

  const hasReport = project.report_available
  const freshReportUrl = () => getReportUrl(project.facility_type, project.competition_id) + '?t=' + reportTs

  const handleRerun = async () => {
    setRunning(true)
    setEvents([])
    setDone(false)
    const startTime = Date.now()
    try {
      for await (const ev of rerunCompare(project.facility_type, project.competition_id)) {
        setEvents(prev => [...prev, { ...ev, _timestamp: startTime }])
        if (ev.type === 'complete') {
          setDone(true)
          setComparisonStale(false)
          setReportTs(Date.now())
          onRerunDone?.()
        }
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
      setReportTs(Date.now())
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
  const RESULT_COLOR = { win: 'var(--color-teal)', contracted: 'var(--color-success)', lose: 'var(--color-text-faint)' }

  return (
    <div style={s.card}>
      <div style={s.cardHeader}>
        <span style={s.badge}>{facilityLabel(project.facility_type)}</span>
        <span style={s.cardName}>{project.competition_name || project.competition_id}</span>
      </div>
      <div style={s.meta}>
        {project.project_number
          ? `${project.project_number} · `
          : (project.year ? `${project.year}년 · ` : '')}
        {project.client || '-'} · 제안서 {subs.length}개 (당선 {winCount}개)
      </div>

      {subs.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {subs.map(sub => (
            <div key={sub.company} style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-xs)' }}>
              <span style={{ fontSize: 'var(--font-size-sm)', color: RESULT_COLOR[sub.result] || 'var(--color-text-muted)' }}>
                {RESULT_KR[sub.result] || sub.result}
              </span>
              <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)' }}>{sub.company}</span>
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
              <button
                style={s.editBtn}
                onClick={() => setEditingCompany(sub.company)}
                title="추출 결과 편집"
              >
                편집
              </button>
            </div>
          ))}
        </div>
      )}

      {comparisonStale && (
        <div style={s.staleBanner}>
          ⚠ 추출 데이터가 수정됐습니다. 비교 리포트 반영을 위해 "비교분석 실행"을 눌러주세요.
          <button
            style={{ ...s.rerunBtn, padding: '4px 10px', fontSize: 'var(--font-size-xs)', marginLeft: 'auto' }}
            onClick={running ? undefined : handleRerun}
          >
            비교분석 실행
          </button>
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
              href={freshReportUrl()}
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
        <div style={{ marginTop: 8, fontSize: 'var(--font-size-sm)',
                      color: rerenderMsg.startsWith('✓') ? 'var(--color-success)' : 'var(--color-danger)' }}>
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

      {editingCompany && (
        <SubmissionEditor
          project={project}
          company={editingCompany}
          onClose={() => setEditingCompany(null)}
          onSaved={({ comparison_stale }) => {
            if (comparison_stale) setComparisonStale(true)
            onRerunDone?.()
          }}
        />
      )}
    </div>
  )
}

export default function ProjectList() {
  const { facilityLabel } = useMeta()
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
          ? (
            <div style={{ padding: '24px 0' }}>
              <div style={{ fontSize: 13, color: 'var(--color-text-faint)', textAlign: 'center', marginBottom: 20 }}>
                아직 등록된 프로젝트가 없습니다.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { step: '1', icon: '📁', title: '내 프로젝트 등록 탭', desc: '우리 회사가 과거에 제출한 제안서를 하나씩 등록합니다. 당선/낙선 결과를 함께 입력하면 자동으로 패턴 DB에 반영됩니다.' },
                  { step: '2', icon: '🗄', title: '경쟁 공모 등록 탭', desc: '한 공모에 참여한 여러 회사의 제안서를 한꺼번에 등록하고, 당선작과 낙선작을 나란히 비교 분석합니다.' },
                  { step: '3', icon: '🔍', title: '제안서 진단 탭', desc: '새로 작성 중인 제안서를 올리면, 과거 당선 패턴과 비교해 잘된 점·부족한 점·개선 방향을 알려줍니다.' },
                ].map(({ step, icon, title, desc }) => (
                  <div key={step} style={{
                    background: 'var(--color-border-strong)', border: '1px solid var(--color-border)',
                    borderRadius: 8, padding: '14px 16px',
                    display: 'flex', gap: 14, alignItems: 'flex-start',
                  }}>
                    <div style={{
                      fontSize: 22, flexShrink: 0, width: 36, height: 36,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>{icon}</div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 4 }}>
                        <span style={{
                          display: 'inline-block', width: 18, height: 18, borderRadius: '50%',
                          background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', fontSize: 10, fontWeight: 'var(--font-weight-bold)',
                          textAlign: 'center', lineHeight: '18px', marginRight: 6,
                        }}>{step}</span>
                        {title}
                      </div>
                      <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)', lineHeight: 1.6 }}>{desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
          : <>
              {/* 시설 유형 탭 */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                {facilityTypes.map(ft => (
                  <button
                    key={ft}
                    onClick={() => setSelectedType(ft)}
                    style={{
                      padding: '5px 14px', borderRadius: 20, fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
                      cursor: 'pointer', border: 'none',
                      background: ft === activeType ? 'var(--color-accent)' : 'var(--color-border)',
                      color: ft === activeType ? 'var(--color-bg-surface)' : 'var(--color-text-muted)',
                    }}
                  >
                    {facilityLabel(ft)}
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
