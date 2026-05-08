import { useMutation } from '@tanstack/react-query'
import { post } from './base'
import type { AdminLoginPayload, AdminLoginResponse } from '@/models/super-admin'

export const useAdminLogin = () =>
  useMutation({
    mutationFn: (data: AdminLoginPayload) =>
      post<AdminLoginResponse>('v1/auth/admin-login', { json: data }),
  })
