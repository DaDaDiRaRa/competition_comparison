import { useState, useMemo } from 'react'
import { GRADE_COLOR, GRADE_BG, toGrade } from '../../constants'
import { useMeta } from '../../hooks/useMeta'

/**
 * Dynamic comparison dashboard — light theme
 *
 * comparison: {
 *   submissions: { company: { concept:{grade,strengths,weaknesses,notes}, ... } },
 *   concept_comparison: { axisId: "<Korean paragraph comparing every company's approach>" }
 * }
 * facilityType: facility_type key — axis labels/icons come from useMeta().axesFor(facilityType),
 * the single source of truth (per-facility-type axis keys differ, e.g. general vs redev groups).
 *
 * 종합 순위(ranking/blind_ranking)는 의도적으로 노출하지 않는다 — "누가 1등이냐"보다
 * 각 회사가 무엇을 어떻게 풀었는지 비교하는 쪽이 더 유용하다는 결정(2026-07-01).
 * ranking은 백엔드 comparison.json에는 gap_analysis 계산용으로 계속 보존된다.
 */

const PALETTE = [
  'var(--color-danger)', 'var(--color-accent-hover)', 'var(--color-info)', 'var(--color-warning)', 'var(--color-accent)',
  'var(--color-purple)', '#db2777', '#0284c7',
]

function buildCompanyColors(companies) {
  const map = {}
  companies.forEach((c, i) => { map[c] = PALETTE[i % PALETTE.length] })
  return map
}

function CompanyFilterBar({ companies, colors, selected, onToggle, onExpandAll, allExpanded }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--gap-sm)', marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
      <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)', marginRight: 4 }}>FILTER</span>
      {companies.map(c => {
        const active = selected.length === 0 || selected.includes(c)
        const color = colors[c]
        return (
          <button key={c} onClick={() => onToggle(c)} style={{
            background: active ? `${color}20` : 'transparent',
            border: `1px solid ${active ? color : 'var(--color-border)'}`,
            color: active ? color : 'var(--color-text-muted)',
            padding: '4px 14px', borderRadius: 2, fontSize: 'var(--font-size-sm)',
            fontWeight: 'var(--font-weight-semibold)', cursor: 'pointer', transition: 'all 0.15s',
            fontFamily: 'inherit',
          }}>
            {c}
          </button>
        )
      })}
      <button onClick={onExpandAll} style={{
        background: 'transparent', border: '1px solid var(--color-border)',
        color: 'var(--color-text-faint)', padding: '4px 14px', borderRadius: 2,
        fontSize: 'var(--font-size-sm)', cursor: 'pointer', marginLeft: 'auto', fontFamily: 'inherit',
      }}>
        {allExpanded ? '모두 접기' : '모두 펼치기'}
      </button>
    </div>
  )
}

