'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import { useAdminLogin } from '@/service/use-admin-auth'
import { useAdminAuthStore } from '@/context/admin-auth-store'
import { getErrorMessage } from '@/service/base'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Alert } from '@/app/components/base/alert'
import { IconEye, IconEyeOff, IconHome } from '@tabler/icons-react'

export default function AdminLoginPage() {
  return (
    <Suspense>
      <AdminLoginContent />
    </Suspense>
  )
}

function AdminLoginContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const loginMutation = useAdminLogin()
  const setAuth = useAdminAuthStore((s) => s.setAuth)

  const [form, setForm] = useState({ username: '', password: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: '' }))
    setApiError('')
  }

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!form.username) errs.username = '请输入用户名'
    if (!form.password) errs.password = '请输入密码'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    try {
      const res = await loginMutation.mutateAsync({
        username: form.username,
        password: form.password,
      })
      setAuth(res.user, res.token)

      const redirect = searchParams.get('redirect')
      router.push(redirect && redirect.startsWith('/') ? redirect : '/admin/tenants')
    } catch (err) {
      const msg = await getErrorMessage(err)
      setApiError(msg)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FAFAFA]">
      <div className="w-full max-w-[400px] rounded-lg border border-[#E5E5E5] bg-white p-6 shadow-sm">
        <div className="mb-6 space-y-1">
          <div className="flex items-center gap-2">
            <IconHome size={24} className="text-[#1a1a1a]" />
            <h1 className="text-2xl font-bold text-[#1a1a1a]">管理后台</h1>
          </div>
          <p className="text-sm text-[#737373]">使用超级管理员账号登录</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="用户名"
            required
            value={form.username}
            onChange={(e) => updateField('username', e.target.value)}
            error={errors.username}
            placeholder="请输入用户名"
            maxLength={64}
          />

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[#1a1a1a]">
              密码<span className="ml-0.5 text-[#DC2626]">*</span>
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={(e) => updateField('password', e.target.value)}
                placeholder="请输入密码"
                maxLength={72}
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
      </div>
    </div>
  )
}
