'use client'

import { IconRocket } from '@tabler/icons-react'

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="relative flex min-h-screen flex-col bg-[#F5F5F5]">
      <div className="absolute left-6 top-5 flex items-center gap-2">
        <IconRocket size={24} className="text-[#1a1a1a]" />
        <span className="text-lg font-bold tracking-tight text-[#1a1a1a]">
          OpenAgent
        </span>
      </div>

      <main className="flex flex-1 items-center justify-center px-4">
        {children}
      </main>
    </div>
  )
}
