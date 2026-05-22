import { COMPLIANCE_COLOR, GRADE_COLOR, toGrade } from '../../constants'
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
      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 10,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 12 }}>
        정량 지표 비교
        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)', fontWeight: 'var(--font-weight-regular)', marginLeft: 8 }}>
          (당선 평균 vs {hasLose ? '낙선 평균 vs ' : ''}내 제출물)
        </span>
      </div>
      <div style={{ display: 'flex', gap: 'var(--gap-md)', marginBottom: 10 }}>
        <LegendDot color="var(--color-accent)" label="당선 평균" />
        {hasLose && <LegendDot color="var(--color-amber-dark)" label="낙선 평균" />}
        <LegendDot color="var(--color-info)" label="내 제출물" />
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
            ? 'var(--color-danger)' : (wVal != null && sVal != null && sVal >= wVal * 0.95)
            ? 'var(--color-success)' : 'var(--color-info)'

          return (
            <div key={k}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {meta.label} <span style={{ color: 'var(--color-text-muted)' }}>({meta.unit})</span>
                </span>
              </div>
              <BarRow pct={wPct} color="var(--color-accent)" value={fmt(wVal)} unit={meta.unit} />
              {hasLose && lVal != null && (
                <BarRow pct={lPct} color="var(--color-amber-dark)" value={fmt(lVal)} unit={meta.unit} />
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
    <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-xs)', fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)' }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
      {label}
    </span>
  )
}

function BarRow({ pct, color, value, unit, isMine }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
      <div style={{ flex: 1, background: 'var(--color-bg-surface-alt)', borderRadius: 3, height: 13, overflow: 'visible', position: 'relative' }}>
        <div style={{
          width: `${pct}%`, height: '100%', borderRadius: 3,
          background: color,
          position: 'relative',
          boxShadow: isMine ? `0 0 6px ${color}88` : 'none',
        }} />
      </div>
      <span style={{
        fontSize: 'var(--font-size-xs)', minWidth: 72, color: isMine ? color : 'var(--color-text-faint)',
        fontWeight: isMine ? 700 : 400,
      }}>
        {value != null ? `${value} ${unit}` : '—'}
        {isMine && ' ★'}
      </span>
    </div>
  )
}

