'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { PublicTab } from '@/models/help-center'
import { cn } from '@/utils/classnames'

export function TopNav({
  slug,
  tabs,
}: {
  slug: string
  tabs: PublicTab[]
}) {
  const pathname = usePathname()
  const showTabs = tabs.length >= 2

  if (!showTabs) return null

  const slugEnc = encodeURIComponent(slug)

  return (
    <nav
      aria-label="帮助中心版块"
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
    >
      <ul className="pointer-events-auto flex items-center gap-1">
        {tabs.map((t) => {
          const tabHref = `/hc/${slugEnc}/t/${encodeURIComponent(t.tab_slug)}`
          const active = pathname === tabHref || pathname.startsWith(`${tabHref}/`)
          return (
            <li key={t.id}>
              <Link
                href={tabHref}
                className={cn(
                  'inline-flex h-9 items-center rounded-full px-4 text-sm font-medium transition-colors',
                  active
                    ? 'bg-[#F5F5F5] text-[#1a1a1a]'
                    : 'text-[#525252] hover:bg-[#F5F5F5] hover:text-[#1a1a1a]',
                )}
              >
                {t.display_name}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
