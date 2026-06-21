import type { Metadata } from 'next'
import { QueryProvider } from '@/context/query-client'
import { ToastProvider } from '@/app/components/base/toast'
import SourceAttribution from '@/app/components/base/source-attribution'
import UpdateNotice from '@/app/components/update-notice'
import '@/styles/globals.css'

export const metadata: Metadata = {
  title: 'OpenAgent',
  description: 'OpenAgent Multi-tenant Management Platform',
  icons: {
    icon: '/favicon.svg',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>
        <QueryProvider>
          <ToastProvider>{children}</ToastProvider>
          <UpdateNotice />
        </QueryProvider>
        {/* AGPLv3 §13 source-availability notice — keep this on every page. */}
        <SourceAttribution />
      </body>
    </html>
  )
}
