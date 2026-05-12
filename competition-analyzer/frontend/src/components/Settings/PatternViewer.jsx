import { useState, useEffect } from 'react'
import { getPattern, rebuildPattern } from '../../api/client'
import { useMeta } from '../../hooks/useMeta'

const QUANT_LABELS = {
  total_floor_area_sqm: { label: '연면적', unit: '㎡' },
  site_area_sqm: { label: '대지면적', unit: '㎡' },
  building_area_sqm: { label: '건축면적', unit: '㎡' },
  floor_area_ratio_pct: { label: '용적률', unit: '%' },
  building_coverage_ratio_pct: { label: '건폐율', unit: '%' },
  floors_above: { label: '지상층수', unit: '층' },
  floors_below: { label: '지하층수', unit: '층' },
  parking_count: { label: '주차대수', unit: '대' },
}

const s = {
  sec: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 10,
    padding: 16, marginBottom: 14,
  },
  secTitle: {
    fontSize: 13, fontWeight: 700, color: '#1e3a8a', marginBottom: 12,
    paddingBottom: 6, borderBottom: '1px solid #e5e7eb',
  },
}

function PageDistBars({ winDist = {}, loseDist = {}, pageTypeLabel }) {
  const allKeys = Array.from(
    new Set([
      ...Object.keys(winDist).filter(k => !k.endsWith('_ratio')),
      ...Object.keys(loseDist).filter(k => !k.endsWith('_ratio')),
    ])
  )
  if (!allKeys.length) return <div style={{ color: '#4a5568', fontSize: 12 }}>데이터 없음</div>

  const maxVal = allKeys.reduce((m, k) => {
    return Math.max(m, winDist[k]?.mean || 0, loseDist[k]?.mean || 0)
  }, 0.1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#4b5563' }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#1e3a8a', display: 'inline-block' }} />
          당선
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#4b5563' }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#92400e', display: 'inline-block' }} />
          낙선
        </span>
      </div>
      {allKeys.map(k => {
        const wm = winDist[k]?.mean || 0
        const lm = loseDist[k]?.mean || 0
        const wStd = winDist[k]?.std
        const lStd = loseDist[k]?.std
        return (
          <div key={k} style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: '#4b5563', textAlign: 'right' }}>
              {pageTypeLabel(k)}
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ flex: 1, background: '#f9fafb', borderRadius: 2, height: 11, overflow: 'hidden' }}>
                  <div style={{ width: `${(wm / maxVal) * 100}%`, height: '100%', background: '#1e3a8a', borderRadius: 2 }} />
                </div>
                <span style={{ fontSize: 10, color: '#6b7280', minWidth: 42 }}>
                  {wm.toFixed(1)}{wStd != null ? `±${wStd.toFixed(1)}` : ''}
                </span>
              </div>
              {Object.keys(loseDist).length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ flex: 1, background: '#f9fafb', borderRadius: 2, height: 11, overflow: 'hidden' }}>
                    <div style={{ width: `${(lm / maxVal) * 100}%`, height: '100%', background: '#92400e', borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: 10, color: '#6b7280', minWidth: 42 }}>
                    {lm.toFixed(1)}{lStd != null ? `±${lStd.toFixed(1)}` : ''}
                  </span>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function QuantTable({ winQuant = {}, loseQuant = {} }) {
  const fields = Object.keys(QUANT_LABELS).filter(
    k => winQuant[k]?.mean != null || loseQuant[k]?.mean != null
  )
  if (!fields.length) return <div style={{ color: '#4a5568', fontSize: 12 }}>데이터 없음</div>

  const hasLose = Object.keys(loseQuant).length > 0

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ color: '#6b7280', borderBottom: '1px solid #e5e7eb' }}>
          <th style={{ textAlign: 'left', padding: '4px 8px' }}>지표</th>
          <th style={{ textAlign: 'right', padding: '4px 8px', color: '#1e3a8a' }}>당선 평균</th>
          {hasLose && (
            <th style={{ textAlign: 'right', padding: '4px 8px', color: '#92400e' }}>낙선 평균</th>
          )}
        </tr>
      </thead>
      <tbody>
        {fields.map(f => {
          const meta = QUANT_LABELS[f]
          const wm = winQuant[f]?.mean
          const lm = loseQuant[f]?.mean
          const fmt = v => v == null ? '—' : Number.isInteger(v) ? v.toLocaleString() : v.toFixed(1)
          return (
            <tr key={f} style={{ borderBottom: '1px solid #f9fafb' }}>
              <td style={{ padding: '5px 8px', color: '#4b5563' }}>
                {meta.label} <span style={{ color: '#4a5568' }}>({meta.unit})</span>
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right', color: '#1f2937', fontWeight: 600 }}>
                {fmt(wm)}
              </td>
              {hasLose && (
                <td style={{ padding: '5px 8px', textAlign: 'right', color: '#1f2937' }}>
                  {fmt(lm)}
                </td>
              )}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function KeywordCloud({ keywords = {}, loseKeywords = {} }) {
  const entries = Object.entries(keywords).sort((a, b) => b[1] - a[1]).slice(0, 20)
  if (!entries.length) return <div style={{ color: '#4a5568', fontSize: 12 }}>데이터 없음</div>

  const hasLose = Object.keys(loseKeywords).length > 0

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {entries.map(([kw, freq]) => {
        const loseFreq = loseKeywords[kw] || 0
        const diff = freq - loseFreq
        const bg = diff > 0.2 ? '#15803d' : diff < -0.2 ? '#fee2e2' : '#f9fafb'
        const color = diff > 0.2 ? '#16a34a' : diff < -0.2 ? '#dc2626' : '#4b5563'
        return (
          <span key={kw} title={hasLose ? `당선 ${(freq*100).toFixed(0)}% / 낙선 ${(loseFreq*100).toFixed(0)}%` : `${(freq*100).toFixed(0)}%`} style={{
            background: bg, color, fontSize: 12,
            padding: '3px 10px', borderRadius: 20,
            border: `1px solid ${color}33`,
          }}>
            {kw} <span style={{ fontSize: 10, opacity: 0.7 }}>{(freq * 100).toFixed(0)}%</span>
          </span>
        )
      })}
    </div>
  )
}

function QualitativeInsights({ insights }) {
  if (!insights) return null
  const { winner_patterns = [], loser_patterns = [], key_differentiators = [] } = insights

  const col = (title, items, color) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color, marginBottom: 8 }}>{title}</div>
      {items.length === 0
        ? <div style={{ fontSize: 12, color: '#4a5568' }}>없음</div>
        : items.map((item, i) => (
            <div key={i} style={{
              fontSize: 12, color: '#1f2937', padding: '5px 10px', marginBottom: 4,
              background: '#ffffff', borderRadius: 4, borderLeft: `3px solid ${color}`,
            }}>
              {item}
            </div>
          ))
      }
    </div>
  )

  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      {col('당선 패턴', winner_patterns, '#16a34a')}
      {col('낙선 패턴', loser_patterns, '#dc2626')}
      {col('차별화 요소', key_differentiators, '#ea580c')}
    </div>
  )
}

