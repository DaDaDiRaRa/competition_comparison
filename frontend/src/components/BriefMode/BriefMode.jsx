import { useState } from 'react'
import { useMeta } from '../../hooks/useMeta'
import { runBriefAnalyze, getBriefExportUrl, reinterpretBrief } from '../../api/client'
import DropZone from '../common/DropZone'
import ProgressLog from '../common/ProgressLog'

const SEV = {
  high:   { color: 'var(--color-danger)',  bg: 'var(--color-danger-bg)',  label: '높음' },
  medium: { color: 'var(--color-warning)', bg: 'var(--color-warning-bg)', label: '중간' },
  low:    { color: 'var(--color-info)',    bg: 'var(--color-info-bg)',    label: '낮음' },
}

const s = {
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24 },
  title: { fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)', marginBottom: 4, color: 'var(--color-text-body)' },
  subtitle: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', marginBottom: 20 },
  label: { fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 6, display: 'block' },
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
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  btn: {
    background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '12px 28px', cursor: 'pointer', fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)',
    marginTop: 16, width: '100%',
  },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  divider: { borderTop: '1px solid var(--color-border)', margin: '24px 0' },
  sectionTitle: {
    fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)',
    color: 'var(--color-text-body)', marginBottom: 12,
  },
  dlRow: { display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 20 },
  dlBtn: (primary) => ({
    display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none',
    padding: '9px 20px', borderRadius: 6, fontSize: 'var(--font-size-base)',
    fontWeight: 'var(--font-weight-semibold)', cursor: 'pointer',
    background: primary ? 'var(--color-accent)' : 'var(--color-bg-surface-alt)',
    color: primary ? 'var(--color-text-on-accent)' : 'var(--color-text-body)',
    border: primary ? 'none' : '1px solid var(--color-border)',
  }),
  summaryRow: { display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' },
  badge: (sev) => ({
    display: 'inline-flex', alignItems: 'center', gap: 5,
    padding: '5px 14px', borderRadius: 20,
    background: SEV[sev]?.bg || 'var(--color-bg-surface-alt)',
    color: SEV[sev]?.color || 'var(--color-text-body)',
    border: `1px solid ${SEV[sev]?.color || 'var(--color-border)'}`,
    fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
  }),
  flagList: { display: 'flex', flexDirection: 'column', gap: 8 },
  flagItem: (sev) => ({
    padding: '10px 14px', borderRadius: '0 6px 6px 0',
    borderLeft: `3px solid ${SEV[sev]?.color || 'var(--color-border)'}`,
    background: SEV[sev]?.bg || 'var(--color-bg-surface-alt)',
  }),
  flagSev: (sev) => ({
    fontSize: 11, fontWeight: 'var(--font-weight-bold)', letterSpacing: '0.04em',
    color: SEV[sev]?.color || 'var(--color-text-muted)',
    marginBottom: 2, display: 'block',
  }),
  flagMsg: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)', marginBottom: 2 },
  flagEvidence: { fontSize: 12, color: 'var(--color-text-muted)', fontStyle: 'italic' },
  noFlags: {
    padding: '14px 16px', borderRadius: 8, textAlign: 'center',
    background: 'var(--color-success-bg)', border: '1px solid var(--color-success)',
    color: 'var(--color-success)', fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
  },
}

