import { COMPLIANCE_COLOR } from '../../constants'
import { useMeta } from '../../hooks/useMeta'
import PageDistChart from '../common/PageDistChart'

const QUANT_META = {
  total_floor_area_sqm:          { label: '연면적',   unit: '㎡' },
  site_area_sqm:                 { label: '대지면적', unit: '㎡' },
  building_area_sqm:             { label: '건축면적', unit: '㎡' },
  floor_area_ratio_pct:          { label: '용적률',   unit: '%' },
  building_coverage_ratio_pct:   { label: '건폐율',   unit: '%' },
  floors_above:                  { label: '지상층수', unit: '층' },
  floors_below:                  { label: '지하층수', unit: '층' },
  parking_count:                 { label: '주차대수', unit: '대' },
}

function QuantCompare({ subQuant = {}, winQuant = {}, loseQuant = {} }) {
  const fields = Object.keys(QUANT_META).filter(
    k => subQuant[k] != null || winQuant[k]?.mean != null
  )
  if (!fields.length) return null

  const hasLose = Object.keys(loseQuant).length > 0
  const fmt = v => {
    if (v == null) return null
    const n = Number(v)
    if (isNaN(n)) return null
    return n >= 1000 ? n.toLocaleString('ko-KR', { maximumFractionDigits: 0 }) : n.toFixed(1)
  }

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #2d3748', borderRadius: 10,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#90cdf4', marginBottom: 12 }}>
        정량 지표 비교
        <span style={{ fontSize: 11, color: '#718096', fontWeight: 400, marginLeft: 8 }}>
          (당선 평균 vs {hasLose ? '낙선 평균 vs ' : ''}내 제출물)
        </span>
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
        <LegendDot color="#2b6cb0" label="당선 평균" />
        {hasLose && <LegendDot color="#744210" label="낙선 평균" />}
        <LegendDot color="#553c9a" label="내 제출물" />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {fields.map(k => {
          const meta = QUANT_META[k]
          const wVal = winQuant[k]?.mean ?? null
          const lVal = hasLose ? (loseQuant[k]?.mean ?? null) : null
          const sVal = subQuant[k] != null ? Number(subQuant[k]) : null
          const maxVal = Math.max(wVal ?? 0, lVal ?? 0, sVal ?? 0, 0.001)

          const wPct = wVal != null ? (wVal / maxVal) * 100 : 0
          const lPct = lVal != null ? (lVal / maxVal) * 100 : 0
          const sPct = sVal != null ? (sVal / maxVal) * 100 : 0

          // 내 제출물이 당선보다 낮으면 주의 색
          const sColor = (wVal != null && sVal != null && sVal < wVal * 0.85)
            ? '#fc8181' : (wVal != null && sVal != null && sVal >= wVal * 0.95)
            ? '#68d391' : '#b794f4'

          return (
            <div key={k}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ fontSize: 12, color: '#a0aec0' }}>
                  {meta.label} <span style={{ color: '#4a5568' }}>({meta.unit})</span>
                </span>
              </div>
              <BarRow pct={wPct} color="#2b6cb0" value={fmt(wVal)} unit={meta.unit} />
              {hasLose && lVal != null && (
                <BarRow pct={lPct} color="#744210" value={fmt(lVal)} unit={meta.unit} />
              )}
              {sVal != null && (
                <BarRow pct={sPct} color={sColor} value={fmt(sVal)} unit={meta.unit} isMine />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LegendDot({ color, label }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#a0aec0' }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
      {label}
    </span>
  )
}

function BarRow({ pct, color, value, unit, isMine }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
      <div style={{ flex: 1, background: '#1a2535', borderRadius: 3, height: 13, overflow: 'visible', position: 'relative' }}>
        <div style={{
          width: `${pct}%`, height: '100%', borderRadius: 3,
          background: color,
          position: 'relative',
          boxShadow: isMine ? `0 0 6px ${color}88` : 'none',
        }} />
      </div>
      <span style={{
        fontSize: 11, minWidth: 72, color: isMine ? color : '#718096',
        fontWeight: isMine ? 700 : 400,
      }}>
        {value != null ? `${value} ${unit}` : '—'}
        {isMine && ' ★'}
      </span>
    </div>
  )
}

const REQ_STATUS_COLOR = {
  yes: '#68d391',
  partial: '#f6ad55',
  no: '#fc8181',
  unclear: '#718096',
}

const REQ_STATUS_KR = {
  yes: '충족',
  partial: '부분충족',
  no: '미충족',
  unclear: '불명확',
}

function RequirementMapping({ mapping, axisLabel }) {
  if (!mapping?.length) return null
  return (
    <div style={{
      background: '#0d1117', border: '1px solid #2d3748', borderRadius: 10,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#90cdf4', marginBottom: 10 }}>
        지침서 요구사항 충족도
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: '#718096', borderBottom: '1px solid #2d3748' }}>
            <th style={{ textAlign: 'left', padding: '4px 8px', width: '35%' }}>요구사항</th>
            <th style={{ textAlign: 'left', padding: '4px 8px', width: '20%' }}>평가축</th>
            <th style={{ textAlign: 'center', padding: '4px 8px', width: '15%' }}>충족여부</th>
            <th style={{ textAlign: 'left', padding: '4px 8px' }}>근거</th>
          </tr>
        </thead>
        <tbody>
          {mapping.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #1a2535' }}>
              <td style={{ padding: '5px 8px', color: '#e2e8f0' }}>{row.requirement}</td>
              <td style={{ padding: '5px 8px', color: '#a0aec0' }}>
                {axisLabel(row.axis)}
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                <span style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 20,
                  background: REQ_STATUS_COLOR[row.status] || '#718096',
                  color: '#0d1117', fontWeight: 600,
                }}>
                  {REQ_STATUS_KR[row.status] || row.status}
                </span>
              </td>
              <td style={{ padding: '5px 8px', color: '#718096' }}>{row.evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

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

function AxisDiagCard({ axis, data, axisLabel }) {
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
            {axisLabel(axis)}
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
          <div style={{ fontSize: 12, color: '#f6ad55', marginBottom: 4 }}>
            → 보강: {data.recommendations.join(' / ')}
          </div>
        )}
        {data.evidence && (
          <div style={{ fontSize: 11, color: '#718096', fontStyle: 'italic', marginTop: 2 }}>
            근거: {data.evidence}
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

export default function DiagnosisResult({ data, pattern }) {
  const { axisLabel: _axisLabel } = useMeta()
  if (!data) return null

  const ft = data.facility_type || ''
  const axisLabel = (key) => _axisLabel(ft, key)

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

      <QuantCompare
        subQuant={data.submission_quantitative || {}}
        winQuant={pattern?.quantitative || {}}
        loseQuant={pattern?.loser_stats?.quantitative || {}}
      />

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
          {data.pattern_deviation.quantitative_gaps && Object.keys(data.pattern_deviation.quantitative_gaps).length > 0 && (
            <div style={{
              background: '#1a1200', border: '1px solid #744210', borderRadius: 8,
              padding: 12, marginBottom: 12,
            }}>
              <div style={{ fontSize: 13, color: '#f6ad55', marginBottom: 8 }}>
                ⚠ 정량 지표 편차 (당선·낙선 패턴 대비)
              </div>
              {Object.entries(data.pattern_deviation.quantitative_gaps).map(([k, v]) => (
                <div key={k} style={{ fontSize: 12, color: '#e2e8f0', marginBottom: 4 }}>
                  <span style={{ color: '#a0aec0', marginRight: 6 }}>{k}:</span>{v}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <RequirementMapping mapping={data.requirement_mapping} axisLabel={axisLabel} />

      {data.axes && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 12, marginBottom: 20,
        }}>
          {Object.entries(data.axes).map(([axis, axisData]) => (
            <AxisDiagCard key={axis} axis={axis} data={axisData} axisLabel={axisLabel} />
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