function AxisCard({ axisId, axisData, companies, colors, selected }) {
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
              background: 'var(--color-bg-surface-alt)',
              border: '1px solid var(--color-border)',
              borderTop: `3px solid ${color}`,
              borderRadius: 2, padding: 16, minWidth: 0,
            }}>
              <div style={{ fontSize: 'var(--font-size-xs)', color, fontWeight: 'var(--font-weight-bold)', marginBottom: 6, letterSpacing: '0.05em' }}>
                {company}
              </div>
              {toGrade(d) && (
                <div style={{ marginBottom: 6 }}>
                  <span style={{
                    display: 'inline-block', padding: '3px 12px', borderRadius: 14,
                    background: GRADE_BG[toGrade(d)], color: GRADE_COLOR[toGrade(d)],
                    fontWeight: 'var(--font-weight-bold)', fontSize: 'var(--font-size-base)', letterSpacing: 1,
                  }}>
                    {toGrade(d)}
                  </span>
                </div>
              )}
              {d.notes && (
                <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', lineHeight: 1.7, marginBottom: 10 }}>
                  {d.notes}
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-xs)', marginBottom: 10 }}>
                {keywords.slice(0, 6).map((kw, i) => (
                  <span key={i} style={{
                    fontSize: 'var(--font-size-xs)', padding: '2px 8px',
                    background: `${color}20`, color,
                    borderRadius: 2, fontWeight: 'var(--font-weight-medium)',
                  }}>{kw}</span>
                ))}
              </div>
              {d.strengths?.length > 0 && (
                <div style={{ fontSize: 'var(--font-size-xs)', marginBottom: 4 }}>
                  <span style={{ color: 'var(--color-success)', fontWeight: 'var(--font-weight-semibold)' }}>▲ 강점 </span>
                  <span style={{ color: 'var(--color-text-faint)' }}>{d.strengths.join(' · ')}</span>
                </div>
              )}
              {d.weaknesses?.length > 0 && (
                <div style={{ fontSize: 'var(--font-size-xs)' }}>
                  <span style={{ color: 'var(--color-grade-d)', fontWeight: 'var(--font-weight-semibold)' }}>▼ 약점 </span>
                  <span style={{ color: 'var(--color-text-faint)' }}>{d.weaknesses.join(' · ')}</span>
                </div>
              )}
              {d.brief_compliance && (
                <div style={{ marginTop: 8 }}>
                  <span style={{
                    fontSize: 'var(--font-size-xs)', padding: '2px 8px', borderRadius: 2,
                    background: d.brief_compliance === 'yes' ? 'var(--color-success)'
                      : d.brief_compliance === 'partial' ? 'var(--color-amber-dark)'
                      : d.brief_compliance === 'no' ? 'var(--color-danger)' : 'var(--color-border)',
                    color: 'var(--color-text-on-accent)', fontWeight: 'var(--font-weight-semibold)',
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

function CategoryRow({ axisId, axisMeta, axisData, companies, colors, selected, expanded, onToggle }) {
  const meta = axisMeta[axisId] || {}
  const label = meta.label_ko || axisId
  const icon = meta.icon || '•'
  return (
    <div style={{
      background: 'var(--color-bg-surface)',
      border: `1px solid ${expanded ? 'var(--color-border-strong)' : 'var(--color-border)'}`,
      borderRadius: 2, marginBottom: 12, overflow: 'hidden', transition: 'border-color 0.2s',
    }}>
      <button onClick={() => onToggle(axisId)} style={{
        width: '100%', background: 'none', border: 'none', color: 'var(--color-text-body)',
        padding: '16px 20px', display: 'flex', alignItems: 'center',
        gap: 'var(--gap-md)', cursor: 'pointer', fontSize: 'var(--font-size-md)', fontFamily: 'inherit', textAlign: 'left',
      }}>
        <span style={{ fontSize: 'var(--font-size-lg)', opacity: 0.6 }}>{icon}</span>
        <span style={{ fontWeight: 'var(--font-weight-semibold)', letterSpacing: '0.02em' }}>{label}</span>
        <span style={{
          marginLeft: 'auto', opacity: 0.4, fontSize: 'var(--font-size-sm)',
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

function ConceptComparisonBlock({ conceptComparison, axisMeta }) {
  const axisIds = Object.keys(conceptComparison || {})
    .filter(id => (conceptComparison[id] || '').trim())
  if (axisIds.length === 0) return null

  return (
    <div style={{
      background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
      borderRadius: 2, padding: 20, marginBottom: 20,
    }}>
      <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-bold)', color: 'var(--color-text-muted)', letterSpacing: '0.1em', marginBottom: 12 }}>
        축별 컨셉·설계 방향 비교
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {axisIds.map(axisId => {
          const meta = axisMeta[axisId] || {}
          const label = meta.label_ko || axisId
          const icon = meta.icon || '•'
          return (
            <div key={axisId} style={{ borderLeft: '3px solid var(--color-accent)', paddingLeft: 14 }}>
              <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-text-body)', marginBottom: 4 }}>
                {icon} {label}
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)', lineHeight: 1.7 }}>
                {conceptComparison[axisId]}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ComparisonDashboard({ comparison, facilityType }) {
  const { axesFor } = useMeta()
  const [selected, setSelected] = useState([])
  const [expandedAxes, setExpandedAxes] = useState(new Set())

  const axisMeta = axesFor(facilityType)

  const companies = useMemo(
    () => comparison?.submissions ? Object.keys(comparison.submissions) : [],
    [comparison?.submissions]
  )
  const colors = useMemo(() => buildCompanyColors(companies), [companies])
  const axes = Object.keys(axisMeta).filter(ax => companies.some(c => comparison.submissions[c]?.[ax]))
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
      background: 'var(--color-bg-page)', color: 'var(--color-text-body)',
      borderRadius: 12, padding: '28px 24px', marginTop: 24,
    }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)', letterSpacing: '0.15em', marginBottom: 4 }}>
          COMPETITION ANALYSIS · 비교 분석 대시보드
        </div>
        <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 'var(--font-weight-bold)', letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}>
          경쟁사 제안서 비교 분석
        </div>
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)', marginTop: 6 }}>
          {companies.length}개 출품사 · {axes.length}개 분석 카테고리
        </div>
      </div>

      <ConceptComparisonBlock conceptComparison={comparison.concept_comparison} axisMeta={axisMeta} />

      <CompanyFilterBar
        companies={companies} colors={colors} selected={selected}
        onToggle={toggleCompany} onExpandAll={handleExpandAll} allExpanded={allExpanded}
      />

      {axes.map(axisId => (
        <CategoryRow
          key={axisId}
          axisId={axisId}
          axisMeta={axisMeta}
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
        borderTop: '1px solid var(--color-border)',
        fontSize: 'var(--font-size-xs)', color: 'var(--color-text-faint)',
      }}>
        Claude Vision AI 분석 · 파이프라인 자동 생성
      </div>
    </div>
  )
}
