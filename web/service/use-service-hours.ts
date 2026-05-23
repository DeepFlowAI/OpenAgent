import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/service/base'
import type { PaginatedResponse } from '@/models/common'
import type {
  CreateServiceHoursPayload,
  ServiceHours,
  UpdateServiceHoursPayload,
} from '@/models/service-hours'

const NS = 'service-hours'

export const serviceHoursKeys = {
  all: [NS] as const,
  lists: () => [...serviceHoursKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...serviceHoursKeys.lists(), params] as const,
  details: () => [...serviceHoursKeys.all, 'detail'] as const,
  detail: (id: number) => [...serviceHoursKeys.details(), id] as const,
}

export const useServiceHoursList = (
  params: { page?: number; per_page?: number } = {}
) =>
  useQuery({
    queryKey: serviceHoursKeys.list(params),
    queryFn: () =>
      get<PaginatedResponse<ServiceHours>>('v1/service-hours', {
        searchParams: params,
      }),
  })

export const useServiceHours = (id: number | null) =>
  useQuery({
    queryKey: id ? serviceHoursKeys.detail(id) : serviceHoursKeys.details(),
    queryFn: () => get<ServiceHours>(`v1/service-hours/${id}`),
    enabled: id !== null,
  })

export const useCreateServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateServiceHoursPayload) =>
      post<ServiceHours>('v1/service-hours', { json: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() }),
  })
}

export const useUpdateServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: UpdateServiceHoursPayload
    }) => put<ServiceHours>(`v1/service-hours/${id}`, { json: payload }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: serviceHoursKeys.detail(vars.id) })
      qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() })
    },
  })
}

export const useDeleteServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      del<{ message: string }>(`v1/service-hours/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() }),
  })
}
