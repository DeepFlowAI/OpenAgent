import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, patch } from './base'
import type {
  Tenant,
  CreateTenantPayload,
  UpdateTenantPayload,
  UpdateTenantStatusPayload,
} from '@/models/tenant'
import type { PaginatedResponse } from '@/models/common'

const NS = 'tenants'

export const tenantKeys = {
  all: [NS] as const,
  lists: () => [...tenantKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...tenantKeys.lists(), params] as const,
  details: () => [...tenantKeys.all, 'detail'] as const,
  detail: (id: string) => [...tenantKeys.details(), id] as const,
}

export const useTenants = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: tenantKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<Tenant>>('v1/tenants', { searchParams: params }),
  })

export const useTenant = (id: string) =>
  useQuery({
    queryKey: tenantKeys.detail(id),
    queryFn: () => get<Tenant>(`v1/tenants/${id}`),
    enabled: !!id,
  })

export const useCreateTenant = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTenantPayload) =>
      post<Tenant>('v1/tenants', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantKeys.lists() }),
  })
}

export const useUpdateTenant = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTenantPayload }) =>
      put<Tenant>(`v1/tenants/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: tenantKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: tenantKeys.lists() })
    },
  })
}

export const useUpdateTenantStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTenantStatusPayload }) =>
      patch<Tenant>(`v1/tenants/${id}/status`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantKeys.lists() }),
  })
}
