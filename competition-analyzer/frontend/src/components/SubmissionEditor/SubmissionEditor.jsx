import { useState, useEffect, useCallback } from 'react'
import { getSubmission, updateSubmission } from '../../api/client'

// ── 정량 필드 정의 ────────────────────────────────────────────────────────────
const QUANT_FIELDS = [
  { key: 'site_area_sqm',               label: '대지면적',   unit: '㎡' },
  { key: 'building_area_sqm',           label: '건축면적',   unit: '㎡' },
  { key: 'total_floor_area_sqm',        label: '연면적',     unit: '㎡' },
  { key: 'area_above_ground_sqm',       label: '지상 연면적', unit: '㎡' },
  { key: 'area_below_ground_sqm',       label: '지하 연면적', unit: '㎡' },
  { key: 'building_coverage_ratio_pct', label: '건폐율',     unit: '%' },
  { key: 'floor_area_ratio_pct',        label: '용적률',     unit: '%' },
  { key: 'floors_above',               label: '지상층수',   unit: '층' },
  { key: 'floors_below',               label: '지하층수',   unit: '층' },
  { key: 'parking_count',              label: '주차대수',   unit: '대' },
]

const MASS_TYPE_OPTIONS = [
  '', 'LINEAR', 'TOWER', 'ATRIUM', 'COURTYARD', 'MIXED', 'SLAB', 'PODIUM', 'OTHER',
]

const RESULT_OPTIONS = [
  { value: 'win',        label: '★ 당선',    color: '#0d9488', bg: '#fef3c7' },
  { value: 'contracted', label: '◆ 수의계약', color: '#16a34a', bg: '#dcfce7' },
  { value: 'lose',       label: '낙선',       color: '#6b7280', bg: '#ffffff' },
]

const SECTIONS = [
  { id: 'quant',    label: '📊 정량 데이터' },
  { id: 'meta',     label: '🏷 메타 정보' },
  { id: 'concept',  label: '💡 컨셉' },
  { id: 'floor',    label: '📐 평면' },
  { id: 'area',     label: '📋 면적표' },
  { id: 'cover',    label: '🗂 표지' },
  { id: 'advanced', label: '⚙ 고급 편집' },
]

// ── 스타일 ─────────────────────────────────────────────────────────────────────
const s = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000, padding: 20,
  },
  modal: {
    background: '#ffffff', borderRadius: 14, width: '90%', maxWidth: 920,
    maxHeight: '90vh', display: 'flex', flexDirection: 'column',
    border: '1px solid #e5e7eb', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
  },
  header: {
    padding: '18px 24px', borderBottom: '1px solid #e5e7eb',
    display: 'flex', alignItems: 'center', gap: 12,
  },
  title: { fontSize: 16, fontWeight: 700, color: '#1f2937', flex: 1 },
  closeBtn: {
    background: 'none', border: 'none', color: '#6b7280',
    fontSize: 20, cursor: 'pointer', lineHeight: 1,
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  sidebar: {
    width: 160, borderRight: '1px solid #e5e7eb',
    padding: '12px 8px', overflowY: 'auto', flexShrink: 0,
  },
  sideBtn: (active) => ({
    display: 'block', width: '100%', textAlign: 'left',
    padding: '9px 12px', borderRadius: 8, border: 'none', cursor: 'pointer',
    fontSize: 12, fontWeight: active ? 700 : 400,
    background: active ? '#475569' : 'transparent',
    color: active ? '#ffffff' : '#6b7280',
    marginBottom: 2,
  }),
  content: { flex: 1, overflowY: 'auto', padding: 24 },
  footer: {
    padding: '14px 24px', borderTop: '1px solid #e5e7eb',
    display: 'flex', gap: 10, justifyContent: 'flex-end', alignItems: 'center',
  },
  cancelBtn: {
    background: 'transparent', border: '1px solid #4a5568', borderRadius: 8,
    color: '#4b5563', padding: '9px 20px', cursor: 'pointer', fontSize: 14,
  },
  saveBtn: (dirty) => ({
    background: dirty ? '#15803d' : '#dcfce7',
    border: 'none', borderRadius: 8, color: dirty ? '#fff' : '#4a5568',
    padding: '9px 24px', cursor: dirty ? 'pointer' : 'not-allowed',
    fontSize: 14, fontWeight: 700, transition: 'all 0.15s',
  }),
  label: { fontSize: 12, color: '#4b5563', marginBottom: 5, display: 'block' },
  input: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 6,
    padding: '8px 10px', color: '#1f2937', fontSize: 13, width: '100%',
    boxSizing: 'border-box',
  },
  select: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 6,
    padding: '8px 10px', color: '#1f2937', fontSize: 13, width: '100%',
  },
  textarea: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 6,
    padding: '8px 10px', color: '#1f2937', fontSize: 12, width: '100%',
    minHeight: 120, resize: 'vertical', boxSizing: 'border-box', fontFamily: 'monospace',
  },
  group: { marginBottom: 16 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 },
  sectionTitle: { fontSize: 14, fontWeight: 700, color: '#334155', marginBottom: 16 },
  original: { fontSize: 11, color: '#4a5568', marginTop: 3 },
  tag: {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 20,
    padding: '3px 10px', fontSize: 12, color: '#1f2937', margin: '3px 3px 3px 0',
  },
  tagRemove: {
    background: 'none', border: 'none', color: '#6b7280',
    cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0,
  },
  rowCard: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 8,
    padding: '12px 14px', marginBottom: 8,
  },
  addBtn: {
    background: '#334155', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 12, marginTop: 8,
  },
  removeBtn: {
    background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer',
    fontSize: 12, marginLeft: 'auto',
  },
  toast: (type) => ({
    fontSize: 13, color: type === 'ok' ? '#16a34a' : '#dc2626',
    flex: 1,
  }),
}

