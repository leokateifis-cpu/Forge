import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { useSplitRecommendation, useLockSplit } from '../hooks/usePipeline'

export function DataSplitTab({ stage }: { stage: { status: string } }) {
  const { activeProjectId } = useAppStore()
  const rec = useSplitRecommendation(activeProjectId)
  const lock = useLockSplit(activeProjectId!)

  const split = rec.data
  const isLocked = stage?.status === 'complete' || stage?.status === 'skipped'

  async function handleLock() {
    if (!split) return
    await lock.mutateAsync({
      train_start: split.train_start,
      train_end: split.train_end,
      test_start: split.test_start,
      test_end: split.test_end,
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Data Split</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Forge recommends a train/test split based on minimum training ratio theory.
            The test set is locked away — you will only see it once during Stage 5 OOS validation.
          </p>
        </div>
        {isLocked && <Badge variant="success">Locked</Badge>}
      </div>

      {rec.isLoading && (
        <Card className="flex items-center gap-3 py-6">
          <Spinner />
          <span className="text-xs text-slate-400">Computing recommended split…</span>
        </Card>
      )}

      {split && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card title="Training Set" className="border-green-900/50">
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-500">Start</span>
                <span className="text-green-400">{split.train_start}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">End</span>
                <span className="text-green-400">{split.train_end}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Bars</span>
                <span className="text-green-400">{split.train_bars?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Fraction</span>
                <span className="text-green-400">{(split.train_fraction * 100).toFixed(1)}%</span>
              </div>
            </div>
          </Card>

          <Card title="Test Set (locked)" className="border-red-900/50">
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-500">Start</span>
                <span className="text-red-400">{split.test_start}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">End</span>
                <span className="text-red-400">{split.test_end}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Bars</span>
                <span className="text-red-400">{split.test_bars?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Fraction</span>
                <span className="text-red-400">{(split.test_fraction * 100).toFixed(1)}%</span>
              </div>
            </div>
            <div className="mt-3 text-[10px] text-slate-600 leading-relaxed">
              You will not see this data until OOS validation. Any access before then would
              invalidate your results.
            </div>
          </Card>

          {split.mtr_info && (
            <Card title="MTR Analysis" className="md:col-span-2">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                <div>
                  <div className="text-slate-500 mb-1">Sharpe estimate</div>
                  <div className="text-white">{split.mtr_info.expected_sharpe?.toFixed(2) ?? '—'}</div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Recommended train %</div>
                  <div className="text-white">{(split.train_fraction * 100).toFixed(0)}%</div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Min train bars</div>
                  <div className="text-white">{split.mtr_info.min_train_bars}</div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Min test bars</div>
                  <div className="text-white">{split.mtr_info.min_test_bars}</div>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {!isLocked && split && (
        <div className="flex justify-end">
          <Button onClick={handleLock} loading={lock.isPending}>
            Lock split &amp; advance to Development
          </Button>
        </div>
      )}
    </div>
  )
}
