'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useLogin } from '@/service/use-auth'
import { useSystemInfo } from '@/service/use-system'
import { useAuthStore } from '@/context/auth-store'
import { getErrorMessage } from '@/service/base'
import { tenantLoginFieldError } from '@/lib/tenant-login-field'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Alert } from '@/app/components/base/alert'
import { IconEye, IconEyeOff } from '@tabler/icons-react'

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  )
}

function LoginContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const loginMutation = useLogin()
  const setAuth = useAuthStore((s) => s.setAuth)
  const { data: systemInfo } = useSystemInfo()
  // Default to false (= show field) when info unavailable — safer for users
  // who otherwise wouldn't see what to type.
  const singleTenantMode = systemInfo?.single_tenant_mode ?? false

  const [form, setForm] = useState({
    tenant: searchParams.get('tenant') || '',
    username: '',
    password: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  // Auto-fill the tenant field with the server-provided default when running
  // in single-tenant (OSS) mode so the form submits a valid value even though
  // the input is hidden.
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

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!singleTenantMode) {
      const tenantErr = tenantLoginFieldError(form.tenant)
      if (tenantErr) errs.tenant = tenantErr
    }

    if (!form.username) errs.username = '请输入账号'

    if (!form.password) errs.password = '请输入密码'
    else if (
      form.password.length < 8 ||
      form.password.length > 32 ||
      !/[a-z]/.test(form.password) ||
      !/[A-Z]/.test(form.password) ||
      !/[0-9]/.test(form.password)
    )
      errs.password = '密码为 8–32 位，需包含大小写字母和数字'

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    try {
      const res = await loginMutation.mutateAsync({
        tenant: singleTenantMode ? form.tenant : form.tenant.trim(),
        username: form.username,
        password: form.password,
      })
      setAuth(res.user, res.token)

      const redirect = searchParams.get('redirect')
      router.push(redirect && redirect.startsWith('/') ? redirect : '/knowledge-space')
    } catch (err) {
      const msg = await getErrorMessage(err)
      setApiError(msg)
    }
  }

  return (
    <div className="w-full max-w-[400px] rounded-lg border border-[#E5E5E5] bg-white p-6 shadow-sm">
      <div className="mb-6 space-y-1">
        <h1 className="text-2xl font-bold text-[#1a1a1a]">登录</h1>
        <p className="text-sm text-[#737373]">使用企业账号登录</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Tenant — hidden in single-tenant mode (OSS edition); the value
            is auto-filled from /api/v1/system/info default_tenant_id. */}
        {!singleTenantMode && (
          <Input
            id="login-tenant"
            name="tenant"
            label="企业 ID"
            autoComplete="organization"
            required
            value={form.tenant}
            onChange={(e) => updateField('tenant', e.target.value)}
            onBlur={() => {
              const err = form.tenant ? tenantLoginFieldError(form.tenant) : null
              if (err) setErrors((prev) => ({ ...prev, tenant: err }))
            }}
            error={errors.tenant}
            placeholder="请输入企业 ID"
            maxLength={64}
          />
        )}

        <Input
          id="login-username"
          name="username"
          label="账号"
          autoComplete="username"
          required
          value={form.username}
          onChange={(e) => updateField('username', e.target.value)}
          error={errors.username}
          placeholder="请输入账号"
          maxLength={64}
        />

        <div className="space-y-1.5">
          <label
            htmlFor="login-password"
            className="text-sm font-medium text-[#1a1a1a]"
          >
            密码<span className="ml-0.5 text-[#DC2626]">*</span>
          </label>
          <div className="relative">
            <input
              id="login-password"
              name="password"
              autoComplete="current-password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={(e) => updateField('password', e.target.value)}
              placeholder="请输入密码"
              maxLength={32}
              className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 pr-10 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A3A3A3] transition-colors hover:text-[#1a1a1a]"
            >
              {showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
            </button>
          </div>
          {errors.password && (
            <p className="text-xs text-[#DC2626]">{errors.password}</p>
          )}
        </div>

        {apiError && (
          <Alert variant="destructive" onDismiss={() => setApiError('')}>
            {apiError}
          </Alert>
        )}

        <Button
          type="submit"
          className="!h-11 w-full"
          loading={loginMutation.isPending}
          disabled={loginMutation.isPending}
        >
          登录
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Link
          href={`/login/forgot-password${
            form.tenant.trim()
              ? `?tenant=${encodeURIComponent(form.tenant.trim())}`
              : ''
          }`}
          className="text-sm text-[#737373] transition-colors hover:text-[#1a1a1a]"
        >
          忘记密码？
        </Link>
      </div>
    </div>
  )
}
