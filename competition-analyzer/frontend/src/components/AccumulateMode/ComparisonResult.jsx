import { COMPLIANCE_COLOR } from '../../constants'
import { useMeta } from '../../hooks/useMeta'

function AxisCard({ axis, data, axisLabel }) {
  return (
    <div style={{
      background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8, padding: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, color: '#90cdf4' }}>{axisLabel(axis)}</span>
        {data.score != null && (
          <span style={{ fontSize: 20, fontWeight: 700, color: '#f6e05e' }}>
            {data.score.toFixed(1)}
          </span>
        )}
      </div>
      {data.brief_compliance && (
        <div style={{ marginBottom: 6 }}>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 20,
            background: COMPLIANCE_COLOR[data.brief_compliance] || '#718096',
            color: '#0d1117', fontWeight: 600,
          }}>
            지침 {data.brief_compliance}
          </span>
        </div>
      )}
      {data.strengths?.length > 0 && (
        <div style={{ fontSize: 12, color: '#68d391', marginTop: 4 }}>
          ▲ {data.strengths.join(' · ')}
        </div>
      )}
      {data.weaknesses?.length > 0 && (
        <div style={{ fontSize: 12, color: '#fc8181', marginTop: 2 }}>
          ▼ {data.weaknesses.join(' · ')}
        </div>
      )}
      {data.notes && (
        <div style={{ fontSize: 12, color: '#a0aec0', marginTop: 4 }}>{data.notes}</div>
      )}
    </div>
  )
}

function GapAnalysisCard({ gap }) {
  if (!gap) return null
  const alignColor = { high: '#68d391', partial: '#f6ad55', low: '#fc8181' }[gap.alignment] || '#718096'
  const alignKr = { high: '일치도 높음', partial: '부분 일치', low: '낮은 일치', unknown: '—' }[gap.alignment] || '—'
  const match = gap.top1_matches_winner
  return (
    <div style={{
      background: '#0d1117', borderLeft: `4px solid ${alignColor}`,
      borderRadius: 8, padding: 14, marginBottom: 16,
    }}>
      <div style={{ fontSize: 13, color: '#90cdf4', fontWeight: 600, marginBottom: 8 }}>
        🔍 블라인드 분석 vs 실제 결과
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: alignColor }}>정렬 상태: {alignKr}</span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600,
          background: match ? '#1c4a2e' : '#2d1515',
          color: match ? '#68d391' : '#fc8181',
        }}>
          {match ? '✓ AI 1위 = 실제 당선' : '⚠ AI 1위 ≠ 실제 당선'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 20, fontSize: 12, color: '#a0aec0', flexWrap: 'wrap', marginBottom: 6 }}>
        <span>AI 1위: <strong style={{ color: '#e2e8f0' }}>{gap.blind_top1 || '—'}</strong></span>
        <span>실제 당선: <strong style={{ color: '#e2e8f0' }}>{(gap.actual_winners || []).join(' · ') || '—'}</strong></span>
      </div>
      {gap.notes && (
        <div style={{
          fontSize: 12, color: '#cbd5e0', lineHeight: 1.6,
          paddingTop: 8, borderTop: '1px solid #1a2535', marginTop: 6,
        }}>{gap.notes}</div>
      )}
      <div style={{ fontSize: 10, color: '#4a5568', fontStyle: 'italic', marginTop: 6 }}>
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
      <div style={{ fontSize: 15, fontWeight: 600, color: '#90cdf4', marginBottom: 12 }}>
        비교분석 결과
      </div>

      <GapAnalysisCard gap={gap_analysis} />

      {key_differentiators?.length > 0 && (
        <div style={{
          background: '#1a2a1a', border: '1px solid #276749', borderRadius: 8,
          padding: 12, marginBottom: 16, fontSize: 13, color: '#68d391',
        }}>
          <strong>핵심 차별화 요소:</strong> {key_differentiators.join(' · ')}
        </div>
      )}

      {ranking?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 6 }}>
            종합 순위 <span style={{ fontSize: 11, color: '#4a5568', fontWeight: 400 }}>(블라인드 분석 기준)</span>
          </div>
          {ranking.map((company, i) => (
            <div key={company} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%',
                background: i === 0 ? '#d69e2e' : i === 1 ? '#718096' : '#c05621',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#fff',
              }}>{i + 1}</span>
              <span style={{ color: '#e2e8f0', fontWeight: i === 0 ? 600 : 400 }}>{company}</span>
            </div>
          ))}
        </div>
      )}

      {submissions && Object.entries(submissions).map(([company, axes]) => (
        <div key={company} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 8 }}>
            {company}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
            {Object.entries(axes).map(([axis, axisData]) => (
              <AxisCard key={axis} axis={axis} data={axisData} axisLabel={axisLabel} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
