'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { IconKey, IconBroadcast, IconBook2, IconCalendarClock } from '@tabler/icons-react'

const secondNavItems = [
  {
    label: 'API 密钥',
    href: '/system/api-keys',
    icon: IconKey,
  },
  {
    label: '渠道',
    href: '/system/channels',
    icon: IconBroadcast,
  },
  {
    label: '服务时间',
    href: '/system/service-hours',
    icon: IconCalendarClock,
  },
  {
    label: '帮助中心',
    href: '/system/help-centers',
    icon: IconBook2,
  },
]

export default function SystemLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex h-full">
      <aside className="flex w-[200px] flex-col border-r border-[#ECECEC] bg-[#FAFAFA] px-4 py-6">
        <div className="px-2 pb-2">
          <span className="text-sm font-semibold text-[#18181B]">系统管理</span>
        </div>
        <div className="h-2" />
        <nav className="flex flex-col gap-1">
          {secondNavItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-[#F0F0F0] text-[#18181B]'
                    : 'text-[#737373] hover:bg-[#F0F0F0] hover:text-[#18181B]'
                )}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            )
          })}
        </nav>
      </aside>
      <div className="flex-1 overflow-auto">{children}</div>
    </div>
  )
}
