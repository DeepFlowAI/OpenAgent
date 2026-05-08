'use client'

import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/utils/classnames'

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string
  error?: string
  hint?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-[#1a1a1a]"
          >
            {label}
            {props.required && <span className="ml-0.5 text-[#DC2626]">*</span>}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'h-11 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] transition-colors placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10 disabled:cursor-not-allowed disabled:bg-[#F5F5F5] disabled:text-[#737373]',
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
Input.displayName = 'Input'

export { Input }
export type { InputProps }
