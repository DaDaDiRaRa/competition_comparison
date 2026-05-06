import { useState } from 'react'
import AccumulateMode from './components/AccumulateMode/AccumulateMode'
import DiagnoseMode from './components/DiagnoseMode/DiagnoseMode'
import SettingsPanel from './components/Settings/SettingsPanel'

const TABS = [
  { id: 'accumulate', label: '데이터 축적', icon: '🗄' },
  { id: 'diagnose', label: '신규 진단', icon: '🔍' },
  { id: 'settings', label: '설정', icon: '⚙' },
]

const s = {
  app: { minHeight: '100vh', background: '#0f1117' },
  header: {
    background: '#1a1f2e', borderBottom: '1px solid #2d3748',
    padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24,
  },
  logo: { fontSize: 15, fontWeight: 700, color: '#90cdf4', padding: '16px 0', flexShrink: 0 },
  nav: { display: 'flex', gap: 4 },
  tab: (active) => ({
    padding: '16px 18px', cursor: 'pointer', fontSize: 14, fontWeight: active ? 600 : 400,
    color: active ? '#90cdf4' : '#718096',
    borderBottom: active ? '2px solid #90cdf4' : '2px solid transparent',
    background: 'none', border: 'none', transition: 'all 0.15s',
    display: 'flex', alignItems: 'center', gap: 6,
  }),
  content: { maxWidth: 1100, margin: '0 auto', padding: 24 },
  badge: {
    fontSize: 10, background: '#2b6cb0', color: '#fff',
    padding: '1px 6px', borderRadius: 10, marginLeft: 4,
  },
}

export default function App() {
  const [activeTab, setActiveTab] = useState('accumulate')

  return (
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
        {activeTab === 'accumulate' && <AccumulateMode />}
        {activeTab === 'diagnose' && <DiagnoseMode />}
        {activeTab === 'settings' && <SettingsPanel />}
      </main>
    </div>
  )
}
