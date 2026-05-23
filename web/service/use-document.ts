import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import { knowledgeBaseKeys } from './use-knowledge-base'
import type { Document, Slice, SyncLog } from '@/models/document'
import type { PaginatedResponse } from '@/models/common'

const NS = 'documents'

export const documentKeys = {
  all: [NS] as const,
  lists: () => [...documentKeys.all, 'list'] as const,
  list: (kbId: number, params?: Record<string, unknown>) =>
    [...documentKeys.lists(), kbId, params] as const,
  details: () => [...documentKeys.all, 'detail'] as const,
  detail: (kbId: number, docId: number) =>
    [...documentKeys.details(), kbId, docId] as const,
  slices: (kbId: number, docId: number) =>
    [...documentKeys.all, 'slices', kbId, docId] as const,
  syncLogs: (kbId: number) => [...documentKeys.all, 'sync-logs', kbId] as const,
}

export const useDocuments = (
  kbId: number,
  params?: { page?: number; per_page?: number }
) =>
  useQuery({
    queryKey: documentKeys.list(kbId, params),
    queryFn: () =>
      get<PaginatedResponse<Document>>(
        `v1/knowledge-bases/${kbId}/documents`,
        { searchParams: params }
      ),
    enabled: !!kbId,
  })

export const useDocument = (kbId: number, docId: number) =>
  useQuery({
    queryKey: documentKeys.detail(kbId, docId),
    queryFn: () =>
      get<Document>(`v1/knowledge-bases/${kbId}/documents/${docId}`),
    enabled: !!kbId && !!docId,
  })

export const useSlices = (
  kbId: number,
  docId: number,
  params?: { page?: number; per_page?: number }
) =>
  useQuery({
    queryKey: documentKeys.slices(kbId, docId),
    queryFn: () =>
      get<PaginatedResponse<Slice>>(
        `v1/knowledge-bases/${kbId}/documents/${docId}/slices`,
        { searchParams: params }
      ),
    enabled: !!kbId && !!docId,
  })

export const useSyncLogs = (kbId: number) =>
  useQuery({
    queryKey: documentKeys.syncLogs(kbId),
    queryFn: () =>
      get<PaginatedResponse<SyncLog>>(
        `v1/knowledge-bases/${kbId}/sync-logs`
      ),
    enabled: !!kbId,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some((log) => log.status === 'running') ? 5000 : false
    },
  })

export type SyncMode = 'auto' | 'full'

export const useTriggerSync = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kbId, syncMode = 'auto' }: { kbId: number; syncMode?: SyncMode }) =>
      post<Record<string, unknown>>(
        `v1/knowledge-bases/${kbId}/sync`,
        { json: { sync_mode: syncMode } }
      ),
    onSuccess: (_, { kbId }) => {
      qc.invalidateQueries({ queryKey: documentKeys.syncLogs(kbId) })
      qc.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

export const useCancelSync = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      kbId,
      syncLogId,
    }: {
      kbId: number
      syncLogId?: number
    }) =>
      post<{ sync_log_id: number; status: string }>(
        `v1/knowledge-bases/${kbId}/sync/cancel`,
        {
          searchParams: syncLogId ? { sync_log_id: syncLogId } : undefined,
        },
      ),
    onSuccess: (_, { kbId }) => {
      qc.invalidateQueries({ queryKey: documentKeys.syncLogs(kbId) })
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.detail(kbId) })
      qc.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}
