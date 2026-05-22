import { COMPLIANCE_COLOR, GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'
import { useMeta } from '../../hooks/useMeta'

function AxisCard({ axis, data, axisLabel }) {
  const grade = toGrade(data)
  return (
    <div style={{
      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 8, padding: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)' }}>{axisLabel(axis)}</span>
        {grade && (
          <span style={{
            padding: '3px 12px', borderRadius: 14,
            background: GRADE_BG[grade], color: GRADE_COLOR[grade],
            fontWeight: 'var(--font-weight-bold)', fontSize: 'var(--font-size-base)', letterSpacing: 1,
          }}>
            {grade}
          </span>
        )}
      </div>
      {data.brief_compliance && (
        <div style={{ marginBottom: 6 }}>
          <span style={{
            fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20,
            background: COMPLIANCE_COLOR[data.brief_compliance] || 'var(--color-text-faint)',
            color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-semibold)',
          }}>
            지침 {data.brief_compliance}
          </span>
        </div>
      )}
      {data.strengths?.length > 0 && (
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-success)', marginTop: 4 }}>
          ▲ {data.strengths.join(' · ')}
        </div>
      )}
      {data.weaknesses?.length > 0 && (
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-danger)', marginTop: 2 }}>
          ▼ {data.weaknesses.join(' · ')}
        </div>
      )}
      {data.notes && (
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', marginTop: 4 }}>{data.notes}</div>
      )}
    </div>
  )
}

function GapAnalysisCard({ gap }) {
  if (!gap) return null
  const alignColor = { high: 'var(--color-success)', partial: 'var(--color-grade-d)', low: 'var(--color-danger)' }[gap.alignment] || 'var(--color-text-faint)'
  const alignKr = { high: '일치도 높음', partial: '부분 일치', low: '낮은 일치', unknown: '—' }[gap.alignment] || '—'
  const match = gap.top1_matches_winner
  return (
    <div style={{
      background: 'var(--color-bg-surface)', borderLeft: `4px solid ${alignColor}`,
      borderRadius: 8, padding: 14, marginBottom: 16,
    }}>
      <div style={{ fontSize: 13, color: 'var(--color-accent)', fontWeight: 'var(--font-weight-semibold)', marginBottom: 8 }}>
        🔍 블라인드 분석 vs 실제 결과
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-bold)', color: alignColor }}>정렬 상태: {alignKr}</span>
        <span style={{
          fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20, fontWeight: 'var(--font-weight-semibold)',
          background: match ? 'var(--color-success)' : 'var(--color-danger-bg)',
          color: match ? 'var(--color-success)' : 'var(--color-danger)',
        }}>
          {match ? '✓ AI 1위 = 실제 당선' : '⚠ AI 1위 ≠ 실제 당선'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 'var(--gap-lg)', fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', flexWrap: 'wrap', marginBottom: 6 }}>
        <span>AI 1위: <strong style={{ color: 'var(--color-text-body)' }}>{gap.blind_top1 || '—'}</strong></span>
        <span>실제 당선: <strong style={{ color: 'var(--color-text-body)' }}>{(gap.actual_winners || []).join(' · ') || '—'}</strong></span>
      </div>
      {gap.notes && (
        <div style={{
          fontSize: 'var(--font-size-sm)', color: '#374151', lineHeight: 1.6,
          paddingTop: 8, borderTop: '1px solid var(--color-bg-surface-alt)', marginTop: 6,
        }}>{gap.notes}</div>
      )}
      <div style={{ fontSize: 10, color: 'var(--color-text-muted)', fontStyle: 'italic', marginTop: 6 }}>
        * 블라인드 채점 후 실제 결과와 비교한 사후 분석
      </div>
    </div>
  )
}

export default function ComparisonResult({ data, facility_type = '' }) {
  const { axisLabel: _axisLabel } = useMeta()
  if (!data) return null
  const { submissions, ranking, key_differentiators, gap_analysis } = data
  const axisLabel = (key) => _axisLabel(facility_type, key)

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 12 }}>
        비교분석 결과
      </div>

      <GapAnalysisCard gap={gap_analysis} />

      {key_differentiators?.length > 0 && (
        <div style={{
          background: '#1a2a1a', border: '1px solid var(--color-success)', borderRadius: 8,
          padding: 12, marginBottom: 16, fontSize: 13, color: 'var(--color-success)',
        }}>
          <strong>핵심 차별화 요소:</strong> {key_differentiators.join(' · ')}
        </div>
      )}

      {ranking?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 6 }}>
            종합 순위 <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', fontWeight: 'var(--font-weight-regular)' }}>(블라인드 분석 기준)</span>
          </div>
          {ranking.map((company, i) => (
            <div key={company} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%',
                background: i === 0 ? '#d97706' : i === 1 ? 'var(--color-text-faint)' : '#c2410c',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-bold)', color: 'var(--color-text-on-accent)',
              }}>{i + 1}</span>
              <span style={{ color: 'var(--color-text-body)', fontWeight: i === 0 ? 600 : 400 }}>{company}</span>
            </div>
          ))}
        </div>
      )}

      {submissions && Object.entries(submissions).map(([company, axes]) => (
        <div key={company} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 8 }}>
            {company}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--gap-sm)' }}>
            {Object.entries(axes).map(([axis, axisData]) => (
              <AxisCard key={axis} axis={axis} data={axisData} axisLabel={axisLabel} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
