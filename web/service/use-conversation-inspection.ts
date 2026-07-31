import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './base'

export type InspectionTag = 'good' | 'pass' | 'bad'
export type QualityConversation = { id: number; external_id: string; external_user_id: string | null; source: string; channel_name: string | null; channel_source: string | null; started_at: string | null; round_count: number; inspection_status: 'pending' | 'in_progress' | 'completed'; inspection_tag: InspectionTag | null; assistant_reply_count: number; inspected_count: number }
export type QualityQueue = { items: QualityConversation[]; total: number }
export type InspectionSave = { tag: InspectionTag; issue_types?: string[]; issue_description?: string | null }

export const useQualityQueue = (agentId: number, params: Record<string, string>) => useQuery({ queryKey: ['quality-queue', agentId, params], queryFn: () => get<QualityQueue>(`v1/agents/${agentId}/quality/conversations`, { searchParams: Object.fromEntries(Object.entries(params).filter(([, value]) => value)) }), enabled: !!agentId })

export const useSaveInspection = (agentId: number, conversationId: number) => {
  const client = useQueryClient()
  return useMutation({ mutationFn: ({ stepId, ...body }: InspectionSave & { stepId: number }) => post(`v1/agents/${agentId}/quality/conversations/${conversationId}/steps/${stepId}`, { json: body }), onSuccess: () => client.invalidateQueries({ queryKey: ['quality-queue', agentId] }) })
}
