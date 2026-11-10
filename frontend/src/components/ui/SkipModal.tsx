import { useState } from 'react'
import { Button } from './Button'
import { pipelineApi } from '../../lib/api'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  projectId: string
  stage: number
  stageLabel: string
  onClose: () => void
  onSkipped: () => void
}

export function SkipModal({ projectId, stage, stageLabel, onClose, onSkipped }: Props) {
  const [confirmed, setConfirmed] = useState(false)
  const [loading, setLoading] = useState(false)
  const qc = useQueryClient()

  async function handleSkip() {
    if (!confirmed) {
      setConfirmed(true)
      return
    }
    setLoading(true)
    try {
      await pipelineApi.skip(projectId, stage, true)
      qc.invalidateQueries({ queryKey: ['pipeline', projectId] })
      onSkipped()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-[#13131f] border border-[#1e1e2e] rounded-lg w-full max-w-md p-6">
        <div className="flex items-start gap-3 mb-4">
          <span className="text-yellow-400 text-xl">⚠</span>
          <div>
            <h3 className="text-sm font-semibold text-white mb-1">Skip {stageLabel}?</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              This strategy has not been fully validated through this stage. Skipping means
              you are proceeding without the confidence this step provides — you should proceed
              with significant caution and treat any results as preliminary only.
            </p>
          </div>
        </div>

        {confirmed && (
          <div className="bg-yellow-500/10 border border-yellow-700 rounded p-3 mb-4 text-xs text-yellow-300">
            Are you sure? This action will be recorded in the validation report and your
            final score will be capped to reflect the skipped stage.
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" loading={loading} onClick={handleSkip}>
            {confirmed ? 'Confirm skip' : 'Skip this stage'}
          </Button>
        </div>
      </div>
    </div>
  )
}
