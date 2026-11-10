import { useState } from 'react'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { useRunValidation } from '../hooks/usePipeline'
import { useJobPoller } from '../hooks/useJobPoller'
import { reportsApi } from '../lib/api'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

export function ValidationTab({ stage }: { stage: { status: string } }) {
  const { activeProjectId } = useAppStore()
  const [jobId, setJobId] = useState<string | null>(null)
  const run = useRunValidation(activeProjectId!)
  const job = useJobPoller(activeProjectId!, 'validation', jobId)

  const reportQuery = useQuery({
    queryKey: ['report', activeProjectId],
    queryFn: () => reportsApi.get(activeProjectId!).then((r) => r.data),
    enabled: !!activeProjectId && stage?.status === 'complete',
  })

  const isOosConsumed = stage?.status === 'complete' || stage?.status === 'skipped'

  async function handleRun() {
    const { data } = await run.mutateAsync() as any
    setJobId(data?.job_id ?? null)
  }

  const report = reportQuery.data
  const findings = report?.findings

  const equityData = findings?.equity_curve?.map((v: number, i: number) => ({
    date: findings.equity_dates?.[i]?.slice(0, 10),
    equity: parseFloat(v.toFixed(4)),
  })) ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Out-of-Sample Validation</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            One-time test on the locked data. This action cannot be undone.
          </p>
        </div>
        {!isOosConsumed && (
          <Button size="sm" variant="primary" onClick={handleRun} loading={run.isPending}>
            Run OOS validation
          </Button>
        )}
        {isOosConsumed && <Badge variant="success">OOS consumed</Badge>}
      </div>

      {!isOosConsumed && !jobId && (
        <Card className="border-yellow-900/50 bg-yellow-500/5">
          <p className="text-xs text-yellow-300 leading-relaxed">
            <strong>This is a one-time operation.</strong> Once you run OOS validation,
            the test set is locked — you will never be able to test on this data again.
            Only proceed when you are satisfied with your in-sample development results.
          </p>
        </Card>
      )}

      {(job.status === 'pending' || job.status === 'running') && (
        <Card className="flex items-center gap-3 py-6">
          <Spinner />
          <div>
            <div className="text-xs text-slate-300">Running OOS validation battery…</div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Permutation test (1,000) · Bootstrap CI · Monte Carlo (10,000 paths) · Deflated Sharpe
            </div>
          </div>
        </Card>
      )}

      {job.status === 'failed' && (
        <Card className="border-red-900">
          <div className="text-xs text-red-400">{job.error}</div>
        </Card>
      )}

      {report && (
        <>
          {/* Score */}
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-slate-500 mb-1">Validation Score</div>
                <div className="text-4xl font-bold font-mono text-white">
                  {report.score}
                  <span className="text-lg text-slate-500">/100</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs font-mono">
                {Object.entries(report.score_breakdown ?? {})
                  .filter(([k]) => !['total', 'raw_total', 'cap_applied'].includes(k))
                  .map(([k, v]) => (
                    <div key={k}>
                      <div className="text-slate-500 text-[10px]">{k.replace(/_/g, ' ')}</div>
                      <div className="text-white">{(v as number).toFixed(1)}</div>
                    </div>
                  ))}
              </div>
            </div>
            {report.score_breakdown?.cap_applied && (
              <div className="mt-3 text-xs text-yellow-400 bg-yellow-500/10 rounded px-2 py-1.5">
                Score capped due to skipped stages. Strategy is not fully validated.
              </div>
            )}
          </Card>

          {/* OOS metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(findings?.oos_metrics ?? {}).map(([k, v]) => (
              <Card key={k}>
                <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wide">
                  {k.replace(/_/g, ' ')}
                </div>
                <div className="text-sm font-semibold text-white font-mono">
                  {typeof v === 'number' ? v.toFixed(3) : String(v)}
                </div>
              </Card>
            ))}
          </div>

          {/* OOS equity curve */}
          {equityData.length > 0 && (
            <Card title="OOS Equity Curve">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={equityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#13131f', border: '1px solid #1e1e2e', fontSize: 11 }}
                    formatter={(v: any) => [v.toFixed(4), 'NAV']}
                  />
                  <Line type="monotone" dataKey="equity" stroke="#22c55e" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Significance tests */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Permutation Test">
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-500">p-value</span>
                  <span className={findings?.permutation?.p_value < 0.05 ? 'text-green-400' : 'text-red-400'}>
                    {findings?.permutation?.p_value?.toFixed(4)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Significant</span>
                  <Badge variant={findings?.permutation?.is_significant ? 'success' : 'danger'}>
                    {findings?.permutation?.is_significant ? 'Yes' : 'No'}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Real Sharpe</span>
                  <span className="text-white">{findings?.permutation?.real_sharpe?.toFixed(3)}</span>
                </div>
              </div>
            </Card>

            <Card title="Deflated Sharpe">
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-500">DSR probability</span>
                  <span className={findings?.deflated_sharpe_ratio > 0.95 ? 'text-green-400' : 'text-yellow-400'}>
                    {(findings?.deflated_sharpe_ratio * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Trials (versions)</span>
                  <span className="text-white">{findings?.n_trials}</span>
                </div>
              </div>
            </Card>

            <Card title="Monte Carlo (10k paths)">
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-500">P(profit)</span>
                  <span className="text-green-400">
                    {(findings?.monte_carlo?.prob_profit * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">P(ruin)</span>
                  <span className={findings?.monte_carlo?.prob_ruin > 0.1 ? 'text-red-400' : 'text-slate-300'}>
                    {(findings?.monte_carlo?.prob_ruin * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </Card>

            <Card title="Bootstrap CI (Sharpe)">
              <div className="space-y-2 text-xs font-mono">
                {Object.entries(findings?.bootstrap_ci?.sharpe_ratio ?? {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-slate-500">{k}</span>
                    <span className="text-white">{(v as number).toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Skipped stages warning */}
          {report.skipped_stages?.length > 0 && (
            <Card className="border-yellow-900/50 bg-yellow-500/5">
              <div className="text-xs text-yellow-300">
                <strong>Note:</strong> Stages {report.skipped_stages.join(', ')} were skipped.
                This strategy is not fully validated and you should proceed with caution.
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
