'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { IconHome, IconBuilding, IconLogout } from '@tabler/icons-react'
import { AdminAuthGuard } from '@/app/components/base/admin-auth-guard'
import { useAdminAuthStore } from '@/context/admin-auth-store'

const navGroups = [
  {
    label: '管理',
    items: [
      { label: '租户管理', href: '/admin/tenants', icon: IconBuilding },
    ],
  },
]

export default function MainLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, clearAuth } = useAdminAuthStore()

  const handleLogout = () => {
    clearAuth()
    router.replace('/admin/login')
  }

  return (
    <AdminAuthGuard>
      <div className="flex h-screen">
        <aside className="flex w-60 flex-col border-r border-border bg-[#FAFAFA]">
          <div className="flex items-center gap-2.5 px-6 py-4">
            <IconHome size={24} className="text-foreground" />
            <span className="text-lg font-bold tracking-tight text-foreground">
              OpenAgent
            </span>
          </div>
          <nav className="flex-1 space-y-4 px-4 pt-2">
            {navGroups.map((group) => (
              <div key={group.label} className="space-y-1">
                <p className="px-2 text-xs font-medium text-muted-foreground">
                  {group.label}
                </p>
                {group.items.map((item) => {
                  const Icon = item.icon
                  const isActive = pathname.startsWith(item.href)
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-[#F0F0F0] text-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                      )}
                    >
                      <Icon size={18} />
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            ))}
          </nav>
          <div className="border-t border-border px-4 py-3">
            {user && (
              <p className="mb-2 truncate px-2.5 text-xs text-muted-foreground">
                {user.username}
              </p>
            )}
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <IconLogout size={18} />
              退出登录
            </button>
          </div>
        </aside>
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </AdminAuthGuard>
  )
}
