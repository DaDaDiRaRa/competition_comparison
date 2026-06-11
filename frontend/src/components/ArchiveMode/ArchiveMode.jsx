import { useState, useEffect } from 'react'
import { listArchive, searchArchive, getArchiveDetail } from '../../api/client'
import { useMeta } from '../../hooks/useMeta'
import ArchiveCard from './ArchiveCard'
import ArchiveDetail from './ArchiveDetail'

const RESULT_FILTERS = [
  { value: 'all',  label: '전체' },
  { value: 'win',  label: '당선있음' },
  { value: 'lose', label: '당선없음' },
]

const s = {
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24, marginBottom: 16 },
  title: {
    fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)',
    color: 'var(--color-text-body)', marginBottom: 16,
  },
  searchRow: { display: 'flex', gap: 8, marginBottom: 12 },
  input: {
    flex: 1, background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '10px 14px', color: 'var(--color-text-body)',
    fontSize: 'var(--font-size-base)',
  },
  searchBtn: {
    background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: 'none',
    borderRadius: 6, padding: '0 22px', cursor: 'pointer',
    fontSize: 'var(--font-size-base)', fontWeight: 'var(--font-weight-semibold)',
    flexShrink: 0,
  },
  filters: { display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
  select: {
    background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)',
    fontSize: 'var(--font-size-sm)', cursor: 'pointer',
  },
  toggleGroup: {
    display: 'inline-flex', gap: 0, border: '1px solid var(--color-border)',
    borderRadius: 6, overflow: 'hidden',
  },
  toggleBtn: (active) => ({
    background: active ? 'var(--color-accent)' : 'var(--color-bg-surface)',
    color: active ? 'var(--color-text-on-accent)' : 'var(--color-text-muted)',
    border: 'none', padding: '8px 14px', cursor: 'pointer',
    fontSize: 'var(--font-size-sm)',
    fontWeight: active ? 'var(--font-weight-semibold)' : 'var(--font-weight-regular)',
  }),
  interpreted: {
    fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)',
    marginTop: 10, fontStyle: 'italic',
  },
  resultsHeader: {
    fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)',
    marginBottom: 10,
  },
  grid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: 12,
  },
  centerBox: {
    padding: '40px 0', textAlign: 'center',
    color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)',
  },
  spinner: {
    display: 'inline-block', width: 28, height: 28,
    border: '3px solid var(--color-border)',
    borderTopColor: 'var(--color-accent)',
    borderRadius: '50%',
    animation: 'archive-spin 0.8s linear infinite',
  },
}

export default function ArchiveMode() {
  const { facilityTypes } = useMeta()
  const [query, setQuery] = useState('')
  const [facilityFilter, setFacilityFilter] = useState('')
  const [resultFilter, setResultFilter] = useState('all')
  const [items, setItems] = useState([])
  const [queryInterpreted, setQueryInterpreted] = useState('')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [detail, setDetail] = useState(null)

  // 초기 로드: 전체 목록 (필터 없음)
  useEffect(() => {
    let cancel = false
    setLoading(true)
    listArchive()
      .then(res => { if (!cancel) setItems(res.items || []) })
      .catch(() => { if (!cancel) setItems([]) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [])

  // 필터(시설유형/결과)가 바뀌면 검색을 재실행 (query 없이 → 전체 + 필터)
  useEffect(() => {
    let cancel = false
    setLoading(true)
    searchArchive(query, facilityFilter, resultFilter)
      .then(res => {
        if (cancel) return
        setItems(res.items || [])
        setQueryInterpreted(res.query_interpreted || '')
      })
      .catch(() => { if (!cancel) setItems([]) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilityFilter, resultFilter])

  const runSearch = async () => {
    setLoading(true)
    setSearched(true)
    try {
      const res = await searchArchive(query, facilityFilter, resultFilter)
      setItems(res.items || [])
      setQueryInterpreted(res.query_interpreted || '')
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') runSearch()
  }

  const openDetail = async (competition_id, facility_type) => {
    try {
      const data = await getArchiveDetail(facility_type, competition_id)
      // _comparison.json엔 facility_type 필드 없음 → 헤더 뱃지/축 라벨용으로 머지
      setDetail({ ...data, facility_type, competition_id })
    } catch {
      // 상세 조회 실패 시 무시 (사용자가 다시 클릭 가능)
    }
  }

  return (
    <div>
      {/* CSS keyframes for spinner — 컴포넌트 내부에 한 번만 정의 */}
      <style>{`@keyframes archive-spin { to { transform: rotate(360deg); } }`}</style>

      <div style={s.panel}>
        <div style={s.title}>아카이브 검색</div>

        <div style={s.searchRow}>
          <input
            style={s.input}
            placeholder="예: 판교 공동주택 배치 전략 참고할 거 있어?"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button style={s.searchBtn} onClick={runSearch}>검색</button>
        </div>

        <div style={s.filters}>
          <select
            style={s.select}
            value={facilityFilter}
            onChange={e => setFacilityFilter(e.target.value)}
          >
            <option value="">전체 시설유형</option>
            {(facilityTypes || []).map(ft => (
              <option key={ft.key} value={ft.key}>{ft.label_ko}</option>
            ))}
          </select>

          <div style={s.toggleGroup}>
            {RESULT_FILTERS.map(f => (
              <button
                key={f.value}
                style={s.toggleBtn(resultFilter === f.value)}
                onClick={() => setResultFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {searched && queryInterpreted && (
          <div style={s.interpreted}>해석된 검색어: {queryInterpreted}</div>
        )}
      </div>

      <div style={s.resultsHeader}>
        {!loading && `총 ${items.length}건`}
      </div>

      {loading && (
        <div style={s.centerBox}>
          <div style={s.spinner} />
        </div>
      )}

      {!loading && items.length === 0 && (
        <div style={s.centerBox}>관련 공모를 찾지 못했어요</div>
      )}

      {!loading && items.length > 0 && (
        <div style={s.grid}>
          {items.map(card => (
            <ArchiveCard
              key={`${card.facility_type}__${card.competition_id}`}
              card={card}
              onSelect={openDetail}
            />
          ))}
        </div>
      )}

      <ArchiveDetail data={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
