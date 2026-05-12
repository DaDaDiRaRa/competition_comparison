import { useState, useMemo } from 'react'
import { GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'

/**
 * Dynamic version of competition_analysis.jsx
 * Accepts API comparison result and renders the same dark dashboard UI.
 *
 * comparison: {
 *   submissions: { company: { concept:{score,strengths,weaknesses,notes}, ... } },
 *   ranking: [company, ...],
 *   key_differentiators: [...]
 * }
 * submissionMeta: [{ company, result, total_pages, page_distribution }]
 */

const AXIS_LABEL = {
  concept: { label: '설계 컨셉', icon: '◈' },
  mass:    { label: '매스 전략', icon: '◼' },
  landscape: { label: '공원·조경 연계', icon: '◉' },
  program: { label: '프로그램 구성', icon: '▲' },
  facade:  { label: '파사드·외관', icon: '◧' },
  technical: { label: '구조·기술', icon: '⚙' },
  quantitative: { label: '정량 데이터', icon: '≡' },
}

const WIN_COLOR = '#dc2626'
const PALETTE = [
  '#dc2626', '#475569', '#0891b2', '#ca8a04', '#334155',
  '#7c3aed', '#db2777', '#0284c7',
]

function useCompanyColors(companies) {
  const map = {}
  companies.forEach((c, i) => { map[c] = PALETTE[i % PALETTE.length] })
  return map
}

function CompanyFilterBar({ companies, colors, selected, onToggle, onExpandAll, allExpanded }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: '#666', marginRight: 4 }}>FILTER</span>
      {companies.map(c => {
        const active = selected.length === 0 || selected.includes(c)
        const color = colors[c]
        return (
          <button key={c} onClick={() => onToggle(c)} style={{
            background: active ? `${color}20` : 'transparent',
            border: `1px solid ${active ? color : 'rgba(255,255,255,0.1)'}`,
            color: active ? color : '#555',
            padding: '4px 14px', borderRadius: 2, fontSize: 12,
            fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
            fontFamily: 'inherit',
          }}>
            {c}
          </button>
        )
      })}
      <button onClick={onExpandAll} style={{
        background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
        color: '#666', padding: '4px 14px', borderRadius: 2,
        fontSize: 12, cursor: 'pointer', marginLeft: 'auto', fontFamily: 'inherit',
      }}>
        {allExpanded ? '모두 접기' : '모두 펼치기'}
      </button>
    </div>
  )
}

function AxisCard({ axisId, axisData, companies, colors, selected }) {
  const { label, icon } = AXIS_LABEL[axisId] || { label: axisId, icon: '•' }
  const visible = selected.length === 0 ? companies : companies.filter(c => selected.includes(c))

  return (
    <div style={{ padding: '0 20px 20px' }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${visible.length}, 1fr)`,
        gap: 10,
      }}>
        {visible.map(company => {
          const d = axisData[company]
          if (!d) return null
          const color = colors[company]
          const keywords = [
            ...(d.strengths || []).map(s => `▲ ${s}`),
            ...(d.weaknesses || []).map(w => `▼ ${w}`),
          ]
          return (
            <div key={company} style={{
              background: 'rgba(0,0,0,0.3)', borderRadius: 2, padding: 16,
              borderTop: `3px solid ${color}`, minWidth: 0,
            }}>
              <div style={{ fontSize: 11, color, fontWeight: 700, marginBottom: 6, letterSpacing: '0.05em' }}>
                {company}
              </div>
              {toGrade(d) && (
                <div style={{ marginBottom: 6 }}>
                  <span style={{
                    display: 'inline-block', padding: '3px 12px', borderRadius: 14,
                    background: GRADE_BG[toGrade(d)], color: GRADE_COLOR[toGrade(d)],
                    fontWeight: 700, fontSize: 14, letterSpacing: 1,
                  }}>
                    {toGrade(d)}
                  </span>
                </div>
              )}
              {d.notes && (
                <div style={{ fontSize: 12, color: '#aaa', lineHeight: 1.7, marginBottom: 10 }}>
                  {d.notes}
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
                {keywords.slice(0, 6).map((kw, i) => (
                  <span key={i} style={{
                    fontSize: 10, padding: '2px 8px',
                    background: `${color}20`, color,
                    borderRadius: 2, fontWeight: 500,
                  }}>{kw}</span>
                ))}
              </div>
              {d.strengths?.length > 0 && (
                <div style={{ fontSize: 11, marginBottom: 4 }}>
                  <span style={{ color: '#16a34a', fontWeight: 600 }}>▲ 강점 </span>
                  <span style={{ color: '#999' }}>{d.strengths.join(' · ')}</span>
                </div>
              )}
              {d.weaknesses?.length > 0 && (
                <div style={{ fontSize: 11 }}>
                  <span style={{ color: '#ea580c', fontWeight: 600 }}>▼ 약점 </span>
                  <span style={{ color: '#999' }}>{d.weaknesses.join(' · ')}</span>
                </div>
              )}
              {d.brief_compliance && (
                <div style={{ marginTop: 8 }}>
                  <span style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 2,
                    background: d.brief_compliance === 'yes' ? '#15803d'
                      : d.brief_compliance === 'partial' ? '#92400e'
                      : d.brief_compliance === 'no' ? '#b91c1c' : '#e5e7eb',
                    color: '#fff', fontWeight: 600,
                  }}>지침 {d.brief_compliance}</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CategoryRow({ axisId, axisData, companies, colors, selected, expanded, onToggle }) {
  const { label, icon } = AXIS_LABEL[axisId] || { label: axisId, icon: '•' }
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      border: `1px solid ${expanded ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.08)'}`,
      borderRadius: 2, marginBottom: 12, overflow: 'hidden', transition: 'border-color 0.2s',
    }}>
      <button onClick={() => onToggle(axisId)} style={{
        width: '100%', background: 'none', border: 'none', color: '#e5e7eb',
        padding: '16px 20px', display: 'flex', alignItems: 'center',
        gap: 12, cursor: 'pointer', fontSize: 15, fontFamily: 'inherit', textAlign: 'left',
      }}>
        <span style={{ fontSize: 18, opacity: 0.6 }}>{icon}</span>
        <span style={{ fontWeight: 600, letterSpacing: '0.02em' }}>{label}</span>
        <span style={{
          marginLeft: 'auto', opacity: 0.4, fontSize: 12,
          transform: expanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s',
        }}>▼</span>
      </button>
      {expanded && (
        <AxisCard axisId={axisId} axisData={axisData}
          companies={companies} colors={colors} selected={selected} />
      )}
    </div>
  )
}

