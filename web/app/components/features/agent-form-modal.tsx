'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/utils/classnames'
import { Button } from '@/app/components/base/button'
import { IconX } from '@tabler/icons-react'

type AgentFormModalProps = {
  open: boolean
  onClose: () => void
  onSubmit: (data: { name: string; description: string }) => Promise<void>
  title: string
  initialValues?: { name: string; description: string }
  loading?: boolean
}

export function AgentFormModal({
  open,
  onClose,
  onSubmit,
  title,
  initialValues,
  loading,
}: AgentFormModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<{ name?: string; description?: string }>({})

  useEffect(() => {
    if (open) {
      setName(initialValues?.name ?? '')
      setDescription(initialValues?.description ?? '')
      setErrors({})
    }
  }, [open, initialValues])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  const validate = () => {
    const newErrors: { name?: string; description?: string } = {}
    const trimmed = name.trim()
    if (!trimmed) {
      newErrors.name = '请输入 Agent 名称'
    } else if (trimmed.length > 64) {
      newErrors.name = '名称不超过 64 个字符'
    }
    if (description.length > 256) {
      newErrors.description = '描述不超过 256 个字符'
    }
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    await onSubmit({ name: name.trim(), description })
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/25" onClick={onClose} />
      <div className="relative z-10 w-[480px] rounded-xl bg-white shadow-[0_8px_24px_rgba(0,0,0,0.09)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#ECECEC] px-6 py-5">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          <button
            onClick={onClose}
            className="text-[#999] transition-colors hover:text-foreground"
          >
            <IconX size={20} />
          </button>
        </div>

        {/* Form */}
        <div className="flex flex-col gap-5 px-6 py-6">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">
              Agent 名称 <span className="text-destructive">*</span>
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="请输入 Agent 名称"
              className={cn(
                'h-10 rounded-lg border bg-white px-3 text-sm text-foreground transition-colors placeholder:text-[#A3A3A3] focus:outline-none focus:ring-2',
                errors.name
                  ? 'border-destructive focus:ring-destructive/10'
                  : 'border-[#D4D4D4] focus:border-foreground focus:ring-foreground/10'
              )}
            />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="请输入描述（可选）"
              rows={4}
              className={cn(
                'rounded-lg border bg-white px-3 py-2.5 text-sm text-foreground transition-colors placeholder:text-[#A3A3A3] focus:outline-none focus:ring-2 resize-none',
                errors.description
                  ? 'border-destructive focus:ring-destructive/10'
                  : 'border-[#D4D4D4] focus:border-foreground focus:ring-foreground/10'
              )}
            />
            {errors.description && (
              <p className="text-xs text-destructive">{errors.description}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-[#ECECEC] px-6 py-4">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button onClick={handleSubmit} loading={loading}>
            确定
          </Button>
        </div>
      </div>
    </div>
  )
}