export default function PatternViewer() {
  const { facilityTypes, pageTypeLabel, ready } = useMeta()
  const [selectedFt, setSelectedFt] = useState('')
  const [pattern, setPattern] = useState(null)
  const [loading, setLoading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildMsg, setRebuildMsg] = useState('')

  useEffect(() => {
    if (ready && facilityTypes.length && !selectedFt) {
      setSelectedFt(facilityTypes[0].key)
    }
  }, [ready, facilityTypes])

  useEffect(() => {
    if (!selectedFt) return
    setLoading(true)
    setPattern(null)
    getPattern(selectedFt)
      .then(p => setPattern(p?.win_count > 0 ? p : null))
      .finally(() => setLoading(false))
  }, [selectedFt])

  const rebuild = async () => {
    if (!selectedFt) return
    setRebuilding(true)
    setRebuildMsg('')
    try {
      const res = await rebuildPattern(selectedFt)
      const p = res?.pattern
      setPattern(p?.win_count > 0 ? p : null)
      setRebuildMsg(`✓ 재구축 완료 (당선 ${p?.win_count || 0}개 / 낙선 ${p?.loser_stats?.lose_count || 0}개)`)
    } catch (e) {
      setRebuildMsg('✗ 재구축 실패: ' + (e.message || ''))
    } finally {
      setRebuilding(false)
      setTimeout(() => setRebuildMsg(''), 4000)
    }
  }

  if (!ready) return null

  const loseDist = pattern?.loser_stats?.page_distribution || {}
  const loseQuant = pattern?.loser_stats?.quantitative || {}
  const loseKeywords = pattern?.loser_stats?.concept_keywords || {}
  const loseCount = pattern?.loser_stats?.lose_count || 0

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: '#1f2937', marginBottom: 16, borderBottom: '1px solid #e5e7eb', paddingBottom: 10 }}>
        패턴 뷰어
      </div>

      {/* 시설유형 탭 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {facilityTypes.map(ft => (
          <button
            key={ft.key}
            onClick={() => setSelectedFt(ft.key)}
            style={{
              padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
              cursor: 'pointer',
              border: selectedFt === ft.key ? '2px solid #1e3a8a' : '2px solid #e5e7eb',
              background: selectedFt === ft.key ? '#f9fafb' : '#ffffff',
              color: selectedFt === ft.key ? '#1e3a8a' : '#6b7280',
            }}
          >
            {ft.label_ko}
          </button>
        ))}
      </div>

      {/* 상단 바 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          {pattern ? (
            <>
              <span style={{ background: '#dcfce7', color: '#15803d', fontSize: 12, padding: '3px 10px', borderRadius: 20 }}>
                당선 {pattern.win_count}개
              </span>
              {loseCount > 0 && (
                <span style={{ background: '#fee2e2', color: '#dc2626', fontSize: 12, padding: '3px 10px', borderRadius: 20 }}>
                  낙선 {loseCount}개
                </span>
              )}
            </>
          ) : loading ? (
            <span style={{ fontSize: 12, color: '#6b7280' }}>로딩 중...</span>
          ) : (
            <span style={{ fontSize: 12, color: '#92400e' }}>⚠ 패턴 없음 (당선 데이터 축적 필요)</span>
          )}
        </div>
        <button
          onClick={rebuild}
          disabled={rebuilding}
          style={{
            background: '#1e3a8a', color: '#fff', border: 'none', borderRadius: 6,
            padding: '5px 14px', fontSize: 12, cursor: rebuilding ? 'not-allowed' : 'pointer',
            opacity: rebuilding ? 0.6 : 1,
          }}
        >
          {rebuilding ? '재구축 중...' : '패턴 재구축'}
        </button>
      </div>
      {rebuildMsg && <div style={{ fontSize: 12, color: '#16a34a', marginBottom: 10 }}>{rebuildMsg}</div>}

      {pattern && (
        <>
          {/* 페이지 구성 비교 */}
          <div style={s.sec}>
            <div style={s.secTitle}>페이지 구성 통계 (평균 페이지 수)</div>
            <PageDistBars
              winDist={pattern.page_distribution || {}}
              loseDist={loseDist}
              pageTypeLabel={pageTypeLabel}
            />
          </div>

          {/* 정량 지표 비교 */}
          {(Object.keys(pattern.quantitative || {}).length > 0 || Object.keys(loseQuant).length > 0) && (
            <div style={s.sec}>
              <div style={s.secTitle}>정량 지표 평균</div>
              <QuantTable winQuant={pattern.quantitative || {}} loseQuant={loseQuant} />
            </div>
          )}

          {/* 컨셉 키워드 */}
          {Object.keys(pattern.concept_keywords || {}).length > 0 && (
            <div style={s.sec}>
              <div style={s.secTitle}>
                컨셉 키워드 빈도
                {loseCount > 0 && (
                  <span style={{ fontSize: 11, color: '#6b7280', fontWeight: 400, marginLeft: 8 }}>
                    (녹색 = 당선 우세, 적색 = 낙선 우세)
                  </span>
                )}
              </div>
              <KeywordCloud keywords={pattern.concept_keywords || {}} loseKeywords={loseKeywords} />
            </div>
          )}

          {/* 질적 인사이트 */}
          {pattern.qualitative_insights && (
            <div style={s.sec}>
              <div style={s.secTitle}>과거 공모 정성 인사이트</div>
              <QualitativeInsights insights={pattern.qualitative_insights} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
