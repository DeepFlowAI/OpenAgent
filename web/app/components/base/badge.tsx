'use client'

import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/classnames'

const badgeVariants = cva(
  'inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium',
  {
    variants: {
      variant: {
        default: 'bg-[#F5F5F5] text-[#737373]',
        success: 'bg-[#ECFDF5] text-[#059669]',
        danger: 'bg-[#FEF2F2] text-[#DC2626]',
        warning: 'bg-[#FFFBEB] text-[#D97706]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, className }))} {...props} />
  )
}
