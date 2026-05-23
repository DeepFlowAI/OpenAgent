'use client'

import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useParams, usePathname } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { useAgent } from '@/service/use-agent'
import { normalizeConversationSettings } from '@/utils/welcome-message'
import {
  IconChevronLeft,
  IconCpu,
  IconTool,
  IconMessages,
  IconChartBar,
} from '@tabler/icons-react'
import { ChatTestFab } from '@/app/components/features/chat-test-fab'
import { ChatTestDrawer } from '@/app/components/features/chat-test-drawer'

const secondNavItems = [
  {
    label: '核心引擎',
    segment: 'engine',
    icon: IconCpu,
  },
  {
    label: '工具管理',
    segment: 'tools',
    icon: IconTool,
  },
  {
    label: '会话记录',
    segment: 'conversations',
    icon: IconMessages,
  },
  {
    label: '会话报表',
    segment: 'conversation-report',
    icon: IconChartBar,
  },
]

const thirdNavItems = [
  { label: '基础设定', path: 'engine/basic' },
  { label: '预召回', path: 'engine/pre-recall' },
  { label: '消息预处理', path: 'engine/preprocessing' },
  { label: '对话设置', path: 'engine/conversation-settings' },
]

export default function AgentDetailLayout({ children }: { children: ReactNode }) {
  const params = useParams()
  const pathname = usePathname()
  const agentId = params.id as string
  const basePath = `/agent/agents/${agentId}`

  const { data: agent } = useAgent(Number(agentId))
  const [chatOpen, setChatOpen] = useState(false)
  const conversationSettings = useMemo(
    () => normalizeConversationSettings(agent?.engine_config?.conversation_settings),
    [agent],
  )

  const activeSecondNav = secondNavItems.find((item) =>
    pathname.includes(`/${item.segment}`)
  )
  const isEngineActive = activeSecondNav?.segment === 'engine'

  return (
    <div className="flex h-full">
      {/* Second-level nav */}
      <aside className="flex w-[200px] shrink-0 flex-col gap-1 border-r border-[#ECECEC] bg-[#FAFAFA] px-4 py-6">
        <Link
          href="/agent/agents"
          className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-[#F0F0F0]"
        >
          <IconChevronLeft size={16} className="text-[#71717A]" />
          <span className="truncate">{agent?.name || 'Agent'}</span>
        </Link>
        <div className="h-2" />
        {secondNavItems.map((item) => {
          const Icon = item.icon
          const href =
            item.segment === 'engine'
              ? `${basePath}/engine/basic`
              : `${basePath}/${item.segment}`
          const isActive = activeSecondNav?.segment === item.segment
          return (
            <Link
              key={item.segment}
              href={href}
              className={cn(
                'flex items-center gap-2 rounded-lg px-3 py-[10px] text-sm transition-colors',
                isActive
                  ? 'bg-[#F0F0F0] font-medium text-[#18181B]'
                  : 'text-[#71717A] hover:bg-[#F0F0F0] hover:text-[#18181B]'
              )}
            >
              <Icon size={18} />
              {item.label}
            </Link>
          )
        })}
      </aside>

      {/* Third-level nav (only for engine) */}
      {isEngineActive && (
        <aside className="flex w-[180px] shrink-0 flex-col gap-0.5 border-r border-[#ECECEC] bg-[#FAFAFA] px-3 py-6">
          <span className="px-3 text-[11px] font-semibold tracking-[1px] text-[#A1A1AA]">
            核心引擎
          </span>
          <div className="h-2" />
          {thirdNavItems.map((item) => {
            const href = `${basePath}/${item.path}`
            const isActive = pathname === href || pathname.startsWith(href + '/')
            return (
              <Link
                key={item.path}
                href={href}
                className={cn(
                  'rounded-md px-3 py-2 text-[13px] transition-colors',
                  isActive
                    ? 'bg-[#EDEDEF] font-medium text-[#18181B]'
                    : 'text-[#71717A] hover:bg-[#EDEDEF] hover:text-[#18181B]'
                )}
              >
                {item.label}
              </Link>
            )
          })}
        </aside>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-auto">{children}</div>

      {/* Chat test FAB + Drawer */}
      {!chatOpen && <ChatTestFab onClick={() => setChatOpen(true)} />}
      <ChatTestDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        agentId={Number(agentId)}
        conversationSettings={conversationSettings}
      />
    </div>
  )
}
