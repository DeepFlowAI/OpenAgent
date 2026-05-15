import { useQuery } from '@tanstack/react-query'
import { get, getBlob, post } from './base'
import type { Conversation, ConversationDetail } from '@/models/conversation'
import type { PaginatedResponse } from '@/models/common'

const NS = 'conversations'

export const conversationKeys = {
  all: [NS] as const,
  lists: () => [...conversationKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) =>
    [...conversationKeys.lists(), params] as const,
  details: () => [...conversationKeys.all, 'detail'] as const,
  detail: (id: number) => [...conversationKeys.details(), id] as const,
}

export type ConversationListParams = {
  page?: number
  per_page?: number
  start_time?: string
  end_time?: string
  status_filter?: string
  source?: string
  conversation_id?: string
  external_user_id?: string
  search?: string
}

export const useConversations = (
  agentId: number,
  tenantId: string,
  params?: ConversationListParams
) =>
  useQuery({
    queryKey: conversationKeys.list({ agentId, tenantId, ...params }),
    queryFn: () =>
      get<PaginatedResponse<Conversation>>(
        `v1/agents/${agentId}/conversations`,
        {
          searchParams: {
            tenant_id: tenantId,
            ...Object.fromEntries(
              Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== '')
            ),
          },
        }
      ),
    enabled: !!agentId && !!tenantId,
  })

export const useConversation = (agentId: number, conversationId: number) =>
  useQuery({
    queryKey: conversationKeys.detail(conversationId),
    queryFn: () =>
      get<ConversationDetail>(
        `v1/agents/${agentId}/conversations/${conversationId}`
      ),
    enabled: !!agentId && !!conversationId,
  })

export const exportConversations = (
  agentId: number,
  tenantId: string,
  params?: Omit<ConversationListParams, 'page' | 'per_page'>
) =>
  getBlob(`v1/agents/${agentId}/conversations/export`, {
    searchParams: {
      tenant_id: tenantId,
      ...Object.fromEntries(
        Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== '')
      ),
    },
  })

export const endConversation = (agentId: number, conversationId: number) =>
  post<Conversation>(
    `v1/agents/${agentId}/conversations/${conversationId}/end`
  )
