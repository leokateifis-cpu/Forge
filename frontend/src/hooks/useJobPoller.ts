import { useState, useEffect, useRef } from 'react'
import { pipelineApi } from '../lib/api'

type JobStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed'

interface JobResult {
  status: JobStatus
  result: unknown
  error: string | null
}

export function useJobPoller(
  projectId: string,
  jobType: 'development' | 'validation',
  jobId: string | null
): JobResult {
  const [status, setStatus] = useState<JobStatus>('idle')
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return

    setStatus('pending')

    const poll = async () => {
      try {
        const fetcher =
          jobType === 'development'
            ? pipelineApi.devJobStatus(projectId, jobId)
            : pipelineApi.validationJobStatus(projectId, jobId)
        const { data } = await fetcher
        if (data.status === 'success') {
          setStatus('success')
          setResult(data.result)
          if (intervalRef.current) clearInterval(intervalRef.current)
        } else if (data.status === 'failed') {
          setStatus('failed')
          setError(data.error || 'Job failed')
          if (intervalRef.current) clearInterval(intervalRef.current)
        } else {
          setStatus('running')
        }
      } catch (e) {
        setStatus('failed')
        setError(String(e))
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 3000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [jobId, projectId, jobType])

  return { status, result, error }
}
