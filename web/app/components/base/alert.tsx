'use client'

import { IconX } from '@tabler/icons-react'
import { cn } from '@/utils/classnames'

type AlertProps = {
  children: React.ReactNode
  variant?: 'destructive' | 'default'
  className?: string
  /** When set, shows a dismiss control; caller clears state in onDismiss. */
  onDismiss?: () => void
}

export function Alert({
  children,
  variant = 'default',
  className,
  onDismiss,
}: AlertProps) {
  return (
    <div
      className={cn(
        'flex gap-3 rounded-lg border px-4 py-3 text-sm',
        variant === 'destructive'
          ? 'border-[#FCA5A5] bg-[#FEF2F2] text-[#DC2626]'
          : 'border-[#E5E5E5] bg-[#F5F5F5] text-[#1a1a1a]',
        className
      )}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className={cn(
            'shrink-0 rounded p-0.5 transition-colors',
            variant === 'destructive'
              ? 'text-[#DC2626] hover:bg-[#FECACA]/60'
              : 'text-[#737373] hover:bg-[#E5E5E5]'
          )}
          aria-label="关闭"
        >
          <IconX size={18} stroke={1.5} />
        </button>
      )}
    </div>
  )
}
