import { useEffect, useRef } from 'react'
import { useMeta } from '../../hooks/useMeta'

const STAGE_KR = {
  brief: '지침서 처리', brief_extract: '지침서 추출', submission: '제안서 처리',
  extract: '제안서 추출', compare: '비교분석', pattern: '패턴 업데이트',
  load_patterns: '패턴 로드', diagnose: 'AI 진단', report: '리포트 생성',
}

export default function ProgressLog({ events }) {
  const { pageTypeLabel } = useMeta()
  const ref = useRef()
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [events])

  function eventToText(ev) {
    if (ev.type === 'stage') return `▶ ${ev.msg || STAGE_KR[ev.stage] || ev.stage}`
    if (ev.type === 'progress') {
      const typeLabel = ev.page_type ? ` [${pageTypeLabel(ev.page_type)}]` : ''
      const co = ev.company ? ` (${ev.company})` : ''
      return `  ${ev.step}${co} ${ev.page}/${ev.total}${typeLabel}`
    }
    if (ev.type === 'done') return `✓ ${ev.step} 완료 (${ev.total_pages || ''} pages)`
    if (ev.type === 'info') return `  패턴: ${ev.win_count}개 당선작 로드됨`
    if (ev.type === 'complete') return '✅ 분석 완료'
    if (ev.type === 'error') return `❌ 오류: ${ev.message}${ev.detail ? '\n' + ev.detail : ''}`
    return JSON.stringify(ev)
  }

  return (
    <div
      ref={ref}
      style={{
        background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 8,
        padding: '12px 16px', fontFamily: 'monospace', fontSize: 'var(--font-size-sm)',
        color: 'var(--color-text-muted)', maxHeight: 280, overflowY: 'auto', lineHeight: 1.6,
      }}
    >
      {events.length === 0
        ? <span style={{ color: 'var(--color-text-muted)' }}>분석 로그가 여기에 표시됩니다...</span>
        : events.map((ev, i) => (
          <div key={i} style={{ color: ev.type === 'error' ? 'var(--color-danger)' : ev.type === 'complete' ? 'var(--color-success)' : undefined, whiteSpace: 'pre-wrap' }}>
            {eventToText(ev)}
          </div>
        ))
      }
    </div>
  )
}