// ── 유틸 ──────────────────────────────────────────────────────────────────────
function safeList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  return [val]
}

function safeObj(val) {
  if (!val || typeof val !== 'object' || Array.isArray(val)) return {}
  return val
}

// ── 섹션 컴포넌트들 ───────────────────────────────────────────────────────────

function QuantSection({ quant, originalQuant, onChange }) {
  return (
    <div>
      <div style={s.sectionTitle}>정량 데이터</div>
      <div style={s.grid2}>
        {QUANT_FIELDS.map(({ key, label, unit }) => (
          <div key={key}>
            <label style={s.label}>{label} ({unit})</label>
            <input
              style={s.input}
              type="number"
              step="any"
              value={quant[key] ?? ''}
              onChange={e => {
                const v = e.target.value === '' ? null : parseFloat(e.target.value)
                onChange({ ...quant, [key]: isNaN(v) ? null : v })
              }}
            />
            {originalQuant[key] != null && originalQuant[key] !== quant[key] && (
              <div style={s.original}>AI 추출값: {originalQuant[key]}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function MetaSection({ result, meta, onChange }) {
  return (
    <div>
      <div style={s.sectionTitle}>메타 정보</div>
      <div style={s.group}>
        <label style={s.label}>결과</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {RESULT_OPTIONS.map(opt => (
            <div
              key={opt.value}
              onClick={() => onChange('result', opt.value)}
              style={{
                flex: 1, padding: '9px 0', textAlign: 'center', borderRadius: 8,
                cursor: 'pointer', fontSize: 13, fontWeight: 600,
                border: result === opt.value ? `2px solid ${opt.color}` : '2px solid #e5e7eb',
                background: result === opt.value ? opt.bg : '#ffffff',
                color: result === opt.value ? opt.color : '#4a5568',
              }}
            >
              {opt.label}
            </div>
          ))}
        </div>
      </div>
      <div style={s.grid2}>
        <div>
          <label style={s.label}>회사명 (변경 불가)</label>
          <input style={{ ...s.input, opacity: 0.5 }} value={meta.company || ''} readOnly />
        </div>
        <div>
          <label style={s.label}>발주처</label>
          <input style={s.input} value={meta.client || ''}
            onChange={e => onChange('client', e.target.value)} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={s.label}>대지위치</label>
          <input style={s.input} value={meta.location || ''}
            onChange={e => onChange('location', e.target.value)} />
        </div>
      </div>
    </div>
  )
}

function TagInput({ tags, onChange }) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !tags.includes(v)) onChange([...tags, v])
    setInput('')
  }
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: 6 }}>
        {tags.map((t, i) => (
          <span key={i} style={s.tag}>
            {t}
            <button style={s.tagRemove} onClick={() => onChange(tags.filter((_, j) => j !== i))}>×</button>
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          style={{ ...s.input, flex: 1 }}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder="입력 후 Enter"
        />
        <button style={{ ...s.addBtn, marginTop: 0 }} onClick={add}>추가</button>
      </div>
    </div>
  )
}

function ConceptSection({ concept, onChange }) {
  const c = safeList(concept)[0] || {}
  const update = (key, val) => {
    const updated = { ...c, [key]: val }
    onChange(Array.isArray(concept) ? [updated, ...safeList(concept).slice(1)] : updated)
  }
  return (
    <div>
      <div style={s.sectionTitle}>컨셉</div>
      <div style={s.group}>
        <label style={s.label}>컨셉명</label>
        <input style={s.input} value={c.concept_name || ''}
          onChange={e => update('concept_name', e.target.value)} />
      </div>
      <div style={s.group}>
        <label style={s.label}>매스 타입</label>
        <select style={s.select} value={c.mass_type || ''}
          onChange={e => update('mass_type', e.target.value)}>
          {MASS_TYPE_OPTIONS.map(o => <option key={o} value={o}>{o || '(선택 안함)'}</option>)}
        </select>
      </div>
      <div style={s.group}>
        <label style={s.label}>키워드</label>
        <TagInput tags={c.keywords || []}
          onChange={tags => update('keywords', tags)} />
      </div>
      <div style={s.group}>
        <label style={s.label}>설명</label>
        <textarea style={s.textarea} value={c.description || ''}
          onChange={e => update('description', e.target.value)} />
      </div>
    </div>
  )
}

function FloorSection({ floorPlan, onChange }) {
  const rows = safeList(floorPlan)
  const updateRow = (i, key, val) => {
    const updated = rows.map((r, j) => j === i ? { ...r, [key]: val } : r)
    onChange(updated)
  }
  const removeRow = (i) => onChange(rows.filter((_, j) => j !== i))
  const addRow = () => onChange([...rows, { floor_level: '', main_programs: [] }])

  return (
    <div>
      <div style={s.sectionTitle}>평면 (층별 프로그램)</div>
      {rows.map((row, i) => (
        <div key={i} style={s.rowCard}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: '#4b5563', fontWeight: 600 }}>층 {i + 1}</span>
            <button style={s.removeBtn} onClick={() => removeRow(i)}>× 삭제</button>
          </div>
          <div style={s.grid2}>
            <div>
              <label style={s.label}>층 표기</label>
              <input style={s.input} value={row.floor_level || ''}
                onChange={e => updateRow(i, 'floor_level', e.target.value)}
                placeholder="예: 1F, B2, 옥상" />
            </div>
            <div>
              <label style={s.label}>주요 프로그램</label>
              <TagInput
                tags={Array.isArray(row.main_programs) ? row.main_programs : []}
                onChange={tags => updateRow(i, 'main_programs', tags)}
              />
            </div>
          </div>
        </div>
      ))}
      <button style={s.addBtn} onClick={addRow}>+ 층 추가</button>
    </div>
  )
}

function AreaSection({ areaTable, onChange }) {
  const rows = safeList(safeObj(areaTable).rows || areaTable)
  const updateCell = (i, key, val) => {
    const updated = rows.map((r, j) => j === i ? { ...r, [key]: val } : r)
    onChange({ ...safeObj(areaTable), rows: updated })
  }
  const removeRow = (i) => {
    const updated = rows.filter((_, j) => j !== i)
    onChange({ ...safeObj(areaTable), rows: updated })
  }
  const addRow = () => {
    onChange({ ...safeObj(areaTable), rows: [...rows, { name: '', area: '', note: '' }] })
  }

  return (
    <div>
      <div style={s.sectionTitle}>면적표</div>
      {rows.map((row, i) => (
        <div key={i} style={{ ...s.rowCard, display: 'grid', gridTemplateColumns: '2fr 1fr 2fr auto', gap: 8, alignItems: 'end' }}>
          <div>
            {i === 0 && <label style={s.label}>항목명</label>}
            <input style={s.input} value={row.name || row.area_name || ''}
              onChange={e => updateCell(i, 'name', e.target.value)} />
          </div>
          <div>
            {i === 0 && <label style={s.label}>면적 (㎡)</label>}
            <input style={s.input} type="number" step="any" value={row.area || row.area_sqm || ''}
              onChange={e => updateCell(i, 'area', e.target.value)} />
          </div>
          <div>
            {i === 0 && <label style={s.label}>비고</label>}
            <input style={s.input} value={row.note || ''}
              onChange={e => updateCell(i, 'note', e.target.value)} />
          </div>
          <button style={{ ...s.removeBtn, marginBottom: 2 }} onClick={() => removeRow(i)}>×</button>
        </div>
      ))}
      <button style={s.addBtn} onClick={addRow}>+ 행 추가</button>
    </div>
  )
}

function CoverSection({ cover, onChange }) {
  const c = safeList(cover)[0] || safeObj(cover)
  const editableKeys = Object.entries(c).filter(([k]) => k !== '_page' && typeof c[k] === 'string')
  return (
    <div>
      <div style={s.sectionTitle}>표지 정보</div>
      {editableKeys.map(([key, val]) => (
        <div key={key} style={s.group}>
          <label style={s.label}>{key}</label>
          <input style={s.input} value={val}
            onChange={e => {
              const updated = { ...c, [key]: e.target.value }
              onChange(Array.isArray(cover) ? [updated, ...safeList(cover).slice(1)] : updated)
            }} />
        </div>
      ))}
      {editableKeys.length === 0 && (
        <div style={{ color: '#4a5568', fontSize: 13 }}>표지 데이터가 추출되지 않았습니다.</div>
      )}
    </div>
  )
}

function AdvancedSection({ extracted, onChange, onErrorChange }) {
  const [text, setText] = useState(() => {
    const { _quantitative, concept, floor_plan, area_table, cover, _by_type, page_map, page_distribution, total_pages, _page, ...rest } = extracted
    return JSON.stringify(rest, null, 2)
  })
  const [error, setError] = useState('')

  const handleChange = (val) => {
    setText(val)
    try {
      const parsed = JSON.parse(val)
      setError('')
      onErrorChange?.(false)
      onChange(parsed)
    } catch {
      setError('JSON 형식이 올바르지 않습니다.')
      onErrorChange?.(true)
    }
  }

  // 컴포넌트 unmount 시 error 플래그 해제 (다른 탭으로 이동해도 저장 가능)
  useEffect(() => () => onErrorChange?.(false), [])

  return (
    <div>
      <div style={s.sectionTitle}>고급 편집</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 10, lineHeight: 1.6 }}>
        위 섹션에서 다루지 않는 추출 필드를 직접 편집합니다.<br />
        정량·컨셉·평면·면적표·표지는 상단 섹션에서 편집하세요.
      </div>
      <textarea
        style={{ ...s.textarea, minHeight: 300, borderColor: error ? '#dc2626' : '#e5e7eb' }}
        value={text}
        onChange={e => handleChange(e.target.value)}
      />
      {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>{error}</div>}
    </div>
  )
}

