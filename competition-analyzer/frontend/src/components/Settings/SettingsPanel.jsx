import { useState, useEffect } from 'react'
import { getSettings, updateSettings, setApiKey, clearApiKey, setDbPath } from '../../api/client'
import PatternViewer from './PatternViewer'

const s = {
  panel: { background: '#ffffff', borderRadius: 12, padding: 24 },
  title: { fontSize: 18, fontWeight: 600, marginBottom: 20, color: '#1f2937' },
  group: { marginBottom: 16 },
  label: { fontSize: 13, color: '#4b5563', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: '#ffffff', border: '1px solid #e5e7eb',
    borderRadius: 6, padding: '8px 12px', color: '#1f2937', fontSize: 14,
    boxSizing: 'border-box',
  },
  inputReadonly: {
    width: '100%', background: '#f3f4f6', border: '1px solid #e5e7eb',
    borderRadius: 6, padding: '8px 12px', color: '#6b7280', fontSize: 13,
    boxSizing: 'border-box', fontFamily: 'monospace',
  },
  inputWrap: { position: 'relative' },
  inputWithToggle: {
    width: '100%', background: '#ffffff', border: '1px solid #e5e7eb',
    borderRadius: 6, padding: '8px 44px 8px 12px', color: '#1f2937', fontSize: 14,
    fontFamily: 'monospace', boxSizing: 'border-box',
  },
  toggle: {
    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
    background: 'transparent', border: 'none', color: '#334155', cursor: 'pointer',
    fontSize: 16, padding: 6,
  },
  btn: {
    background: '#334155', color: '#fff', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13, marginRight: 8,
  },
  btnDanger: {
    background: '#b91c1c', color: '#fff', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13,
  },
  btnPrimary: {
    background: '#334155', color: '#fff', border: 'none', borderRadius: 6,
    padding: '10px 20px', cursor: 'pointer', fontSize: 14, marginTop: 8,
  },
  success: { color: '#16a34a', fontSize: 13, marginTop: 8 },
  hint: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  status: (active) => ({
    display: 'inline-block', fontSize: 12, padding: '2px 8px', borderRadius: 4,
    background: active ? '#dcfce7' : '#fee2e2', color: active ? '#15803d' : '#b91c1c',
    marginLeft: 8,
  }),
}

export default function SettingsPanel() {
  const [form, setForm] = useState({ db_path: '', model_id: '' })
  const [hasDbPath, setHasDbPath] = useState(false)
  const [dbPathMsg, setDbPathMsg] = useState('')
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
      setHasDbPath(!!data.has_db_path)
      setHasKey(!!data.has_api_key)
      setLoading(false)
    })
  }

  useEffect(() => { refresh() }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const saveDbPath = async () => {
    if (!form.db_path.trim()) return
    setDbPathMsg('')
    try {
      await setDbPath(form.db_path.trim())
      setDbPathMsg('✓ DB 경로가 저장되었습니다')
      setHasDbPath(true)
      setTimeout(() => setDbPathMsg(''), 3000)
    } catch (e) {
      setDbPathMsg('✗ ' + (e.message || '저장 실패'))
    }
  }

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

  if (loading) return <div style={{ color: '#4b5563' }}>로딩 중...</div>

  return (
    <div style={s.panel}>
      <div style={s.title}>앱 설정</div>

      <div style={s.group}>
        <label style={s.label}>
          DB 경로
          <span style={s.status(hasDbPath)}>{hasDbPath ? '사용자 설정' : '기본 경로'}</span>
        </label>
        <input
          style={s.input}
          value={form.db_path}
          onChange={e => set('db_path', e.target.value)}
          placeholder="예: C:\Users\홍길동\CompetitionDB"
        />
        <div style={s.hint}>
          미설정 시 기본 경로(~/CompetitionAnalyzerDB)를 사용합니다.
        </div>
        <button style={{ ...s.btn, marginTop: 8 }} onClick={saveDbPath} disabled={!form.db_path.trim()}>
          DB 경로 저장
        </button>
        {dbPathMsg && <div style={s.success}>{dbPathMsg}</div>}
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
