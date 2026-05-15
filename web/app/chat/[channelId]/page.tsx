'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { get } from '@/service/base'
import { sendPublicChatMessage } from '@/service/use-chat'
import type { Conversation, ConversationTimelineResponse, StepTimelineItem } from '@/models/conversation'
import {
  useExternalStoreRuntime,
  AssistantRuntimeProvider,
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ActionBarPrimitive,
  AuiIf,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import {
  ThinkingBlockUI,
  ToolBlockUI,
  InlineContentUI,
  StreamingMarkdownContent,
  StreamingThinkingPlaceholder,
} from '@/app/components/features/chat-message-blocks'
import type { PublicChannel } from '@/models/channel'
import type { ChatMessage, ToolBlock } from '@/models/conversation'
import {
  IconPlus,
  IconX,
  IconAlignLeft,
  IconMessageChatbot,
  IconMessageCirclePlus,
  IconLoader2,
  IconArrowUp,
  IconArrowDown,
  IconCopy,
  IconCheck,
  IconMessageCircleQuestion,
  IconHeadset,
} from '@tabler/icons-react'

// ─── Types ────────────────────────────────────────────────

type AppearanceCfg = {
  favicon?: string
  pageTitle?: string
  logo?: string
  pcMemberLogo?: string
  mobileLogo?: string
  mobileMemberLogo?: string
  headerCustomButtonImage?: string
  headerCustomButtonUrl?: string
  headerMemberCustomButtonImage?: string
  headerMemberCustomButtonUrl?: string
  title?: string
  pcTitleColor?: string
  headerBgColor?: string
  headerTitleColor?: string
  historySidebarBgColor?: string
  historySidebarTextColor?: string
  historyItemActiveBgColor?: string
  historyItemHoverBgColor?: string
  messageAreaBgColor?: string
  pcEmptyStateImage?: string
  mobileEmptyStateImage?: string
  pcMemberEmptyStateImage?: string
  mobileMemberEmptyStateImage?: string
  sendMessageButtonBgColor?: string
  sendMessageButtonIconColor?: string
  stopMessageButtonBgColor?: string
  agentBubbleBgColor?: string
  agentBubbleTextColor?: string
  agentBubbleBorderColor?: string
  agentBubbleRadius?: string
  agentAvatar?: string
  userAvatar?: string
  userBubbleBgColor?: string
  userBubbleTextColor?: string
  userBubbleBorderColor?: string
  userBubbleRadius?: string
  embedButtonBgColor?: string
  embedButtonIconColor?: string
  // Sidebar footer (company intro & links)
  sidebarFooterLogos?: string[]
  sidebarFooterIntro?: string
  sidebarFooterSubtext?: string
  sidebarFooterLinkLabel?: string
  sidebarFooterLinkUrl?: string
}

type BehaviorCfg = {
  inputPlaceholder?: string
}

type StoredConv = {
  id: number
  title: string
  conversationId: number
  messages: ChatMessage[]
}

// ─── localStorage helpers ─────────────────────────────────

const STORAGE_KEY_PREFIX = 'openagent_chat_'
const ANON_USER_KEY = 'openagent_anon_uid'

// Legacy keys from before the OpenAgent rename. Read-only fallback so users
// who chatted under the previous build keep their anon id and history; the
// migration copies into the new key on first read and removes the old one.
const LEGACY_STORAGE_KEY_PREFIX = 'newagent_chat_'
const LEGACY_ANON_USER_KEY = 'newagent_anon_uid'

function getOrCreateAnonUserId(): string {
  try {
    const existing = localStorage.getItem(ANON_USER_KEY)
    if (existing) return existing
    const legacy = localStorage.getItem(LEGACY_ANON_USER_KEY)
    if (legacy) {
      localStorage.setItem(ANON_USER_KEY, legacy)
      localStorage.removeItem(LEGACY_ANON_USER_KEY)
      return legacy
    }
    const uid = `anon_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`
    localStorage.setItem(ANON_USER_KEY, uid)
    return uid
  } catch {
    return `anon_${Date.now()}`
  }
}

function getStorageKey(channelId: number) {
  return `${STORAGE_KEY_PREFIX}${channelId}`
}

function loadConversations(channelId: number): StoredConv[] {
  try {
    let raw = localStorage.getItem(getStorageKey(channelId))
    if (!raw) {
      const legacyKey = `${LEGACY_STORAGE_KEY_PREFIX}${channelId}`
      raw = localStorage.getItem(legacyKey)
      if (raw) {
        localStorage.setItem(getStorageKey(channelId), raw)
        localStorage.removeItem(legacyKey)
      }
    }
    if (!raw) return []
    return JSON.parse(raw) as StoredConv[]
  } catch {
    return []
  }
}

function saveConversations(channelId: number, convs: StoredConv[]) {
  try {
    localStorage.setItem(getStorageKey(channelId), JSON.stringify(convs.slice(0, 50)))
  } catch { /* quota exceeded */ }
}

let _counter = 0
function genId() { return `msg_${Date.now()}_${++_counter}` }

// `100dvh` (dynamic viewport) tracks the mobile address bar show/hide so the
// composer stays inside the visible area without external scroll. We do NOT
// bind to `visualViewport.height` here: on some Android browsers it lags
// behind URL bar transitions and leaves a large gap below the composer.
const CHAT_VIEWPORT_STYLE = { height: '100dvh' } as const

// ─── Reconstruct ChatMessage[] from server timeline steps ──

function stepsToMessages(steps: StepTimelineItem[]): ChatMessage[] {
  const messages: ChatMessage[] = []
  let currentAssistant: ChatMessage | null = null
  let timelineCounter = 0

  for (const step of steps) {
    if (step.step_type === 'user_message') {
      // Flush previous assistant message
      if (currentAssistant) {
        messages.push(currentAssistant)
        currentAssistant = null
      }
      messages.push({
        id: `srv_user_${step.id}`,
        role: 'user',
        content: step.content || '',
        timestamp: step.created_at
          ? new Date(step.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : '',
        isStreaming: false,
        thinkingBlocks: [],
        contentBlocks: [],
        toolBlocks: [],
        llmStepId: null,
        assistantStepId: null,
      })
      timelineCounter = 0
    } else if (step.step_type === 'assistant_message') {
      const ts = step.created_at
        ? new Date(step.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        : ''
      if (!currentAssistant) {
        currentAssistant = {
          id: `srv_asst_${step.id}`,
          role: 'assistant',
          content: step.content || '',
          timestamp: ts,
          isStreaming: false,
          thinkingBlocks: [],
          contentBlocks: [{
            id: `srv_cb_${step.id}`,
            content: step.content || '',
            llmStepId: null,
            isStreaming: false,
            timelineIndex: ++timelineCounter,
          }],
          toolBlocks: [],
          llmStepId: null,
          assistantStepId: step.id,
        }
      } else {
        currentAssistant.content = step.content || ''
        currentAssistant.timestamp = ts
        currentAssistant.assistantStepId = step.id
        currentAssistant.contentBlocks.push({
          id: `srv_cb_${step.id}`,
          content: step.content || '',
          llmStepId: currentAssistant.llmStepId,
          isStreaming: false,
          timelineIndex: ++timelineCounter,
        })
      }
    } else if (step.step_type === 'llm_call') {
      if (!currentAssistant) {
        currentAssistant = {
          id: `srv_asst_r${step.round_number}`,
          role: 'assistant',
          content: '',
          timestamp: '',
          isStreaming: false,
          thinkingBlocks: [],
          contentBlocks: [],
          toolBlocks: [],
          llmStepId: step.id,
          assistantStepId: null,
        }
      }
      currentAssistant.llmStepId = step.id
      // Only extract thinking content from llm_call; the reply content
      // comes from the assistant_message step to avoid duplication.
      if (step.thinking_content) {
        currentAssistant.thinkingBlocks.push({
          id: `srv_think_${step.id}`,
          content: step.thinking_content,
          llmStepId: step.id,
          isStreaming: false,
          timelineIndex: ++timelineCounter,
        })
      }
    } else if (step.step_type === 'tool_call') {
      if (!currentAssistant) {
        currentAssistant = {
          id: `srv_asst_r${step.round_number}`,
          role: 'assistant',
          content: '',
          timestamp: '',
          isStreaming: false,
          thinkingBlocks: [],
          contentBlocks: [],
          toolBlocks: [],
          llmStepId: null,
          assistantStepId: null,
        }
      }
      currentAssistant.toolBlocks.push({
        id: `srv_tool_${step.id}`,
        toolName: step.tool_name || '',
        brief: step.brief || '',
        toolCallId: step.tool_call_id || '',
        stepId: step.id,
        llmStepId: step.parent_step_id,
        isExecuting: false,
        timelineIndex: ++timelineCounter,
      })
    }
  }
  // Flush last assistant message
  if (currentAssistant) {
    messages.push(currentAssistant)
  }
  return messages
}

// ─── Custom icons matching design spec ────────────────────

// ─── Radius helper ────────────────────────────────────────

function parseRadius(v?: string, fallback = '10') {
  const val = v || fallback
  const parts = val.trim().split(/\s+/)
  if (parts.length === 4) return parts.map(p => `${p}px`).join(' ')
  return `${parts[0]}px`
}

function HeaderCustomButton({ imageUrl, href }: { imageUrl: string; href: string }) {
  const [failed, setFailed] = useState(false)
  const img = (imageUrl || '').trim()
  if (!img || failed) return null
  const rawHref = (href || '').trim()
  const isHttp = /^https?:\/\//i.test(rawHref)
  const className =
    'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-black/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-black/20 [-webkit-tap-highlight-color:transparent]'
  const inner = (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={img}
      alt=""
      className="max-h-7 max-w-7 object-contain"
      onError={() => setFailed(true)}
    />
  )
  if (isHttp) {
    return (
      <a
        href={rawHref}
        target="_blank"
        rel="noopener noreferrer"
        className={className}
        aria-label="自定义链接"
      >
        {inner}
      </a>
    )
  }
  return <span className={className}>{inner}</span>
}

// ─── Sidebar content (shared desktop + overlay) ───────────

function SidebarContent({
  appearance,
  logoSrc,
  titleText,
  titleColor,
  headerCustomButtonImage,
  headerCustomButtonUrl,
  isEmbed,
  storedConvs,
  activeConvId,
  onNewChat,
  onSwitchConv,
}: {
  appearance: AppearanceCfg
  logoSrc: string
  titleText: string
  titleColor: string
  headerCustomButtonImage: string
  headerCustomButtonUrl: string
  isEmbed: boolean
  storedConvs: StoredConv[]
  activeConvId: number | null
  onNewChat: () => void
  onSwitchConv: (conv: StoredConv) => void
}) {
  return (
    <>
      <div className="flex flex-col gap-4 px-5 pb-0 pt-4">
        <div className="flex min-h-0 min-w-0 items-center gap-2">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {logoSrc ? (
              <img
                src={logoSrc}
                alt=""
                className="max-h-8 h-auto w-auto max-w-full shrink-0 rounded object-contain"
              />
            ) : (
              <IconHeadset size={22} className="shrink-0" />
            )}
            {titleText ? (
              <span className="min-w-0 truncate text-base font-bold" style={{ color: titleColor }}>
                {titleText}
              </span>
            ) : null}
          </div>
          {isEmbed ? (
            <div className="shrink-0 md:hidden">
              <HeaderCustomButton imageUrl={headerCustomButtonImage} href={headerCustomButtonUrl} />
            </div>
          ) : (
            <HeaderCustomButton imageUrl={headerCustomButtonImage} href={headerCustomButtonUrl} />
          )}
        </div>
        <button
          type="button"
          className="flex h-10 w-full cursor-pointer items-center gap-2 rounded-xl border border-[#E5E5E5] bg-white px-4 shadow-[0_1px_4px_rgba(0,0,0,0.055)] outline-none ring-0 [-webkit-tap-highlight-color:transparent] focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 active:outline-none active:ring-0"
          onClick={onNewChat}
        >
          <IconPlus size={16} />
          <span className="text-sm font-medium">新建会话</span>
        </button>
      </div>
      <div className="flex flex-1 flex-col overflow-auto px-4 pt-4">
        <div className="pb-3.5">
          <span className="text-[11px] font-medium text-[#A3A3A3]">历史会话</span>
        </div>
        <div className="flex flex-col gap-[3px]">
          {storedConvs.filter(conv => conv.messages.length > 0).map((conv) => {
            const isActive = conv.conversationId === activeConvId
            return (
              <button
                type="button"
                key={conv.conversationId}
                className={cn(
                  'flex h-[38px] w-full cursor-pointer items-center gap-2 rounded-xl border px-3 text-left transition-colors',
                  'outline-none ring-0 [-webkit-tap-highlight-color:transparent]',
                  'focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0',
                  'active:outline-none active:ring-0 [&::-moz-focus-inner]:border-0',
                  isActive
                    ? 'border-[#E5E5E5] bg-white shadow-[0_1px_4px_rgba(0,0,0,0.055)]'
                    : 'border-transparent hover:bg-white/50',
                )}
                style={isActive ? { backgroundColor: appearance.historyItemActiveBgColor || '#FFFFFF' } : undefined}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.backgroundColor = appearance.historyItemHoverBgColor || 'rgba(255,255,255,0.5)'
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.backgroundColor = 'transparent'
                }}
                onClick={() => onSwitchConv(conv)}
              >
                <IconMessageCircleQuestion size={16} stroke={1.5} className={isActive ? 'shrink-0 text-[#1A1A1A]' : 'shrink-0 text-[#737373]'} />
                <span className={cn('truncate text-[13px]', isActive ? 'font-medium text-[#1A1A1A]' : 'text-[#737373]')}>
                  {conv.title || '新会话'}
                </span>
              </button>
            )
          })}
        </div>
      </div>
      <SidebarFooter appearance={appearance} />
    </>
  )
}

// ─── Sidebar footer (company intro + privacy link) ────────

function SidebarFooter({ appearance }: { appearance: AppearanceCfg }) {
  const logos = (appearance.sidebarFooterLogos || []).filter(s => (s || '').trim().length > 0)
  const intro = (appearance.sidebarFooterIntro || '').trim()
  const subtext = (appearance.sidebarFooterSubtext || '').trim()
  const linkLabel = (appearance.sidebarFooterLinkLabel || '').trim()
  const linkUrl = (appearance.sidebarFooterLinkUrl || '').trim()
  const showLink = Boolean(linkLabel) && Boolean(linkUrl)

  if (logos.length === 0 && !intro && !subtext && !showLink) return null

  return (
    <div className="flex shrink-0 flex-col gap-2 border-t border-black/5 px-5 pb-4 pt-3">
      {logos.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          {logos.map((src, idx) => (
            <SidebarFooterLogo key={`${src}-${idx}`} src={src} />
          ))}
        </div>
      )}
      {intro && (
        <span className="text-[12px] leading-snug">{intro}</span>
      )}
      {subtext && (
        <span className="text-[11px] leading-snug text-[#A3A3A3]">{subtext}</span>
      )}
      {showLink && (
        <a
          href={linkUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="self-start text-[12px] underline-offset-2 hover:underline"
        >
          {linkLabel}
        </a>
      )}
    </div>
  )
}

function SidebarFooterLogo({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      className="h-auto w-auto min-w-0 max-w-full object-contain"
      onError={() => setFailed(true)}
    />
  )
}

// ─── Main Page ────────────────────────────────────────────

export default function ChatPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const channelToken = params.channelId as string
  const embedParam = (searchParams.get('embed') || '').toLowerCase()
  const isEmbed = embedParam === '1' || embedParam === 'true' || embedParam === 'yes'
  const embedToken = searchParams.get('token') || null
  const isMember = Boolean(embedToken?.trim())

  const [channel, setChannel] = useState<PublicChannel | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const [storedConvs, setStoredConvs] = useState<StoredConv[]>([])
  const [activeConvId, setActiveConvId] = useState<number | null>(null)
  const [anonUserId] = useState(() => getOrCreateAnonUserId())

  const abortRef = useRef<AbortController | null>(null)
  const currentAssistantRef = useRef<string | null>(null)
  const lastLlmStepIdRef = useRef<number | null>(null)
  const timelineCounterRef = useRef(0)
  const conversationIdRef = useRef<number | null>(null)

  const appearance = useMemo<AppearanceCfg>(() => {
    const cfg = channel?.config as Record<string, unknown> | undefined
    return ((cfg?.appearance ?? {}) as AppearanceCfg)
  }, [channel])
  const titleText = (appearance.title || '').trim()
  const pcTitleColor = appearance.pcTitleColor || appearance.headerTitleColor || '#1A1A1A'
  const mobileTitleColor = appearance.headerTitleColor || '#1A1A1A'
  const defaultPcLogo = appearance.logo || ''
  const sidebarLogo = isMember
    ? (appearance.pcMemberLogo || defaultPcLogo)
    : defaultPcLogo
  const defaultMobileLogo = appearance.mobileLogo || appearance.logo || ''
  const mobileHeaderLogo = isMember
    ? (appearance.mobileMemberLogo || defaultMobileLogo)
    : defaultMobileLogo
  const defaultPcEmptyStateImage = (appearance.pcEmptyStateImage || '').trim() || sidebarLogo
  const defaultMobileEmptyStateImage = (appearance.mobileEmptyStateImage || '').trim() || mobileHeaderLogo
  const pcEmptyStateImage = isMember
    ? ((appearance.pcMemberEmptyStateImage || '').trim() || defaultPcEmptyStateImage)
    : defaultPcEmptyStateImage
  const mobileEmptyStateImage = isMember
    ? ((appearance.mobileMemberEmptyStateImage || '').trim() || defaultMobileEmptyStateImage)
    : defaultMobileEmptyStateImage

  const headerCustomBtnImg = (appearance.headerCustomButtonImage || '').trim()
  const headerMemberCustomBtnImg = (appearance.headerMemberCustomButtonImage || '').trim()
  const headerCustomBtnUrl = (appearance.headerCustomButtonUrl || '').trim()
  const headerMemberCustomBtnUrl = (appearance.headerMemberCustomButtonUrl || '').trim()
  const resolvedHeaderCustomImage = isMember
    ? (headerMemberCustomBtnImg || headerCustomBtnImg)
    : headerCustomBtnImg
  const resolvedHeaderCustomUrl = isMember
    ? (headerMemberCustomBtnUrl || headerCustomBtnUrl)
    : headerCustomBtnUrl

  const behavior = useMemo<BehaviorCfg>(() => {
    const cfg = channel?.config as Record<string, unknown> | undefined
    return ((cfg?.behavior ?? {}) as BehaviorCfg)
  }, [channel])

  const agentId = channel?.agent_id ?? null

  const channelId = channel?.id ?? 0

  useEffect(() => {
    get<PublicChannel>(`v1/public/channels/${channelToken}`)
      .then((ch) => { setChannel(ch); setLoading(false) })
      .catch(() => { setError('渠道不存在或已被删除'); setLoading(false) })
  }, [channelToken])

  // Load conversation history from server using anonymous user ID
  useEffect(() => {
    if (!channelId) return
    // First load from localStorage cache for instant display
    setStoredConvs(loadConversations(channelId))
    // Then fetch from server for authoritative data
    const userId = embedToken ? null : anonUserId
    if (!userId) return
    get<Conversation[]>(`v1/public/channels/${channelToken}/conversations?external_user_id=${encodeURIComponent(userId)}`)
      .then(async (convs) => {
        if (convs.length === 0) return
        // Fetch steps for each conversation and reconstruct messages
        const rebuilt: StoredConv[] = await Promise.all(
          convs.map(async (conv) => {
            try {
              const timeline = await get<ConversationTimelineResponse>(
                `v1/public/channels/${channelToken}/conversations/${conv.id}/steps`
              )
              return {
                id: conv.id,
                title: conv.title || '新会话',
                conversationId: conv.id,
                messages: stepsToMessages(timeline.steps),
              }
            } catch {
              return {
                id: conv.id,
                title: conv.title || '新会话',
                conversationId: conv.id,
                messages: [],
              }
            }
          })
        )
        const valid = rebuilt.filter(c => c.messages.length > 0)
        if (valid.length > 0) {
          setStoredConvs(valid)
          saveConversations(channelId, valid)
        }
      })
      .catch(() => { /* keep localStorage cache on network failure */ })
  }, [channelId, channelToken, anonUserId, embedToken])

  useEffect(() => {
    if (!channelId || storedConvs.length === 0) return
    saveConversations(channelId, storedConvs)
  }, [storedConvs, channelId])

  useEffect(() => {
    if (appearance.pageTitle && typeof document !== 'undefined') {
      document.title = appearance.pageTitle
    }
  }, [appearance.pageTitle])

  useEffect(() => {
    if (!appearance.favicon || typeof document === 'undefined') return
    let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement | null
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = appearance.favicon
  }, [appearance.favicon])

  const convertMessage = useCallback((msg: ChatMessage): ThreadMessageLike => {
    const base = { id: msg.id }
    if (msg.role === 'user') {
      return {
        ...base,
        role: 'user' as const,
        content: [{ type: 'text' as const, text: msg.content }],
      }
    }
    return {
      ...base,
      role: 'assistant' as const,
      content: [{ type: 'text' as const, text: msg.content || ' ' }],
      status: msg.isStreaming
        ? { type: 'running' as const }
        : { type: 'complete' as const, reason: 'stop' as const },
    }
  }, [])

  const handleNewMessage = useCallback(async (message: AppendMessage) => {
    if (message.content[0]?.type !== 'text') return
    const text = message.content[0].text.trim()
    if (!text || !agentId) return

    setIsStreaming(true)

    const userMsg: ChatMessage = {
      id: genId(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      isStreaming: false,
      thinkingBlocks: [],
      contentBlocks: [],
      toolBlocks: [],
      llmStepId: null,
      assistantStepId: null,
    }

    const assistantId = genId()
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: '',
      isStreaming: true,
      thinkingBlocks: [],
      contentBlocks: [],
      toolBlocks: [],
      llmStepId: null,
      assistantStepId: null,
    }
    currentAssistantRef.current = assistantId
    timelineCounterRef.current = 0

    setMessages(prev => [...prev, userMsg, assistantMsg])

    const controller = sendPublicChatMessage(channelToken, text, conversationId, {
      onConversationCreated: (data) => {
        setConversationId(data.conversation_id)
        conversationIdRef.current = data.conversation_id
        setActiveConvId(data.conversation_id)
        const newStored: StoredConv = {
          id: data.conversation_id,
          title: text.slice(0, 30),
          conversationId: data.conversation_id,
          messages: [],
        }
        setStoredConvs(prev => [newStored, ...prev])
      },
      onThinkingDelta: (data) => {
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const blocks = [...m.thinkingBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + data.content }
            return { ...m, thinkingBlocks: blocks, retryStatus: null }
          }
          const closedContentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          blocks.push({
            id: `think_${Date.now()}`,
            content: data.content,
            llmStepId: null,
            isStreaming: true,
            timelineIndex: ++timelineCounterRef.current,
          })
          return { ...m, thinkingBlocks: blocks, contentBlocks: closedContentBlocks, retryStatus: null }
        }))
      },
      onContentDelta: (data) => {
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const blocks = [...m.contentBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + data.content }
          } else {
            blocks.push({
              id: `content_${Date.now()}`,
              content: data.content,
              llmStepId: lastLlmStepIdRef.current,
              isStreaming: true,
              timelineIndex: ++timelineCounterRef.current,
            })
          }
          return { ...m, content: m.content + data.content, contentBlocks: blocks, retryStatus: null }
        }))
      },
      onToolCall: (data) => {
        const toolBlock: ToolBlock = {
          id: `tool_${data.tool_call_id}`,
          toolName: data.tool_name,
          brief: data.brief,
          toolCallId: data.tool_call_id,
          stepId: data.step_id,
          llmStepId: lastLlmStepIdRef.current,
          isExecuting: true,
          timelineIndex: ++timelineCounterRef.current,
        }
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: lastLlmStepIdRef.current } : b
          )
          const contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: lastLlmStepIdRef.current } : b
          )
          return { ...m, thinkingBlocks: thinkBlocks, contentBlocks, toolBlocks: [...m.toolBlocks, toolBlock], retryStatus: null }
        }))
      },
      onToolResult: (data) => {
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const tools = m.toolBlocks.map(tb =>
            tb.toolCallId === data.tool_call_id ? { ...tb, isExecuting: false } : tb
          )
          return { ...m, toolBlocks: tools }
        }))
      },
      onLlmStepCreated: (data) => {
        lastLlmStepIdRef.current = data.step_id
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, llmStepId: data.step_id } : b
          )
          const contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, llmStepId: data.step_id } : b
          )
          return { ...m, thinkingBlocks: thinkBlocks, contentBlocks, llmStepId: data.step_id }
        }))
      },
      onDone: (data) => {
        const targetId = currentAssistantRef.current
        setMessages(prev => {
          const updated = prev.map(m => {
            if (m.id !== targetId) return m
            const finalContent = data.final_content
            const thinkBlocks = m.thinkingBlocks.map(b =>
              b.isStreaming ? { ...b, isStreaming: false, llmStepId: lastLlmStepIdRef.current } : b
            )
            let contentBlocks = m.contentBlocks.map(b =>
              b.isStreaming ? { ...b, isStreaming: false, llmStepId: lastLlmStepIdRef.current } : b
            )
            let content = m.content
            if (typeof finalContent === 'string') {
              const lastIdx = contentBlocks.length - 1
              if (lastIdx >= 0) {
                const previous = contentBlocks[lastIdx]
                contentBlocks = contentBlocks.map((b, idx) =>
                  idx === lastIdx ? { ...b, content: finalContent } : b
                )
                content = content.endsWith(previous.content)
                  ? `${content.slice(0, content.length - previous.content.length)}${finalContent}`
                  : finalContent
              } else if (finalContent) {
                contentBlocks = [{
                  id: `content_final_${Date.now()}`,
                  content: finalContent,
                  llmStepId: lastLlmStepIdRef.current,
                  isStreaming: false,
                  timelineIndex: ++timelineCounterRef.current,
                }]
                content = finalContent
              }
            }
            return {
              ...m,
              content,
              isStreaming: false,
              thinkingBlocks: thinkBlocks,
              contentBlocks,
              timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
              assistantStepId: data.assistant_step_id,
              retryStatus: null,
              errorMessage: null,
            }
          })
          const cid = conversationIdRef.current
          setStoredConvs(convs => convs.map(c =>
            c.conversationId === cid ? { ...c, messages: updated } : c
          ))
          return updated
        })
        setIsStreaming(false)
        currentAssistantRef.current = null
      },
      onRoundStart: (data) => {
        // Step-replay reconnect (sub-req 4): the server is reattaching us to
        // an existing round and will re-emit ALL its events from the top.
        // We MUST wipe the bubble first or the buffer-cold reconnect path
        // double-renders every delta.
        //
        // Buffer fast-path doesn't reach this branch — it slices `seq >
        // cursor` and skips the round_start frame entirely, so the existing
        // bubble stays and the missing tail just appends. That's the whole
        // point of sub-req 4: don't blank pixels the server is about to
        // confirm with increments.
        if (!data.resume) return
        const targetId = currentAssistantRef.current
        if (!targetId) return
        timelineCounterRef.current = 0
        lastLlmStepIdRef.current = null
        setMessages(prev => prev.map(m => {
          if (m.id !== targetId) return m
          return {
            ...m,
            content: '',
            isStreaming: true,
            thinkingBlocks: [],
            contentBlocks: [],
            toolBlocks: [],
            llmStepId: null,
            assistantStepId: null,
            retryStatus: null,
            errorMessage: null,
          }
        }))
      },
      onRetry: (attempt, maxAttempts) => {
        // Sub-req 4: surface "网络不稳，重连中 (n/max)" inline on the
        // assistant bubble so users understand the brief stall isn't a UI
        // bug. Do NOT wipe content here — SDK retries now carry
        // `last_event_id`, and the server's buffer fast-path replays just
        // the missing tail. Wiping would throw away pixels we're about to
        // append to. The step-replay path (cold buffer) clears via
        // `onRoundStart` above; in-stream RESET clears via `onAssistantReset`.
        const targetId = currentAssistantRef.current
        if (!targetId) return
        setMessages(prev => prev.map(m => {
          if (m.id !== targetId) return m
          return {
            ...m,
            retryStatus: { attempt, maxAttempts },
            errorMessage: null,
          }
        }))
      },
      onAssistantReset: () => {
        // Backend stream-level retry (stream-level retry spec): the LLM stream broke
        // mid-round and the engine is about to re-stream the SAME tool
        // round from scratch. Wipe the partial bubble so fresh deltas
        // land on a clean slate. (Distinct from onRoundStart: this fires
        // INSIDE one connection, not on reconnect.)
        const targetId = currentAssistantRef.current
        if (!targetId) return
        timelineCounterRef.current = 0
        lastLlmStepIdRef.current = null
        setMessages(prev => prev.map(m => {
          if (m.id !== targetId) return m
          return {
            ...m,
            content: '',
            isStreaming: true,
            thinkingBlocks: [],
            contentBlocks: [],
            toolBlocks: [],
            llmStepId: null,
            assistantStepId: null,
            retryStatus: null,
          }
        }))
      },
      onError: async (data) => {
        // Don't fold error into m.content — that hides "stream cut off mid-reply"
        // (m.content already had partial text → `||` swallowed the error). Keep
        // partial content as-is, surface the failure via a dedicated field, and
        // close out streaming flags on every block so the typewriter flushes.
        const targetId = currentAssistantRef.current
        setMessages(prev => {
          const updated = prev.map(m => {
            if (m.id !== targetId) return m
            const thinkBlocks = m.thinkingBlocks.map(b =>
              b.isStreaming ? { ...b, isStreaming: false } : b
            )
            const contentBlocks = m.contentBlocks.map(b =>
              b.isStreaming ? { ...b, isStreaming: false } : b
            )
            return {
              ...m,
              isStreaming: false,
              thinkingBlocks: thinkBlocks,
              contentBlocks,
              retryStatus: null,
              errorMessage: data.message || '连接中断，请稍后重试',
            }
          })
          const cid = conversationIdRef.current
          if (cid) {
            setStoredConvs(convs => convs.map(c =>
              c.conversationId === cid ? { ...c, messages: updated } : c
            ))
          }
          return updated
        })
        setIsStreaming(false)
        currentAssistantRef.current = null

        // Sub-req 4: ultimate-failure timeline reconciliation.
        //
        // On a final SSE failure we may still be one of two states:
        //   (a) Server actually completed the round and persisted a full
        //       assistant_message; only the SSE delivery to this client died.
        //   (b) Server gave up mid-stream, leaving partial llm_call rows.
        //
        // The public timeline endpoint already filters out `incomplete` steps
        // (sub-req 2), so anything it returns is publishable. If it has a
        // FRESHER complete answer than what our UI shows, swap it in and
        // clear the error banner — the user gets the answer back automatically
        // instead of being told to retry.
        const cidForRebuild = conversationIdRef.current
        if (cidForRebuild && targetId) {
          // Stash the captured cid; conversationIdRef may shift while we await.
          const capturedCid = cidForRebuild
          try {
            const data2 = await get<ConversationTimelineResponse>(
              `v1/public/channels/${channelToken}/conversations/${capturedCid}/steps`,
            )
            // Guard against late resolution after the user navigated to a
            // different conversation: discard stale rebuild payloads.
            if (conversationIdRef.current !== capturedCid) return
            const rebuilt = stepsToMessages(data2.steps)
            const lastServerAsst = [...rebuilt].reverse().find(m => m.role === 'assistant')
            if (!lastServerAsst || lastServerAsst.assistantStepId == null) return
            setMessages(prev => {
              const target = prev.find(m => m.id === targetId)
              if (!target) return prev

              // Anti-duplication guard: the public timeline filters out
              // `incomplete` steps, so if THIS round never persisted a
              // complete assistant_message the rebuilt timeline's "last
              // assistant" is actually the PREVIOUS round's answer. Without
              // this check we'd copy round N-1's content under round N's
              // user message. Reconcile only when the server's last assistant
              // step is NOT already rendered in another message bubble.
              const alreadyShown = prev.some(m =>
                m.id !== targetId
                && m.role === 'assistant'
                && m.assistantStepId === lastServerAsst.assistantStepId,
              )
              if (alreadyShown) return prev

              // Only replace when the server's answer is fresher: it must
              // have an assistant_step_id (= a complete assistant_message
              // step) and our local placeholder has no such id, OR our local
              // content is shorter than the server's (server saw more bytes
              // before the SSE dropped).
              const localComplete = target.assistantStepId != null
              const localContentLen = (target.content || '').length
              const serverContentLen = (lastServerAsst.content || '').length
              const shouldReplace =
                !localComplete || serverContentLen > localContentLen
              if (!shouldReplace) return prev
              const updated = prev.map(m => {
                if (m.id !== targetId) return m
                // Keep our client id stable so React keys / refs don't shuffle.
                return { ...lastServerAsst, id: m.id, retryStatus: null, errorMessage: null }
              })
              setStoredConvs(convs => convs.map(c =>
                c.conversationId === capturedCid ? { ...c, messages: updated } : c
              ))
              return updated
            })
          } catch {
            // Reconciliation is best-effort — keep the inline error banner.
          }
        }
      },
    }, embedToken, embedToken ? null : { external_user_id: anonUserId, source: 'chat' })

    abortRef.current = controller
    await controller.completion
  }, [agentId, conversationId, embedToken, anonUserId])

  const handleCancel = useCallback(async () => {
    abortRef.current?.abort()
    const targetId = currentAssistantRef.current
    if (targetId) {
      setMessages(prev => {
        const updated = prev.map(m => {
          if (m.id !== targetId) return m
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          const contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          return { ...m, isStreaming: false, thinkingBlocks: thinkBlocks, contentBlocks }
        })
        const cid = conversationIdRef.current
        if (cid) {
          setStoredConvs(convs => convs.map(c =>
            c.conversationId === cid ? { ...c, messages: updated } : c
          ))
        }
        return updated
      })
      currentAssistantRef.current = null
    }
    setIsStreaming(false)
  }, [])

  // Note: runtime is created inside ChatThreadView (keyed by activeConvId)
  // so it gets destroyed and recreated on conversation switch.

  const handleNewChat = useCallback(() => {
    if (isStreaming) {
      abortRef.current?.abort()
      setIsStreaming(false)
    }
    setMessages([])
    setConversationId(null)
    conversationIdRef.current = null
    setActiveConvId(null)
    currentAssistantRef.current = null
    lastLlmStepIdRef.current = null
    timelineCounterRef.current = 0
    setSidebarOpen(false)
  }, [isStreaming])

  const handleSwitchConv = useCallback((conv: StoredConv) => {
    if (conv.conversationId === conversationIdRef.current) return
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setIsStreaming(false)
    currentAssistantRef.current = null
    lastLlmStepIdRef.current = null
    timelineCounterRef.current = 0
    setMessages(conv.messages.map(m => ({ ...m })))
    setConversationId(conv.conversationId)
    conversationIdRef.current = conv.conversationId
    setActiveConvId(conv.conversationId)
    setSidebarOpen(false)
  }, [])

  const handleClose = useCallback(() => {
    if (isEmbed && typeof window !== 'undefined') {
      window.parent.postMessage({ type: 'openagent-close' }, '*')
    }
  }, [isEmbed])

  const defaultUserRadius = isEmbed ? '16 16 4 16' : '14 14 4 14'
  const defaultAgentRadius = isEmbed ? '4 16 16 16' : '4 14 14 14'

  // ── Loading / Error states ──

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center" style={CHAT_VIEWPORT_STYLE}>
        <IconLoader2 size={32} className="animate-spin text-[#A1A1AA]" />
      </div>
    )
  }

  if (error || !channel) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4" style={CHAT_VIEWPORT_STYLE}>
        <IconMessageChatbot size={48} className="text-[#A1A1AA]" />
        <p className="text-lg text-[#737373]">{error || '渠道未找到'}</p>
      </div>
    )
  }

  if (!agentId) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4" style={CHAT_VIEWPORT_STYLE}>
        <IconMessageChatbot size={48} className="text-[#A1A1AA]" />
        <p className="text-lg text-[#737373]">该渠道尚未绑定 Agent</p>
      </div>
    )
  }

  // ── Render ──

  return (
    <div className="flex h-screen overflow-hidden" style={CHAT_VIEWPORT_STYLE}>
      {/* ── Desktop sidebar (URL mode, ≥md) ── */}
      {!isEmbed && (
        <aside
          className="hidden w-[304px] shrink-0 flex-col border-r border-[#E5E5E5] md:flex"
          style={{
            backgroundColor: appearance.historySidebarBgColor || '#F5F5F5',
            color: appearance.historySidebarTextColor || '#1A1A1A',
          }}
        >
          <SidebarContent
            appearance={appearance}
            logoSrc={sidebarLogo}
            titleText={titleText}
            titleColor={pcTitleColor}
            headerCustomButtonImage={resolvedHeaderCustomImage}
            headerCustomButtonUrl={resolvedHeaderCustomUrl}
            isEmbed={isEmbed}
            storedConvs={storedConvs}
            activeConvId={activeConvId}
            onNewChat={handleNewChat}
            onSwitchConv={handleSwitchConv}
          />
        </aside>
      )}

      {/* ── Sidebar overlay (mobile URL + embed) ── */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/30" onClick={() => setSidebarOpen(false)} />
          <aside
            className="relative z-10 flex w-[304px] flex-col shadow-xl"
            style={{
              backgroundColor: appearance.historySidebarBgColor || '#F5F5F5',
              color: appearance.historySidebarTextColor || '#1A1A1A',
            }}
          >
            <div className="flex items-center justify-end px-3 pt-3">
              <button
                className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-black/5"
                onClick={() => setSidebarOpen(false)}
              >
                <IconX size={16} />
              </button>
            </div>
            <SidebarContent
              appearance={appearance}
              logoSrc={sidebarLogo}
              titleText={titleText}
              titleColor={pcTitleColor}
              headerCustomButtonImage={resolvedHeaderCustomImage}
              headerCustomButtonUrl={resolvedHeaderCustomUrl}
              isEmbed={isEmbed}
              storedConvs={storedConvs}
              activeConvId={activeConvId}
              onNewChat={handleNewChat}
              onSwitchConv={handleSwitchConv}
            />
          </aside>
        </div>
      )}

      {/* ── Main area ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header: always in embed; mobile-only in URL mode */}
        <header
          className={cn(
            'flex h-[64px] shrink-0 items-center border-b border-[#E5E5E5] px-3',
            isEmbed ? 'flex' : 'flex md:hidden',
          )}
          style={{
            backgroundColor: appearance.headerBgColor || '#FFFFFF',
            color: appearance.headerTitleColor || '#1A1A1A',
          }}
        >
          <div className="flex flex-1 items-center">
            <button
              type="button"
              className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-colors hover:bg-black/5"
              onClick={() => setSidebarOpen(true)}
            >
              <IconAlignLeft size={22} stroke={1.75} />
              <span className="text-[15px] font-medium leading-none">历史</span>
            </button>
          </div>
          <div className="flex min-w-0 flex-1 items-center justify-center px-1">
            {mobileHeaderLogo || titleText || (isEmbed && resolvedHeaderCustomImage) ? (
              <div className="flex min-w-0 max-w-full items-center justify-center gap-2">
                {mobileHeaderLogo ? (
                  // Slot is always 32px tall; object-contain may letterbox. With max-w on the slot,
                  // very wide logos scale down to fit width first, so the drawn bitmap can be shorter than 32px.
                  <div className="flex h-8 max-w-[240px] shrink-0 items-center justify-center">
                    <img
                      src={mobileHeaderLogo}
                      alt=""
                      className="block max-h-full max-w-full object-contain"
                    />
                  </div>
                ) : null}
                {titleText ? (
                  <span
                    className="truncate text-[17px] font-semibold leading-tight"
                    style={{ color: mobileTitleColor }}
                  >
                    {titleText}
                  </span>
                ) : null}
                {/* Mobile: custom button only in sidebar drawer; embed desktop (md+) keeps it in header center */}
                {isEmbed ? (
                  <div className="hidden shrink-0 md:flex">
                    <HeaderCustomButton
                      imageUrl={resolvedHeaderCustomImage}
                      href={resolvedHeaderCustomUrl}
                    />
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex flex-1 items-center justify-end gap-0.5">
            <button
              type="button"
              className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-black/5"
              onClick={handleNewChat}
              title="新建会话"
            >
              <IconMessageCirclePlus size={24} stroke={1.75} />
            </button>
            {isEmbed && (
              <button
                type="button"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-black/5"
                onClick={handleClose}
                title="关闭"
              >
                <IconX size={20} stroke={1.75} className="text-[#52525B]" />
              </button>
            )}
          </div>
        </header>

        {/* ── Thread ── */}
        <ChatThreadView
          key={activeConvId ?? 'new'}
          messages={messages}
          isStreaming={isStreaming}
          convertMessage={convertMessage}
          onNew={handleNewMessage}
          onCancel={handleCancel}
          appearance={appearance}
          titleText={titleText}
          pcEmptyStateImage={pcEmptyStateImage}
          mobileEmptyStateImage={mobileEmptyStateImage}
          pcTitleColor={pcTitleColor}
          mobileTitleColor={mobileTitleColor}
          behavior={behavior}
          isEmbed={isEmbed}
          defaultUserRadius={defaultUserRadius}
          defaultAgentRadius={defaultAgentRadius}
        />
      </div>
    </div>
  )
}

// ── Thread View (keyed by conversation, owns its own runtime) ──

function ChatThreadView({
  messages,
  isStreaming,
  convertMessage,
  onNew,
  onCancel,
  appearance,
  titleText,
  pcEmptyStateImage,
  mobileEmptyStateImage,
  pcTitleColor,
  mobileTitleColor,
  behavior,
  isEmbed,
  defaultUserRadius,
  defaultAgentRadius,
}: {
  messages: ChatMessage[]
  isStreaming: boolean
  convertMessage: (msg: ChatMessage) => ThreadMessageLike
  onNew: (message: AppendMessage) => Promise<void>
  onCancel: () => Promise<void>
  appearance: AppearanceCfg
  titleText: string
  pcEmptyStateImage: string
  mobileEmptyStateImage: string
  pcTitleColor: string
  mobileTitleColor: string
  behavior: BehaviorCfg
  isEmbed: boolean
  defaultUserRadius: string
  defaultAgentRadius: string
}) {
  const runtime = useExternalStoreRuntime({
    isRunning: isStreaming,
    messages,
    convertMessage,
    onNew,
    onCancel,
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
        {/*
          Library pattern (ThreadViewportFooter.tsx): Viewport = scrollport + autoScroll;
          ViewportFooter uses sticky bottom-0 so composer stays in the lower visible area while
          messages stream above. Same scroll element keeps autoScroll + ScrollToBottom in sync.
        */}
        <ThreadPrimitive.Viewport
          autoScroll
          className="flex min-h-0 flex-1 flex-col overflow-y-auto"
          style={{ backgroundColor: appearance.messageAreaBgColor || (isEmbed ? '#FFFFFF' : '#FAFAFA') }}
        >
            {/* ── Empty state: centered logo + title ── */}
            <AuiIf condition={(s) => s.thread.isEmpty}>
              <div className="flex min-h-full w-full flex-col items-center justify-center px-4 pb-6">
                {isEmbed ? (
                  <BrandEmptyState
                    logoSrc={mobileEmptyStateImage}
                    titleText={titleText}
                    titleColor={mobileTitleColor}
                    isEmbed={true}
                  />
                ) : (
                  <>
                    <div className="flex md:hidden">
                      <BrandEmptyState
                        logoSrc={mobileEmptyStateImage}
                        titleText={titleText}
                        titleColor={mobileTitleColor}
                        isEmbed={false}
                      />
                    </div>
                    <div className="hidden md:flex">
                      <BrandEmptyState
                        logoSrc={pcEmptyStateImage}
                        titleText={titleText}
                        titleColor={pcTitleColor}
                        isEmbed={false}
                      />
                    </div>
                  </>
                )}
              </div>
            </AuiIf>

            {/* ── Has messages: message list ── */}
            <AuiIf condition={(s) => !s.thread.isEmpty}>
              <div className="min-h-6 grow" />

              <div className={cn(
                'mx-auto w-full',
                isEmbed ? 'px-4 pb-5 pt-4' : 'max-w-[740px] px-4 pb-6 pt-6 md:px-0',
              )}>
                <div className="flex flex-col gap-4">
                  <ThreadPrimitive.Messages>
                    {({ message }) => {
                      const original = messages.find(m => m.id === message.id)
                      if (!original) return null
                      if (original.role === 'user') {
                        return (
                          <ChatUserMessage
                            message={original}
                            appearance={appearance}
                            isEmbed={isEmbed}
                            defaultRadius={defaultUserRadius}
                          />
                        )
                      }
                      return (
                        <ChatAssistantMessage
                          message={original}
                          appearance={appearance}
                          isEmbed={isEmbed}
                          defaultRadius={defaultAgentRadius}
                        />
                      )
                    }}
                  </ThreadPrimitive.Messages>
                </div>
              </div>
            </AuiIf>

          <ThreadPrimitive.ViewportFooter
            className={cn(
              'sticky bottom-0 z-10 w-full shrink-0',
              isEmbed
                ? 'px-3 pt-3 pb-[max(8px,env(safe-area-inset-bottom))]'
                : 'px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))] md:px-0',
            )}
            style={{
              backgroundColor: appearance.messageAreaBgColor || (isEmbed ? '#FFFFFF' : '#FAFAFA'),
            }}
          >
            <div className={cn('relative mx-auto w-full', isEmbed ? '' : 'max-w-[740px]')}>
              <ThreadPrimitive.ScrollToBottom className="absolute bottom-full left-1/2 z-10 mb-1 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-[#E4E4E7] bg-white text-[#71717A] shadow-sm transition-all hover:bg-[#F5F5F5] disabled:pointer-events-none disabled:opacity-0">
                <IconArrowDown size={14} />
              </ThreadPrimitive.ScrollToBottom>

              <ComposerPrimitive.Root className={cn(
                'relative z-0 flex w-full items-center rounded-full border border-[#E5E5E5] bg-white',
                isEmbed
                  ? 'gap-2 px-3.5 py-3 shadow-[0_-4px_16px_rgba(0,0,0,0.06)]'
                  : 'gap-2 px-3 py-3 shadow-[0_-2px_10px_rgba(0,0,0,0.07)]',
              )}>
                <ComposerPrimitive.Input
                  placeholder={behavior.inputPlaceholder || (isEmbed ? '提出问题...' : '请输入您的问题')}
                  rows={1}
                  className={cn(
                    'min-h-[24px] max-h-[120px] flex-1 resize-none bg-transparent leading-relaxed text-foreground outline-none placeholder:text-[#A3A3A3]',
                    isEmbed ? 'text-[13px]' : 'py-1 text-sm',
                  )}
                />
                <AuiIf condition={(s) => !s.thread.isRunning}>
                  <ComposerPrimitive.Send
                    className={cn(
                      'flex shrink-0 items-center justify-center rounded-full transition-colors',
                      isEmbed
                        ? 'h-8 w-8 disabled:!bg-[#E8E8E8] disabled:!text-[#737373]'
                        : 'h-9 w-9 disabled:opacity-40',
                    )}
                    style={{
                      backgroundColor: appearance.sendMessageButtonBgColor || '#1A1A1A',
                      color: appearance.sendMessageButtonIconColor || '#FFFFFF',
                    }}
                  >
                    <IconArrowUp size={isEmbed ? 14 : 16} />
                  </ComposerPrimitive.Send>
                </AuiIf>
                <AuiIf condition={(s) => s.thread.isRunning}>
                  <ComposerPrimitive.Cancel
                    className={cn(
                      'flex shrink-0 items-center justify-center rounded-full transition-colors',
                      isEmbed ? 'h-8 w-8' : 'h-9 w-9',
                    )}
                    style={{
                      backgroundColor: appearance.stopMessageButtonBgColor || '#DC2626',
                      color: appearance.sendMessageButtonIconColor || '#FFFFFF',
                    }}
                  >
                    <span className="block h-3 w-3 rounded-[2px] bg-current" />
                  </ComposerPrimitive.Cancel>
                </AuiIf>
              </ComposerPrimitive.Root>
            </div>
          </ThreadPrimitive.ViewportFooter>

        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  )
}

function BrandEmptyState({
  logoSrc,
  titleText,
  titleColor,
  isEmbed,
}: {
  logoSrc: string
  titleText: string
  titleColor: string
  isEmbed: boolean
}) {
  const hasTitle = Boolean(titleText)
  return (
    <div
      className={cn(
        // Match message column width so wide empty-state art can use full canvas
        'flex w-full max-w-[740px] flex-col items-center justify-center',
        hasTitle ? 'gap-4' : 'gap-0',
      )}
    >
      {logoSrc ? (
        <img
          src={logoSrc}
          alt=""
          className={cn(
            'h-auto w-auto max-w-full shrink-0 object-contain',
            isEmbed
              ? 'max-h-[min(36vh,240px)]'
              : 'max-h-[min(42vh,360px)] md:max-h-[min(48vh,420px)]',
          )}
        />
      ) : (
        <div className="flex h-[60px] w-[60px] shrink-0 items-center justify-center rounded-xl bg-[#F5F5F5]">
          <IconMessageChatbot size={32} className="text-[#A3A3A3]" />
        </div>
      )}
      {hasTitle ? (
        <span
          className={cn(
            'text-center font-semibold',
            isEmbed ? 'text-lg' : 'text-xl',
          )}
          style={{ color: titleColor }}
        >
          {titleText}
        </span>
      ) : null}
    </div>
  )
}

// ── User Message ─────────────────────────────────────────

function ChatUserMessage({
  message,
  appearance,
  isEmbed,
  defaultRadius,
}: {
  message: ChatMessage
  appearance: AppearanceCfg
  isEmbed: boolean
  defaultRadius: string
}) {
  const bubbleTextColor = appearance.userBubbleTextColor || '#FFFFFF'
  const configuredUserAvatar = (appearance.userAvatar || '').trim()
  const [userAvatarFailed, setUserAvatarFailed] = useState(false)
  const showUserAvatar = Boolean(configuredUserAvatar) && !userAvatarFailed

  useEffect(() => {
    setUserAvatarFailed(false)
  }, [configuredUserAvatar])

  return (
    <MessagePrimitive.Root className="group flex w-full justify-end">
      <div
        className={cn(
          'flex max-w-[80%] items-start justify-end',
          showUserAvatar && 'gap-2.5',
        )}
      >
        <div className="flex min-w-0 flex-col items-end gap-1">
          <div
            className={cn(
              'w-fit max-w-full min-w-0 whitespace-pre-wrap break-words leading-[26px]',
              isEmbed ? 'text-[13px]' : 'text-sm',
            )}
            style={{
              backgroundColor: appearance.userBubbleBgColor || '#1A1A1A',
              color: bubbleTextColor,
              borderColor: appearance.userBubbleBorderColor || 'transparent',
              borderWidth: '1px',
              borderStyle: 'solid',
              borderRadius: parseRadius(appearance.userBubbleRadius, defaultRadius),
              padding: '10px 12px',
            }}
          >
            {message.content}
          </div>
          {message.timestamp && (
            <span className="text-[11px] text-[#A3A3A3]">{message.timestamp}</span>
          )}
        </div>
        {showUserAvatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={configuredUserAvatar}
            alt=""
            aria-label="User avatar"
            className="h-[38px] w-[38px] shrink-0 rounded-full object-cover"
            onError={() => setUserAvatarFailed(true)}
          />
        ) : null}
      </div>
    </MessagePrimitive.Root>
  )
}

// ── Assistant Message ────────────────────────────────────

function ChatAssistantMessage({
  message,
  appearance,
  isEmbed,
  defaultRadius,
}: {
  message: ChatMessage
  appearance: AppearanceCfg
  isEmbed: boolean
  defaultRadius: string
}) {
  const contentBlocks = message.contentBlocks
  const lastIdx = contentBlocks.length - 1
  const bottomBlock = lastIdx >= 0 && (contentBlocks[lastIdx].isStreaming || !message.isStreaming)
    ? contentBlocks[lastIdx]
    : null
  const inlineContentBlocks = bottomBlock
    ? contentBlocks.slice(0, lastIdx)
    : [...contentBlocks]

  const bottomTextTrimmed = bottomBlock?.content?.trim() ?? ''
  const showReplyBubble =
    Boolean(bottomTextTrimmed) ||
    (message.isStreaming && (!bottomBlock || !bottomTextTrimmed))

  const bubbleTextColor = appearance.agentBubbleTextColor || (isEmbed ? '#3F3F46' : '#1A1A1A')

  const configuredAgentAvatar = (appearance.agentAvatar || '').trim()
  const [agentAvatarFailed, setAgentAvatarFailed] = useState(false)
  const showAgentAvatar = Boolean(configuredAgentAvatar) && !agentAvatarFailed

  useEffect(() => {
    setAgentAvatarFailed(false)
  }, [configuredAgentAvatar])

  return (
    <MessagePrimitive.Root
      className={cn('group flex w-full', showAgentAvatar && 'gap-2.5')}
    >
      {showAgentAvatar ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={configuredAgentAvatar}
          alt=""
          aria-label="Agent avatar"
          className="h-[38px] w-[38px] shrink-0 rounded-full object-cover"
          onError={() => setAgentAvatarFailed(true)}
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {message.retryStatus && (
          // Sub-req 4: weak-network reconnect indicator. Sits above the
          // streaming bubble area so users see it even when no partial
          // content has rendered yet. Cleared on first delta / done / error.
          <div
            className={cn(
              'flex w-fit items-center gap-1.5 self-start rounded-md border border-[#FCD34D] bg-[#FFFBEB] px-2 py-1',
              isEmbed ? 'text-[11px]' : 'text-[12px]',
            )}
            style={{ color: '#92400E' }}
            role="status"
            aria-live="polite"
          >
            <IconLoader2 size={12} className="animate-spin" />
            <span>
              {`网络不稳，重连中 (${message.retryStatus.attempt}/${message.retryStatus.maxAttempts})`}
            </span>
          </div>
        )}

        {[
          ...message.thinkingBlocks.map(b => ({ type: 'thinking' as const, block: b, idx: b.timelineIndex ?? 0 })),
          ...message.toolBlocks.map(b => ({ type: 'tool' as const, block: b, idx: b.timelineIndex ?? 0 })),
          ...inlineContentBlocks.map(b => ({ type: 'content' as const, block: b, idx: b.timelineIndex ?? 0 })),
        ]
          .sort((a, b) => a.idx - b.idx)
          .map(entry => {
            switch (entry.type) {
              case 'thinking':
                return <ThinkingBlockUI key={entry.block.id} block={entry.block} />
              case 'tool':
                return <ToolBlockUI key={entry.block.id} block={entry.block} />
              case 'content':
                return <InlineContentUI key={entry.block.id} block={entry.block} />
            }
          })
        }

        {showReplyBubble && (
          <div
            className={cn(
              'w-fit max-w-full min-w-0 self-start break-words',
              '[&_p]:m-0 [&_p+p]:mt-2 [&_ul]:my-1 [&_ol]:my-1',
              '[&>div]:min-h-[26px] [&>div]:leading-[26px]',
              '[&_p]:leading-[26px] [&_li]:leading-[26px]',
              isEmbed ? '[&>div]:text-[13px]' : '[&>div]:text-sm',
              // Override @uiw/react-markdown-preview markdown.css (.wmde-markdown 16px/1.5, .wmde-markdown p { margin-bottom: 10px })
              isEmbed ? '[&_.wmde-markdown]:!text-[13px]' : '[&_.wmde-markdown]:!text-sm',
              '[&_.wmde-markdown]:!leading-[26px]',
              '[&_.wmde-markdown_p]:!m-0',
            )}
            style={{
              backgroundColor: appearance.agentBubbleBgColor || (isEmbed ? '#FFFFFF' : '#F5F5F5'),
              color: bubbleTextColor,
              borderColor: appearance.agentBubbleBorderColor || '#E5E5E5',
              borderWidth: '1px',
              borderStyle: 'solid',
              borderRadius: parseRadius(appearance.agentBubbleRadius, defaultRadius),
              padding: '10px 12px',
            }}
          >
            {bottomTextTrimmed ? (
              <StreamingMarkdownContent
                source={bottomBlock!.content}
                isStreaming={bottomBlock!.isStreaming}
                style={{ color: bubbleTextColor }}
              />
            ) : (
              message.isStreaming && (
                <StreamingThinkingPlaceholder
                  className={cn(
                    'min-h-[26px] leading-[26px]',
                    isEmbed ? 'text-[13px]' : 'text-sm',
                  )}
                />
              )
            )}
          </div>
        )}

        {message.errorMessage && !message.isStreaming && (
          <div
            className={cn(
              'w-fit max-w-full self-start break-words rounded-md border border-[#FCA5A5] bg-[#FEF2F2] px-3 py-2 text-[#B91C1C]',
              isEmbed ? 'text-[12px]' : 'text-[13px]',
            )}
            role="alert"
          >
            {message.errorMessage}
          </div>
        )}

        {!message.isStreaming && bottomTextTrimmed && (
          <div className="mt-0.5 flex min-h-[18px] items-center gap-2 pb-0.5 text-[11px] text-[#A3A3A3]">
            {message.timestamp && <span>{message.timestamp}</span>}
            <ActionBarPrimitive.Root hideWhenRunning className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
              <ActionBarPrimitive.Copy className="group/copy flex items-center justify-center text-[#A3A3A3] transition-colors hover:text-[#71717A]">
                <IconCopy size={12} className="group-data-[copied]/copy:hidden" />
                <IconCheck size={12} className="hidden text-[#059669] group-data-[copied]/copy:block" />
              </ActionBarPrimitive.Copy>
            </ActionBarPrimitive.Root>
          </div>
        )}
      </div>
    </MessagePrimitive.Root>
  )
}
