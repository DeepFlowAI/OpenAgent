import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, del } from './base'
import type {
  ApiKeyInfo,
  ApiKeyFull,
  ApiKeyItem,
  ApiKeyCreatePayload,
  ApiKeyCreateResponse,
  ApiKeyListResponse,
} from '@/models/api-key'

const NS = 'api-key'

export const apiKeyKeys = {
  all: [NS] as const,
  detail: () => [...apiKeyKeys.all, 'detail'] as const,
  full: () => [...apiKeyKeys.all, 'full'] as const,
  list: (page: number) => [...apiKeyKeys.all, 'list', page] as const,
}

// --- Legacy single-key hooks (backward compat) ---

export const useApiKey = () =>
  useQuery({
    queryKey: apiKeyKeys.detail(),
    queryFn: () => get<ApiKeyInfo>('v1/system/api-key'),
  })

export const useApiKeyFull = () => {
  return useMutation({
    mutationFn: () => get<ApiKeyFull>('v1/system/api-key/full'),
  })
}

export const useResetApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<ApiKeyInfo>('v1/system/api-key/reset'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: apiKeyKeys.detail() })
    },
  })
}

// --- Multi-key management hooks ---

export const useApiKeyList = (page: number = 1, perPage: number = 20) =>
  useQuery({
    queryKey: apiKeyKeys.list(page),
    queryFn: () =>
      get<ApiKeyListResponse>('v1/system/api-keys', {
        searchParams: { page, per_page: perPage },
      }),
  })

/** Fetch full key for one row (e.g. copy to clipboard). Not cached in query client. */
export const useApiKeyFullById = () =>
  useMutation({
    mutationFn: (keyId: number) =>
      get<ApiKeyFull>(`v1/system/api-keys/${keyId}/full`),
  })

export const useCreateApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ApiKeyCreatePayload) =>
      post<ApiKeyCreateResponse>('v1/system/api-keys', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: apiKeyKeys.all })
    },
  })
}

export const useRotateApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (keyId: number) =>
      post<ApiKeyCreateResponse>(`v1/system/api-keys/${keyId}/rotate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: apiKeyKeys.all })
    },
  })
}

export const useRevokeApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (keyId: number) =>
      del<{ message: string }>(`v1/system/api-keys/${keyId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: apiKeyKeys.all })
    },
  })
}
