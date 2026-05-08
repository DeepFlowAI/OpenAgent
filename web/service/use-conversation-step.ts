import { useQuery } from '@tanstack/react-query'
import { get } from './base'
import type {
  ConversationTimelineResponse,
  StepDetail,
} from '@/models/conversation'

const NS = 'conversation-steps'

export const stepKeys = {
  all: [NS] as const,
  timelines: () => [...stepKeys.all, 'timeline'] as const,
  timeline: (conversationId: number) =>
    [...stepKeys.timelines(), conversationId] as const,
  details: () => [...stepKeys.all, 'detail'] as const,
  detail: (stepId: number) => [...stepKeys.details(), stepId] as const,
}

export const useConversationTimeline = (
  agentId: number,
  conversationId: number
) =>
  useQuery({
    queryKey: stepKeys.timeline(conversationId),
    queryFn: () =>
      get<ConversationTimelineResponse>(
        `v1/agents/${agentId}/conversations/${conversationId}/steps`
      ),
    enabled: !!agentId && !!conversationId,
  })

export const useStepDetail = (
  agentId: number,
  conversationId: number,
  stepId: number
) =>
  useQuery({
    queryKey: stepKeys.detail(stepId),
    queryFn: () =>
      get<StepDetail>(
        `v1/agents/${agentId}/conversations/${conversationId}/steps/${stepId}`
      ),
    enabled: !!agentId && !!conversationId && !!stepId,
  })
