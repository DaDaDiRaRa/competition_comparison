import { useState, useEffect } from 'react'
import AccumulateMode from './components/AccumulateMode/AccumulateMode'
import CrossCompareMode from './components/CrossCompare/CrossCompareMode'
import DiagnoseMode from './components/DiagnoseMode/DiagnoseMode'
import MyProjectMode from './components/MyProjectMode/MyProjectMode'
import SettingsPanel from './components/Settings/SettingsPanel'
import ApiKeyGate from './components/common/ApiKeyGate'
import { MetaProvider } from './hooks/useMeta'

const TABS = [
  { id: 'myproject', label: '내 프로젝트 등록', icon: '📁' },
  { id: 'accumulate', label: '경쟁 공모 등록', icon: '🗄' },
  { id: 'crosscompare', label: '교차 비교', icon: '⚖' },
  { id: 'diagnose', label: '제안서 진단', icon: '🔍' },
  { id: 'settings', label: '설정', icon: '⚙' },
]

const s = {
  app: { minHeight: '100vh', background: '#fafafa' },
  header: {
    background: '#ffffff', borderBottom: '1px solid #e5e7eb',
    padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24,
  },
  logo: { fontSize: 15, fontWeight: 700, color: '#1e3a8a', padding: '16px 0', flexShrink: 0 },
  nav: { display: 'flex', gap: 4 },
  tab: (active) => ({
    padding: '16px 18px', cursor: 'pointer', fontSize: 14, fontWeight: active ? 600 : 400,
    color: active ? '#1e3a8a' : '#6b7280',
    borderTop: 'none', borderLeft: 'none', borderRight: 'none',
    borderBottom: active ? '2px solid #1e3a8a' : '2px solid transparent',
    background: 'none', transition: 'all 0.15s',
    display: 'flex', alignItems: 'center', gap: 6,
  }),
  content: { maxWidth: 1100, margin: '0 auto', padding: 24 },
  badge: {
    fontSize: 10, background: '#1e3a8a', color: '#fff',
    padding: '1px 6px', borderRadius: 10, marginLeft: 4,
  },
}

export default function App() {
  const [activeTab, setActiveTab] = useState('myproject')

  // PyWebView 네이티브 모드: target="_blank" 링크는 시스템 기본 브라우저로 위임.
  // 리포트(HTML/PDF 인쇄)를 사용자에게 익숙한 환경에서 보게 함.
  useEffect(() => {
    const handler = (e) => {
      const link = e.target.closest('a[target="_blank"]')
      if (!link) return
      if (window.pywebview?.api?.open_external) {
        e.preventDefault()
        window.pywebview.api.open_external(link.href)
      }
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [])

  return (
    <MetaProvider>
    <ApiKeyGate>
    <div style={s.app}>
      <header style={s.header}>
        <div style={s.logo}>
          설계공모 경쟁분석
        </div>
        <nav style={s.nav}>
          {TABS.map(t => (
            <button
              key={t.id}
              style={s.tab(activeTab === t.id)}
              onClick={() => setActiveTab(t.id)}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main style={s.content}>
        {activeTab === 'myproject' && <MyProjectMode />}
        {activeTab === 'accumulate' && <AccumulateMode />}
        {activeTab === 'crosscompare' && <CrossCompareMode />}
        {activeTab === 'diagnose' && <DiagnoseMode />}
        {activeTab === 'settings' && <SettingsPanel />}
      </main>
    </div>
    </ApiKeyGate>
    </MetaProvider>
  )
}
