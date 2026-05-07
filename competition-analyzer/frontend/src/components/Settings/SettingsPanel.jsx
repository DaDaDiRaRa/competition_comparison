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
  segment: { display: 'flex', gap: 8 },
  segBtn: (active) => ({
    flex: 1,
    background: active ? '#3182ce' : '#0d1117',
    border: `1px solid ${active ? '#3182ce' : '#2d3748'}`,
    color: active ? '#fff' : '#a0aec0',
    borderRadius: 6, padding: '10px 12px', cursor: 'pointer', fontSize: 14,
    textAlign: 'left',
  }),
  segHint: { fontSize: 12, color: '#718096', marginTop: 6, lineHeight: 1.5 },
}

export default function SettingsPanel() {
  const [form, setForm] = useState({
    db_path: '', anthropic_api_key: '', model_id: '', provider: 'api',
  })
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSettings().then(data => {
      setForm({
        db_path: data.db_path || '',
        anthropic_api_key: '',
        model_id: data.model_id || 'claude-sonnet-4-6',
        provider: data.provider === 'sdk' ? 'sdk' : 'api',
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
        <label style={s.label}>Claude 호출 방식</label>
        <div style={s.segment}>
          <button type="button" style={s.segBtn(form.provider === 'api')}
            onClick={() => set('provider', 'api')}>
            <div style={{ fontWeight: 600 }}>API 모드</div>
            <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
              Anthropic API 토큰 사용 (유료)
            </div>
          </button>
          <button type="button" style={s.segBtn(form.provider === 'sdk')}
            onClick={() => set('provider', 'sdk')}>
            <div style={{ fontWeight: 600 }}>SDK 모드 (구독)</div>
            <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
              Claude Code 구독 사용 (claude login 필요)
            </div>
          </button>
        </div>
        <div style={s.segHint}>
          {form.provider === 'sdk'
            ? 'SDK 모드: 백엔드 머신에서 claude login이 되어 있어야 동작합니다. 호출당 약간의 오버헤드가 있고 5시간 메시지 한도가 적용됩니다.'
            : 'API 모드: 호출당 토큰이 차감됩니다. 아래 API 키 또는 ANTHROPIC_API_KEY 환경변수가 필요합니다.'}
        </div>
      </div>

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

      <button style={s.btn} onClick={save}>저장</button>
      {saved && <div style={s.success}>✓ 저장 완료</div>}
    </div>
  )
}
