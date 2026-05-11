import { useState, useEffect } from 'react'
import { getSettings, updateSettings, setApiKey, clearApiKey } from '../../api/client'
import PatternViewer from './PatternViewer'

const s = {
  panel: { background: '#1a1f2e', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, marginBottom: 20, color: '#e2e8f0' },
  group: { marginBottom: 16 },
  label: { fontSize: 13, color: '#a0aec0', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 14,
    boxSizing: 'border-box',
  },
  inputReadonly: {
    width: '100%', background: '#0a0d12', border: '1px solid #1f2937',
    borderRadius: 6, padding: '8px 12px', color: '#718096', fontSize: 13,
    boxSizing: 'border-box', fontFamily: 'monospace',
  },
  inputWrap: { position: 'relative' },
  inputWithToggle: {
    width: '100%', background: '#0d1117', border: '1px solid #2d3748',
    borderRadius: 6, padding: '8px 44px 8px 12px', color: '#e2e8f0', fontSize: 14,
    fontFamily: 'monospace', boxSizing: 'border-box',
  },
  toggle: {
    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
    background: 'transparent', border: 'none', color: '#90cdf4', cursor: 'pointer',
    fontSize: 16, padding: 6,
  },
  btn: {
    background: '#3182ce', color: '#fff', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13, marginRight: 8,
  },
  btnDanger: {
    background: '#742a2a', color: '#fff', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13,
  },
  btnPrimary: {
    background: '#3182ce', color: '#fff', border: 'none', borderRadius: 6,
    padding: '10px 20px', cursor: 'pointer', fontSize: 14, marginTop: 8,
  },
  success: { color: '#68d391', fontSize: 13, marginTop: 8 },
  hint: { fontSize: 12, color: '#718096', marginTop: 4 },
  status: (active) => ({
    display: 'inline-block', fontSize: 12, padding: '2px 8px', borderRadius: 4,
    background: active ? '#22543d' : '#742a2a', color: active ? '#9ae6b4' : '#fc8181',
    marginLeft: 8,
  }),
}

export default function SettingsPanel() {
  const [form, setForm] = useState({ db_path: '', model_id: '' })
  const [hasKey, setHasKey] = useState(false)
  const [keyInput, setKeyInput] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [keyMsg, setKeyMsg] = useState('')
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    getSettings().then(data => {
      setForm({
        db_path: data.db_path || '',
        model_id: data.model_id || 'claude-sonnet-4-6',
      })
      setHasKey(!!data.has_api_key)
      setLoading(false)
    })
  }

  useEffect(() => { refresh() }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const saveModel = async () => {
    await updateSettings({ model_id: form.model_id })
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  const updateKey = async () => {
    if (!keyInput.trim()) return
    setKeyMsg('')
    try {
      await setApiKey(keyInput.trim())
      setKeyInput('')
      setKeyMsg('✓ API 키가 갱신되었습니다 (세션 전용)')
      refresh()
      setTimeout(() => setKeyMsg(''), 3000)
    } catch (e) {
      setKeyMsg('✗ ' + (e.message || '실패'))
    }
  }

  const removeKey = async () => {
    if (!confirm('현재 세션의 API 키를 제거하시겠습니까? 다시 입력해야 사용할 수 있습니다.')) return
    await clearApiKey()
    refresh()
  }

  if (loading) return <div style={{ color: '#a0aec0' }}>로딩 중...</div>

  return (
    <div style={s.panel}>
      <div style={s.title}>앱 설정</div>

      <div style={s.group}>
        <label style={s.label}>
          DB 경로 <span style={{ color: '#718096', fontSize: 11 }}>(코드 상수 — 변경 불가)</span>
        </label>
        <input style={s.inputReadonly} value={form.db_path} readOnly />
        <div style={s.hint}>경로 변경은 향후 앱 업데이트로 적용됩니다.</div>
      </div>

      <div style={s.group}>
        <label style={s.label}>
          Anthropic API Key
          <span style={s.status(hasKey)}>{hasKey ? '설정됨' : '미설정'}</span>
        </label>
        <div style={s.inputWrap}>
          <input
            style={s.inputWithToggle}
            type={showKey ? 'text' : 'password'}
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            placeholder={hasKey ? '새 키로 교체하려면 입력...' : 'sk-ant-...'}
          />
          <button
            type="button"
            style={s.toggle}
            onClick={() => setShowKey(v => !v)}
            title={showKey ? '숨기기' : '보기'}
          >
            {showKey ? '🙈' : '👁'}
          </button>
        </div>
        <div style={{ marginTop: 8 }}>
          <button style={s.btn} onClick={updateKey} disabled={!keyInput.trim()}>키 적용</button>
          {hasKey && <button style={s.btnDanger} onClick={removeKey}>현재 키 제거</button>}
        </div>
        <div style={s.hint}>
          🔒 세션 전용 — 디스크에 저장되지 않으며, 앱 종료 시 자동 초기화됩니다.
        </div>
        {keyMsg && <div style={s.success}>{keyMsg}</div>}
      </div>

      <div style={s.group}>
        <label style={s.label}>모델 ID</label>
        <input style={s.input} value={form.model_id}
          onChange={e => set('model_id', e.target.value)} />
      </div>

      <button style={s.btnPrimary} onClick={saveModel}>모델 설정 저장</button>
      {saved && <div style={s.success}>✓ 저장 완료</div>}

      <PatternViewer />
    </div>
  )
}
