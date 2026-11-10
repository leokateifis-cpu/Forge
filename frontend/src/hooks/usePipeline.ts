import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { pipelineApi } from '../lib/api'

export function usePipelineStatus(projectId: string | null) {
  return useQuery({
    queryKey: ['pipeline', projectId],
    queryFn: () => pipelineApi.status(projectId!).then((r) => r.data),
    enabled: !!projectId,
    refetchInterval: 5000,
  })
}

export function useSkipWarning(projectId: string | null, stage: number) {
  return useQuery({
    queryKey: ['skip-warning', projectId, stage],
    queryFn: () => pipelineApi.skipWarning(projectId!, stage).then((r) => r.data),
    enabled: !!projectId,
  })
}

export function useGenerateCode(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => pipelineApi.generateCode(projectId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline', projectId] }),
  })
}

export function useScanCode(projectId: string) {
  return useMutation({
    mutationFn: (versionId: string) =>
      pipelineApi.scanCode(projectId, versionId).then((r) => r.data),
  })
}

export function useActivateCode(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (versionId: string) =>
      pipelineApi.activateCode(projectId, versionId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline', projectId] }),
  })
}

export function useSplitRecommendation(projectId: string | null) {
  return useQuery({
    queryKey: ['split', projectId],
    queryFn: () => pipelineApi.splitRecommendation(projectId!).then((r) => r.data),
    enabled: !!projectId,
  })
}

export function useLockSplit(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: object) =>
      pipelineApi.lockSplit(projectId, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline', projectId] }),
  })
}

export function useRunDevelopment(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => pipelineApi.runDevelopment(projectId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline', projectId] }),
  })
}

export function useRunValidation(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => pipelineApi.runValidation(projectId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline', projectId] }),
  })
}
