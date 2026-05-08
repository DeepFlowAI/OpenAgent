import { useMutation } from '@tanstack/react-query'
import { post } from './base'
import type {
  LoginPayload,
  LoginResponse,
  SendCodePayload,
  ResetPasswordPayload,
  MessageResponse,
} from '@/models/auth'

export const useLogin = () =>
  useMutation({
    mutationFn: (data: LoginPayload) =>
      post<LoginResponse>('v1/auth/login', { json: data }),
  })

export const useSendVerificationCode = () =>
  useMutation({
    mutationFn: (data: SendCodePayload) =>
      post<MessageResponse>('v1/auth/send-verification-code', { json: data }),
  })

export const useResetPassword = () =>
  useMutation({
    mutationFn: (data: ResetPasswordPayload) =>
      post<MessageResponse>('v1/auth/reset-password', { json: data }),
  })
