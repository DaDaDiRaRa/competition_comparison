import { COMPLIANCE_COLOR, GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'
import { useMeta } from '../../hooks/useMeta'

function AxisCard({ axis, data, axisLabel }) {
  const grade = toGrade(data)
  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, color: '#334155' }}>{axisLabel(axis)}</span>
        {grade && (
          <span style={{
            padding: '3px 12px', borderRadius: 14,
            background: GRADE_BG[grade], color: GRADE_COLOR[grade],
            fontWeight: 700, fontSize: 14, letterSpacing: 1,
          }}>
            {grade}
          </span>
        )}
      </div>
      {data.brief_compliance && (
        <div style={{ marginBottom: 6 }}>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 20,
            background: COMPLIANCE_COLOR[data.brief_compliance] || '#6b7280',
            color: '#ffffff', fontWeight: 600,
          }}>
            지침 {data.brief_compliance}
          </span>
        </div>
      )}
      {data.strengths?.length > 0 && (
        <div style={{ fontSize: 12, color: '#16a34a', marginTop: 4 }}>
          ▲ {data.strengths.join(' · ')}
        </div>
      )}
      {data.weaknesses?.length > 0 && (
        <div style={{ fontSize: 12, color: '#dc2626', marginTop: 2 }}>
          ▼ {data.weaknesses.join(' · ')}
        </div>
      )}
      {data.notes && (
        <div style={{ fontSize: 12, color: '#4b5563', marginTop: 4 }}>{data.notes}</div>
      )}
    </div>
  )
}

function GapAnalysisCard({ gap }) {
  if (!gap) return null
  const alignColor = { high: '#16a34a', partial: '#ea580c', low: '#dc2626' }[gap.alignment] || '#6b7280'
  const alignKr = { high: '일치도 높음', partial: '부분 일치', low: '낮은 일치', unknown: '—' }[gap.alignment] || '—'
  const match = gap.top1_matches_winner
  return (
    <div style={{
      background: '#ffffff', borderLeft: `4px solid ${alignColor}`,
      borderRadius: 8, padding: 14, marginBottom: 16,
    }}>
      <div style={{ fontSize: 13, color: '#334155', fontWeight: 600, marginBottom: 8 }}>
        🔍 블라인드 분석 vs 실제 결과
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: alignColor }}>정렬 상태: {alignKr}</span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600,
          background: match ? '#15803d' : '#fee2e2',
          color: match ? '#16a34a' : '#dc2626',
        }}>
          {match ? '✓ AI 1위 = 실제 당선' : '⚠ AI 1위 ≠ 실제 당선'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 20, fontSize: 12, color: '#4b5563', flexWrap: 'wrap', marginBottom: 6 }}>
        <span>AI 1위: <strong style={{ color: '#1f2937' }}>{gap.blind_top1 || '—'}</strong></span>
        <span>실제 당선: <strong style={{ color: '#1f2937' }}>{(gap.actual_winners || []).join(' · ') || '—'}</strong></span>
      </div>
      {gap.notes && (
        <div style={{
          fontSize: 12, color: '#374151', lineHeight: 1.6,
          paddingTop: 8, borderTop: '1px solid #f9fafb', marginTop: 6,
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
      <div style={{ fontSize: 15, fontWeight: 600, color: '#334155', marginBottom: 12 }}>
        비교분석 결과
      </div>

      <GapAnalysisCard gap={gap_analysis} />

      {key_differentiators?.length > 0 && (
        <div style={{
          background: '#1a2a1a', border: '1px solid #15803d', borderRadius: 8,
          padding: 12, marginBottom: 16, fontSize: 13, color: '#16a34a',
        }}>
          <strong>핵심 차별화 요소:</strong> {key_differentiators.join(' · ')}
        </div>
      )}

      {ranking?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 6 }}>
            종합 순위 <span style={{ fontSize: 11, color: '#4a5568', fontWeight: 400 }}>(블라인드 분석 기준)</span>
          </div>
          {ranking.map((company, i) => (
            <div key={company} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%',
                background: i === 0 ? '#d97706' : i === 1 ? '#6b7280' : '#c2410c',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#fff',
              }}>{i + 1}</span>
              <span style={{ color: '#1f2937', fontWeight: i === 0 ? 600 : 400 }}>{company}</span>
            </div>
          ))}
        </div>
      )}

      {submissions && Object.entries(submissions).map(([company, axes]) => (
        <div key={company} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#1f2937', marginBottom: 8 }}>
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
