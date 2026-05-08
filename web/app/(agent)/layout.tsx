'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { IconRocket, IconBook2, IconSettings, IconRobot, IconLogout } from '@tabler/icons-react'
import { AuthGuard } from '@/app/components/base/auth-guard'
import { useAuthStore } from '@/context/auth-store'

const navItems = [
  {
    label: 'Agent',
    href: '/agent/agents',
    icon: IconRobot,
  },
  {
    label: '知识空间',
    href: '/knowledge-space',
    icon: IconBook2,
  },
  {
    label: '系统管理',
    href: '/system',
    icon: IconSettings,
  },
]

export default function AgentLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { user, clearAuth } = useAuthStore()

  const handleLogout = () => {
    const tenantId = user?.tenant_id
    clearAuth()
    window.location.href = tenantId ? `/login?tenant=${tenantId}` : '/login'
  }

  return (
    <AuthGuard>
      <div className="flex h-screen">
        <aside className="flex w-16 flex-col items-center border-r border-border bg-surface py-5 gap-4">
          <Link href="/agent/agents" className="flex items-center justify-center">
            <IconRocket size={24} className="text-foreground" />
          </Link>
          <div className="h-px w-8 bg-[#E8E8E8]" />
          <nav className="flex flex-1 flex-col items-center gap-2">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = pathname.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={item.label}
                  className={cn(
                    'flex h-11 w-11 items-center justify-center rounded-[10px] transition-colors',
                    isActive
                      ? 'bg-accent text-foreground'
                      : 'text-[#999] hover:bg-accent hover:text-foreground'
                  )}
                >
                  <Icon size={22} />
                </Link>
              )
            })}
          </nav>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="flex h-11 w-11 items-center justify-center rounded-[10px] text-[#999] transition-colors hover:bg-accent hover:text-foreground"
          >
            <IconLogout size={22} />
          </button>
        </aside>
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </AuthGuard>
  )
}
