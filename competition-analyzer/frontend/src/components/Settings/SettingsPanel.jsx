import { useState, useEffect } from 'react'
import { getSettings, updateSettings } from '../../api/client'

const s = {
  panel: { background: '#1a1f2e', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, marginBottom: 20, color: '#e2e8f0' },
  group: { marginBottom: 16 },
  label: { fontSize: 13, color: '#a0aec0', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 14,
  },
  btn: {
    background: '#3182ce', color: '#fff', border: 'none', borderRadius: 6,
    padding: '10px 20px', cursor: 'pointer', fontSize: 14, marginTop: 8,
  },
  success: { color: '#68d391', fontSize: 13, marginTop: 8 },
}

export default function SettingsPanel() {
  const [form, setForm] = useState({
    db_path: '', anthropic_api_key: '', raster_dpi_classify: 72,
    raster_dpi_extract: 150, model_id: '',
  })
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSettings().then(data => {
      setForm({
        db_path: data.db_path || '',
        anthropic_api_key: '',
        raster_dpi_classify: data.raster_dpi_classify || 72,
        raster_dpi_extract: data.raster_dpi_extract || 150,
        model_id: data.model_id || 'claude-sonnet-4-6',
      })
      setLoading(false)
    })
  }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const save = async () => {
    const payload = { ...form }
    if (!payload.anthropic_api_key) delete payload.anthropic_api_key
    await updateSettings(payload)
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  if (loading) return <div style={{ color: '#a0aec0' }}>로딩 중...</div>

  return (
    <div style={s.panel}>
      <div style={s.title}>앱 설정</div>

      <div style={s.group}>
        <label style={s.label}>DB 경로 (JSON 파일 저장 폴더)</label>
        <input style={s.input} value={form.db_path}
          onChange={e => set('db_path', e.target.value)} placeholder="/path/to/competition_db" />
      </div>

      <div style={s.group}>
        <label style={s.label}>Anthropic API Key</label>
        <input style={s.input} type="password" value={form.anthropic_api_key}
          onChange={e => set('anthropic_api_key', e.target.value)}
          placeholder="sk-ant-... (비워두면 환경변수 사용)" />
      </div>

      <div style={s.group}>
        <label style={s.label}>모델 ID</label>
        <input style={s.input} value={form.model_id}
          onChange={e => set('model_id', e.target.value)} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={s.group}>
          <label style={s.label}>분류 DPI (기본 72)</label>
          <input style={s.input} type="number" value={form.raster_dpi_classify}
            onChange={e => set('raster_dpi_classify', Number(e.target.value))} />
        </div>
        <div style={s.group}>
          <label style={s.label}>추출 DPI (기본 150)</label>
          <input style={s.input} type="number" value={form.raster_dpi_extract}
            onChange={e => set('raster_dpi_extract', Number(e.target.value))} />
        </div>
      </div>

      <button style={s.btn} onClick={save}>저장</button>
      {saved && <div style={s.success}>✓ 저장 완료</div>}
    </div>
  )
}
