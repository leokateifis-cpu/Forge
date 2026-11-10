import { useState } from 'react'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { useGenerateCode, useScanCode, useActivateCode } from '../hooks/usePipeline'
import { pipelineApi } from '../lib/api'
import { useQuery } from '@tanstack/react-query'

interface ScanFinding {
  rule: string
  message: string
  line?: number
}

interface Version {
  id: string
  version_num: number
  is_active: boolean
  scan_passed: boolean | null
  scan_findings: ScanFinding[]
  source_code: string
  created_at: string
}

export function CodeTab({ stage }: { stage: { status: string } }) {
  const { activeProjectId } = useAppStore()
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [showCode, setShowCode] = useState(false)

  const versionsQuery = useQuery({
    queryKey: ['code-versions', activeProjectId],
    queryFn: () =>
      pipelineApi.listVersions(activeProjectId!).then((r) => r.data as Version[]),
    enabled: !!activeProjectId,
  })

  const generate = useGenerateCode(activeProjectId!)
  const scan = useScanCode(activeProjectId!)
  const activate = useActivateCode(activeProjectId!)

  const versions: Version[] = versionsQuery.data || []
  const selectedVersion = versions.find((v) => v.id === selectedVersionId) ?? versions[versions.length - 1]
  const isLocked = stage?.status === 'complete' || stage?.status === 'skipped'

  async function handleGenerate() {
    const result = await generate.mutateAsync()
    versionsQuery.refetch()
    setSelectedVersionId(result.id)
  }

  async function handleScan(versionId: string) {
    await scan.mutateAsync(versionId)
    versionsQuery.refetch()
  }

  async function handleActivate(versionId: string) {
    await activate.mutateAsync(versionId)
    versionsQuery.refetch()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Strategy Code</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Forge generates code from your hypothesis. Each iteration counts toward the multiple-testing correction.
          </p>
        </div>
        {!isLocked && (
          <Button size="sm" onClick={handleGenerate} loading={generate.isPending}>
            Generate v{versions.length + 1}
          </Button>
        )}
      </div>

      {versions.length === 0 && !generate.isPending && (
        <Card className="text-center py-8">
          <p className="text-xs text-slate-500">No code generated yet.</p>
          <p className="text-xs text-slate-600 mt-1">
            Complete the hypothesis interview first, then generate code.
          </p>
        </Card>
      )}

      {generate.isPending && (
        <Card className="flex items-center gap-3 py-6">
          <Spinner />
          <span className="text-xs text-slate-400">Generating strategy code…</span>
        </Card>
      )}

      {versions.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {/* Version selector */}
          <div className="flex gap-2 flex-wrap">
            {versions.map((v) => (
              <button
                key={v.id}
                onClick={() => setSelectedVersionId(v.id)}
                className={`text-xs px-2 py-1 rounded border font-mono transition-colors ${
                  selectedVersion?.id === v.id
                    ? 'border-indigo-600 bg-indigo-600/20 text-indigo-300'
                    : 'border-[#1e1e2e] text-slate-400 hover:border-slate-600'
                }`}
              >
                v{v.version_num}
                {v.is_active && <span className="ml-1 text-green-400">●</span>}
              </button>
            ))}
          </div>

          {selectedVersion && (
            <Card
              title={`v${selectedVersion.version_num}`}
              actions={
                <div className="flex gap-2 items-center">
                  {selectedVersion.scan_passed === null && !isLocked && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleScan(selectedVersion.id)}
                      loading={scan.isPending}
                    >
                      Scan for lookahead
                    </Button>
                  )}
                  {selectedVersion.scan_passed === true && !selectedVersion.is_active && !isLocked && (
                    <Button
                      size="sm"
                      onClick={() => handleActivate(selectedVersion.id)}
                      loading={activate.isPending}
                    >
                      Activate &amp; advance
                    </Button>
                  )}
                  {selectedVersion.scan_passed !== null && (
                    <Badge variant={selectedVersion.scan_passed ? 'success' : 'danger'}>
                      {selectedVersion.scan_passed ? 'Scan passed' : 'Scan failed'}
                    </Badge>
                  )}
                  {selectedVersion.is_active && <Badge variant="active">Active</Badge>}
                </div>
              }
            >
              {/* Scan findings */}
              {selectedVersion.scan_findings?.length > 0 && (
                <div className="mb-3 space-y-1">
                  {selectedVersion.scan_findings.map((f, i) => (
                    <div
                      key={i}
                      className="flex gap-2 text-xs bg-red-500/10 border border-red-900 rounded px-2 py-1.5"
                    >
                      <span className="text-red-400 shrink-0">✕</span>
                      <span className="text-red-300">
                        {f.rule}: {f.message}
                        {f.line ? ` (line ${f.line})` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Code viewer */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-500">Strategy source</span>
                <button
                  className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
                  onClick={() => setShowCode((v) => !v)}
                >
                  {showCode ? 'Hide' : 'Show'} code
                </button>
              </div>

              {showCode && (
                <pre className="bg-black/40 rounded p-3 text-xs text-slate-300 overflow-x-auto max-h-80 leading-relaxed font-mono">
                  {selectedVersion.source_code}
                </pre>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
