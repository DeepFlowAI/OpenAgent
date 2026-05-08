'use client'

import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/classnames'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20',
  {
    variants: {
      variant: {
        default:
          'bg-[#1a1a1a] text-white hover:bg-[#333] disabled:bg-[#D4D4D4] disabled:text-[#A3A3A3]',
        destructive:
          'bg-[#DC2626] text-white hover:bg-[#B91C1C] disabled:bg-[#D4D4D4] disabled:text-[#A3A3A3]',
        outline:
          'border border-[#E5E5E5] bg-white text-[#1a1a1a] hover:bg-[#F5F5F5] disabled:text-[#A3A3A3]',
        secondary:
          'bg-[#F5F5F5] text-[#1a1a1a] hover:bg-[#E5E5E5] disabled:text-[#A3A3A3]',
        ghost:
          'text-[#1a1a1a] hover:bg-[#F5F5F5]',
        link:
          'text-[#1a1a1a] underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-5 py-2',
        sm: 'h-9 px-3',
        lg: 'h-11 px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
)

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { loading?: boolean }

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg
          className="mr-2 h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  )
)
Button.displayName = 'Button'

export { Button, buttonVariants }
export type { ButtonProps }
