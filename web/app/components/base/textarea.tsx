'use client'

import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/utils/classnames'

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: string
  error?: string
  hint?: string
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, hint, id, ...props }, ref) => {
    const textareaId = id || label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={textareaId}
            className="text-sm font-medium text-[#1a1a1a]"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={cn(
            'min-h-[120px] rounded-lg border border-[#E5E5E5] bg-white px-3 py-3 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10 disabled:cursor-not-allowed disabled:bg-[#F5F5F5] disabled:text-[#737373]',
            error && 'border-[#DC2626] focus:border-[#DC2626] focus:ring-[#DC2626]/10',
            className
          )}
          {...props}
        />
        {error && <p className="text-xs text-[#DC2626]">{error}</p>}
        {hint && !error && <p className="text-xs text-[#A3A3A3]">{hint}</p>}
      </div>
    )
  }
)
Textarea.displayName = 'Textarea'

export { Textarea }
export type { TextareaProps }
