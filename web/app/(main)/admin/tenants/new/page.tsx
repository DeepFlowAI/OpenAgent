'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { useCreateTenant } from '@/service/use-tenant'
import { getErrorMessage } from '@/service/base'
import { createTenantSchema, type CreateTenantFormData } from '@/utils/validators'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Textarea } from '@/app/components/base/textarea'
import { useToast } from '@/app/components/base/toast'
import { IconArrowLeft, IconEye, IconEyeOff } from '@tabler/icons-react'

function generateRandomPassword(length = 16): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%'
  return Array.from({ length }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

export default function NewTenantPage() {
  const router = useRouter()
  const mutation = useCreateTenant()
  const { toast } = useToast()

  const [form, setForm] = useState<CreateTenantFormData>({
    name: '',
    slug: '',
    remark: '',
    admin_username: '',
    admin_password: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [showPassword, setShowPassword] = useState(false)
  const [isDirty, setIsDirty] = useState(false)

  const canSave = useMemo(() => {
    return isDirty && form.name && form.admin_username && form.admin_password
  }, [isDirty, form])

  const updateField = (field: keyof CreateTenantFormData, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: '' }))
    setIsDirty(true)
  }

  const handleGeneratePassword = () => {
    const password = generateRandomPassword()
    setForm((prev) => ({ ...prev, admin_password: password }))
    setShowPassword(true)
    setIsDirty(true)
  }

  const handleSubmit = async () => {
    const result = createTenantSchema.safeParse(form)
    if (!result.success) {
      const fieldErrors: Record<string, string> = {}
      result.error.issues.forEach((issue) => {
        const key = issue.path[0] as string
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      })
      setErrors(fieldErrors)
      return
    }

    try {
      const tenant = await mutation.mutateAsync({
        name: form.name,
        slug: form.slug || undefined,
        remark: form.remark || undefined,
        admin_username: form.admin_username,
        admin_password: form.admin_password,
      })
      toast(`租户创建成功！ID: ${tenant.id}，超管: ${tenant.admin_username}`)
      router.push('/admin/tenants')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const handleBack = () => {
    if (isDirty) {
      if (window.confirm('有未保存的更改，确定离开？')) {
        router.push('/admin/tenants')
      }
    } else {
      router.push('/admin/tenants')
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#E5E5E5] bg-white/80 px-6 py-3 backdrop-blur-sm">
        <button
          onClick={handleBack}
          className="flex items-center gap-2 transition-colors hover:text-[#1a1a1a]"
        >
          <IconArrowLeft size={20} className="text-[#737373]" />
          <span className="text-base font-semibold text-[#1a1a1a]">
            新建租户
          </span>
        </button>
        <Button
          disabled={!canSave}
          loading={mutation.isPending}
          onClick={handleSubmit}
        >
          保存
        </Button>
      </div>

      <div className="flex-1 overflow-auto px-10 py-8">
        <div className="max-w-[600px] space-y-8">
          <div className="space-y-6">
            <h2 className="text-base font-semibold text-[#1a1a1a]">
              基本信息
            </h2>
            <Input
              label="租户名称"
              required
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              error={errors.name}
              placeholder="请输入租户名称"
              maxLength={64}
            />
            <Input
              label="租户别名"
              value={form.slug}
              onChange={(e) => updateField('slug', e.target.value)}
              error={errors.slug}
              placeholder="请输入租户别名，如 qdma/osram"
              maxLength={64}
              hint="可选，仅支持小写字母、数字、短横线和斜杠"
            />
            <Textarea
              label="备注"
              value={form.remark}
              onChange={(e) => updateField('remark', e.target.value)}
              error={errors.remark}
              placeholder="请输入备注信息"
              maxLength={256}
              hint="最多 256 个字符"
            />
          </div>

          <div className="border-t border-[#E5E5E5]" />

          <div className="space-y-6">
            <h2 className="text-base font-semibold text-[#1a1a1a]">
              超管账号
            </h2>
            <Input
              label="用户名"
              required
              value={form.admin_username}
              onChange={(e) => updateField('admin_username', e.target.value)}
              error={errors.admin_username}
              placeholder="请输入超管用户名"
              maxLength={64}
            />
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[#1a1a1a]">
                密码<span className="ml-0.5 text-[#DC2626]">*</span>
              </label>
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={form.admin_password}
                    onChange={(e) => updateField('admin_password', e.target.value)}
                    placeholder="请输入超管密码"
                    maxLength={64}
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
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGeneratePassword}
                >
                  生成随机密码
                </Button>
              </div>
              {errors.admin_password && (
                <p className="text-xs text-[#DC2626]">{errors.admin_password}</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
