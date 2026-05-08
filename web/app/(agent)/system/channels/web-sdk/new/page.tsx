'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useCreateChannel } from '@/service/use-channel'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Button } from '@/app/components/base/button'
import { IconArrowLeft } from '@tabler/icons-react'

export default function NewWebSdkChannelPage() {
  const router = useRouter()
  const { toast } = useToast()
  const user = useAuthStore((s) => s.user)
  const tenantId = user?.tenant_id ?? ''

  const createMutation = useCreateChannel()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = '请输入渠道名称'
    else if (name.length > 64) errs.name = '名称不能超过 64 个字符'
    if (description.length > 500) errs.description = '描述不能超过 500 个字符'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    try {
      const channel = await createMutation.mutateAsync({
        tenant_id: tenantId,
        name: name.trim(),
        description: description.trim() || undefined,
      })
      toast('已创建', 'success')
      router.push(`/system/channels/web-sdk/${channel.id}`)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <div className="px-12 py-10" style={{ padding: '40px 48px' }}>
      {/* Back */}
      <button
        className="mb-4 flex items-center gap-1.5 text-sm text-[#737373] transition-colors hover:text-foreground"
        onClick={() => router.push('/system/channels/web-sdk')}
      >
        <IconArrowLeft size={16} />
        返回列表
      </button>

      {/* Title */}
      <h1 className="text-2xl font-bold text-foreground">新建 Web SDK</h1>

      <div className="my-6 h-px w-full bg-[#E4E4E7]" />

      {/* Form */}
      <div className="flex max-w-[560px] flex-col gap-6">
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-foreground">
            名称 <span className="text-[#DC2626]">*</span>
          </label>
          <input
            className={`h-10 rounded-lg border bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A] ${
              errors.name ? 'border-[#DC2626]' : 'border-[#E4E4E7]'
            }`}
            placeholder="请输入渠道名称"
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              if (errors.name) setErrors((prev) => ({ ...prev, name: '' }))
            }}
            maxLength={64}
          />
          {errors.name && <span className="text-xs text-[#DC2626]">{errors.name}</span>}
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-foreground">描述</label>
          <textarea
            className="min-h-[80px] resize-none rounded-lg border border-[#E4E4E7] bg-white px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A]"
            placeholder="选填，用于内部识别"
            value={description}
            onChange={(e) => {
              setDescription(e.target.value)
              if (errors.description) setErrors((prev) => ({ ...prev, description: '' }))
            }}
            maxLength={500}
          />
          {errors.description && (
            <span className="text-xs text-[#DC2626]">{errors.description}</span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={handleSubmit} loading={createMutation.isPending}>
            下一步
          </Button>
          <Button variant="outline" onClick={() => router.push('/system/channels/web-sdk')}>
            取消
          </Button>
        </div>
      </div>
    </div>
  )
}
