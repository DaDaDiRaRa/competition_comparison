import { useEffect, useState } from 'react'
import { getApiKeyStatus, setApiKey } from '../../api/client'

const s = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 9999,
  },
  modal: {
    background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: 12,
    padding: 32, width: 460, maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
  },
  title: { fontSize: 18, fontWeight: 700, color: '#334155', marginBottom: 8 },
  desc: { fontSize: 13, color: '#4b5563', marginBottom: 20, lineHeight: 1.6 },
  label: { fontSize: 13, color: '#374151', marginBottom: 6, display: 'block' },
  inputWrap: { position: 'relative' },
  input: {
    width: '100%', background: '#ffffff', border: '1px solid #e5e7eb',
    borderRadius: 6, padding: '10px 44px 10px 12px', color: '#1f2937', fontSize: 14,
    fontFamily: 'monospace', boxSizing: 'border-box',
  },
  toggle: {
    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
    background: 'transparent', border: 'none', color: '#334155', cursor: 'pointer',
    fontSize: 16, padding: 6, borderRadius: 4,
  },
  btn: {
    width: '100%', background: '#334155', color: '#fff', border: 'none',
    borderRadius: 6, padding: '12px', cursor: 'pointer', fontSize: 14,
    fontWeight: 600, marginTop: 16,
  },
  btnDisabled: {
    background: '#e5e7eb', color: '#6b7280', cursor: 'not-allowed',
  },
  error: {
    color: '#dc2626', fontSize: 13, marginTop: 10, padding: 8,
    background: 'rgba(252,129,129,0.1)', borderRadius: 6,
  },
  notice: {
    fontSize: 12, color: '#6b7280', marginTop: 12, padding: 10,
    background: '#ffffff', borderRadius: 6, lineHeight: 1.5,
  },
}

export default function ApiKeyGate({ children }) {
  const [hasKey, setHasKey] = useState(null)  // null = 확인 중
  const [value, setValue] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getApiKeyStatus()
      .then(d => setHasKey(d.has_key))
      .catch(() => setHasKey(false))
  }, [])

  const submit = async () => {
    if (!value.trim()) return
    setSubmitting(true)
    setError('')
    try {
      await setApiKey(value.trim())
      setHasKey(true)
      setValue('')
    } catch (e) {
      setError(e.message || '설정에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  if (hasKey === null) {
    return (
      <div style={s.overlay}>
        <div style={{ color: '#4b5563' }}>로딩 중...</div>
      </div>
    )
  }

  if (hasKey) return children

  return (
    <>
      {children}
      <div style={s.overlay}>
        <div style={s.modal}>
          <div style={s.title}>🔑 Anthropic API 키 입력</div>
          <div style={s.desc}>
            앱을 사용하려면 Anthropic API 키가 필요합니다.<br />
            키는 <strong>현재 세션에서만 유지</strong>되며, 앱을 종료하면 자동으로 초기화됩니다.
          </div>

          <label style={s.label}>API Key</label>
          <div style={s.inputWrap}>
            <input
              style={s.input}
              type={showKey ? 'text' : 'password'}
              value={value}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder="sk-ant-..."
              autoFocus
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

          {error && <div style={s.error}>{error}</div>}

          <button
            style={{ ...s.btn, ...(submitting || !value.trim() ? s.btnDisabled : {}) }}
            onClick={submit}
            disabled={submitting || !value.trim()}
          >
            {submitting ? '확인 중...' : '시작하기'}
          </button>

          <div style={s.notice}>
            💡 키는 디스크에 저장되지 않고 메모리에만 보관됩니다.<br />
            앱 재실행 시 다시 입력해야 합니다.
          </div>
        </div>
      </div>
    </>
  )
}
