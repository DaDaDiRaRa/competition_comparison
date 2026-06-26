import { useState, useEffect } from 'react'
import { getSettings, updateSettings, setStoredApiKey, clearStoredApiKey, hasStoredApiKey, setDbPath } from '../../api/client'
import PatternViewer from './PatternViewer'

const s = {
  panel: { background: 'var(--color-bg-surface)', borderRadius: 12, padding: 24 },
  title: { fontSize: 'var(--font-size-lg)', fontWeight: 'var(--font-weight-semibold)', marginBottom: 20, color: 'var(--color-text-body)' },
  group: { marginBottom: 16 },
  label: { fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 6, display: 'block' },
  input: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
    boxSizing: 'border-box',
  },
  inputReadonly: {
    width: '100%', background: 'var(--color-bg-input-disabled)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 12px', color: 'var(--color-text-faint)', fontSize: 13,
    boxSizing: 'border-box', fontFamily: 'monospace',
  },
  inputWrap: { position: 'relative' },
  inputWithToggle: {
    width: '100%', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)',
    borderRadius: 6, padding: '8px 44px 8px 12px', color: 'var(--color-text-body)', fontSize: 'var(--font-size-base)',
    fontFamily: 'monospace', boxSizing: 'border-box',
  },
  toggle: {
    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
    background: 'transparent', border: 'none', color: 'var(--color-accent)', cursor: 'pointer',
    fontSize: 16, padding: 6,
  },
  btn: {
    background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13, marginRight: 8,
  },
  btnDanger: {
    background: 'var(--color-danger)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '8px 16px', cursor: 'pointer', fontSize: 13,
  },
  btnPrimary: {
    background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: 'none', borderRadius: 6,
    padding: '10px 20px', cursor: 'pointer', fontSize: 'var(--font-size-base)', marginTop: 8,
  },
  success: { color: 'var(--color-success)', fontSize: 13, marginTop: 8 },
  hint: { fontSize: 'var(--font-size-sm)', color: 'var(--color-text-faint)', marginTop: 4 },
  status: (active) => ({
    display: 'inline-block', fontSize: 'var(--font-size-sm)', padding: '2px 8px', borderRadius: 4,
    background: active ? 'var(--color-success-bg)' : 'var(--color-danger-bg)', color: active ? 'var(--color-success)' : 'var(--color-danger)',
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
      setHasKey(hasStoredApiKey())   // 키는 이 브라우저(localStorage) 기준
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

  const updateKey = () => {
    if (!keyInput.trim()) return
    setStoredApiKey(keyInput.trim())
    setKeyInput('')
    setHasKey(true)
    setKeyMsg('✓ API 키가 이 브라우저에 저장되었습니다')
    window.dispatchEvent(new Event('api-key-changed'))
    setTimeout(() => setKeyMsg(''), 3000)
  }

  const removeKey = () => {
    if (!confirm('이 브라우저에 저장된 API 키를 제거하시겠습니까? 다시 입력해야 사용할 수 있습니다.')) return
    clearStoredApiKey()
    setHasKey(false)
    window.dispatchEvent(new Event('api-key-changed'))
  }

  if (loading) return <div style={{ color: 'var(--color-text-muted)' }}>로딩 중...</div>

  return (
    <div style={s.panel}>
      <div style={s.title}>앱 설정</div>

      {/* API 키 미설정 시 최상단 강조 안내 */}
      {!hasKey && (
        <div style={{
          background: 'var(--color-warning-bg)', border: '1px solid #f59e0b', borderRadius: 8,
          padding: '14px 16px', marginBottom: 20,
          fontSize: 13, color: 'var(--color-amber-dark)', lineHeight: 1.6,
        }}>
          <strong>⚠️ API 키를 먼저 입력하세요</strong><br />
          아래 <strong>Anthropic API Key</strong> 항목에 본인의 키를 입력하고 <strong>키 적용</strong> 버튼을 누르면 분석 기능을 사용할 수 있습니다.
        </div>
      )}

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
          🔒 이 브라우저에만 저장됩니다 — 다른 사람·다른 PC와 공유되지 않으며, 분석은 본인 키로 본인 Anthropic 계정에 과금됩니다.
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