export default function BriefMode() {
  const { facilityTypes, facilityLabel } = useMeta()

  const [facilityType, setFacilityType] = useState('')
  const [briefName, setBriefName] = useState('')
  const [briefFile, setBriefFile] = useState(null)
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)   // complete 이벤트 payload
  const [flags, setFlags] = useState([])        // validate done의 flag_list
  const [includeInsight, setIncludeInsight] = useState(true)  // AI 종합 해설 포함 여부
  const [regening, setRegening] = useState(false)             // 해설 재생성 진행 중
  const [regenErr, setRegenErr] = useState('')

  const defaultFt = facilityTypes[0]?.key ?? ''
  const ft = facilityType || defaultFt

  // 파일 확장자로 포맷 판단 (텍스트 기반: docx / hwp / hwpx)
  const fileExt = (briefFile?.name || '').toLowerCase()
  const isDocx = /\.docx$/.test(fileExt)
  const isHwp  = /\.(hwp|hwpx)$/.test(fileExt)
  const fileFormat = isDocx ? 'docx'
    : /\.hwpx$/.test(fileExt) ? 'hwpx'
    : /\.hwp$/.test(fileExt) ? 'hwp'
    : 'pdf'

  // complete 이벤트가 알려주는 source_format 우선, 없으면 업로드 파일 확장자 기반
  const sourceFormat = result?.source_format ?? fileFormat
  // 블록 기반 포맷(docx/hwp/hwpx)은 flag location 을 "블록 N" 으로 표시
  const isBlockFormat = sourceFormat === 'docx' || sourceFormat === 'hwp' || sourceFormat === 'hwpx'

  const canRun = !!briefFile && !running && !!ft

  const run = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)
    setFlags([])

    setRegenErr('')

    const fd = new FormData()
    fd.append('facility_type', ft)
    fd.append('brief_name', briefName.trim())
    fd.append('brief_pdf', briefFile)
    fd.append('include_insight', includeInsight ? 'true' : 'false')

    try {
      for await (const ev of runBriefAnalyze(fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'done' && ev.step === 'validate') {
          setFlags(ev.flag_list || [])
        }
        if (ev.type === 'complete') {
          setResult(ev)
        }
        if (ev.type === 'error') break
      }
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', message: e.message }])
    }
    setRunning(false)
  }

  const summary = result?.validation_summary || {}
  const sevOrder = { high: 0, medium: 1, low: 2 }
  const sortedFlags = [...flags].sort((a, b) =>
    (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9)
  )

  const handleDownload = async (url, filename) => {
    if (window.pywebview?.api?.save_file) {
      const fullUrl = window.location.origin + url
      const res = await window.pywebview.api.save_file(fullUrl, filename)
      if (res && !res.ok && res.reason !== 'cancelled') {
        alert(`저장 실패: ${res.reason}`)
      }
    } else {
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  // HTML 리포트: 웹은 새 탭에서 보기(인라인), 데스크톱은 파일 저장
  const handleHtml = (filename) => {
    const url = getBriefExportUrl(filename)
    if (window.pywebview?.api?.save_file) {
      handleDownload(url, filename)
    } else {
      window.open(url, '_blank', 'noopener')
    }
  }

  // AI 종합 해설만 재생성 (분석 시 껐거나 실패한 경우). 추출 재처리 없음.
  const handleRegenInsight = async () => {
    if (!result?.brief_id || regening) return
    setRegening(true)
    setRegenErr('')
    try {
      const res = await reinterpretBrief(result.brief_id)
      setResult(prev => ({ ...prev, has_insight: res.has_insight }))
    } catch (e) {
      setRegenErr(e.message || 'AI 종합 해설 생성 실패')
    }
    setRegening(false)
  }

  return (
    <div style={s.panel}>
      <div style={s.title}>지침서 분석</div>
      <div style={s.subtitle}>공모 지침서 PDF를 업로드하면 요구사항을 추출하고 검증 경고를 생성합니다.</div>

      <div style={s.grid2}>
        <div style={s.group}>
          <label style={s.label}>시설유형</label>
          <select
            style={s.select}
            value={ft}
            onChange={e => setFacilityType(e.target.value)}
          >
            {facilityTypes.map(({ key }) => (
              <option key={key} value={key}>{facilityLabel(key)} ({key})</option>
            ))}
          </select>
        </div>
        <div style={s.group}>
          <label style={s.label}>
            지침서 이름
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginLeft: 4 }}>(선택)</span>
          </label>
          <input
            style={s.input}
            value={briefName}
            onChange={e => setBriefName(e.target.value)}
            placeholder="예: 영등포구 신청사 건립 공모 지침서"
          />
        </div>
      </div>

      <div style={s.group}>
        <label style={s.label}>지침서 파일 (PDF, DOCX, HWP, HWPX)</label>
        <DropZone
          label="지침서 PDF/DOCX/HWP/HWPX 드래그 또는 클릭"
          accept=".pdf,.docx,.hwp,.hwpx"
          onFiles={setBriefFile}
        />
        {isDocx && (
          <div style={{
            marginTop: 8,
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
            background: 'var(--color-info-bg)',
            border: '1px solid var(--color-info)',
            borderRadius: 6,
            padding: '8px 12px',
          }}>
            DOCX 파일: 텍스트와 표만 분석됩니다. 도면이 포함된 지침서는 PDF로 업로드해주세요.
          </div>
        )}
        {isHwp && (
          <div style={{
            marginTop: 8,
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
            background: 'var(--color-info-bg)',
            border: '1px solid var(--color-info)',
            borderRadius: 6,
            padding: '8px 12px',
          }}>
            HWP/HWPX 파일: 텍스트와 표만 분석됩니다. 도면이 포함된 지침서는 PDF로 업로드해주세요.
          </div>
        )}
      </div>

      <label style={{
        display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 16, cursor: 'pointer',
        fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)',
      }}>
        <input
          type="checkbox"
          checked={includeInsight}
          onChange={e => setIncludeInsight(e.target.checked)}
          style={{ marginTop: 2, cursor: 'pointer' }}
        />
        <span>
          AI 종합 해설 포함
          <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-xs)', marginLeft: 6 }}>
            지침서가 강조하는 것·놓치면 안 되는 것을 근거와 함께 정리합니다 (API 토큰 소량 사용)
          </span>
        </span>
      </label>

      <button
        style={{ ...s.btn, marginTop: 12, ...(canRun ? {} : s.btnDisabled) }}
        onClick={canRun ? run : undefined}
        disabled={!canRun}
      >
        {running ? '분석 중...' : '분석 시작'}
      </button>

      {events.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>진행 로그</div>
          <ProgressLog events={events} />
        </div>
      )}

      {result && (
        <>
          <div style={s.divider} />

          <div style={s.sectionTitle}>체크리스트 내보내기</div>
          <div style={s.dlRow}>
            {result.html_filename && (
              <button
                style={s.dlBtn(true)}
                onClick={() => handleHtml(result.html_filename)}
              >
                📄 리포트 .html
              </button>
            )}
            <button
              style={s.dlBtn(false)}
              onClick={() => handleDownload(getBriefExportUrl(result.xlsx_filename), result.xlsx_filename)}
            >
              ⬇ 체크리스트 .xlsx
            </button>
            <button
              style={s.dlBtn(false)}
              onClick={() => handleDownload(getBriefExportUrl(result.md_filename), result.md_filename)}
            >
              ⬇ 체크리스트 .md
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            {result.has_insight ? (
              <span style={{
                fontSize: 'var(--font-size-sm)', color: 'var(--color-accent)',
                fontWeight: 'var(--font-weight-semibold)',
              }}>
                🔍 AI 종합 해설이 리포트(.html) 상단에 포함되었습니다
              </span>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  AI 종합 해설 미포함
                </span>
                <button
                  style={{ ...s.dlBtn(false), ...(regening ? s.btnDisabled : {}) }}
                  onClick={handleRegenInsight}
                  disabled={regening}
                >
                  {regening ? '생성 중...' : '🔍 AI 종합 해설 생성'}
                </button>
              </>
            )}
            {regenErr && (
              <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-danger)' }}>{regenErr}</span>
            )}
          </div>

          <div style={s.sectionTitle}>검증 결과</div>

          <div style={s.summaryRow}>
            {(['high', 'medium', 'low']).map(sev => (
              <div key={sev} style={s.badge(sev)}>
                {SEV[sev].label} {summary[sev] ?? 0}건
              </div>
            ))}
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', alignSelf: 'center', marginLeft: 4 }}>
              전체 {result.total_pages}페이지
            </div>
          </div>

          {sortedFlags.length === 0 ? (
            <div style={s.noFlags}>검증 경고 없음 — 지침서 요건이 모두 충족되었습니다.</div>
          ) : (
            <div style={s.flagList}>
              {sortedFlags.map((flag, i) => (
                <div key={i} style={s.flagItem(flag.severity)}>
                  <span style={s.flagSev(flag.severity)}>
                    {SEV[flag.severity]?.label ?? flag.severity} · {flag.type}
                  </span>
                  <div style={s.flagMsg}>{flag.message}</div>
                  {flag.location && (
                    <div style={s.flagEvidence}>
                      {isBlockFormat
                        ? flag.location.replace(/p\.(\d+)/g, '블록 $1')
                        : flag.location}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
