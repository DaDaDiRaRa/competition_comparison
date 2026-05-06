import { useEffect, useRef } from 'react'
import { PAGE_TYPE_KR } from '../../constants'

const STAGE_KR = {
  brief: '지침서 처리', brief_extract: '지침서 추출', submission: '제안서 처리',
  compare: '비교분석', pattern: '패턴 업데이트', load_patterns: '패턴 로드',
  diagnose: 'AI 진단',
}

function eventToText(ev) {
  if (ev.type === 'stage') return `▶ ${ev.msg || STAGE_KR[ev.stage] || ev.stage}`
  if (ev.type === 'progress') {
    const typeLabel = ev.page_type ? ` [${PAGE_TYPE_KR[ev.page_type] || ev.page_type}]` : ''
    const co = ev.company ? ` (${ev.company})` : ''
    return `  ${ev.step}${co} ${ev.page}/${ev.total}${typeLabel}`
  }
  if (ev.type === 'done') return `✓ ${ev.step} 완료 (${ev.total_pages || ''} pages)`
  if (ev.type === 'info') return `  패턴: ${ev.win_count}개 당선작 로드됨`
  if (ev.type === 'complete') return '✅ 분석 완료'
  if (ev.type === 'error') return `❌ 오류: ${ev.message}`
  return JSON.stringify(ev)
}

export default function ProgressLog({ events }) {
  const ref = useRef()
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [events])

  return (
    <div
      ref={ref}
      style={{
        background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8,
        padding: '12px 16px', fontFamily: 'monospace', fontSize: 12,
        color: '#a0aec0', maxHeight: 280, overflowY: 'auto', lineHeight: 1.6,
      }}
    >
      {events.length === 0
        ? <span style={{ color: '#4a5568' }}>분석 로그가 여기에 표시됩니다...</span>
        : events.map((ev, i) => (
          <div key={i} style={{ color: ev.type === 'error' ? '#fc8181' : ev.type === 'complete' ? '#68d391' : undefined }}>
            {eventToText(ev)}
          </div>
        ))
      }
    </div>
  )
}
