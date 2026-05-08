'use client'

import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/utils/classnames'

type SwitchProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> & {
  checked: boolean
  onChange: (checked: boolean) => void
}

const Switch = forwardRef<HTMLButtonElement, SwitchProps>(
  ({ checked, onChange, className, disabled, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-[22px] w-[40px] shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200',
        checked ? 'bg-[#18181B]' : 'bg-[#D4D4D8]',
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
      {...props}
    >
      <span
        className={cn(
          'pointer-events-none block h-[18px] w-[18px] rounded-full bg-white shadow-sm transition-transform duration-200',
          checked ? 'translate-x-[20px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  ),
)
Switch.displayName = 'Switch'

export { Switch }
