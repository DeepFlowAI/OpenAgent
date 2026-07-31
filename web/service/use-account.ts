import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  Account,
  AccountListParams,
  AccountPayload,
  AccountResourceOptions,
  CreateAccountPayload,
} from '@/models/account'
import type { PaginatedResponse } from '@/models/common'
import { del, get, post, put } from '@/service/base'

const NS = 'accounts'

export const accountKeys = {
  all: [NS] as const,
  lists: () => [...accountKeys.all, 'list'] as const,
  list: (params: AccountListParams) =>
    [...accountKeys.lists(), params] as const,
  details: () => [...accountKeys.all, 'detail'] as const,
  detail: (id: number) => [...accountKeys.details(), id] as const,
  options: () => [...accountKeys.all, 'resource-options'] as const,
}

export const useAccounts = (params: AccountListParams) =>
  useQuery({
    queryKey: accountKeys.list(params),
    queryFn: () =>
      get<PaginatedResponse<Account>>('v1/accounts', {
        searchParams: {
          ...(params.q ? { q: params.q } : {}),
          ...(params.role ? { role: params.role } : {}),
          page: params.page,
          per_page: params.per_page,
        },
      }),
  })

export const useAccount = (id: number | null) =>
  useQuery({
    queryKey: accountKeys.detail(id ?? 0),
    queryFn: () => get<Account>(`v1/accounts/${id}`),
    enabled: id !== null && id > 0,
  })

export const useAccountResourceOptions = () =>
  useQuery({
    queryKey: accountKeys.options(),
    queryFn: () =>
      get<AccountResourceOptions>('v1/accounts/resource-options'),
  })

export const useCreateAccount = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAccountPayload) =>
      post<Account>('v1/accounts', { json: data }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: accountKeys.lists() }),
  })
}

export const useUpdateAccount = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AccountPayload }) =>
      put<Account>(`v1/accounts/${id}`, { json: data }),
    onSuccess: (account) => {
      queryClient.setQueryData(accountKeys.detail(account.id), account)
      queryClient.invalidateQueries({ queryKey: accountKeys.lists() })
    },
  })
}

export const useDeleteAccount = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      del<{ message: string }>(`v1/accounts/${id}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: accountKeys.lists() }),
  })
}
