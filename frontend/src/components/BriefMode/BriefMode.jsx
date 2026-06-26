import { useState, useEffect } from 'react'
import { useMeta } from '../../hooks/useMeta'
import { runBriefAnalyze, getBriefExportUrl, reinterpretBrief, proposeBrief, listBriefs, analyzeSite, getBriefSiteImageUrl, getBriefSiteContext } from '../../api/client'
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
  historyPanel: {
    marginTop: 24, background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24,
  },
  historyCard: {
    border: '1px solid var(--color-border)', borderRadius: 8, padding: '14px 16px',
    marginBottom: 10, background: 'var(--color-bg-base)',
  },
  historyCardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' },
  historyName: { fontWeight: 'var(--font-weight-semibold)', fontSize: 'var(--font-size-base)', color: 'var(--color-text-body)', marginBottom: 2 },
  historyMeta: { fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 8 },
  historyActions: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' },
  historyBtn: (primary) => ({
    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '6px 14px',
    borderRadius: 6, fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)',
    cursor: 'pointer', border: primary ? 'none' : '1px solid var(--color-border)',
    background: primary ? 'var(--color-accent)' : 'var(--color-bg-surface-alt)',
    color: primary ? 'var(--color-text-on-accent)' : 'var(--color-text-body)',
  }),
  fmtBadge: {
    fontSize: 11, padding: '2px 7px', borderRadius: 10,
    background: 'var(--color-bg-surface-alt)', border: '1px solid var(--color-border)',
    color: 'var(--color-text-muted)', fontWeight: 'var(--font-weight-semibold)',
  },
  insightBadge: {
    fontSize: 11, padding: '2px 7px', borderRadius: 10,
    background: 'var(--color-info-bg)', border: '1px solid var(--color-info)',
    color: 'var(--color-info)', fontWeight: 'var(--font-weight-semibold)',
  },
}

