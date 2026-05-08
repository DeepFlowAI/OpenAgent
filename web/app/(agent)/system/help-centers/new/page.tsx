'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Textarea } from '@/app/components/base/textarea'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { useCreateHelpCenter } from '@/service/use-help-center'
import { IconArrowLeft } from '@tabler/icons-react'

export default function NewHelpCenterPage() {
  const router = useRouter()
  const { toast } = useToast()
  const createMutation = useCreateHelpCenter()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [nameError, setNameError] = useState<string | null>(null)

  const handleSubmit = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError('请输入帮助中心名称')
      return
    }
    try {
      const created = await createMutation.mutateAsync({
        name: trimmed,
        description: description.trim() || undefined,
      })
      toast('已创建', 'success')
      router.push(`/system/help-centers/${created.id}`)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <div style={{ padding: '40px 48px' }}>
      <Link
        href="/system/help-centers"
        className="inline-flex items-center gap-1 text-sm text-[#737373] transition-colors hover:text-foreground"
      >
        <IconArrowLeft size={16} />
        返回列表
      </Link>

      <h1 className="mt-4 text-2xl font-bold text-foreground">新建 Help Center</h1>

      <div className="mt-8 max-w-[640px]">
        <div className="flex flex-col gap-6">
          <Input
            label="名称"
            required
            value={name}
            placeholder="请输入帮助中心名称"
            maxLength={64}
            error={nameError ?? undefined}
            onChange={(e) => {
              setName(e.target.value)
              if (nameError) setNameError(null)
            }}
          />

          <Textarea
            label="描述"
            value={description}
            placeholder="选填，用于内部识别或列表展示"
            maxLength={500}
            rows={4}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="mt-8 flex items-center gap-3">
          <Button onClick={handleSubmit} loading={createMutation.isPending}>
            下一步
          </Button>
          <Link href="/system/help-centers">
            <Button variant="outline" disabled={createMutation.isPending}>
              取消
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
