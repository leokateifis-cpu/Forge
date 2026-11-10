import { useState } from 'react'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { accountApi } from '../lib/api'
import { useQuery, useMutation } from '@tanstack/react-query'

export function AccountSetupTab() {
  const { activeProjectId, user } = useAppStore()
  const [accountType, setAccountType] = useState<'prop_firm' | 'live' | null>(
    (user?.account_type as any) ?? null
  )
  const [accountSize, setAccountSize] = useState('')
  const [rankings, setRankings] = useState<any[]>([])
  const [kellyTable, setKellyTable] = useState<any[]>([])

  const propFirmsQuery = useQuery({
    queryKey: ['prop-firms'],
    queryFn: () => accountApi.propFirms().then((r) => r.data),
  })

  const rankMutation = useMutation({
    mutationFn: () => accountApi.rankPropFirms(activeProjectId!).then((r) => r.data),
    onSuccess: (data) => setRankings(data),
  })

  const kellyMutation = useMutation({
    mutationFn: () =>
      accountApi.kellyTable(activeProjectId!, parseFloat(accountSize)).then((r) => r.data),
    onSuccess: (data) => setKellyTable(data),
  })

  const setTypeMutation = useMutation({
    mutationFn: (type: 'prop_firm' | 'live') => accountApi.setAccountType(type),
    onSuccess: (_, type) => setAccountType(type),
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-white">Account Setup</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Configure your trading account context. Analysis requires a validated strategy.
        </p>
      </div>

      {/* Account type */}
      <Card title="Account Type">
        <div className="flex gap-3">
          {(['prop_firm', 'live'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeMutation.mutate(t)}
              className={`flex-1 py-3 rounded border text-xs font-mono transition-colors ${
                accountType === t
                  ? 'border-indigo-600 bg-indigo-600/20 text-indigo-300'
                  : 'border-[#1e1e2e] text-slate-400 hover:border-slate-600'
              }`}
            >
              {t === 'prop_firm' ? 'Prop Firm' : 'Live Account'}
            </button>
          ))}
        </div>
      </Card>

      {/* Prop firm section */}
      {(accountType === 'prop_firm' || !accountType) && (
        <div className="space-y-4">
          <Card
            title="Prop Firm Comparison"
            actions={
              <Button
                size="sm"
                onClick={() => rankMutation.mutate()}
                loading={rankMutation.isPending}
                disabled={!activeProjectId}
              >
                Rank by EV
              </Button>
            }
          >
            {!activeProjectId && (
              <p className="text-xs text-slate-500">Select a validated project to rank prop firms by expected value.</p>
            )}

            {propFirmsQuery.data && rankings.length === 0 && (
              <div className="space-y-2">
                {propFirmsQuery.data.map((f: any) => (
                  <div key={f.firm} className="flex items-center justify-between py-2 border-b border-[#1e1e2e] last:border-0">
                    <span className="text-xs font-mono text-slate-300">{f.firm}</span>
                    <div className="flex gap-3 text-[10px] text-slate-500 font-mono">
                      <span>Max DD {(f.trailing_drawdown_pct * 100).toFixed(0)}%</span>
                      <span>Target {(f.profit_target_pct * 100).toFixed(0)}%</span>
                      <span>Fee ${f.evaluation_fee.toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {rankings.length > 0 && (
              <div className="space-y-2">
                {rankings.slice(0, 10).map((r, i) => (
                  <div
                    key={`${r.firm}-${r.account_size}`}
                    className="flex items-center gap-3 py-2 border-b border-[#1e1e2e] last:border-0"
                  >
                    <span className="text-xs text-slate-500 w-5">#{i + 1}</span>
                    <div className="flex-1">
                      <div className="text-xs font-mono text-slate-200">{r.firm}</div>
                      <div className="text-[10px] text-slate-500">${r.account_size.toLocaleString()}</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-xs font-mono font-semibold ${r.ev > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        EV ${r.ev.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        P(pass) {(r.prob_pass * 100).toFixed(1)}%
                      </div>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 font-mono">
                      {(r.optimal_risk_pct * 100).toFixed(1)}% risk
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Live account section */}
      {accountType === 'live' && (
        <Card title="Kelly Risk Table">
          <div className="flex gap-3 mb-4">
            <input
              type="number"
              placeholder="Account size ($)"
              value={accountSize}
              onChange={(e) => setAccountSize(e.target.value)}
              className="flex-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
            />
            <Button
              size="sm"
              onClick={() => kellyMutation.mutate()}
              loading={kellyMutation.isPending}
              disabled={!activeProjectId || !accountSize}
            >
              Compute
            </Button>
          </div>

          {kellyTable.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-slate-500 text-left">
                    <th className="pb-2">Risk %</th>
                    <th className="pb-2">Risk $</th>
                    <th className="pb-2">Exp. annual return</th>
                    <th className="pb-2">Exp. max DD</th>
                    <th className="pb-2">P(ruin)</th>
                    <th className="pb-2">Kelly</th>
                  </tr>
                </thead>
                <tbody>
                  {kellyTable.map((row) => (
                    <tr
                      key={row.risk_pct}
                      className="border-t border-[#1e1e2e] hover:bg-white/2"
                    >
                      <td className="py-1.5 text-slate-300">{(row.risk_pct * 100).toFixed(1)}%</td>
                      <td className="py-1.5">${row.risk_dollars.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td className={`py-1.5 ${row.expected_annual_return_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {(row.expected_annual_return_pct * 100).toFixed(1)}%
                      </td>
                      <td className="py-1.5 text-yellow-400">
                        {(row.expected_max_drawdown_pct * 100).toFixed(1)}%
                      </td>
                      <td className={`py-1.5 ${row.prob_ruin > 0.1 ? 'text-red-400' : 'text-slate-400'}`}>
                        {(row.prob_ruin * 100).toFixed(1)}%
                      </td>
                      <td className="py-1.5 text-slate-400">{row.kelly_fraction.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
