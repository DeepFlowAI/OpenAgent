'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/utils/classnames'

// Version baked into THIS client bundle at build time (see web/Dockerfile).
const CURRENT_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || ''
const POLL_INTERVAL_MS = 3 * 60 * 1000
const DISMISS_KEY = 'newagent:update-dismissed-version'
// Visitor / embed-facing routes where a "site updated" prompt would be out of place.
const EXCLUDED_PREFIXES = ['/hc', '/chat/', '/welcome-embed']

async function fetchDeployedVersion(): Promise<string> {
  // Cache-busted + no-store so we always see the freshly deployed file.
  const res = await fetch(`/version.json?_=${Date.now()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`version.json ${res.status}`)
  const data = (await res.json()) as { version?: string }
  return data.version || ''
}

/**
 * Global "site updated, please refresh" notice. Polls the deployed
 * version.json and compares it to the version baked into the running bundle;
 * when they differ a new deploy has gone out and we prompt the user to reload.
 * Hidden on visitor-facing routes (help center / chat widget / embed).
 */
export default function UpdateNotice() {
  const pathname = usePathname()
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null)

  useEffect(() => {
    setDismissedVersion(localStorage.getItem(DISMISS_KEY))
  }, [])

  const isExcluded = EXCLUDED_PREFIXES.some((p) => pathname?.startsWith(p))
  // No baseline in dev (version unset) -> never nag.
  const enabled = !isExcluded && CURRENT_VERSION !== ''

  const { data: deployedVersion } = useQuery({
    queryKey: ['app-version'],
    queryFn: fetchDeployedVersion,
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
    staleTime: 0,
    retry: false,
  })

  if (!enabled) return null
  if (!deployedVersion || deployedVersion === CURRENT_VERSION) return null
  if (deployedVersion === dismissedVersion) return null

  return (
    <div className="fixed left-1/2 top-3 z-[1000] -translate-x-1/2">
      <div
        role="status"
        className={cn(
          'flex items-center gap-2 rounded-full border border-gray-200 bg-white/95 px-3 py-1.5',
          'text-sm text-gray-800 shadow-lg backdrop-blur'
        )}
      >
        <svg
          className="size-4 shrink-0 text-blue-600"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M21 12a9 9 0 1 1-2.64-6.36" />
          <path d="M21 3v6h-6" />
        </svg>
        <span className="whitespace-nowrap">网站已更新，请刷新</span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-medium text-white hover:bg-blue-700"
        >
          刷新
        </button>
        <button
          type="button"
          aria-label="关闭"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, deployedVersion)
            setDismissedVersion(deployedVersion)
          }}
          className="text-gray-400 hover:text-gray-700"
        >
          <svg
            className="size-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
