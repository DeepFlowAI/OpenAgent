import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  HelpCenter,
  HelpCenterCreatePayload,
  HelpCenterUpdatePayload,
  HelpCenterListResponse,
  SlugAvailability,
} from '@/models/help-center'

const NS = 'help-center'

export const helpCenterKeys = {
  all: [NS] as const,
  list: (page: number, perPage: number) =>
    [...helpCenterKeys.all, 'list', page, perPage] as const,
  detail: (id: number) => [...helpCenterKeys.all, 'detail', id] as const,
}

export const useHelpCenterList = (page: number = 1, perPage: number = 10) =>
  useQuery({
    queryKey: helpCenterKeys.list(page, perPage),
    queryFn: () =>
      get<HelpCenterListResponse>('v1/help-centers', {
        searchParams: { page, per_page: perPage },
      }),
  })

export const useHelpCenter = (id: number | null) =>
  useQuery({
    queryKey: helpCenterKeys.detail(id ?? -1),
    queryFn: () => get<HelpCenter>(`v1/help-centers/${id}`),
    enabled: id !== null && id > 0,
  })

export const useCreateHelpCenter = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: HelpCenterCreatePayload) =>
      post<HelpCenter>('v1/help-centers', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterKeys.all })
    },
  })
}

export const useUpdateHelpCenter = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: HelpCenterUpdatePayload
    }) => put<HelpCenter>(`v1/help-centers/${id}`, { json: payload }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: helpCenterKeys.detail(vars.id) })
      qc.invalidateQueries({ queryKey: helpCenterKeys.all })
    },
  })
}

export const useDeleteHelpCenter = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      del<{ message: string }>(`v1/help-centers/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterKeys.all })
    },
  })
}

/** Mutation form: callable on demand (e.g. debounced from a controlled input). */
export const useCheckSlug = () =>
  useMutation({
    mutationFn: ({ slug, excludeId }: { slug: string; excludeId?: number }) =>
      get<SlugAvailability>('v1/help-centers/check-slug', {
        searchParams: excludeId
          ? { slug, exclude_id: excludeId }
          : { slug },
      }),
  })
