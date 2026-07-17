import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post, put } from '@/service/base'
import type { PaginatedResponse } from '@/models/common'
import type {
  KnowledgeBaseQa,
  KnowledgeBaseQaListParams,
  KnowledgeBaseQaPayload,
} from '@/models/knowledge-base-qa'

const NS = 'knowledge-base-qas'

export const knowledgeBaseQaKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (kbId: number, params: KnowledgeBaseQaListParams) =>
    [NS, 'list', kbId, params] as const,
  details: () => [NS, 'detail'] as const,
  detail: (kbId: number, qaId: number) => [NS, 'detail', kbId, qaId] as const,
}

function searchParams(params: KnowledgeBaseQaListParams) {
  const result: Record<string, string | number | boolean> = {}
  if (params.search) result.search = params.search
  if (params.enabled !== undefined) result.enabled = params.enabled
  if (params.process_status) result.process_status = params.process_status
  if (params.directory_id) result.directory_id = params.directory_id
  if (params.page) result.page = params.page
  if (params.per_page) result.per_page = params.per_page
  return result
}

export const useKnowledgeBaseQas = (
  kbId: number,
  params: KnowledgeBaseQaListParams,
  queryEnabled = true,
) =>
  useQuery({
    queryKey: knowledgeBaseQaKeys.list(kbId, params),
    queryFn: () =>
      get<PaginatedResponse<KnowledgeBaseQa>>(`v1/knowledge-bases/${kbId}/qas`, {
        searchParams: searchParams(params),
      }),
    enabled: !!kbId && queryEnabled,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.process_status === 'processing')
        ? 2000
        : false,
  })

export const useKnowledgeBaseQa = (kbId: number, qaId: number) =>
  useQuery({
    queryKey: knowledgeBaseQaKeys.detail(kbId, qaId),
    queryFn: () => get<KnowledgeBaseQa>(`v1/knowledge-bases/${kbId}/qas/${qaId}`),
    enabled: !!kbId && !!qaId,
    refetchInterval: (query) =>
      query.state.data?.process_status === 'processing' ? 2000 : false,
  })

function useInvalidateQa() {
  const qc = useQueryClient()
  return (kbId: number, qaId?: number) => {
    void qc.invalidateQueries({ queryKey: knowledgeBaseQaKeys.lists() })
    if (qaId) {
      void qc.invalidateQueries({ queryKey: knowledgeBaseQaKeys.detail(kbId, qaId) })
    }
    void qc.invalidateQueries({ queryKey: ['knowledge-base-qa-directories', 'list', kbId] })
  }
}

export const useCreateKnowledgeBaseQa = () => {
  const invalidate = useInvalidateQa()
  return useMutation({
    mutationFn: ({ kbId, data }: { kbId: number; data: KnowledgeBaseQaPayload }) =>
      post<KnowledgeBaseQa>(`v1/knowledge-bases/${kbId}/qas`, { json: data }),
    onSuccess: (item) => invalidate(item.knowledge_base_id, item.id),
  })
}

export const useUpdateKnowledgeBaseQa = () => {
  const invalidate = useInvalidateQa()
  return useMutation({
    mutationFn: ({ kbId, qaId, data }: { kbId: number; qaId: number; data: KnowledgeBaseQaPayload }) =>
      put<KnowledgeBaseQa>(`v1/knowledge-bases/${kbId}/qas/${qaId}`, { json: data }),
    onSuccess: (item) => invalidate(item.knowledge_base_id, item.id),
  })
}

export const useDeleteKnowledgeBaseQa = () => {
  const invalidate = useInvalidateQa()
  return useMutation({
    mutationFn: ({ kbId, qaId }: { kbId: number; qaId: number }) =>
      del(`v1/knowledge-bases/${kbId}/qas/${qaId}`),
    onSuccess: (_, values) => invalidate(values.kbId),
  })
}

export const useToggleKnowledgeBaseQa = () => {
  const invalidate = useInvalidateQa()
  return useMutation({
    mutationFn: ({ kbId, qaId }: { kbId: number; qaId: number }) =>
      patch<KnowledgeBaseQa>(`v1/knowledge-bases/${kbId}/qas/${qaId}/toggle`),
    onSuccess: (item) => invalidate(item.knowledge_base_id, item.id),
  })
}

export const useRetryKnowledgeBaseQa = () => {
  const invalidate = useInvalidateQa()
  return useMutation({
    mutationFn: ({ kbId, qaId }: { kbId: number; qaId: number }) =>
      post<KnowledgeBaseQa>(`v1/knowledge-bases/${kbId}/qas/${qaId}/retry`),
    onSuccess: (item) => invalidate(item.knowledge_base_id, item.id),
  })
}
