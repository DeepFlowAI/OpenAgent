'use client'

import { type ReactNode, useEffect } from 'react'
import { cn } from '@/utils/classnames'
import { Button } from '@/app/components/base/button'

type ModalProps = {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  className?: string
}

export function Modal({ open, onClose, title, children, footer, className }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        className={cn(
          'relative z-10 w-[420px] rounded-xl border border-[#E5E5E5] bg-white p-6 shadow-[0_8px_24px_rgba(0,0,0,0.08)]',
          className
        )}
      >
        <h2 className="text-lg font-semibold text-[#1a1a1a]">{title}</h2>
        <div className="mt-5">{children}</div>
        {footer && <div className="mt-5 flex justify-end gap-3">{footer}</div>}
      </div>
    </div>
  )
}

type ConfirmModalProps = {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
  confirmText?: string
  cancelText?: string
  variant?: 'default' | 'destructive'
  loading?: boolean
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = '确定',
  cancelText = '取消',
  variant = 'default',
  loading,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {cancelText}
          </Button>
          <Button
            variant={variant === 'destructive' ? 'destructive' : 'default'}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmText}
          </Button>
        </>
      }
    >
      <p className="text-sm leading-relaxed text-[#737373]">{description}</p>
    </Modal>
  )
}
