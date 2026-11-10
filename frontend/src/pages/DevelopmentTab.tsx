import { useState } from 'react'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { useRunDevelopment } from '../hooks/usePipeline'
import { useJobPoller } from '../hooks/useJobPoller'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

interface WFResult {
  walk_forward: {
    consistency_score: number
    folds: Array<{
      fold_num: number
      metrics: { sharpe_ratio: number; max_drawdown: number }
    }>
  }
  insample_metrics: Record<string, number>
  sensitivity: {
    overall_fragile: boolean
    fragility_reasons: string[]
    params: Array<{
      param_name: string
      is_fragile: boolean
      shifts: Record<string, number>
    }>
  }
  equity_curve: number[]
  equity_dates: string[]
}

export function DevelopmentTab({ stage }: { stage: { status: string } }) {
  const { activeProjectId } = useAppStore()
  const [jobId, setJobId] = useState<string | null>(null)
  const run = useRunDevelopment(activeProjectId!)

  const job = useJobPoller(activeProjectId!, 'development', jobId)
  const result = job.result as WFResult | null

  const isLocked = stage?.status === 'complete' || stage?.status === 'skipped'

  async function handleRun() {
    const { data } = await run.mutateAsync() as any
    setJobId(data?.job_id ?? null)
  }

  const equityData = result?.equity_curve?.map((v, i) => ({
    date: result.equity_dates?.[i]?.slice(0, 10),
    equity: parseFloat(v.toFixed(4)),
  })) ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Development (In-Sample)</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Walk-forward analysis and parameter sensitivity on training data only.
          </p>
        </div>
        {!isLocked && !jobId && (
          <Button size="sm" onClick={handleRun} loading={run.isPending}>
            Run development
          </Button>
        )}
        {isLocked && <Badge variant="success">Complete</Badge>}
      </div>

      {job.status === 'pending' || job.status === 'running' ? (
        <Card className="flex items-center gap-3 py-6">
          <Spinner />
          <div>
            <div className="text-xs text-slate-300">Running walk-forward analysis…</div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Running {5} expanding folds on training data
            </div>
          </div>
        </Card>
      ) : null}

      {job.status === 'failed' && (
        <Card className="border-red-900">
          <div className="text-xs text-red-400">{job.error}</div>
        </Card>
      )}

      {result && (
        <>
          {/* Equity curve */}
          {equityData.length > 0 && (
            <Card title="In-Sample Equity Curve">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={equityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#13131f', border: '1px solid #1e1e2e', fontSize: 11 }}
                    formatter={(v: any) => [v.toFixed(4), 'NAV']}
                  />
                  <Line
                    type="monotone"
                    dataKey="equity"
                    stroke="#6366f1"
                    dot={false}
                    strokeWidth={1.5}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(result.insample_metrics ?? {}).map(([k, v]) => (
              <Card key={k}>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wide">{k.replace(/_/g, ' ')}</div>
                <div className="text-sm font-semibold text-white font-mono">
                  {typeof v === 'number' ? v.toFixed(3) : v}
                </div>
              </Card>
            ))}
          </div>

          {/* Walk-forward folds */}
          <Card title="Walk-Forward Folds">
            <div className="mb-2 flex gap-3 text-xs">
              <span className="text-slate-500">Consistency score:</span>
              <span
                className={
                  result.walk_forward.consistency_score >= 0.6
                    ? 'text-green-400'
                    : 'text-yellow-400'
                }
              >
                {(result.walk_forward.consistency_score * 100).toFixed(0)}%
              </span>
            </div>
            <div className="space-y-1">
              {result.walk_forward.folds?.map((f) => (
                <div
                  key={f.fold_num}
                  className="flex items-center gap-4 text-xs font-mono py-1 border-b border-[#1e1e2e] last:border-0"
                >
                  <span className="text-slate-500 w-10">F{f.fold_num}</span>
                  <span
                    className={
                      f.metrics.sharpe_ratio > 0 ? 'text-green-400' : 'text-red-400'
                    }
                  >
                    SR {f.metrics.sharpe_ratio?.toFixed(2)}
                  </span>
                  <span className="text-slate-500">
                    DD {(f.metrics.max_drawdown * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </Card>

          {/* Sensitivity */}
          <Card
            title="Parameter Sensitivity"
            actions={
              result.sensitivity.overall_fragile ? (
                <Badge variant="danger">Fragile</Badge>
              ) : (
                <Badge variant="success">Robust</Badge>
              )
            }
          >
            {result.sensitivity.fragility_reasons?.length > 0 && (
              <div className="mb-3 space-y-1">
                {result.sensitivity.fragility_reasons.map((r, i) => (
                  <div key={i} className="text-xs text-yellow-400 bg-yellow-500/10 rounded px-2 py-1">
                    {r}
                  </div>
                ))}
              </div>
            )}
            <div className="space-y-2">
              {result.sensitivity.params?.map((p) => (
                <div key={p.param_name}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-slate-300">{p.param_name}</span>
                    {p.is_fragile && <Badge variant="warning">fragile</Badge>}
                  </div>
                  <div className="flex gap-1 flex-wrap">
                    {Object.entries(p.shifts ?? {}).map(([shift, sr]) => (
                      <span
                        key={shift}
                        className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                          (sr as number) > 0
                            ? 'bg-green-500/10 text-green-400'
                            : 'bg-red-500/10 text-red-400'
                        }`}
                      >
                        {shift}: {(sr as number).toFixed(2)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
