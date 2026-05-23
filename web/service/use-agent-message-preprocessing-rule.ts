import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  AgentMessagePreprocessingRule,
  AgentMessagePreprocessingRuleListResponse,
  CreateAgentMessagePreprocessingRulePayload,
  UpdateAgentMessagePreprocessingRulePayload,
} from '@/models/agent-message-preprocessing-rule'

const NS = 'agent-message-preprocessing-rules'

export const agentMessagePreprocessingRuleKeys = {
  all: [NS] as const,
  lists: () => [...agentMessagePreprocessingRuleKeys.all, 'list'] as const,
  list: (agentId: number) =>
    [...agentMessagePreprocessingRuleKeys.lists(), agentId] as const,
}

export const useAgentMessagePreprocessingRules = (agentId: number) =>
  useQuery({
    queryKey: agentMessagePreprocessingRuleKeys.list(agentId),
    queryFn: () =>
      get<AgentMessagePreprocessingRuleListResponse>(
        `v1/agents/${agentId}/preprocessing-rules`,
      ),
    enabled: !!agentId,
  })

export const useCreateAgentMessagePreprocessingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      agentId,
      data,
    }: {
      agentId: number
      data: CreateAgentMessagePreprocessingRulePayload
    }) =>
      post<AgentMessagePreprocessingRule>(
        `v1/agents/${agentId}/preprocessing-rules`,
        { json: data },
      ),
    onSuccess: (_, v) => {
      qc.invalidateQueries({
        queryKey: agentMessagePreprocessingRuleKeys.list(v.agentId),
      })
    },
  })
}

export const useUpdateAgentMessagePreprocessingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      agentId,
      ruleId,
      data,
    }: {
      agentId: number
      ruleId: number
      data: UpdateAgentMessagePreprocessingRulePayload
    }) =>
      put<AgentMessagePreprocessingRule>(
        `v1/agents/${agentId}/preprocessing-rules/${ruleId}`,
        { json: data },
      ),
    onSuccess: (_, v) => {
      qc.invalidateQueries({
        queryKey: agentMessagePreprocessingRuleKeys.list(v.agentId),
      })
    },
  })
}

export const useDeleteAgentMessagePreprocessingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ agentId, ruleId }: { agentId: number; ruleId: number }) =>
      del(`v1/agents/${agentId}/preprocessing-rules/${ruleId}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({
        queryKey: agentMessagePreprocessingRuleKeys.list(v.agentId),
      })
    },
  })
}
