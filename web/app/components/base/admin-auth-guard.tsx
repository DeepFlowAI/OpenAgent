'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAdminAuthStore } from '@/context/admin-auth-store'

export function AdminAuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const token = useAdminAuthStore((s) => s.token)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    if (useAdminAuthStore.persist.hasHydrated()) {
      setHydrated(true)
      return
    }

    const unsub = useAdminAuthStore.persist.onFinishHydration(() => {
      setHydrated(true)
    })
    return unsub
  }, [])

  useEffect(() => {
    if (hydrated && !token) {
      router.replace(`/admin/login?redirect=${encodeURIComponent(pathname)}`)
    }
  }, [hydrated, token, router, pathname])

  if (!hydrated || !token) return null

  return <>{children}</>
}
