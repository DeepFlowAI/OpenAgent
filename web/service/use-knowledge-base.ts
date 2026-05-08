import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  KnowledgeBase,
  CreateKnowledgeBasePayload,
  UpdateKnowledgeBasePayload,
} from '@/models/knowledge-base'
import type { PaginatedResponse } from '@/models/common'

const NS = 'knowledge-bases'

export const knowledgeBaseKeys = {
  all: [NS] as const,
  lists: () => [...knowledgeBaseKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) =>
    [...knowledgeBaseKeys.lists(), params] as const,
  details: () => [...knowledgeBaseKeys.all, 'detail'] as const,
  detail: (id: number) => [...knowledgeBaseKeys.details(), id] as const,
}

export const useKnowledgeBases = (
  tenantId: string,
  params?: { page?: number; per_page?: number }
) =>
  useQuery({
    queryKey: knowledgeBaseKeys.list({ tenantId, ...params }),
    queryFn: () =>
      get<PaginatedResponse<KnowledgeBase>>('v1/knowledge-bases', {
        searchParams: { tenant_id: tenantId, ...params },
      }),
    enabled: !!tenantId,
  })

export const useKnowledgeBase = (id: number) =>
  useQuery({
    queryKey: knowledgeBaseKeys.detail(id),
    queryFn: () => get<KnowledgeBase>(`v1/knowledge-bases/${id}`),
    enabled: !!id,
  })

export const useCreateKnowledgeBase = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateKnowledgeBasePayload) =>
      post<KnowledgeBase>('v1/knowledge-bases', { json: data }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.lists() }),
  })
}

export const useUpdateKnowledgeBase = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: number
      data: UpdateKnowledgeBasePayload
    }) => put<KnowledgeBase>(`v1/knowledge-bases/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.lists() })
    },
  })
}

export const useDeleteKnowledgeBase = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/knowledge-bases/${id}`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.lists() }),
  })
}

export type KBMetaFields = {
  doc_meta: string[]
  slice_meta: string[]
}

export const useKBMetaFields = (kbId: number | null | undefined) =>
  useQuery({
    queryKey: [...knowledgeBaseKeys.all, 'meta-fields', kbId] as const,
    queryFn: () =>
      get<KBMetaFields>(`v1/knowledge-bases/${kbId}/meta-fields`),
    enabled: !!kbId,
  })

export type FieldDefinition = {
  name: string
  type: string
  values?: string[]
  description?: string
}

export type MetaSchemaFields = {
  doc_meta: FieldDefinition[]
  slice_meta: FieldDefinition[]
}

export const useKBMetaSchema = (kbId: number | null | undefined) =>
  useQuery({
    queryKey: [...knowledgeBaseKeys.all, 'meta-schema', kbId] as const,
    queryFn: () =>
      get<MetaSchemaFields>(`v1/knowledge-bases/${kbId}/meta-schema`),
    enabled: !!kbId,
  })
