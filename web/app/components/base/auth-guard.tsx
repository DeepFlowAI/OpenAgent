'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const token = useAuthStore((s) => s.token)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true)
      return
    }

    const unsub = useAuthStore.persist.onFinishHydration(() => {
      setHydrated(true)
    })
    return unsub
  }, [])

  useEffect(() => {
    if (hydrated && !token) {
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`)
    }
  }, [hydrated, token, router, pathname])

  if (!hydrated || !token) return null

  return <>{children}</>
}
