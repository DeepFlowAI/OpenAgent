import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type {
  Agent,
  CreateAgentPayload,
  UpdateAgentPayload,
  UpdateAgentStatusPayload,
  EngineConfig,
} from '@/models/agent'
import type { PaginatedResponse } from '@/models/common'

const NS = 'agents'

export const agentKeys = {
  all: [NS] as const,
  lists: () => [...agentKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) =>
    [...agentKeys.lists(), params] as const,
  details: () => [...agentKeys.all, 'detail'] as const,
  detail: (id: number) => [...agentKeys.details(), id] as const,
}

export const useAgent = (id: number) =>
  useQuery({
    queryKey: agentKeys.detail(id),
    queryFn: () => get<Agent>(`v1/agents/${id}`),
    enabled: !!id,
  })

export const useAgents = (
  tenantId: string,
  statusFilter: string = 'active',
  params?: { page?: number; per_page?: number }
) =>
  useQuery({
    queryKey: agentKeys.list({ tenantId, statusFilter, ...params }),
    queryFn: () =>
      get<PaginatedResponse<Agent>>('v1/agents', {
        searchParams: {
          tenant_id: tenantId,
          status_filter: statusFilter,
          ...params,
        },
      }),
    enabled: !!tenantId,
  })

export const useCreateAgent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAgentPayload) =>
      post<Agent>('v1/agents', { json: data }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: agentKeys.lists() }),
  })
}

export const useUpdateAgent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: number
      data: UpdateAgentPayload
    }) => put<Agent>(`v1/agents/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: agentKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: agentKeys.lists() })
    },
  })
}

export const useUpdateAgentStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: number
      data: UpdateAgentStatusPayload
    }) => put<Agent>(`v1/agents/${id}/status`, { json: data }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: agentKeys.lists() }),
  })
}

export const useUpdateEngineConfig = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: number
      data: Partial<EngineConfig>
    }) => put<Agent>(`v1/agents/${id}/engine-config`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: agentKeys.detail(v.id) })
    },
  })
}