// ── 메인 모달 ─────────────────────────────────────────────────────────────────
export default function SubmissionEditor({ project, company, onClose, onSaved }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeSection, setActiveSection] = useState('quant')
  const [toastMsg, setToastMsg] = useState(null) // {type, text}

  // 편집 상태
  const [originalQuant, setOriginalQuant] = useState({})
  const [quant, setQuant] = useState({})
  const [result, setResult] = useState('lose')
  const [meta, setMeta] = useState({})
  const [concept, setConcept] = useState(null)
  const [floorPlan, setFloorPlan] = useState([])
  const [areaTable, setAreaTable] = useState({})
  const [cover, setCover] = useState(null)
  const [advanced, setAdvanced] = useState({})
  const [advancedError, setAdvancedError] = useState(false)
  const [dirty, setDirty] = useState(false)

  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    getSubmission(project.facility_type, project.competition_id, company)
      .then(sub => {
        const ext = sub.extracted_data || {}
        const q = ext._quantitative || {}
        setOriginalQuant(q)
        setQuant({ ...q })
        setResult(sub.result || 'lose')
        setMeta({ company: sub.company, client: sub.client || '', location: sub.location || '' })
        setConcept(ext.concept || null)
        setFloorPlan(safeList(ext.floor_plan))
        setAreaTable(ext.area_table || {})
        setCover(ext.cover || null)
        const { _quantitative, concept: _c, floor_plan: _fp, area_table: _at, cover: _cv,
                _by_type, page_map, page_distribution, total_pages, ...rest } = ext
        setAdvanced(rest)
      })
      .catch(() => {
        setLoadError(true)
        setToastMsg({ type: 'err', text: '데이터를 불러오지 못했습니다.' })
      })
      .finally(() => setLoading(false))
  }, [project.facility_type, project.competition_id, company])

  const markDirty = useCallback((fn) => (...args) => { fn(...args); setDirty(true) }, [])

  const handleClose = () => {
    if (dirty && !window.confirm('저장하지 않은 변경사항이 있습니다. 닫으시겠습니까?')) return
    onClose()
  }

  const buildExtractedData = () => ({
    ...advanced,
    _quantitative: quant,
    concept,
    floor_plan: floorPlan,
    area_table: areaTable,
    cover,
  })

  const handleSave = async () => {
    if (advancedError) {
      setToastMsg({ type: 'err', text: '고급 편집 탭에 JSON 오류가 있습니다.' })
      return
    }
    setSaving(true)
    setToastMsg(null)
    try {
      const res = await updateSubmission(
        project.facility_type, project.competition_id, company,
        {
          extracted_data: buildExtractedData(),
          result,
          meta_overrides: { client: meta.client, location: meta.location },
        }
      )
      setDirty(false)
      onSaved?.({ comparison_stale: res.comparison_stale, pattern_rebuilt: res.pattern_rebuilt })
      onClose()  // 저장 성공 시 모달 자동 닫기 (버튼 텍스트와 일치)
    } catch (e) {
      setToastMsg({ type: 'err', text: e.message })
      setSaving(false)
    }
  }

  const metaOnChange = (key, val) => { setMeta(m => ({ ...m, [key]: val })); setDirty(true) }

  if (loading) return (
    <div style={s.overlay}>
      <div style={{ ...s.modal, alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
        <div style={{ color: '#4b5563', fontSize: 14 }}>데이터 불러오는 중...</div>
      </div>
    </div>
  )

  return (
    <div style={s.overlay} onClick={e => { if (e.target === e.currentTarget) handleClose() }}>
      <div style={s.modal}>
        <div style={s.header}>
          <div style={s.title}>추출 결과 편집 — {company}</div>
          <button style={s.closeBtn} onClick={handleClose}>✕</button>
        </div>

        <div style={s.body}>
          {loadError ? (
            <div style={{ padding: 40, color: '#dc2626', fontSize: 14, lineHeight: 1.7 }}>
              ⚠ 제안서 데이터를 불러올 수 없습니다.<br />
              <span style={{ fontSize: 12, color: '#4b5563' }}>
                새로고침 후 다시 시도하거나 관리자에게 문의하세요.
              </span>
            </div>
          ) : <>
          {/* 사이드바 */}
          <div style={s.sidebar}>
            {SECTIONS.map(sec => (
              <button
                key={sec.id}
                style={s.sideBtn(activeSection === sec.id)}
                onClick={() => setActiveSection(sec.id)}
              >
                {sec.label}
              </button>
            ))}
          </div>

          {/* 컨텐츠 */}
          <div style={s.content}>
            {activeSection === 'quant' && (
              <QuantSection
                quant={quant}
                originalQuant={originalQuant}
                onChange={v => { setQuant(v); setDirty(true) }}
              />
            )}
            {activeSection === 'meta' && (
              <MetaSection result={result} meta={meta} onChange={metaOnChange} />
            )}
            {activeSection === 'concept' && (
              <ConceptSection
                concept={concept}
                onChange={markDirty(setConcept)}
              />
            )}
            {activeSection === 'floor' && (
              <FloorSection
                floorPlan={floorPlan}
                onChange={markDirty(setFloorPlan)}
              />
            )}
            {activeSection === 'area' && (
              <AreaSection
                areaTable={areaTable}
                onChange={markDirty(setAreaTable)}
              />
            )}
            {activeSection === 'cover' && (
              <CoverSection
                cover={cover}
                onChange={markDirty(setCover)}
              />
            )}
            {activeSection === 'advanced' && (
              <AdvancedSection
                extracted={buildExtractedData()}
                onChange={v => { setAdvanced(v); setDirty(true) }}
                onErrorChange={setAdvancedError}
              />
            )}
          </div>
          </>}
        </div>

        <div style={s.footer}>
          {toastMsg && (
            <div style={s.toast(toastMsg.type)}>{toastMsg.text}</div>
          )}
          <button style={s.cancelBtn} onClick={handleClose}>
            {loadError ? '닫기' : '취소'}
          </button>
          {!loadError && (
            <button
              style={s.saveBtn(dirty && !saving && !advancedError)}
              onClick={(dirty && !saving && !advancedError) ? handleSave : undefined}
              disabled={!dirty || saving || advancedError}
            >
              {saving ? '저장 중...' : '저장하고 닫기'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
