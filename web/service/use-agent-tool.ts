import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  AgentTool,
  CreateAgentToolPayload,
  UpdateAgentToolPayload,
  ToggleAgentToolPayload,
} from '@/models/agent-tool'

const NS = 'agent-tools'

export const agentToolKeys = {
  all: [NS] as const,
  lists: () => [...agentToolKeys.all, 'list'] as const,
  list: (agentId: number) => [...agentToolKeys.lists(), agentId] as const,
  details: () => [...agentToolKeys.all, 'detail'] as const,
  detail: (agentId: number, toolId: number) =>
    [...agentToolKeys.details(), agentId, toolId] as const,
}

export const useAgentTools = (agentId: number) =>
  useQuery({
    queryKey: agentToolKeys.list(agentId),
    queryFn: () =>
      get<{ items: AgentTool[] }>(`v1/agents/${agentId}/tools`),
    enabled: !!agentId,
  })

export const useAgentTool = (agentId: number, toolId: number) =>
  useQuery({
    queryKey: agentToolKeys.detail(agentId, toolId),
    queryFn: () =>
      get<AgentTool>(`v1/agents/${agentId}/tools/${toolId}`),
    enabled: !!agentId && !!toolId,
  })

export const useCreateAgentTool = (agentId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAgentToolPayload) =>
      post<AgentTool>(`v1/agents/${agentId}/tools`, { json: data }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: agentToolKeys.list(agentId) }),
  })
}

export const useUpdateAgentTool = (agentId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ toolId, data }: { toolId: number; data: UpdateAgentToolPayload }) =>
      put<AgentTool>(`v1/agents/${agentId}/tools/${toolId}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: agentToolKeys.detail(agentId, v.toolId) })
      qc.invalidateQueries({ queryKey: agentToolKeys.list(agentId) })
    },
  })
}

export const useToggleAgentTool = (agentId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ toolId, data }: { toolId: number; data: ToggleAgentToolPayload }) =>
      put<AgentTool>(`v1/agents/${agentId}/tools/${toolId}/toggle`, { json: data }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: agentToolKeys.list(agentId) }),
  })
}

export const useDeleteAgentTool = (agentId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (toolId: number) =>
      del(`v1/agents/${agentId}/tools/${toolId}`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: agentToolKeys.list(agentId) }),
  })
}