export default function BriefMode() {
  const { facilityTypes, facilityLabel } = useMeta()

  const [facilityType, setFacilityType] = useState('')
  const [briefName, setBriefName] = useState('')
  const [briefFiles, setBriefFiles] = useState([])  // 복수 파일 지원
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)   // complete 이벤트 payload
  const [flags, setFlags] = useState([])        // validate done의 flag_list
  const [includeInsight, setIncludeInsight] = useState(true)  // AI 종합 해설 포함 여부
  const [regening, setRegening] = useState(false)             // 해설 재생성 진행 중
  const [regenErr, setRegenErr] = useState('')
  const [proposing, setProposing] = useState(false)           // 수주 제안서 생성 진행 중
  const [proposeErr, setProposeErr] = useState('')
  const [siteAddr, setSiteAddr] = useState('')                 // 대지 분석 주소 입력
  const [siteAnalyzing, setSiteAnalyzing] = useState(false)
  const [siteResult, setSiteResult] = useState(null)          // 대지 분석 결과
  const [siteErr, setSiteErr] = useState('')
  const [siteHistoryId, setSiteHistoryId] = useState(null)    // 이력 카드 대지분석 열린 brief_id
  const [siteHistoryAddr, setSiteHistoryAddr] = useState('')
  const [siteHistoryBusy, setSiteHistoryBusy] = useState(false)
  const [siteHistoryErr, setSiteHistoryErr] = useState('')
  const [siteViewId, setSiteViewId] = useState(null)          // 이력 카드 대지분석 보기 열린 brief_id
  const [siteViewData, setSiteViewData] = useState({})        // { [brief_id]: siteContext }
  const [history, setHistory] = useState([])

  const loadHistory = () => listBriefs().then(setHistory).catch(() => {})
  useEffect(() => { loadHistory() }, [])

  // 결과 화면에서 has_site_context이지만 siteResult가 없으면 자동 로드
  useEffect(() => {
    if (result?.has_site_context && !siteResult && result.brief_id) {
      getBriefSiteContext(result.brief_id)
        .then(sc => setSiteResult({ matched_address: sc.matched_address || '', analysis: sc.analysis }))
        .catch(() => {})
    }
  }, [result?.brief_id, result?.has_site_context])

  const defaultFt = facilityTypes[0]?.key ?? ''
  const ft = facilityType || defaultFt

  // 첫 번째 파일 기준 포맷 판단 (알림 표시용)
  const firstExt = (briefFiles[0]?.name || '').toLowerCase()
  const hasDocx = briefFiles.some(f => /\.docx$/.test((f.name || '').toLowerCase()))
  const hasHwp  = briefFiles.some(f => /\.(hwp|hwpx)$/.test((f.name || '').toLowerCase()))
  const isDocx  = hasDocx && briefFiles.length === 1
  const isHwp   = hasHwp  && briefFiles.length === 1

  // complete 이벤트가 알려주는 source_format 우선, 없으면 첫 파일 확장자 기반
  const fileFormat = /\.docx$/.test(firstExt) ? 'docx'
    : /\.hwpx$/.test(firstExt) ? 'hwpx'
    : /\.hwp$/.test(firstExt) ? 'hwp'
    : 'pdf'
  const sourceFormat = result?.source_format ?? fileFormat
  const isBlockFormat = sourceFormat === 'docx' || sourceFormat === 'hwp' || sourceFormat === 'hwpx'

  const canRun = briefFiles.length > 0 && !running && !!ft

  const run = async () => {
    setRunning(true)
    setEvents([])
    setResult(null)
    setFlags([])

    setRegenErr('')
    setProposeErr('')

    const fd = new FormData()
    fd.append('facility_type', ft)
    fd.append('brief_name', briefName.trim())
    briefFiles.forEach(f => fd.append('brief_pdf', f))
    fd.append('include_insight', includeInsight ? 'true' : 'false')

    try {
      for await (const ev of runBriefAnalyze(fd)) {
        setEvents(prev => [...prev, ev])
        if (ev.type === 'done' && ev.step === 'validate') {
          setFlags(ev.flag_list || [])
        }
        if (ev.type === 'complete') {
          setResult(ev)
          loadHistory()
          if (ev.has_site_context && ev.site_context) {
            setSiteResult({
              matched_address: ev.site_context.matched_address || '',
              analysis: ev.site_context.analysis,
            })
          }
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

  // VWorld 대지·맥락 분석
  const handleSiteAnalyze = async () => {
    if (!result?.brief_id || siteAnalyzing) return
    const addr = siteAddr.trim()
    if (!addr) return
    setSiteAnalyzing(true)
    setSiteErr('')
    setSiteResult(null)
    try {
      const res = await analyzeSite(result.brief_id, addr)
      setSiteResult(res)
      if (result?.brief_id) setResult(prev => ({ ...prev, has_site_context: true }))
    } catch (e) {
      setSiteErr(e.message || '대지 분석 실패')
    }
    setSiteAnalyzing(false)
  }

  // 이력 카드에서 직접 대지분석
  const handleHistorySiteAnalyze = async (briefId) => {
    const addr = siteHistoryAddr.trim()
    if (!addr || siteHistoryBusy) return
    setSiteHistoryBusy(true)
    setSiteHistoryErr('')
    try {
      await analyzeSite(briefId, addr)
      setHistory(prev => prev.map(h => h.brief_id === briefId ? { ...h, has_site_context: true } : h))
      setSiteHistoryId(null)
      setSiteHistoryAddr('')
    } catch (e) {
      setSiteHistoryErr(e.message || '대지 분석 실패')
    }
    setSiteHistoryBusy(false)
  }

  // 프로젝트 수주 제안서 생성 (수주 전략). 완료 시 새 탭/파일로 제안서 리포트 열기.
  const handlePropose = async (briefId) => {
    const id = briefId || result?.brief_id
    if (!id || proposing) return
    setProposing(true)
    setProposeErr('')
    try {
      const res = await proposeBrief(id)
      if (result?.brief_id === id) {
        setResult(prev => ({ ...prev, has_proposal: true }))
      }
      loadHistory()
      handleHtml(res.proposal_filename || `${id}_proposal.html`)
    } catch (e) {
      setProposeErr(e.message || '수주 제안서 생성 실패')
    }
    setProposing(false)
  }

  return (
    <>
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
        <label style={s.label}>
          지침서 파일 (PDF, DOCX, HWP, HWPX)
          <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginLeft: 6 }}>
            복수 파일 가능 — 첫 번째 파일이 주 문서(배점표·날짜 우선)
          </span>
        </label>
        <DropZone
          label="지침서 PDF/DOCX/HWP/HWPX 드래그 또는 클릭 (복수 선택 가능)"
          accept=".pdf,.docx,.hwp,.hwpx"
          multiple={true}
          onFiles={files => setBriefFiles(Array.isArray(files) ? files : [files].filter(Boolean))}
        />
        {briefFiles.length > 0 && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {briefFiles.map((f, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', borderRadius: 6,
                background: 'var(--color-bg-surface-alt)', border: '1px solid var(--color-border)',
                fontSize: 'var(--font-size-sm)',
              }}>
                <span style={{
                  fontSize: 11, fontWeight: 'var(--font-weight-bold)',
                  color: i === 0 ? 'var(--color-accent)' : 'var(--color-text-muted)',
                  minWidth: 24,
                }}>
                  {i === 0 ? '주' : `${i + 1}`}
                </span>
                <span style={{ flex: 1, color: 'var(--color-text-body)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {f.name}
                </span>
                <span style={{ color: 'var(--color-text-muted)', fontSize: 11 }}>
                  {(f.size / 1024 / 1024).toFixed(1)}MB
                </span>
                <button
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--color-text-muted)', fontSize: 14, padding: '0 2px', lineHeight: 1,
                  }}
                  onClick={() => setBriefFiles(prev => prev.filter((_, j) => j !== i))}
                  title="제거"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        {(isDocx || hasDocx) && (
          <div style={{
            marginTop: 8, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)',
            background: 'var(--color-info-bg)', border: '1px solid var(--color-info)',
            borderRadius: 6, padding: '8px 12px',
          }}>
            DOCX 파일: 텍스트와 표만 분석됩니다. 도면이 포함된 지침서는 PDF로 업로드해주세요.
          </div>
        )}
        {(isHwp || hasHwp) && (
          <div style={{
            marginTop: 8, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)',
            background: 'var(--color-info-bg)', border: '1px solid var(--color-info)',
            borderRadius: 6, padding: '8px 12px',
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

          {/* ── 대지·맥락 분석 ── */}
          <div style={{
            border: '1px solid var(--color-border)', borderRadius: 10, padding: '16px 18px',
            marginBottom: 16, background: 'var(--color-bg-surface-alt)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <div style={{ fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)' }}>
                🛰 대지·맥락 분석
                {result.has_site_context && (
                  <span style={{ fontSize: 11, marginLeft: 8, padding: '2px 7px', borderRadius: 10,
                    background: 'var(--color-info-bg)', border: '1px solid var(--color-info)',
                    color: 'var(--color-info)', fontWeight: 'var(--font-weight-semibold)' }}>
                    완료
                  </span>
                )}
              </div>
              <button
                style={{ fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--color-text-muted)', padding: '2px 6px' }}
                onClick={() => { setSiteAddr(''); setSiteErr(''); setSiteAnalyzing(false);
                  setResult(prev => ({ ...prev, _showSiteInput: !prev._showSiteInput })) }}
              >
                {result._showSiteInput ? '닫기' : (result.has_site_context ? '재분석' : '수동 입력')}
              </button>
            </div>

            {/* 자동 분석 결과 */}
            {siteResult && !result._showSiteInput && (
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginTop: 8 }}>
                <img
                  src={getBriefSiteImageUrl(result.brief_id)}
                  alt="대지 위성사진"
                  style={{ width: 160, height: 160, objectFit: 'cover', borderRadius: 6,
                    border: '1px solid var(--color-border)', flexShrink: 0 }}
                />
                <div style={{ flex: 1, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)' }}>
                  {siteResult.matched_address && (
                    <div style={{ color: 'var(--color-text-muted)', fontSize: 11, marginBottom: 6 }}>
                      {siteResult.matched_address}
                    </div>
                  )}
                  {[
                    ['방위·형상', siteResult.analysis?.orientation],
                    ['접도 조건', siteResult.analysis?.road_access],
                    ['주변 용도', siteResult.analysis?.surrounding_uses],
                    ['자연자산', siteResult.analysis?.natural_assets],
                  ].map(([label, val]) => val && val !== '위성 확인 불가' && (
                    <div key={label} style={{ marginBottom: 3 }}>
                      <span style={{ color: 'var(--color-text-muted)', marginRight: 4 }}>{label}:</span>{val}
                    </div>
                  ))}
                  {siteResult.analysis?.overall_summary && (
                    <div style={{ marginTop: 6, padding: '6px 10px', borderRadius: 6,
                      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
                      fontStyle: 'italic' }}>
                      {siteResult.analysis.overall_summary}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 미완료 안내 */}
            {!siteResult && !result._showSiteInput && (
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                지침서 분석 시 자동 실행됩니다. 주소 추출 실패 시 수동 입력을 사용하세요.
              </div>
            )}

            {/* 수동 입력 (재분석 / 오류 보정) */}
            {result._showSiteInput && (
              <div style={{ marginTop: 10 }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                  <input
                    style={{ ...s.input, flex: 1, marginTop: 0 }}
                    value={siteAddr}
                    onChange={e => setSiteAddr(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSiteAnalyze()}
                    placeholder="대지 주소 (예: 서울시 영등포구 여의대방로 358)"
                    autoFocus
                  />
                  <button
                    style={{ ...s.dlBtn(true), whiteSpace: 'nowrap', ...(siteAnalyzing || !siteAddr.trim() ? s.btnDisabled : {}) }}
                    onClick={handleSiteAnalyze}
                    disabled={siteAnalyzing || !siteAddr.trim()}
                  >
                    {siteAnalyzing ? '분석 중...' : '실행'}
                  </button>
                </div>
                {siteErr && (
                  <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-danger)' }}>{siteErr}</div>
                )}
              </div>
            )}
          </div>

          <div style={{
            border: '1px solid var(--color-accent)', borderRadius: 10, padding: '16px 18px',
            marginBottom: 24, background: 'var(--color-bg-surface-alt)',
          }}>
            <div style={{ fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 4 }}>
              📋 프로젝트 수주 제안서
            </div>
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', marginBottom: 12 }}>
              지침서 근거 위에서 수주 핵심 테마·설계 접근 방향·착수 우선순위·리스크·체크리스트를 제안합니다
              (요약·정리를 넘어선 전략 제안 · 당락 예측 아님 · API 토큰 사용).
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <button
                style={{ ...s.dlBtn(true), ...(proposing ? s.btnDisabled : {}) }}
                onClick={() => handlePropose()}
                disabled={proposing}
              >
                {proposing ? '제안서 생성 중...' : (result.has_proposal ? '🔄 제안서 다시 생성' : '✦ 제안서 생성')}
              </button>
              {result.has_proposal && (
                <button
                  style={s.dlBtn(false)}
                  onClick={() => handleHtml(`${result.brief_id}_proposal.html`)}
                >
                  📄 제안서 열기
                </button>
              )}
              {proposeErr && (
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-danger)' }}>{proposeErr}</span>
              )}
            </div>
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

    {history.length > 0 && (
      <div style={s.historyPanel}>
        <div style={s.sectionTitle}>분석 이력</div>
        {history.map(item => {
          const name = item.brief_name || item.brief_id
          const dateStr = item.analyzed_at
            ? new Date(item.analyzed_at).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
            : ''
          const sv = item.validation_summary || {}
          return (
            <div key={item.brief_id} style={s.historyCard}>
              <div style={s.historyCardTop}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={s.historyName}>{name}</div>
                  <div style={s.historyMeta}>
                    {facilityLabel(item.facility_type)}
                    {dateStr ? ` · ${dateStr}` : ''}
                    {item.total_pages ? ` · ${item.total_pages}p` : ''}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <span style={s.fmtBadge}>
                      {item.source_format === 'multi' ? '복수파일' : (item.source_format || 'pdf').toUpperCase()}
                    </span>
                    {item.has_insight && <span style={s.insightBadge}>AI 해설</span>}
                    {item.has_proposal && (
                      <span style={{ ...s.insightBadge, background: 'var(--color-accent-bg, #fdecee)', borderColor: 'var(--color-accent)', color: 'var(--color-accent)' }}>제안서</span>
                    )}
                    {(['high', 'medium', 'low']).map(sev =>
                      sv[sev] ? (
                        <span key={sev} style={s.badge(sev)}>{SEV[sev].label} {sv[sev]}</span>
                      ) : null
                    )}
                  </div>
                </div>
                <div style={s.historyActions}>
                  {item.has_html && (
                    <button style={s.historyBtn(true)} onClick={() => handleHtml(`${item.brief_id}.html`)}>
                      리포트 열기
                    </button>
                  )}
                  {item.has_proposal ? (
                    <button style={s.historyBtn(false)} onClick={() => handleHtml(`${item.brief_id}_proposal.html`)}>
                      제안서 열기
                    </button>
                  ) : (
                    <button
                      style={{ ...s.historyBtn(false), ...(proposing ? s.btnDisabled : {}) }}
                      onClick={() => handlePropose(item.brief_id)}
                      disabled={proposing}
                    >
                      {proposing ? '생성 중...' : '제안서 생성'}
                    </button>
                  )}
                  {item.has_xlsx && (
                    <button style={s.historyBtn(false)} onClick={() => handleDownload(getBriefExportUrl(`${item.brief_id}.xlsx`), `${item.brief_id}.xlsx`)}>
                      xlsx
                    </button>
                  )}
                  {item.has_md && (
                    <button style={s.historyBtn(false)} onClick={() => handleDownload(getBriefExportUrl(`${item.brief_id}.md`), `${item.brief_id}.md`)}>
                      md
                    </button>
                  )}
                  {item.has_site_context && (
                    <button
                      style={{ ...s.historyBtn(false), color: 'var(--color-info)' }}
                      onClick={() => {
                        const next = siteViewId === item.brief_id ? null : item.brief_id
                        setSiteViewId(next)
                        if (next && !siteViewData[next]) {
                          getBriefSiteContext(next)
                            .then(sc => setSiteViewData(prev => ({ ...prev, [next]: sc })))
                            .catch(() => {})
                        }
                      }}
                    >
                      🛰 대지분석 보기
                    </button>
                  )}
                  <button
                    style={{ ...s.historyBtn(false), color: 'var(--color-text-muted)' }}
                    onClick={() => {
                      setSiteHistoryId(siteHistoryId === item.brief_id ? null : item.brief_id)
                      setSiteHistoryErr('')
                      setSiteHistoryAddr('')
                    }}
                  >
                    🛰 {item.has_site_context ? '재분석' : '대지분석'}
                  </button>
                </div>
              </div>
              {siteViewId === item.brief_id && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--color-border)' }}>
                  {siteViewData[item.brief_id] ? (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                      <img
                        src={getBriefSiteImageUrl(item.brief_id)}
                        alt="대지 위성사진"
                        style={{ width: 140, height: 140, objectFit: 'cover', borderRadius: 6,
                          border: '1px solid var(--color-border)', flexShrink: 0 }}
                      />
                      <div style={{ flex: 1, fontSize: 12, color: 'var(--color-text-body)' }}>
                        {siteViewData[item.brief_id].matched_address && (
                          <div style={{ color: 'var(--color-text-muted)', fontSize: 11, marginBottom: 4 }}>
                            {siteViewData[item.brief_id].matched_address}
                          </div>
                        )}
                        {[
                          ['방위·형상', siteViewData[item.brief_id].analysis?.orientation],
                          ['접도 조건', siteViewData[item.brief_id].analysis?.road_access],
                          ['주변 용도', siteViewData[item.brief_id].analysis?.surrounding_uses],
                          ['자연자산', siteViewData[item.brief_id].analysis?.natural_assets],
                        ].map(([label, val]) => val && val !== '위성 확인 불가' && (
                          <div key={label} style={{ marginBottom: 2 }}>
                            <span style={{ color: 'var(--color-text-muted)', marginRight: 4 }}>{label}:</span>{val}
                          </div>
                        ))}
                        {siteViewData[item.brief_id].analysis?.overall_summary && (
                          <div style={{ marginTop: 6, padding: '5px 8px', borderRadius: 5,
                            background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
                            fontStyle: 'italic' }}>
                            {siteViewData[item.brief_id].analysis.overall_summary}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>로딩 중...</div>
                  )}
                </div>
              )}
              {siteHistoryId === item.brief_id && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--color-border)' }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      style={{ ...s.input, flex: 1, marginTop: 0 }}
                      value={siteHistoryAddr}
                      onChange={e => setSiteHistoryAddr(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleHistorySiteAnalyze(item.brief_id)}
                      placeholder="대지 주소 (예: 서울시 영등포구 여의대방로 358)"
                      autoFocus
                    />
                    <button
                      style={{ ...s.historyBtn(true), whiteSpace: 'nowrap', ...(!siteHistoryAddr.trim() || siteHistoryBusy ? s.btnDisabled : {}) }}
                      onClick={() => handleHistorySiteAnalyze(item.brief_id)}
                      disabled={!siteHistoryAddr.trim() || siteHistoryBusy}
                    >
                      {siteHistoryBusy ? '분석 중...' : '실행'}
                    </button>
                  </div>
                  {siteHistoryErr && (
                    <div style={{ color: 'var(--color-danger)', fontSize: 12, marginTop: 6 }}>{siteHistoryErr}</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    )}
    </>
  )
}
