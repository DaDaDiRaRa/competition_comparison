import { useState, useEffect } from 'react'
import AccumulateMode from './components/AccumulateMode/AccumulateMode'
import ArchiveMode from './components/ArchiveMode/ArchiveMode'
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
  { id: 'archive', label: '아카이브 검색', icon: '🔎' },
]

const s = {
  app: { minHeight: '100vh', background: 'var(--color-bg-page)' },
  header: {
    background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)',
    padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24,
  },
  logo: { fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-bold)', color: 'var(--color-accent)', padding: '16px 0', flexShrink: 0 },
  nav: { display: 'flex', gap: 'var(--gap-xs)', flex: 1 },
  tab: (active) => ({
    padding: '16px 18px', cursor: 'pointer', fontSize: 'var(--font-size-base)', fontWeight: active ? 600 : 400,
    color: active ? 'var(--color-accent)' : 'var(--color-text-faint)',
    borderTop: 'none', borderLeft: 'none', borderRight: 'none',
    borderBottom: active ? '2px solid var(--color-accent)' : '2px solid transparent',
    background: 'none', transition: 'all 0.15s',
    display: 'flex', alignItems: 'center', gap: 6,
  }),
  helpBtn: {
    marginLeft: 'auto', padding: '8px 14px', cursor: 'pointer', fontSize: 13,
    fontWeight: 'var(--font-weight-medium)', color: 'var(--color-text-faint)', border: '1px solid var(--color-border)',
    borderRadius: 6, background: 'var(--color-bg-surface-alt)', flexShrink: 0,
    display: 'flex', alignItems: 'center', gap: 5, transition: 'all 0.15s',
  },
  content: { maxWidth: 1100, margin: '0 auto', padding: 24 },
  badge: {
    fontSize: 10, background: 'var(--color-accent)', color: 'var(--color-text-on-accent)',
    padding: '1px 6px', borderRadius: 10, marginLeft: 4,
  },
  overlay: {
    position: 'fixed', inset: 0, background: 'var(--color-overlay)',
    zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
    padding: '40px 20px',
  },
  modal: {
    background: 'var(--color-bg-surface)', borderRadius: 10, boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
    width: '100%', maxWidth: 960, height: '85vh',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  modalHeader: {
    padding: '14px 20px', borderBottom: '1px solid var(--color-border)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    flexShrink: 0,
  },
  modalTitle: { fontSize: 'var(--font-size-md)', fontWeight: 'var(--font-weight-semibold)', color: 'var(--color-accent)' },
  closeBtn: {
    cursor: 'pointer', fontSize: 'var(--font-size-xl)', color: 'var(--color-text-subtle)', background: 'none',
    border: 'none', lineHeight: 1, padding: '2px 6px', borderRadius: 4,
  },
}

export default function App() {
  const [activeTab, setActiveTab] = useState('myproject')
  const [showReadme, setShowReadme] = useState(false)

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
        <button style={s.helpBtn} onClick={() => setShowReadme(true)}>
          ? 도움말
        </button>
      </header>

      {showReadme && (
        <div style={s.overlay} onClick={() => setShowReadme(false)}>
          <div style={s.modal} onClick={e => e.stopPropagation()}>
            <div style={s.modalHeader}>
              <span style={s.modalTitle}>사용자 매뉴얼</span>
              <button style={s.closeBtn} onClick={() => setShowReadme(false)}>×</button>
            </div>
            <iframe
              src="/api/readme"
              style={{ flex: 1, border: 'none', width: '100%' }}
              title="사용자 매뉴얼"
            />
          </div>
        </div>
      )}

      <main style={s.content}>
        {activeTab === 'myproject' && <MyProjectMode />}
        {activeTab === 'accumulate' && <AccumulateMode />}
        {activeTab === 'crosscompare' && <CrossCompareMode />}
        {activeTab === 'diagnose' && <DiagnoseMode />}
        {activeTab === 'settings' && <SettingsPanel />}
        {activeTab === 'archive' && <ArchiveMode />}
      </main>
    </div>
    </ApiKeyGate>
    </MetaProvider>
  )
}
