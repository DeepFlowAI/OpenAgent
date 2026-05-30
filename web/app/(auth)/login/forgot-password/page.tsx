'use client'

import { Suspense, useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useSendVerificationCode, useResetPassword } from '@/service/use-auth'
import { useSystemInfo } from '@/service/use-system'
import { getErrorMessage } from '@/service/base'
import { tenantLoginFieldError } from '@/lib/tenant-login-field'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Alert } from '@/app/components/base/alert'
import { useToast } from '@/app/components/base/toast'
import { IconEye, IconEyeOff } from '@tabler/icons-react'

export default function ForgotPasswordPage() {
  return (
    <Suspense>
      <ForgotPasswordContent />
    </Suspense>
  )
}

function ForgotPasswordContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const sendCodeMutation = useSendVerificationCode()
  const resetMutation = useResetPassword()
  const { toast } = useToast()
  const { data: systemInfo } = useSystemInfo()
  const singleTenantMode = systemInfo?.single_tenant_mode ?? false

  const [form, setForm] = useState({
    tenant: searchParams.get('tenant') || '',
    username: '',
    verifyCode: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showNewPwd, setShowNewPwd] = useState(false)
  const [showConfirmPwd, setShowConfirmPwd] = useState(false)
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  useEffect(() => {
    if (singleTenantMode && systemInfo) {
      setForm((prev) => ({ ...prev, tenant: systemInfo.default_tenant_id }))
    }
  }, [singleTenantMode, systemInfo])

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: '' }))
    setApiError('')
  }

  const validateSendCode = useCallback((): boolean => {
    const errs: Record<string, string> = {}
    if (!singleTenantMode) {
      const tenantErr = tenantLoginFieldError(form.tenant)
      if (tenantErr) errs.tenant = tenantErr
    }
    if (!form.username) errs.username = '请输入账号'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }, [form.tenant, form.username, singleTenantMode])

  const validateAll = (): boolean => {
    const errs: Record<string, string> = {}
    if (!singleTenantMode) {
      const tenantErr = tenantLoginFieldError(form.tenant)
      if (tenantErr) errs.tenant = tenantErr
    }
    if (!form.username) errs.username = '请输入账号'
    if (!form.verifyCode) errs.verifyCode = '请输入验证码'
    else if (!/^\d{6}$/.test(form.verifyCode))
      errs.verifyCode = '验证码格式不正确'
    if (!form.newPassword) errs.newPassword = '请输入新密码'
    else if (
      form.newPassword.length < 8 ||
      form.newPassword.length > 32 ||
      !/[a-z]/.test(form.newPassword) ||
      !/[A-Z]/.test(form.newPassword) ||
      !/[0-9]/.test(form.newPassword)
    )
      errs.newPassword = '密码为 8–32 位，需包含大小写字母和数字'
    if (!form.confirmPassword) errs.confirmPassword = '请再次输入新密码'
    else if (form.confirmPassword !== form.newPassword)
      errs.confirmPassword = '两次输入的密码不一致'

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSendCode = async () => {
    if (!validateSendCode()) return
    try {
      await sendCodeMutation.mutateAsync({
        tenant: singleTenantMode ? form.tenant : form.tenant.trim(),
        username: form.username,
      })
      toast('验证码已发送至您的邮箱')
      setCountdown(60)
    } catch (err) {
      const msg = await getErrorMessage(err)
      setApiError(msg)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateAll()) return
    try {
      await resetMutation.mutateAsync({
        tenant: singleTenantMode ? form.tenant : form.tenant.trim(),
        username: form.username,
        verify_code: form.verifyCode,
        new_password: form.newPassword,
      })
      toast('密码重置成功，请使用新密码登录')
      setTimeout(() => {
        if (singleTenantMode) {
          router.push('/login')
          return
        }
        const t = form.tenant.trim()
        router.push(`/login${t ? `?tenant=${encodeURIComponent(t)}` : ''}`)
      }, 1500)
    } catch (err) {
      const msg = await getErrorMessage(err)
      setApiError(msg)
    }
  }

  return (
    <div className="w-full max-w-[400px] rounded-lg border border-[#E5E5E5] bg-white p-6 shadow-sm">
      <div className="mb-6 space-y-1">
        <h1 className="text-2xl font-bold text-[#1a1a1a]">找回密码</h1>
        <p className="text-sm text-[#737373]">通过邮箱验证码重置密码</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {!singleTenantMode && (
          <Input
            id="forgot-tenant"
            name="tenant"
            label="企业 ID"
            autoComplete="organization"
            required
            value={form.tenant}
            onChange={(e) => updateField('tenant', e.target.value)}
            error={errors.tenant}
            placeholder="请输入企业 ID"
            maxLength={64}
          />
        )}

        <Input
          id="forgot-username"
          name="username"
          label="账号"
          autoComplete="username"
          required
          value={form.username}
          onChange={(e) => updateField('username', e.target.value)}
          error={errors.username}
          placeholder="请输入用户名或邮箱"
          maxLength={64}
        />

        <div className="space-y-1.5">
          <label
            htmlFor="forgot-verify-code"
            className="text-sm font-medium text-[#1a1a1a]"
          >
            验证码<span className="ml-0.5 text-[#DC2626]">*</span>
          </label>
          <div className="flex gap-3">
            <input
              id="forgot-verify-code"
              name="verifyCode"
              autoComplete="one-time-code"
              value={form.verifyCode}
              onChange={(e) => updateField('verifyCode', e.target.value)}
              placeholder="请输入验证码"
              maxLength={6}
              className="h-11 flex-1 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleSendCode}
              disabled={countdown > 0 || sendCodeMutation.isPending}
              loading={sendCodeMutation.isPending}
              className="shrink-0"
            >
              {countdown > 0 ? `${countdown}s 后重发` : '发送验证码'}
            </Button>
          </div>
          {errors.verifyCode && (
            <p className="text-xs text-[#DC2626]">{errors.verifyCode}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="forgot-new-password"
            className="text-sm font-medium text-[#1a1a1a]"
          >
            新密码<span className="ml-0.5 text-[#DC2626]">*</span>
          </label>
          <div className="relative">
            <input
              id="forgot-new-password"
              name="newPassword"
              autoComplete="new-password"
              type={showNewPwd ? 'text' : 'password'}
              value={form.newPassword}
              onChange={(e) => updateField('newPassword', e.target.value)}
              placeholder="请输入新密码"
              maxLength={32}
              className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 pr-10 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
            />
            <button
              type="button"
              onClick={() => setShowNewPwd(!showNewPwd)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A3A3A3] transition-colors hover:text-[#1a1a1a]"
            >
              {showNewPwd ? <IconEyeOff size={18} /> : <IconEye size={18} />}
            </button>
          </div>
          {errors.newPassword && (
            <p className="text-xs text-[#DC2626]">{errors.newPassword}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="forgot-confirm-password"
            className="text-sm font-medium text-[#1a1a1a]"
          >
            确认新密码<span className="ml-0.5 text-[#DC2626]">*</span>
          </label>
          <div className="relative">
            <input
              id="forgot-confirm-password"
              name="confirmPassword"
              autoComplete="new-password"
              type={showConfirmPwd ? 'text' : 'password'}
              value={form.confirmPassword}
              onChange={(e) => updateField('confirmPassword', e.target.value)}
              placeholder="请再次输入新密码"
              maxLength={32}
              className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 pr-10 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
            />
            <button
              type="button"
              onClick={() => setShowConfirmPwd(!showConfirmPwd)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A3A3A3] transition-colors hover:text-[#1a1a1a]"
            >
              {showConfirmPwd ? <IconEyeOff size={18} /> : <IconEye size={18} />}
            </button>
          </div>
          {errors.confirmPassword && (
            <p className="text-xs text-[#DC2626]">{errors.confirmPassword}</p>
          )}
        </div>

        {apiError && <Alert variant="destructive">{apiError}</Alert>}

        <Button
          type="submit"
          className="!h-11 w-full"
          loading={resetMutation.isPending}
          disabled={resetMutation.isPending}
        >
          重置密码
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Link
          href={`/login${
            form.tenant.trim()
              ? `?tenant=${encodeURIComponent(form.tenant.trim())}`
              : ''
          }`}
          className="text-sm text-[#737373] transition-colors hover:text-[#1a1a1a]"
        >
          返回登录
        </Link>
      </div>
    </div>
  )
}
