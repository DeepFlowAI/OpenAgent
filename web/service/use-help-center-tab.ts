import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  HelpCenterTab,
  SlugAvailability,
  TabCreatePayload,
  TabListResponse,
  TabUpdatePayload,
} from '@/models/help-center'

const NS = 'help-center-tab'

export const helpCenterTabKeys = {
  all: [NS] as const,
  list: (helpCenterId: number) =>
    [...helpCenterTabKeys.all, 'list', helpCenterId] as const,
}

export const useHelpCenterTabs = (helpCenterId: number | null) =>
  useQuery({
    queryKey: helpCenterTabKeys.list(helpCenterId ?? -1),
    queryFn: () =>
      get<TabListResponse>(`v1/help-centers/${helpCenterId}/tabs`),
    enabled: helpCenterId !== null && helpCenterId > 0,
  })

export const useCreateHelpCenterTab = (helpCenterId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: TabCreatePayload) =>
      post<HelpCenterTab>(`v1/help-centers/${helpCenterId}/tabs`, {
        json: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterTabKeys.list(helpCenterId) })
    },
  })
}

export const useUpdateHelpCenterTab = (helpCenterId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      tabId,
      payload,
    }: {
      tabId: number
      payload: TabUpdatePayload
    }) =>
      put<HelpCenterTab>(
        `v1/help-centers/${helpCenterId}/tabs/${tabId}`,
        { json: payload },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterTabKeys.list(helpCenterId) })
    },
  })
}

export const useDeleteHelpCenterTab = (helpCenterId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tabId: number) =>
      del<{ message: string }>(
        `v1/help-centers/${helpCenterId}/tabs/${tabId}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterTabKeys.list(helpCenterId) })
    },
  })
}

export const useReorderHelpCenterTabs = (helpCenterId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tabIds: number[]) =>
      post<TabListResponse>(
        `v1/help-centers/${helpCenterId}/tabs/reorder`,
        { json: { tab_ids: tabIds } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: helpCenterTabKeys.list(helpCenterId) })
    },
  })
}

export const useCheckTabSlug = (helpCenterId: number) =>
  useMutation({
    mutationFn: ({
      slug,
      excludeId,
    }: {
      slug: string
      excludeId?: number
    }) =>
      get<SlugAvailability>(
        `v1/help-centers/${helpCenterId}/tabs/check-slug`,
        {
          searchParams: excludeId
            ? { slug, exclude_id: excludeId }
            : { slug },
        },
      ),
  })
