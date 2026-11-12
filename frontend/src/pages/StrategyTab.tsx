import { useState } from 'react'
import { clsx } from 'clsx'
import { usePipelineStatus } from '../hooks/usePipeline'
import { useAppStore } from '../store'
import { HypothesisTab } from './HypothesisTab'
import { CodeTab } from './CodeTab'
import { DataSplitTab } from './DataSplitTab'
import { DevelopmentTab } from './DevelopmentTab'
import { ValidationTab } from './ValidationTab'

const STRATEGY_STAGES = [
  { id: 'hypothesis', label: 'Hypothesis', stageNum: 1 },
  { id: 'code', label: 'Code', stageNum: 2 },
  { id: 'split', label: 'Data Split', stageNum: 3 },
  { id: 'development', label: 'Development', stageNum: 4 },
  { id: 'validation', label: 'Validation', stageNum: 5 },
]

function stageStatus(stages: Record<string, any>, stageNum: number) {
  return Object.values(stages).find((s: any) => s.stage_num === stageNum)?.status ?? 'locked'
}

function StageIndicator({ label, status, active, onClick }: {
  label: string
  status: string
  active: boolean
  onClick: () => void
}) {
  const accessible = status !== 'locked'
  return (
    <button
      onClick={onClick}
      disabled={!accessible}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono transition-colors',
        active ? 'bg-indigo-600/30 text-indigo-200 border border-indigo-700' :
        accessible ? 'text-slate-400 hover:text-slate-200 border border-transparent hover:border-[#1e1e2e]' :
        'text-slate-700 cursor-not-allowed border border-transparent'
      )}
    >
      <span className={clsx('text-[9px]',
        status === 'complete' ? 'text-green-400' :
        status === 'active' ? 'text-indigo-400' :
        status === 'skipped' ? 'text-yellow-400' : 'text-slate-700'
      )}>
        {status === 'complete' ? '●' : status === 'active' ? '◉' : status === 'skipped' ? '◈' : '○'}
      </span>
      {label}
    </button>
  )
}

export function StrategyTab() {
  const { activeProjectId } = useAppStore()
  const pipeline = usePipelineStatus(activeProjectId)
  const stages: Record<string, any> = pipeline.data?.stages ?? {}
  const [activeStage, setActiveStage] = useState('hypothesis')

  if (!activeProjectId) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-xs text-slate-500">Select or create a project to begin.</p>
      </div>
    )
  }

  const currentStageInfo = Object.values(stages).find(
    (s: any) => s.stage_num === STRATEGY_STAGES.find(st => st.id === activeStage)?.stageNum
  ) ?? { status: 'locked' }

  return (
    <div className="space-y-4">
      {/* Stage progress bar */}
      <div className="flex items-center gap-1 bg-[#0d0d14] border border-[#1e1e2e] rounded-lg px-3 py-2 overflow-x-auto">
        {STRATEGY_STAGES.map((s, i) => (
          <div key={s.id} className="flex items-center">
            {i > 0 && (
              <div className={clsx('w-6 h-px mx-0.5',
                stageStatus(stages, s.stageNum - 1 + 1) !== 'locked' ? 'bg-slate-700' : 'bg-[#1e1e2e]'
              )} />
            )}
            <StageIndicator
              label={s.label}
              status={stageStatus(stages, s.stageNum)}
              active={activeStage === s.id}
              onClick={() => setActiveStage(s.id)}
            />
          </div>
        ))}
      </div>

      {/* Stage content */}
      <div className="min-h-[500px]">
        {activeStage === 'hypothesis' && <HypothesisTab stage={currentStageInfo} />}
        {activeStage === 'code' && <CodeTab stage={currentStageInfo} />}
        {activeStage === 'split' && <DataSplitTab stage={currentStageInfo} />}
        {activeStage === 'development' && <DevelopmentTab stage={currentStageInfo} />}
        {activeStage === 'validation' && <ValidationTab stage={currentStageInfo} />}
      </div>
    </div>
  )
}
