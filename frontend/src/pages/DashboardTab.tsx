import { useAppStore } from '../store'
import { Card } from '../components/ui/Card'
import { reportsApi } from '../lib/api'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'

const STAGE_LABELS: Record<number, string> = {
  1: 'Hypothesis',
  2: 'Code',
  3: 'Data Split',
  4: 'Development',
  5: 'Validation',
  6: 'Done',
}

export function DashboardTab() {
  const { activeProjectId, activeProject } = useAppStore()

  const reportQuery = useQuery({
    queryKey: ['report', activeProjectId],
    queryFn: () => reportsApi.get(activeProjectId!).then((r) => r.data),
    enabled: !!activeProjectId && (activeProject?.current_stage ?? 0) >= 6,
  })

  const report = reportQuery.data
  const findings = report?.findings

  const equityData = findings?.equity_curve?.map((v: number, i: number) => ({
    date: findings.equity_dates?.[i]?.slice(0, 10),
    equity: parseFloat(v.toFixed(4)),
  })) ?? []

  // Compute monthly returns from equity curve
  const monthlyReturns = computeMonthlyReturns(
    findings?.equity_curve ?? [],
    findings?.equity_dates ?? []
  )

  if (!activeProjectId) {
    return (
      <Card className="text-center py-8">
        <p className="text-xs text-slate-500">Select a project to view the dashboard.</p>
      </Card>
    )
  }

  if (!report) {
    return (
      <Card className="text-center py-8">
        <p className="text-xs text-slate-500">
          Dashboard available after completing OOS validation (Stage 5).
        </p>
        {activeProject && (
          <p className="text-xs text-slate-600 mt-1">
            Current stage: {STAGE_LABELS[activeProject.current_stage] ?? activeProject.current_stage}
          </p>
        )}
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">{activeProject?.name}</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {activeProject?.instrument} · {activeProject?.timeframe}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold font-mono text-white">{report.score}</span>
          <span className="text-sm text-slate-500">/100</span>
        </div>
      </div>

      {/* OOS Equity */}
      {equityData.length > 0 && (
        <Card title="OOS Equity Curve">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={equityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#13131f', border: '1px solid #1e1e2e', fontSize: 11 }}
                formatter={(v: any) => [v.toFixed(4), 'NAV']}
              />
              <ReferenceLine y={1} stroke="#1e1e2e" />
              <Line type="monotone" dataKey="equity" stroke="#6366f1" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Sharpe', key: 'sharpe_ratio', decimals: 3, colorFn: (v: number) => v > 1 ? 'text-green-400' : v > 0.5 ? 'text-yellow-400' : 'text-red-400' },
          { label: 'Max DD', key: 'max_drawdown', decimals: 1, pct: true, colorFn: (v: number) => v < -0.2 ? 'text-red-400' : 'text-yellow-400' },
          { label: 'Calmar', key: 'calmar_ratio', decimals: 2, colorFn: (v: number) => v > 1 ? 'text-green-400' : 'text-slate-300' },
          { label: 'Win Rate', key: 'win_rate', decimals: 1, pct: true, colorFn: () => 'text-slate-200' },
        ].map(({ label, key, decimals, pct, colorFn }) => {
          const v = findings?.oos_metrics?.[key] ?? null
          return (
            <Card key={key}>
              <div className="text-[10px] text-slate-500 mb-1">{label}</div>
              <div className={`text-sm font-semibold font-mono ${colorFn(v)}`}>
                {v !== null
                  ? pct
                    ? `${(v * 100).toFixed(decimals)}%`
                    : v.toFixed(decimals)
                  : '—'}
              </div>
            </Card>
          )
        })}
      </div>

      {/* Monthly heatmap */}
      {monthlyReturns.length > 0 && (
        <Card title="Monthly Returns">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={monthlyReturns} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="month" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <Tooltip
                contentStyle={{ background: '#13131f', border: '1px solid #1e1e2e', fontSize: 11 }}
                formatter={(v: any) => [`${(v * 100).toFixed(2)}%`, 'Return']}
              />
              <ReferenceLine y={0} stroke="#6b7280" />
              <Bar
                dataKey="return"
                radius={[2, 2, 0, 0]}
                fill="#6366f1"
              />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Score breakdown */}
      <Card title="Score Breakdown">
        <div className="space-y-2">
          {[
            { label: 'Statistical significance', key: 'significance', max: 30 },
            { label: 'OOS performance', key: 'oos_performance', max: 25 },
            { label: 'OOS vs in-sample', key: 'oos_vs_insample', max: 15 },
            { label: 'Robustness', key: 'robustness', max: 15 },
            { label: 'Risk profile', key: 'risk', max: 15 },
          ].map(({ label, key, max }) => {
            const v = report.score_breakdown?.[key] ?? 0
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-slate-400">{label}</span>
                  <span className="font-mono text-white">{v.toFixed(1)} / {max}</span>
                </div>
                <div className="h-1.5 bg-[#1e1e2e] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 rounded-full transition-all"
                    style={{ width: `${(v / max) * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* Skipped stages */}
      {report.skipped_stages?.length > 0 && (
        <Card className="border-yellow-900/50 bg-yellow-500/5">
          <div className="text-xs text-yellow-300">
            Stages {report.skipped_stages.map((s: number) => STAGE_LABELS[s]).join(', ')} were
            skipped. This strategy is not fully validated and you should proceed with caution.
          </div>
        </Card>
      )}
    </div>
  )
}

function computeMonthlyReturns(equity: number[], dates: string[]) {
  if (!equity.length || !dates.length) return []
  const monthly: Record<string, { start: number; end: number }> = {}
  for (let i = 0; i < dates.length; i++) {
    const month = dates[i]?.slice(0, 7)
    if (!month) continue
    if (!monthly[month]) monthly[month] = { start: equity[i], end: equity[i] }
    monthly[month].end = equity[i]
  }
  return Object.entries(monthly).map(([month, { start, end }]) => ({
    month: month.slice(2),
    return: start > 0 ? (end - start) / start : 0,
  }))
}
