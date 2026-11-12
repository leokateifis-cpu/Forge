import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { useAppStore, type Project } from '../store'
import { authApi, projectsApi } from '../lib/api'
import { Button } from '../components/ui/Button'
import { AccountSetupTab } from './AccountSetupTab'
import { PapersTab } from './PapersTab'
import { DashboardTab } from './DashboardTab'
import { StrategyTab } from './StrategyTab'
import { TradeManagementTab } from './TradeManagementTab'
import { JournalTab } from './JournalTab'

const TABS = [
  { id: 'strategy', label: 'Strategy', always: true },
  { id: 'papers', label: 'Research', always: true },
  { id: 'trademanagement', label: 'Trade Management', always: true },
  { id: 'journal', label: 'Journal', always: true },
  { id: 'account', label: 'Account Setup', always: true },
  { id: 'dashboard', label: 'Dashboard', always: true },
]


export function AppShell() {
  const navigate = useNavigate()
  const { user, setUser, token, activeProjectId, setActiveProjectId, projects, setProjects, activeTab, setActiveTab } =
    useAppStore()

  const [showNewProject, setShowNewProject] = useState(false)

  useEffect(() => {
    if (!token) {
      navigate('/login')
      return
    }
    authApi.me().then((r) => setUser(r.data)).catch(() => navigate('/login'))
    projectsApi.list().then((r) => {
      setProjects(r.data)
      if (!activeProjectId && r.data.length > 0) {
        setActiveProjectId(r.data[0].id)
      }
    })
  }, [token])

  return (
    <div className="min-h-screen flex flex-col bg-[#0a0a0f] text-slate-200">
      {/* Top bar */}
      <header className="border-b border-[#1e1e2e] px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="text-sm font-bold font-mono text-white tracking-tight">⬡ FORGE</span>

          {/* Project selector */}
          <select
            value={activeProjectId ?? ''}
            onChange={(e) => setActiveProjectId(e.target.value || null)}
            className="bg-[#13131f] border border-[#1e1e2e] rounded px-2 py-1 text-xs text-slate-300 font-mono focus:outline-none focus:border-indigo-700"
          >
            <option value="">— select project —</option>
            {projects.map((p: Project) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.instrument})
              </option>
            ))}
          </select>

          <Button size="sm" variant="ghost" onClick={() => setShowNewProject(true)}>
            + New
          </Button>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500 font-mono">{user?.email}</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              useAppStore.getState().setToken(null)
              navigate('/login')
            }}
          >
            Log out
          </Button>
        </div>
      </header>

      {/* Tab bar */}
      <nav className="border-b border-[#1e1e2e] px-4 overflow-x-auto">
        <div className="flex gap-0 min-w-max">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'relative px-4 py-2.5 text-xs font-mono transition-colors border-b-2 whitespace-nowrap',
                  isActive
                    ? 'text-indigo-300 border-indigo-500'
                    : 'text-slate-400 border-transparent hover:text-slate-200'
                )}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto">
          {activeTab === 'strategy' && <StrategyTab />}
          {activeTab === 'papers' && <PapersTab />}
          {activeTab === 'trademanagement' && <TradeManagementTab />}
          {activeTab === 'journal' && <JournalTab />}
          {activeTab === 'account' && <AccountSetupTab />}
          {activeTab === 'dashboard' && <DashboardTab />}
        </div>
      </main>

      {/* New project modal */}
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={(p) => {
            setProjects([...projects, p])
            setActiveProjectId(p.id)
            setShowNewProject(false)
            setActiveTab('strategy')
          }}
        />
      )}
    </div>
  )
}

function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (p: Project) => void
}) {
  const [name, setName] = useState<string>('')
  const [instrument, setInstrument] = useState<string>('ES')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')

  async function create() {
    setError('')
    setLoading(true)
    try {
      const { data } = await projectsApi.create(name, instrument, '1m')
      onCreated(data)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-[#13131f] border border-[#1e1e2e] rounded-lg w-full max-w-md p-6 space-y-4">
        <h3 className="text-sm font-semibold text-white">New Project</h3>
        <input
          placeholder="Strategy name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && name.trim() && create()}
          className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
        />
        <select
          value={instrument}
          onChange={(e) => setInstrument(e.target.value)}
          className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded px-2 py-2 text-xs text-slate-300 font-mono focus:outline-none focus:border-indigo-700"
        >
          <option value="ES">ES (S&amp;P 500 Futures)</option>
          <option value="NQ">NQ (Nasdaq 100 Futures)</option>
        </select>
        <p className="text-[10px] text-slate-600 leading-relaxed">
          SPY, QQQ, and VIX futures data are available as supplementary reference data inside your strategy — select ES or NQ as your primary trading instrument.
        </p>
        {error && (
          <div className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">{error}</div>
        )}
        <div className="flex justify-end gap-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={loading} onClick={create} disabled={!name.trim()}>
            Create
          </Button>
        </div>
      </div>
    </div>
  )
}

