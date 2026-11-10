import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { useAppStore, type Project } from '../store'
import { authApi, projectsApi } from '../lib/api'
import { usePipelineStatus } from '../hooks/usePipeline'
import { Button } from '../components/ui/Button'
import { SkipModal } from '../components/ui/SkipModal'
import { HypothesisTab } from './HypothesisTab'
import { CodeTab } from './CodeTab'
import { DataSplitTab } from './DataSplitTab'
import { DevelopmentTab } from './DevelopmentTab'
import { ValidationTab } from './ValidationTab'
import { AccountSetupTab } from './AccountSetupTab'
import { PapersTab } from './PapersTab'
import { DashboardTab } from './DashboardTab'

const TABS = [
  { id: 'account', label: 'Account Setup', always: true },
  { id: 'papers', label: 'Research Papers', always: true },
  { id: 'hypothesis', label: 'Hypothesis', stage: 1 },
  { id: 'code', label: 'Code', stage: 2 },
  { id: 'split', label: 'Data Split', stage: 3 },
  { id: 'development', label: 'Development', stage: 4 },
  { id: 'validation', label: 'Validation', stage: 5 },
  { id: 'dashboard', label: 'Dashboard', always: true },
]

function statusColor(status: string) {
  if (status === 'complete') return 'text-green-400'
  if (status === 'active') return 'text-indigo-400'
  if (status === 'skipped') return 'text-yellow-400'
  return 'text-slate-600'
}

function statusDot(status: string) {
  if (status === 'complete') return '●'
  if (status === 'active') return '◉'
  if (status === 'skipped') return '◈'
  return '○'
}


export function AppShell() {
  const navigate = useNavigate()
  const { user, setUser, token, activeProjectId, setActiveProjectId, projects, setProjects, activeTab, setActiveTab } =
    useAppStore()

  const [showNewProject, setShowNewProject] = useState(false)
  const [skipModal, setSkipModal] = useState<{ stage: number; label: string } | null>(null)

  const pipeline = usePipelineStatus(activeProjectId)
  const stages: Record<string, { status: string; stage_num: number }> =
    pipeline.data?.stages ?? {}

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

  function getStageForTab(tabId: string) {
    const tab = TABS.find((t) => t.id === tabId)
    if (!tab?.stage) return null
    return Object.values(stages).find((s) => s.stage_num === tab.stage) ?? null
  }

  function isTabAccessible(tabId: string) {
    const tab = TABS.find((t) => t.id === tabId)
    if (!tab) return false
    if (tab.always) return true
    if (!activeProjectId) return false
    const stage = getStageForTab(tabId)
    return stage ? stage.status !== 'locked' : false
  }

  const activeStage = getStageForTab(activeTab)

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
            const accessible = isTabAccessible(tab.id)
            const stageInfo = getStageForTab(tab.id)
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => accessible && setActiveTab(tab.id)}
                disabled={!accessible}
                className={clsx(
                  'relative px-4 py-2.5 text-xs font-mono transition-colors border-b-2 whitespace-nowrap',
                  isActive
                    ? 'text-indigo-300 border-indigo-500'
                    : accessible
                    ? 'text-slate-400 border-transparent hover:text-slate-200'
                    : 'text-slate-700 border-transparent cursor-not-allowed'
                )}
              >
                {stageInfo && (
                  <span className={clsx('mr-1 text-[10px]', statusColor(stageInfo.status))}>
                    {statusDot(stageInfo.status)}
                  </span>
                )}
                {tab.label}
              </button>
            )
          })}
        </div>
      </nav>

      {/* Skip button for active pipeline stage */}
      {activeStage && activeStage.status === 'active' && activeProjectId && (
        <div className="border-b border-[#1e1e2e] px-4 py-1.5 flex justify-end bg-[#0d0d14]">
          <button
            className="text-[10px] text-slate-600 hover:text-yellow-400 transition-colors font-mono"
            onClick={() => {
              const tab = TABS.find((t) => t.id === activeTab)
              setSkipModal({ stage: activeStage.stage_num, label: tab?.label ?? '' })
            }}
          >
            Skip this stage →
          </button>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto">
          {activeTab === 'account' && <AccountSetupTab />}
          {activeTab === 'papers' && <PapersTab />}
          {activeTab === 'hypothesis' && (
            <HypothesisTab stage={activeStage ?? { status: 'locked' }} />
          )}
          {activeTab === 'code' && <CodeTab stage={activeStage ?? { status: 'locked' }} />}
          {activeTab === 'split' && <DataSplitTab stage={activeStage ?? { status: 'locked' }} />}
          {activeTab === 'development' && (
            <DevelopmentTab stage={activeStage ?? { status: 'locked' }} />
          )}
          {activeTab === 'validation' && (
            <ValidationTab stage={activeStage ?? { status: 'locked' }} />
          )}
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
            setActiveTab('hypothesis')
          }}
        />
      )}

      {/* Skip modal */}
      {skipModal && activeProjectId && (
        <SkipModal
          projectId={activeProjectId}
          stage={skipModal.stage}
          stageLabel={skipModal.label}
          onClose={() => setSkipModal(null)}
          onSkipped={() => setSkipModal(null)}
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
  const [timeframe, setTimeframe] = useState<string>('1D')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')

  async function create() {
    setError('')
    setLoading(true)
    try {
      const { data } = await projectsApi.create(name, instrument, timeframe)
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
          className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
        />
        <div className="flex gap-3">
          <select
            value={instrument}
            onChange={(e) => setInstrument(e.target.value)}
            className="flex-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded px-2 py-2 text-xs text-slate-300 font-mono focus:outline-none focus:border-indigo-700"
          >
            <option>ES</option>
            <option>NQ</option>
            <option>SPY</option>
            <option>QQQ</option>
          </select>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="flex-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded px-2 py-2 text-xs text-slate-300 font-mono focus:outline-none focus:border-indigo-700"
          >
            <option value="1D">Daily</option>
            <option value="1H">1 Hour</option>
            <option value="4H">4 Hour</option>
            <option value="15T">15 Min</option>
          </select>
        </div>
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

