import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del, patch } from './base'
import type {
  KbPermissionRule,
  CreateKbPermissionRulePayload,
  UpdateKbPermissionRulePayload,
} from '@/models/kb-permission-rule'

const NS = 'kb-permission-rules'

export const kbPermissionRuleKeys = {
  all: [NS] as const,
  lists: () => [...kbPermissionRuleKeys.all, 'list'] as const,
  list: (kbId: number, tenantId: string) =>
    [...kbPermissionRuleKeys.lists(), kbId, tenantId] as const,
}

export const useKbPermissionRules = (kbId: number, tenantId: string) =>
  useQuery({
    queryKey: kbPermissionRuleKeys.list(kbId, tenantId),
    queryFn: () =>
      get<KbPermissionRule[]>(
        `v1/knowledge-bases/${kbId}/permission-rules`,
        { searchParams: { tenant_id: tenantId } }
      ),
    enabled: !!kbId && !!tenantId,
  })

export const useCreateKbPermissionRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      kbId,
      tenantId,
      data,
    }: {
      kbId: number
      tenantId: string
      data: CreateKbPermissionRulePayload
    }) =>
      post<KbPermissionRule>(
        `v1/knowledge-bases/${kbId}/permission-rules`,
        { json: data, searchParams: { tenant_id: tenantId } }
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: kbPermissionRuleKeys.lists() }),
  })
}

export const useUpdateKbPermissionRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      kbId,
      ruleId,
      tenantId,
      data,
    }: {
      kbId: number
      ruleId: number
      tenantId: string
      data: UpdateKbPermissionRulePayload
    }) =>
      put<KbPermissionRule>(
        `v1/knowledge-bases/${kbId}/permission-rules/${ruleId}`,
        { json: data, searchParams: { tenant_id: tenantId } }
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: kbPermissionRuleKeys.lists() }),
  })
}

export const useDeleteKbPermissionRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      kbId,
      ruleId,
      tenantId,
    }: {
      kbId: number
      ruleId: number
      tenantId: string
    }) =>
      del(
        `v1/knowledge-bases/${kbId}/permission-rules/${ruleId}`,
        { searchParams: { tenant_id: tenantId } }
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: kbPermissionRuleKeys.lists() }),
  })
}

export const useToggleKbPermissionRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      kbId,
      ruleId,
      tenantId,
    }: {
      kbId: number
      ruleId: number
      tenantId: string
    }) =>
      patch<KbPermissionRule>(
        `v1/knowledge-bases/${kbId}/permission-rules/${ruleId}/toggle`,
        { searchParams: { tenant_id: tenantId } }
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: kbPermissionRuleKeys.lists() }),
  })
}