const REQ_STATUS_COLOR = {
  yes: 'var(--color-success)',
  partial: 'var(--color-grade-d)',
  no: 'var(--color-danger)',
  unclear: 'var(--color-text-faint)',
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
      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 10,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 10 }}>
        지침서 요구사항 충족도
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-size-sm)' }}>
        <thead>
          <tr style={{ color: 'var(--color-text-faint)', borderBottom: '1px solid var(--color-border)' }}>
            <th style={{ textAlign: 'left', padding: '4px 8px', width: '35%' }}>요구사항</th>
            <th style={{ textAlign: 'left', padding: '4px 8px', width: '20%' }}>평가축</th>
            <th style={{ textAlign: 'center', padding: '4px 8px', width: '15%' }}>충족여부</th>
            <th style={{ textAlign: 'left', padding: '4px 8px' }}>근거</th>
          </tr>
        </thead>
        <tbody>
          {mapping.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid var(--color-bg-surface-alt)' }}>
              <td style={{ padding: '5px 8px', color: 'var(--color-text-body)' }}>{row.requirement}</td>
              <td style={{ padding: '5px 8px', color: 'var(--color-text-muted)' }}>
                {axisLabel(row.axis)}
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                <span style={{
                  fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20,
                  background: REQ_STATUS_COLOR[row.status] || 'var(--color-text-faint)',
                  color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-semibold)',
                }}>
                  {REQ_STATUS_KR[row.status] || row.status}
                </span>
              </td>
              <td style={{ padding: '5px 8px', color: 'var(--color-text-faint)' }}>{row.evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GradeRing({ grade }) {
  if (!grade) return null
  const color = GRADE_COLOR[grade] || 'var(--color-text-faint)'
  return (
    <div style={{
      width: 64, height: 64, borderRadius: '50%',
      border: `4px solid ${color}`, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <span style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 'var(--font-weight-bold)', color }}>{grade}</span>
      <span style={{ fontSize: 9, color: 'var(--color-text-faint)' }}>등급</span>
    </div>
  )
}

function AxisDiagCard({ axis, data, axisLabel }) {
  const compliance = data.brief_compliance || data.compliance
  return (
    <div style={{
      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 10,
      padding: 16, display: 'flex', gap: 14,
    }}>
      <GradeRing grade={toGrade(data)} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)', marginBottom: 8 }}>
          <span style={{ fontWeight: 'var(--font-weight-bold)', color: 'var(--color-accent)', fontSize: 'var(--font-size-base)' }}>
            {axisLabel(axis)}
          </span>
          {compliance && (
            <span style={{
              fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 20,
              background: COMPLIANCE_COLOR[compliance] || 'var(--color-text-faint)',
              color: 'var(--color-bg-surface)', fontWeight: 'var(--font-weight-semibold)',
            }}>
              지침 {compliance}
            </span>
          )}
        </div>
        {data.strengths?.length > 0 && (
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-success)', marginBottom: 4 }}>
            ▲ 강점: {data.strengths.join(' · ')}
          </div>
        )}
        {data.weaknesses?.length > 0 && (
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-danger)', marginBottom: 4 }}>
            ▼ 약점: {data.weaknesses.join(' · ')}
          </div>
        )}
        {data.recommendations?.length > 0 && (
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-grade-d)', marginBottom: 4 }}>
            → 보강: {data.recommendations.join(' / ')}
          </div>
        )}
        {data.evidence && (
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)', fontStyle: 'italic', marginTop: 2 }}>
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
      background: 'var(--color-warning-bg)', border: '1px solid var(--color-amber-dark)', borderRadius: 8,
      padding: 12, marginBottom: 12,
    }}>
      <div style={{ fontSize: 13, color: 'var(--color-grade-d)', marginBottom: 6 }}>
        ⚠ 누락 페이지 유형 (당선작 대비)
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {gaps.map(t => (
          <span key={t} style={{
            background: 'var(--color-amber-dark)', color: 'var(--color-warning-bg)', fontSize: 'var(--font-size-sm)',
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

  const overallGrade = toGrade(data)
  const overallColor = GRADE_COLOR[overallGrade] || 'var(--color-text-faint)'

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 12,
        padding: 20, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 'var(--gap-lg)',
      }}>
        {overallGrade && (
          <div style={{
            width: 90, height: 90, borderRadius: '50%',
            border: `5px solid ${overallColor}`,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <span style={{ fontSize: 36, fontWeight: 'var(--font-weight-bold)', color: overallColor }}>
              {overallGrade}
            </span>
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)' }}>종합등급</span>
          </div>
        )}
        <div>
          <div style={{ fontSize: 16, fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 4 }}>
            {data.competition_name || data.facility_type} 진단 결과
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
            총 {data.total_pages}페이지 분석 · {data.facility_type}
          </div>
          {data.strengths?.length > 0 && (
            <div style={{ fontSize: 13, color: 'var(--color-success)', marginTop: 6 }}>
              강점: {data.strengths.join(' · ')}
            </div>
          )}
          {data.weaknesses?.length > 0 && (
            <div style={{ fontSize: 13, color: 'var(--color-danger)', marginTop: 2 }}>
              약점: {data.weaknesses.join(' · ')}
            </div>
          )}
        </div>
      </div>

      <div style={{
        background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 10,
        padding: 16, marginBottom: 16,
      }}>
        <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 8 }}>
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
              background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 8,
              padding: 12, marginBottom: 12, fontSize: 13, color: 'var(--color-text-muted)',
            }}>
              <strong style={{ color: 'var(--color-text-body)' }}>페이지 배분 편차:</strong>{' '}
              {data.pattern_deviation.page_distribution_gaps.join(' · ')}
            </div>
          )}
          {data.pattern_deviation.quantitative_gaps && Object.keys(data.pattern_deviation.quantitative_gaps).length > 0 && (
            <div style={{
              background: 'var(--color-warning-bg)', border: '1px solid var(--color-amber-dark)', borderRadius: 8,
              padding: 12, marginBottom: 12,
            }}>
              <div style={{ fontSize: 13, color: 'var(--color-grade-d)', marginBottom: 8 }}>
                ⚠ 정량 지표 편차 (당선·낙선 패턴 대비)
              </div>
              {Object.entries(data.pattern_deviation.quantitative_gaps).map(([k, v]) => (
                <div key={k} style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-body)', marginBottom: 4 }}>
                  <span style={{ color: 'var(--color-text-muted)', marginRight: 6 }}>{k}:</span>{v}
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
          gap: 'var(--gap-md)', marginBottom: 20,
        }}>
          {Object.entries(data.axes).map(([axis, axisData]) => (
            <AxisDiagCard key={axis} axis={axis} data={axisData} axisLabel={axisLabel} />
          ))}
        </div>
      )}

      {data.recommendations?.length > 0 && (
        <div style={{
          background: 'var(--color-bg-surface-alt)', border: '1px solid var(--color-accent-hover)', borderRadius: 10, padding: 16,
        }}>
          <div style={{ fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)', marginBottom: 10 }}>
            보강 포인트
          </div>
          {data.recommendations.map((rec, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 6 }}>
              <span style={{
                background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', borderRadius: '50%',
                width: 20, height: 20, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 'var(--font-size-xs)', fontWeight: 'var(--font-weight-bold)', flexShrink: 0,
              }}>{i + 1}</span>
              <span style={{ fontSize: 13, color: 'var(--color-text-body)' }}>{rec}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
