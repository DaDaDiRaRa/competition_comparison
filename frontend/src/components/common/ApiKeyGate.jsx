import { useEffect, useState } from 'react'
import { getApiKeyStatus } from '../../api/client'

// API 키 상태를 앱 전체에 제공. 블로킹 없음 — 키 없으면 상단 배너만 표시.
// SettingsPanel에서 키 저장 후 'api-key-changed' 이벤트를 dispatch하면 배너 즉시 제거.
export default function ApiKeyGate({ children }) {
  const [hasKey, setHasKey] = useState(null)

  const checkKey = () => {
    getApiKeyStatus()
      .then(d => setHasKey(d.has_key))
      .catch(() => setHasKey(false))
  }

  useEffect(() => {
    checkKey()
    window.addEventListener('api-key-changed', checkKey)
    return () => window.removeEventListener('api-key-changed', checkKey)
  }, [])

  // 로딩 중에도 UI 차단 안 함
  if (hasKey === null) return children

  if (hasKey) return children

  // 키 없음: 상단 배너만 표시, UI는 계속 접근 가능
  return (
    <>
      <div style={{
        background: 'var(--color-warning-bg)',
        borderBottom: '1px solid #f59e0b',
        padding: '10px 20px',
        fontSize: 13,
        color: '#92400e',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--gap-sm)',
      }}>
        <span>⚠️</span>
        <span>
          분석을 실행하려면 Anthropic API 키가 필요합니다.
          <strong style={{ marginLeft: 4 }}>설정 탭</strong>에서 입력 후 사용하세요.
        </span>
      </div>
      {children}
    </>
  )
}

// 키 상태 새로고침용 훅 — 설정 탭에서 키 저장 후 배너 제거에 사용
export function useRefreshApiKeyStatus(setHasKey) {
  return () => {
    getApiKeyStatus()
      .then(d => setHasKey?.(d.has_key))
      .catch(() => {})
  }
}
