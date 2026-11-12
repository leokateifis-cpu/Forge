import { useState } from 'react'
import { clsx } from 'clsx'
import { useAppStore, type Project } from '../store'
import { Card } from '../components/ui/Card'

function StrategyJournal({ project }: { project: Project }) {
  const [entries, setEntries] = useState<{ text: string; ts: string }[]>([])
  const [draft, setDraft] = useState('')

  function addEntry() {
    if (!draft.trim()) return
    setEntries((prev) => [
      { text: draft.trim(), ts: new Date().toLocaleString() },
      ...prev,
    ])
    setDraft('')
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-semibold text-white">{project.name}</h3>
        <p className="text-[10px] text-slate-500 mt-0.5 font-mono">{project.instrument}</p>
      </div>

      <div className="flex gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a journal entry — observations, decisions, what worked, what didn't…"
          rows={3}
          className="flex-1 bg-[#13131f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700 resize-none"
        />
        <button
          onClick={addEntry}
          disabled={!draft.trim()}
          className="px-3 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed text-xs text-white font-mono self-start"
        >
          Add
        </button>
      </div>

      {entries.length === 0 ? (
        <Card className="text-center py-8">
          <p className="text-xs text-slate-500">No journal entries yet.</p>
          <p className="text-xs text-slate-600 mt-1">Record your observations, decisions, and insights for this strategy.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {entries.map((e, i) => (
            <div key={i} className="bg-[#0d0d14] border border-[#1e1e2e] rounded p-3">
              <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{e.text}</p>
              <p className="text-[10px] text-slate-600 mt-2 font-mono">{e.ts}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function JournalTab() {
  const { projects, activeProjectId, setActiveProjectId } = useAppStore()
  const [activeJournalId, setActiveJournalId] = useState<string | null>(activeProjectId)

  const activeProject = projects.find((p) => p.id === activeJournalId) ?? projects[0] ?? null

  if (projects.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-xs text-slate-500">Create a strategy to start journaling.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">Strategy Journal</h2>
        <p className="text-xs text-slate-500 mt-0.5">One journal per strategy.</p>
      </div>

      {/* Strategy sub-tabs */}
      <div className="flex gap-1 flex-wrap border-b border-[#1e1e2e] pb-0">
        {projects.map((p) => (
          <button
            key={p.id}
            onClick={() => setActiveJournalId(p.id)}
            className={clsx(
              'px-3 py-2 text-xs font-mono border-b-2 -mb-px transition-colors whitespace-nowrap',
              activeJournalId === p.id
                ? 'text-indigo-300 border-indigo-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            )}
          >
            {p.name}
            <span className="ml-1.5 text-[9px] text-slate-600">{p.instrument}</span>
          </button>
        ))}
      </div>

      {activeProject && <StrategyJournal key={activeProject.id} project={activeProject} />}
    </div>
  )
}
