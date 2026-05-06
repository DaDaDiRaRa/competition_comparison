import { AXES_KR, COMPLIANCE_COLOR } from '../../constants'

function AxisCard({ axis, data }) {
  return (
    <div style={{
      background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8, padding: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, color: '#90cdf4' }}>{AXES_KR[axis] || axis}</span>
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

export default function ComparisonResult({ data }) {
  if (!data) return null
  const { submissions, ranking, key_differentiators } = data

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#90cdf4', marginBottom: 12 }}>
        비교분석 결과
      </div>

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
          <div style={{ fontSize: 13, color: '#a0aec0', marginBottom: 6 }}>종합 순위</div>
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
              <AxisCard key={axis} axis={axis} data={axisData} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
