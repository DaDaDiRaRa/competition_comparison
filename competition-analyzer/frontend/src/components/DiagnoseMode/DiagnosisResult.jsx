import { AXES_KR, COMPLIANCE_COLOR } from '../../constants'
import PageDistChart from '../common/PageDistChart'

function ScoreRing({ score }) {
  if (score == null) return null
  const color = score >= 7 ? '#68d391' : score >= 5 ? '#f6ad55' : '#fc8181'
  return (
    <div style={{
      width: 64, height: 64, borderRadius: '50%',
      border: `4px solid ${color}`, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <span style={{ fontSize: 20, fontWeight: 700, color }}>{score.toFixed(1)}</span>
      <span style={{ fontSize: 9, color: '#718096' }}>/ 10</span>
    </div>
  )
}

function AxisDiagCard({ axis, data }) {
  const compliance = data.brief_compliance || data.compliance
  return (
    <div style={{
      background: '#0d1117', border: '1px solid #2d3748', borderRadius: 10,
      padding: 16, display: 'flex', gap: 14,
    }}>
      <ScoreRing score={data.score} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{ fontWeight: 700, color: '#90cdf4', fontSize: 14 }}>
            {AXES_KR[axis] || axis}
          </span>
          {compliance && (
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 20,
              background: COMPLIANCE_COLOR[compliance] || '#718096',
              color: '#0d1117', fontWeight: 600,
            }}>
              지침 {compliance}
            </span>
          )}
        </div>
        {data.strengths?.length > 0 && (
          <div style={{ fontSize: 12, color: '#68d391', marginBottom: 4 }}>
            ▲ 강점: {data.strengths.join(' · ')}
          </div>
        )}
        {data.weaknesses?.length > 0 && (
          <div style={{ fontSize: 12, color: '#fc8181', marginBottom: 4 }}>
            ▼ 약점: {data.weaknesses.join(' · ')}
          </div>
        )}
        {data.recommendations?.length > 0 && (
          <div style={{ fontSize: 12, color: '#f6ad55' }}>
            → 보강: {data.recommendations.join(' / ')}
          </div>
        )}
      </div>
    </div>
  )
}

function MissingPageTypes({ gaps }) {
  if (!gaps?.length) return null
  return (
    <div style={{
      background: '#1a1200', border: '1px solid #744210', borderRadius: 8,
      padding: 12, marginBottom: 12,
    }}>
      <div style={{ fontSize: 13, color: '#f6ad55', marginBottom: 6 }}>
        ⚠ 누락 페이지 유형 (당선작 대비)
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {gaps.map(t => (
          <span key={t} style={{
            background: '#744210', color: '#fef3c7', fontSize: 12,
            padding: '2px 10px', borderRadius: 20,
          }}>{t}</span>
        ))}
      </div>
    </div>
  )
}

export default function DiagnosisResult({ data }) {
  if (!data) return null

  const overallColor = data.overall_score >= 7 ? '#68d391'
    : data.overall_score >= 5 ? '#f6ad55' : '#fc8181'

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        background: '#0d1117', border: '1px solid #2d3748', borderRadius: 12,
        padding: 20, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 20,
      }}>
        {data.overall_score != null && (
          <div style={{
            width: 90, height: 90, borderRadius: '50%',
            border: `5px solid ${overallColor}`,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: overallColor }}>
              {data.overall_score.toFixed(1)}
            </span>
            <span style={{ fontSize: 11, color: '#718096' }}>종합점수</span>
          </div>
        )}
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
            {data.competition_name || data.facility_type} 진단 결과
          </div>
          <div style={{ fontSize: 13, color: '#a0aec0' }}>
            총 {data.total_pages}페이지 분석 · {data.facility_type}
          </div>
          {data.strengths?.length > 0 && (
            <div style={{ fontSize: 13, color: '#68d391', marginTop: 6 }}>
              강점: {data.strengths.join(' · ')}
            </div>
          )}
          {data.weaknesses?.length > 0 && (
            <div style={{ fontSize: 13, color: '#fc8181', marginTop: 2 }}>
              약점: {data.weaknesses.join(' · ')}
            </div>
          )}
        </div>
      </div>

      <div style={{
        background: '#0d1117', border: '1px solid #2d3748', borderRadius: 10,
        padding: 16, marginBottom: 16,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#90cdf4', marginBottom: 8 }}>
          페이지 구성
        </div>
        <PageDistChart distribution={data.page_distribution} total={data.total_pages} />
      </div>

      {data.pattern_deviation && (
        <>
          <MissingPageTypes gaps={data.pattern_deviation.missing_page_types} />
          {data.pattern_deviation.page_distribution_gaps?.length > 0 && (
            <div style={{
              background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8,
              padding: 12, marginBottom: 12, fontSize: 13, color: '#a0aec0',
            }}>
              <strong style={{ color: '#e2e8f0' }}>페이지 배분 편차:</strong>{' '}
              {data.pattern_deviation.page_distribution_gaps.join(' · ')}
            </div>
          )}
        </>
      )}

      {data.axes && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 12, marginBottom: 20,
        }}>
          {Object.entries(data.axes).map(([axis, axisData]) => (
            <AxisDiagCard key={axis} axis={axis} data={axisData} />
          ))}
        </div>
      )}

      {data.recommendations?.length > 0 && (
        <div style={{
          background: '#0f2027', border: '1px solid #2c5282', borderRadius: 10, padding: 16,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#90cdf4', marginBottom: 10 }}>
            보강 포인트
          </div>
          {data.recommendations.map((rec, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 6 }}>
              <span style={{
                background: '#2b6cb0', color: '#fff', borderRadius: '50%',
                width: 20, height: 20, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0,
              }}>{i + 1}</span>
              <span style={{ fontSize: 13, color: '#e2e8f0' }}>{rec}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
