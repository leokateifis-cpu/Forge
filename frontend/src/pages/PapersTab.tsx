import { useState } from 'react'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { papersApi } from '../lib/api'

interface PaperResult {
  title: string
  arxiv_id: string
  published: string
  abstract: string
  signal_description: string
  relevance_score: number
  confirmed: boolean
  suggested_application: string
  can_load_to_hypothesis: boolean
  test_result: {
    passed: boolean
    sharpe_ratio?: number
    permutation_p_value?: number
    is_significant?: boolean
    error?: string
  }
}

export function PapersTab() {
  const [query, setQuery] = useState('')
  const [polling, setPolling] = useState(false)
  const [results, setResults] = useState<PaperResult[]>([])
  const [error, setError] = useState<string | null>(null)

  async function handleSearch() {
    if (!query.trim()) return
    setError(null)
    setResults([])
    setPolling(true)
    try {
      const { data } = await papersApi.search(query)
      const id: string = data.task_id

      // Poll for results
      let attempts = 0
      const interval = setInterval(async () => {
        attempts++
        if (attempts > 60) {
          clearInterval(interval)
          setPolling(false)
          setError('Search timed out. Please try again.')
          return
        }
        const { data: job } = await papersApi.jobStatus(id)
        if (job.status === 'success') {
          clearInterval(interval)
          setPolling(false)
          setResults(job.results?.papers ?? [])
        } else if (job.status === 'failed') {
          clearInterval(interval)
          setPolling(false)
          setError(job.error ?? 'Search failed')
        }
      }, 3000)
    } catch (e: any) {
      setPolling(false)
      setError(e.message)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">Research Paper Terminal</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Search academic papers and test their strategies on ES/NQ data.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="e.g. momentum strategies in futures markets"
          className="flex-1 bg-[#13131f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
        />
        <Button size="sm" onClick={handleSearch} loading={polling} disabled={!query.trim()}>
          Search
        </Button>
      </div>

      {polling && (
        <Card className="flex items-center gap-3 py-5">
          <Spinner />
          <div>
            <div className="text-xs text-slate-300">Searching arXiv and testing strategies…</div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Fetching papers → extracting signals → running quick backtests
            </div>
          </div>
        </Card>
      )}

      {error && (
        <Card className="border-red-900">
          <div className="text-xs text-red-400">{error}</div>
        </Card>
      )}

      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((paper) => (
            <Card
              key={paper.arxiv_id}
              actions={
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-500">
                    relevance {paper.relevance_score}%
                  </span>
                  <Badge variant={paper.confirmed ? 'success' : 'muted'}>
                    {paper.confirmed ? '✓ signal confirmed' : 'signal not confirmed'}
                  </Badge>
                </div>
              }
            >
              <div className="mb-2">
                <div className="text-sm font-medium text-slate-200 leading-snug mb-1">
                  {paper.title}
                </div>
                <div className="text-[10px] text-slate-500">{paper.published}</div>
              </div>

              <div className="text-xs text-slate-400 leading-relaxed mb-3">
                {paper.abstract}
              </div>

              <div className="bg-indigo-500/5 border border-indigo-900/50 rounded p-3 mb-3">
                <div className="text-[10px] text-indigo-400 uppercase mb-1 tracking-wide">
                  Extracted Signal
                </div>
                <div className="text-xs text-slate-300 leading-relaxed">
                  {paper.signal_description}
                </div>
              </div>

              {paper.test_result && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 text-xs font-mono">
                  {paper.test_result.sharpe_ratio !== undefined && (
                    <div>
                      <div className="text-slate-500 text-[10px]">Sharpe (ES daily)</div>
                      <div className={paper.test_result.sharpe_ratio > 0.3 ? 'text-green-400' : 'text-red-400'}>
                        {paper.test_result.sharpe_ratio.toFixed(3)}
                      </div>
                    </div>
                  )}
                  {paper.test_result.permutation_p_value !== undefined && (
                    <div>
                      <div className="text-slate-500 text-[10px]">p-value</div>
                      <div className={paper.test_result.permutation_p_value < 0.05 ? 'text-green-400' : 'text-yellow-400'}>
                        {paper.test_result.permutation_p_value.toFixed(4)}
                      </div>
                    </div>
                  )}
                  {paper.test_result.error && (
                    <div className="col-span-2 text-red-400 text-xs">
                      Test error: {paper.test_result.error}
                    </div>
                  )}
                </div>
              )}

              <div className="text-[10px] text-slate-500 italic mb-3">
                {paper.suggested_application}
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={paper.arxiv_id}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  View on arXiv →
                </a>
                {paper.can_load_to_hypothesis && (
                  <Badge variant="info" className="cursor-pointer">
                    Load as hypothesis →
                  </Badge>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {results.length === 0 && !polling && !error && (
        <Card className="text-center py-8">
          <p className="text-xs text-slate-500">Search for papers to test their strategies.</p>
          <p className="text-xs text-slate-600 mt-1">
            Results are tested against 2 years of ES daily data with a permutation test.
          </p>
        </Card>
      )}
    </div>
  )
}