function RankingBlock({ ranking, companies, colors, submissionMeta }) {
  const metaMap = {}
  submissionMeta?.forEach(s => { metaMap[s.company] = s })
  const medals = ['🥇', '🥈', '🥉']

  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 2, padding: 20, marginBottom: 20,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#aaa', letterSpacing: '0.1em', marginBottom: 12 }}>
        종합 순위
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {ranking.map((company, i) => {
          const color = colors[company]
          const meta = metaMap[company]
          return (
            <div key={company} style={{
              background: `${color}15`, border: `1px solid ${color}`,
              borderRadius: 4, padding: '10px 16px', minWidth: 140,
            }}>
              <div style={{ fontSize: 20, marginBottom: 4 }}>{medals[i] || `${i + 1}.`}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color }}>{company}</div>
              {meta && (
                <div style={{ fontSize: 11, color: '#666', marginTop: 2 }}>
                  {meta.result === 'win' ? '✓ 당선' : '낙선'} · {meta.total_pages}p
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ComparisonDashboard({ comparison, submissionMeta = [] }) {
  const [selected, setSelected] = useState([])
  const [expandedAxes, setExpandedAxes] = useState(new Set(['concept']))

  const companies = useMemo(
    () => comparison?.submissions ? Object.keys(comparison.submissions) : [],
    [comparison?.submissions]
  )
  const colors = useMemo(() => useCompanyColors(companies), [companies])
  const axes = useMemo(
    () => Object.keys(AXIS_LABEL).filter(ax => companies.some(c => comparison.submissions[c]?.[ax])),
    [companies, comparison?.submissions]
  )
  const allExpanded = expandedAxes.size === axes.length && axes.length > 0

  if (!comparison?.submissions) return null

  const toggleCompany = (c) =>
    setSelected(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])

  const toggleAxis = (id) =>
    setExpandedAxes(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })

  const handleExpandAll = () =>
    setExpandedAxes(allExpanded ? new Set() : new Set(axes))

  return (
    <div style={{
      fontFamily: "'Pretendard', 'Noto Sans KR', -apple-system, sans-serif",
      background: '#e5e7eb', color: '#e5e7eb',
      borderRadius: 12, padding: '28px 24px', marginTop: 24,
    }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.15em', marginBottom: 4 }}>
          COMPETITION ANALYSIS · 비교 분석 대시보드
        </div>
        <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
          경쟁사 제안서 비교 분석
        </div>
        <div style={{ fontSize: 13, color: '#666', marginTop: 6 }}>
          {companies.length}개 출품사 · {axes.length}개 분석 카테고리
        </div>
      </div>

      {comparison.ranking?.length > 0 && (
        <RankingBlock ranking={comparison.ranking} companies={companies}
          colors={colors} submissionMeta={submissionMeta} />
      )}

      {comparison.key_differentiators?.length > 0 && (
        <div style={{
          background: 'rgba(230,57,70,0.08)', border: '1px solid rgba(230,57,70,0.2)',
          borderRadius: 2, padding: '12px 16px', marginBottom: 20,
          fontSize: 13, color: '#ca8a04',
        }}>
          <strong style={{ color: '#dc2626' }}>핵심 차별화 요소: </strong>
          {comparison.key_differentiators.join(' · ')}
        </div>
      )}

      <CompanyFilterBar
        companies={companies} colors={colors} selected={selected}
        onToggle={toggleCompany} onExpandAll={handleExpandAll} allExpanded={allExpanded}
      />

      {axes.map(axisId => (
        <CategoryRow
          key={axisId}
          axisId={axisId}
          axisData={
            Object.fromEntries(
              companies.map(c => [c, comparison.submissions[c]?.[axisId]])
            )
          }
          companies={companies}
          colors={colors}
          selected={selected}
          expanded={allExpanded || expandedAxes.has(axisId)}
          onToggle={toggleAxis}
        />
      ))}

      <div style={{
        marginTop: 24, paddingTop: 12,
        borderTop: '1px solid rgba(255,255,255,0.06)',
        fontSize: 11, color: '#444',
      }}>
        Claude Vision AI 분석 · 파이프라인 자동 생성
      </div>
    </div>
  )
}
