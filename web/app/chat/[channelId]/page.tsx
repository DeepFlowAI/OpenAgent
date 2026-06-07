'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { get, getErrorMessage } from '@/service/base'
import {
  cancelPublicChatMessage,
  sendPublicChatMessage,
  type ChatEventHandlers,
  type ChatStreamController,
} from '@/service/use-chat'
import { submitPublicStepFeedback } from '@/service/use-feedback'
import type { Conversation, ConversationTimelineResponse, StepTimelineItem } from '@/models/conversation'
import type { FeedbackRating, StepFeedbackResponse } from '@/models/feedback'
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
  IntermediateSteps,
  MarkdownContent,
  StreamingMarkdownContent,
  StreamingThinkingPlaceholder,
} from '@/app/components/features/chat-message-blocks'
import { WelcomeEmbedFrame } from '@/app/components/features/welcome-embed-frame'
import {
  DEFAULT_CONVERSATION_SETTINGS,
  type ConversationSettingsConfig,
  type WelcomeMessageBlock,
} from '@/models/agent'
import type { PublicChannel } from '@/models/channel'
import type { ChatMessage, ToolBlock } from '@/models/conversation'
import {
  isValidWelcomeBlock,
  normalizeConversationSettings,
} from '@/utils/welcome-message'
import {
  getSamePageNavigationLinkProps,
  normalizeSamePageNavigationAllowlist,
} from '@/utils/same-page-navigation-allowlist'
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
  IconInfoCircle,
  IconThumbUp,
  IconThumbUpFilled,
  IconThumbDown,
  IconThumbDownFilled,
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
  feedbackEnabled?: boolean
}

type StoredConv = {
  id: number
  title: string
  conversationId: number
  messages: ChatMessage[]
}

type StreamTurnStatus =
  | 'active'
  | 'detached'
  | 'resuming'
  | 'done'
  | 'error'
  | 'cancelled'

type StreamTurn = {
  clientMessageId: string
  requestId: string
  conversationId: number | null
  userText: string
  userMessageId: string
  assistantMessageId: string
  messages: ChatMessage[]
  lastEventId: string | null
  lastLlmStepId: number | null
  timelineCounter: number
  status: StreamTurnStatus
  controller: ChatStreamController | null
  replayContentCursor: string | null
  replayThinkingCursor: string | null
}

function cloneMessage(message: ChatMessage): ChatMessage {
  return {
    ...message,
    thinkingBlocks: message.thinkingBlocks.map(block => ({ ...block })),
    contentBlocks: message.contentBlocks.map(block => ({ ...block })),
    toolBlocks: message.toolBlocks.map(block => ({ ...block })),
    retryStatus: message.retryStatus ? { ...message.retryStatus } : message.retryStatus,
  }
}

function cloneMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map(cloneMessage)
}

// Guards against messages persisted by older builds (or partially-shaped JSON)
// that predate the thinking/content/tool block model. Without this, the block
// `.map` calls in cloneMessage and the render path throw and take down the
// whole chat. Legacy assistant messages only carried `content`, so synthesize a
// single content block to keep their reply visible. Loaded history is never
// live, so force isStreaming off to avoid a stuck "thinking" state.
function normalizeChatMessage(message: ChatMessage): ChatMessage {
  const thinkingBlocks = Array.isArray(message.thinkingBlocks) ? message.thinkingBlocks : []
  const toolBlocks = Array.isArray(message.toolBlocks) ? message.toolBlocks : []
  let contentBlocks = Array.isArray(message.contentBlocks) ? message.contentBlocks : []
  if (contentBlocks.length === 0 && message.role === 'assistant' && message.content) {
    contentBlocks = [{
      id: `${message.id}_legacy_content`,
      content: message.content,
      llmStepId: null,
      isStreaming: false,
      timelineIndex: 0,
    }]
  }
  return {
    ...message,
    isStreaming: false,
    thinkingBlocks,
    contentBlocks,
    toolBlocks,
  }
}

function isPendingTurn(status: StreamTurnStatus) {
  return status === 'active' || status === 'detached' || status === 'resuming'
}

function isLiveTurn(status: StreamTurnStatus) {
  return status === 'active' || status === 'resuming'
}

function consumeReplayPrefix(
  turn: StreamTurn,
  kind: 'content' | 'thinking',
  existing: string,
  delta: string,
) {
  const key = kind === 'content' ? 'replayContentCursor' : 'replayThinkingCursor'
  const cursor = turn[key]
  if (cursor === null) return delta

  const replayedNext = cursor + delta
  if (existing.startsWith(replayedNext)) {
    turn[key] = replayedNext
    return ''
  }

  if (cursor.length < existing.length) {
    const remainingExisting = existing.slice(cursor.length)
    if (delta.startsWith(remainingExisting)) {
      turn[key] = null
      return delta.slice(remainingExisting.length)
    }
  }

  turn[key] = null
  return delta
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
    const parsed = JSON.parse(raw) as StoredConv[]
    if (!Array.isArray(parsed)) return []
    return parsed.map(conv => ({
      ...conv,
      messages: Array.isArray(conv.messages) ? conv.messages.map(normalizeChatMessage) : [],
    }))
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

function isToolCallLimitError(data: { code?: string; message?: string }) {
  return (
    data.code === 'tool_call_limit_exceeded' ||
    data.message === 'Exceeded maximum tool call rounds'
  )
}

function getToolCallLimitReply(
  data: { reply?: string },
  conversationSettings: ConversationSettingsConfig,
) {
  const eventReply = data.reply?.trim()
  if (eventReply) return eventReply
  const configured = conversationSettings.tool_call_limit_reply.content.trim()
  return configured || DEFAULT_CONVERSATION_SETTINGS.tool_call_limit_reply.content
}

function getEmbedExternalUserId(token: string | null): string | null {
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = `${base64}${'='.repeat((4 - base64.length % 4) % 4)}`
    const data = JSON.parse(atob(padded)) as { external_user_id?: unknown }
    return typeof data.external_user_id === 'string' && data.external_user_id
      ? data.external_user_id
      : null
  } catch {
    return null
  }
}

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
          feedbackRating: step.feedback_rating,
          feedbackComment: step.feedback_comment,
          feedbackUpdatedAt: step.feedback_updated_at,
        }
      } else {
        currentAssistant.content = step.content || ''
        currentAssistant.timestamp = ts
        currentAssistant.assistantStepId = step.id
        currentAssistant.feedbackRating = step.feedback_rating
        currentAssistant.feedbackComment = step.feedback_comment
        currentAssistant.feedbackUpdatedAt = step.feedback_updated_at
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

function HeaderCustomButton({
  imageUrl,
  href,
  samePageNavigationUrlAllowlist,
}: {
  imageUrl: string
  href: string
  samePageNavigationUrlAllowlist: readonly string[]
}) {
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
    const linkProps = getSamePageNavigationLinkProps(rawHref, samePageNavigationUrlAllowlist)
    return (
      <a
        href={rawHref}
        target={linkProps.target}
        rel={linkProps.rel}
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
  samePageNavigationUrlAllowlist,
  isEmbed,
  storedConvs,
  activeConvId,
  conversationStatuses,
  onNewChat,
  onSwitchConv,
}: {
  appearance: AppearanceCfg
  logoSrc: string
  titleText: string
  titleColor: string
  headerCustomButtonImage: string
  headerCustomButtonUrl: string
  samePageNavigationUrlAllowlist: readonly string[]
  isEmbed: boolean
  storedConvs: StoredConv[]
  activeConvId: number | null
  conversationStatuses: Map<number, StreamTurnStatus>
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
              <HeaderCustomButton
                imageUrl={headerCustomButtonImage}
                href={headerCustomButtonUrl}
                samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
              />
            </div>
          ) : (
            <HeaderCustomButton
              imageUrl={headerCustomButtonImage}
              href={headerCustomButtonUrl}
              samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
            />
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
            const status = conversationStatuses.get(conv.conversationId)
            const statusLabel = status === 'active' || status === 'detached' || status === 'resuming'
              ? '生成中'
              : status === 'error'
                ? '失败'
                : ''
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
                <span className={cn('min-w-0 flex-1 truncate text-[13px]', isActive ? 'font-medium text-[#1A1A1A]' : 'text-[#737373]')}>
                  {conv.title || '新会话'}
                </span>
                {statusLabel ? (
                  <span
                    className={cn(
                      'shrink-0 rounded-full px-1.5 py-0.5 text-[10px] leading-none',
                      status === 'error'
                        ? 'bg-[#FEF2F2] text-[#B91C1C]'
                        : 'bg-[#ECFDF5] text-[#047857]',
                    )}
                  >
                    {statusLabel}
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>
      </div>
      <SidebarFooter
        appearance={appearance}
        samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
      />
    </>
  )
}

// ─── Sidebar footer (company intro + privacy link) ────────

function SidebarFooter({
  appearance,
  samePageNavigationUrlAllowlist,
}: {
  appearance: AppearanceCfg
  samePageNavigationUrlAllowlist: readonly string[]
}) {
  const logos = (appearance.sidebarFooterLogos || []).filter(s => (s || '').trim().length > 0)
  const intro = (appearance.sidebarFooterIntro || '').trim()
  const subtext = (appearance.sidebarFooterSubtext || '').trim()
  const linkLabel = (appearance.sidebarFooterLinkLabel || '').trim()
  const linkUrl = (appearance.sidebarFooterLinkUrl || '').trim()
  const showLink = Boolean(linkLabel) && Boolean(linkUrl)
  const linkProps = showLink
    ? getSamePageNavigationLinkProps(linkUrl, samePageNavigationUrlAllowlist)
    : null

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
          target={linkProps?.target}
          rel={linkProps?.rel}
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

function isTruthyQueryParam(
  params: ReturnType<typeof useSearchParams>,
  name: string,
): boolean {
  for (const [key, value] of params.entries()) {
    if (
      key.toLowerCase() === name &&
      ['true', '1', 'yes'].includes(value.toLowerCase())
    ) {
      return true
    }
  }
  return false
}

function normalizeChannelSource(value: string | null): string | null {
  const normalized = value?.trim() ?? ''
  if (!normalized) return null
  if ([...normalized].length > 64) return null
  if (/[\u0000-\u001F\u007F]/u.test(normalized)) return null
  return normalized
}

function getChannelSourceQueryParam(
  params: ReturnType<typeof useSearchParams>,
): string | null {
  for (const [key, value] of params.entries()) {
    if (key === 'channel_source') {
      const normalized = normalizeChannelSource(value)
      if (normalized) return normalized
    }
  }
  return null
}

// ─── Main Page ────────────────────────────────────────────

export default function ChatPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const channelToken = params.channelId as string
  const embedParam = (searchParams.get('embed') || '').toLowerCase()
  const isEmbed = embedParam === '1' || embedParam === 'true' || embedParam === 'yes'
  const rawEmbedToken = searchParams.get('token')?.trim() || null
  const embedExternalUserId = useMemo(
    () => getEmbedExternalUserId(rawEmbedToken),
    [rawEmbedToken],
  )
  const embedToken = embedExternalUserId ? rawEmbedToken : null
  const isMember = Boolean(embedToken)
  const isTest = isTruthyQueryParam(searchParams, 'test')
  const channelSource = getChannelSourceQueryParam(searchParams)

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
  const [turnStatusVersion, setTurnStatusVersion] = useState(0)

  const abortRef = useRef<ChatStreamController | null>(null)
  const messagesRef = useRef<ChatMessage[]>([])
  const conversationIdRef = useRef<number | null>(null)
  const activeConversationIdRef = useRef<number | null>(null)
  const isStreamingRef = useRef(false)
  const turnsByClientMessageIdRef = useRef<Map<string, StreamTurn>>(new Map())
  const turnByConversationIdRef = useRef<Map<number, string>>(new Map())
  // Conversations created this session whose first round is pending a summary
  // title; on first-round done we schedule one delayed refresh to pick it up.
  const firstRoundConvIdsRef = useRef<Set<number>>(new Set())
  const summaryRefreshTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set())

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
  const defaultPcEmptyStateImage = (appearance.pcEmptyStateImage || '').trim()
  const defaultMobileEmptyStateImage = (appearance.mobileEmptyStateImage || '').trim()
  const pcEmptyStateImage = isMember
    ? (appearance.pcMemberEmptyStateImage || '').trim()
    : defaultPcEmptyStateImage
  const mobileEmptyStateImage = isMember
    ? (appearance.mobileMemberEmptyStateImage || '').trim()
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
  const samePageNavigationUrlAllowlist = useMemo(() => {
    const cfg = channel?.config as Record<string, unknown> | undefined
    const rawAllowlist = cfg?.samePageNavigationUrlAllowlist
    const result = normalizeSamePageNavigationAllowlist(
      Array.isArray(rawAllowlist)
        ? rawAllowlist.filter((item): item is string => typeof item === 'string')
        : null
    )
    return result.error ? [] : result.patterns
  }, [channel])
  const conversationSettings = useMemo(
    () => normalizeConversationSettings(channel?.conversation_settings),
    [channel],
  )

  const agentId = channel?.agent_id ?? null

  const channelId = channel?.id ?? 0
  const historyUserId = embedExternalUserId || anonUserId

  useEffect(() => {
    isStreamingRef.current = isStreaming
  }, [isStreaming])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    get<PublicChannel>(`v1/public/channels/${channelToken}`)
      .then((ch) => { setChannel(ch); setLoading(false) })
      .catch(() => { setError('渠道不存在或已被删除'); setLoading(false) })
  }, [channelToken])

  useEffect(() => {
    if (!isEmbed || loading || typeof window === 'undefined') return
    window.parent.postMessage({ type: 'openagent-ready' }, '*')
  }, [isEmbed, loading])

  const refreshConversations = useCallback(async (syncActive = false) => {
    if (!channelId) return
    if (!historyUserId) return
    try {
      const convs = await get<Conversation[]>(
        `v1/public/channels/${channelToken}/conversations?external_user_id=${encodeURIComponent(historyUserId)}`
      )
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
      const merged = rebuilt.map((conv) => {
        const turnId = turnByConversationIdRef.current.get(conv.conversationId)
        const turn = turnId ? turnsByClientMessageIdRef.current.get(turnId) : null
        return turn && isPendingTurn(turn.status)
          ? { ...conv, messages: cloneMessages(turn.messages) }
          : conv
      })
      setStoredConvs(merged)
      saveConversations(channelId, merged)

      const activeId = conversationIdRef.current
      if (syncActive && activeId && !isStreamingRef.current) {
        const active = merged.find(c => c.conversationId === activeId)
        if (active) {
          setMessages(cloneMessages(active.messages))
        }
      }
    } catch {
      /* keep localStorage cache on network failure */
    }
  }, [channelId, channelToken, historyUserId])

  // Load conversation history from server using the public user identity.
  useEffect(() => {
    if (!channelId) return
    setStoredConvs(loadConversations(channelId))
    void refreshConversations(false)
  }, [channelId, refreshConversations])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return

    const refreshOnReturn = () => {
      if (document.visibilityState !== 'visible') return
      void refreshConversations(true)
    }
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'openagent-open') {
        void refreshConversations(true)
      }
    }

    window.addEventListener('focus', refreshOnReturn)
    window.addEventListener('message', handleMessage)
    document.addEventListener('visibilitychange', refreshOnReturn)
    return () => {
      window.removeEventListener('focus', refreshOnReturn)
      window.removeEventListener('message', handleMessage)
      document.removeEventListener('visibilitychange', refreshOnReturn)
    }
  }, [refreshConversations])

  useEffect(() => {
    const timers = summaryRefreshTimersRef.current
    return () => {
      timers.forEach(clearTimeout)
      timers.clear()
    }
  }, [])

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

  const setActiveConversation = useCallback((id: number | null) => {
    setConversationId(id)
    setActiveConvId(id)
    conversationIdRef.current = id
    activeConversationIdRef.current = id
  }, [])

  const bumpTurnStatus = useCallback(() => {
    setTurnStatusVersion(version => version + 1)
  }, [])

  const persistTurnMessages = useCallback((turn: StreamTurn) => {
    const conversationIdValue = turn.conversationId
    if (conversationIdValue == null) return
    const snapshot = cloneMessages(turn.messages)
    setStoredConvs((convs) => {
      const existing = convs.find(c => c.conversationId === conversationIdValue)
      if (existing) {
        return convs.map(c =>
          c.conversationId === conversationIdValue ? { ...c, messages: snapshot } : c
        )
      }
      return [{
        id: conversationIdValue,
        title: turn.userText.slice(0, 30) || '新会话',
        conversationId: conversationIdValue,
        messages: snapshot,
      }, ...convs]
    })
  }, [])

  const syncTurnToActive = useCallback((turn: StreamTurn) => {
    if (activeConversationIdRef.current !== turn.conversationId) return
    const snapshot = cloneMessages(turn.messages)
    messagesRef.current = snapshot
    setMessages(snapshot)
    setIsStreaming(isLiveTurn(turn.status))
  }, [])

  const updateTurnMessages = useCallback((
    turn: StreamTurn,
    updater: (messages: ChatMessage[]) => ChatMessage[],
  ) => {
    turn.messages = updater(turn.messages)
    persistTurnMessages(turn)
    syncTurnToActive(turn)
  }, [persistTurnMessages, syncTurnToActive])

  const setTurnStatus = useCallback((turn: StreamTurn, status: StreamTurnStatus) => {
    turn.status = status
    bumpTurnStatus()
    syncTurnToActive(turn)
  }, [bumpTurnStatus, syncTurnToActive])

  const createTurnHandlers = useCallback((
    resolveClientMessageId: () => string,
  ): ChatEventHandlers => {
    const getTurn = () => turnsByClientMessageIdRef.current.get(resolveClientMessageId())

    const markActive = (turn: StreamTurn) => {
      if (turn.status === 'resuming') {
        turn.status = 'active'
        bumpTurnStatus()
      }
    }

    return {
      onConversationCreated: (data) => {
        const turn = getTurn()
        if (!turn) return
        const wasNewConversation = turn.conversationId == null
        turn.conversationId = data.conversation_id
        turnByConversationIdRef.current.set(data.conversation_id, turn.clientMessageId)
        if (wasNewConversation) {
          // New conversation → its first round generates a summary title async.
          firstRoundConvIdsRef.current.add(data.conversation_id)
        }

        const snapshot = cloneMessages(turn.messages)
        setStoredConvs((convs) => {
          const existing = convs.find(c => c.conversationId === data.conversation_id)
          if (existing) {
            return convs.map(c =>
              c.conversationId === data.conversation_id
                ? { ...c, title: c.title || turn.userText.slice(0, 30), messages: snapshot }
                : c
            )
          }
          return [{
            id: data.conversation_id,
            title: turn.userText.slice(0, 30) || '新会话',
            conversationId: data.conversation_id,
            messages: snapshot,
          }, ...convs]
        })

        if (
          wasNewConversation
          && abortRef.current?.clientMessageId === turn.clientMessageId
          && isLiveTurn(turn.status)
        ) {
          setActiveConversation(data.conversation_id)
        }
        syncTurnToActive(turn)
      },
      onRoundStart: (data) => {
        const turn = getTurn()
        if (!turn) return
        markActive(turn)
        if (data.resume) {
          turn.replayContentCursor = ''
          turn.replayThinkingCursor = ''
        }
        updateTurnMessages(turn, prev => prev.map(m =>
          m.id === turn.assistantMessageId
            ? { ...m, isStreaming: true, retryStatus: null, errorMessage: null }
            : m
        ))
      },
      onThinkingDelta: (data) => {
        const turn = getTurn()
        if (!turn) return
        markActive(turn)
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          const existingThinking = m.thinkingBlocks.map(block => block.content).join('')
          const content = consumeReplayPrefix(turn, 'thinking', existingThinking, data.content)
          if (!content) return { ...m, retryStatus: null }

          const blocks = [...m.thinkingBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + content }
            return { ...m, thinkingBlocks: blocks, retryStatus: null }
          }
          const closedContentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          blocks.push({
            id: `think_${Date.now()}`,
            content,
            llmStepId: turn.lastLlmStepId,
            isStreaming: true,
            timelineIndex: ++turn.timelineCounter,
          })
          return { ...m, thinkingBlocks: blocks, contentBlocks: closedContentBlocks, retryStatus: null }
        }))
      },
      onContentDelta: (data) => {
        const turn = getTurn()
        if (!turn) return
        markActive(turn)
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          const content = consumeReplayPrefix(turn, 'content', m.content || '', data.content)
          if (!content) return { ...m, retryStatus: null }

          const blocks = [...m.contentBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + content }
          } else {
            blocks.push({
              id: `content_${Date.now()}`,
              content,
              llmStepId: turn.lastLlmStepId,
              isStreaming: true,
              timelineIndex: ++turn.timelineCounter,
            })
          }
          return { ...m, content: m.content + content, contentBlocks: blocks, retryStatus: null }
        }))
      },
      onToolCall: (data) => {
        const turn = getTurn()
        if (!turn) return
        markActive(turn)
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          if (m.toolBlocks.some(tb => tb.toolCallId === data.tool_call_id)) {
            return { ...m, retryStatus: null }
          }
          const toolBlock: ToolBlock = {
            id: `tool_${data.tool_call_id}`,
            toolName: data.tool_name,
            brief: data.brief,
            toolCallId: data.tool_call_id,
            stepId: data.step_id,
            llmStepId: turn.lastLlmStepId,
            isExecuting: true,
            timelineIndex: ++turn.timelineCounter,
          }
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: turn.lastLlmStepId } : b
          )
          const contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: turn.lastLlmStepId } : b
          )
          return {
            ...m,
            thinkingBlocks: thinkBlocks,
            contentBlocks,
            toolBlocks: [...m.toolBlocks, toolBlock],
            retryStatus: null,
          }
        }))
      },
      onToolResult: (data) => {
        const turn = getTurn()
        if (!turn) return
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          const tools = m.toolBlocks.map(tb =>
            tb.toolCallId === data.tool_call_id ? { ...tb, isExecuting: false } : tb
          )
          return { ...m, toolBlocks: tools }
        }))
      },
      onLlmStepCreated: (data) => {
        const turn = getTurn()
        if (!turn) return
        turn.lastLlmStepId = data.step_id
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
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
        const turn = getTurn()
        if (!turn) return
        const snapshot = turn.controller?.getSnapshot()
        turn.lastEventId = snapshot?.lastEventId ?? turn.lastEventId
        turn.controller = null
        if (abortRef.current?.clientMessageId === turn.clientMessageId) {
          abortRef.current = null
        }
        setTurnStatus(turn, 'done')
        // After the first round of a new conversation completes,
        // the backend asynchronously generates a summary title. Schedule one
        // delayed refresh so it surfaces in-session without a manual return.
        const summaryConvId = turn.conversationId
        if (summaryConvId != null && firstRoundConvIdsRef.current.has(summaryConvId)) {
          firstRoundConvIdsRef.current.delete(summaryConvId)
          const timer = setTimeout(() => {
            summaryRefreshTimersRef.current.delete(timer)
            void refreshConversations(false)
          }, 3500)
          summaryRefreshTimersRef.current.add(timer)
        }
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          const finalContent = data.final_content
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: turn.lastLlmStepId } : b
          )
          let contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false, llmStepId: turn.lastLlmStepId } : b
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
                llmStepId: turn.lastLlmStepId,
                isStreaming: false,
                timelineIndex: ++turn.timelineCounter,
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
        }))
      },
      onRetry: (attempt, maxAttempts) => {
        const turn = getTurn()
        if (!turn) return
        updateTurnMessages(turn, prev => prev.map(m =>
          m.id === turn.assistantMessageId
            ? { ...m, retryStatus: { attempt, maxAttempts }, errorMessage: null }
            : m
        ))
      },
      onAssistantReset: () => {
        const turn = getTurn()
        if (!turn) return
        turn.timelineCounter = 0
        turn.lastLlmStepId = null
        turn.replayContentCursor = null
        turn.replayThinkingCursor = null
        updateTurnMessages(turn, prev => prev.map(m =>
          m.id === turn.assistantMessageId
            ? {
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
            : m
        ))
      },
      onError: async (data) => {
        const turn = getTurn()
        if (!turn) return
        const isToolLimit = isToolCallLimitError(data)
        const toolLimitReply = isToolLimit
          ? getToolCallLimitReply(data, conversationSettings)
          : null
        const snapshot = turn.controller?.getSnapshot()
        turn.lastEventId = snapshot?.lastEventId ?? turn.lastEventId
        turn.controller = null
        if (abortRef.current?.clientMessageId === turn.clientMessageId) {
          abortRef.current = null
        }
        setTurnStatus(turn, isToolLimit ? 'done' : 'error')
        updateTurnMessages(turn, prev => prev.map((m) => {
          if (m.id !== turn.assistantMessageId) return m
          const thinkBlocks = m.thinkingBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          const contentBlocks = m.contentBlocks.map(b =>
            b.isStreaming ? { ...b, isStreaming: false } : b
          )
          const nextContentBlocks = [...contentBlocks]
          let content = m.content
          if (toolLimitReply) {
            nextContentBlocks.push({
              id: `content_limit_${Date.now()}`,
              content: toolLimitReply,
              llmStepId: turn.lastLlmStepId,
              isStreaming: false,
              timelineIndex: ++turn.timelineCounter,
            })
            content = content ? `${content}\n\n${toolLimitReply}` : toolLimitReply
          }
          const toolBlocks = m.toolBlocks.map(b =>
            b.isExecuting ? { ...b, isExecuting: false } : b
          )
          return {
            ...m,
            content,
            isStreaming: false,
            thinkingBlocks: thinkBlocks,
            contentBlocks: nextContentBlocks,
            toolBlocks,
            retryStatus: null,
            errorMessage: isToolLimit ? null : data.message || '连接中断，请稍后重试',
          }
        }))
        if (isToolLimit) return

        const capturedCid = turn.conversationId
        const targetId = turn.assistantMessageId
        if (!capturedCid) return
        try {
          const data2 = await get<ConversationTimelineResponse>(
            `v1/public/channels/${channelToken}/conversations/${capturedCid}/steps`,
          )
          const latestTurn = turnsByClientMessageIdRef.current.get(turn.clientMessageId)
          if (!latestTurn || latestTurn.conversationId !== capturedCid) return
          const rebuilt = stepsToMessages(data2.steps)
          const lastServerAsst = [...rebuilt].reverse().find(m => m.role === 'assistant')
          if (!lastServerAsst || lastServerAsst.assistantStepId == null) return

          let shouldReplace = false
          latestTurn.messages.forEach((m) => {
            if (m.id !== targetId) return
            const alreadyShown = latestTurn.messages.some(other =>
              other.id !== targetId
              && other.role === 'assistant'
              && other.assistantStepId === lastServerAsst.assistantStepId,
            )
            if (alreadyShown) return
            const localComplete = m.assistantStepId != null
            const localContentLen = (m.content || '').length
            const serverContentLen = (lastServerAsst.content || '').length
            shouldReplace = !localComplete || serverContentLen > localContentLen
          })
          if (!shouldReplace) return
          setTurnStatus(latestTurn, 'done')
          updateTurnMessages(latestTurn, prev => prev.map(m =>
            m.id === targetId
              ? { ...lastServerAsst, id: m.id, retryStatus: null, errorMessage: null }
              : m
          ))
        } catch {
          // Reconciliation is best-effort; keep the partial content plus error banner.
        }
      },
    }
  }, [
    bumpTurnStatus,
    channelToken,
    conversationSettings,
    refreshConversations,
    setActiveConversation,
    setTurnStatus,
    syncTurnToActive,
    updateTurnMessages,
  ])

  const detachActiveStream = useCallback(() => {
    const controller = abortRef.current
    if (!controller) return
    const turn = turnsByClientMessageIdRef.current.get(controller.clientMessageId)
    const snapshot = controller.detach()
    abortRef.current = null
    if (!turn || !isPendingTurn(turn.status)) return

    turn.requestId = snapshot.requestId
    turn.lastEventId = snapshot.lastEventId
    turn.conversationId = snapshot.conversationId ?? turn.conversationId
    if (turn.conversationId != null) {
      turnByConversationIdRef.current.set(turn.conversationId, turn.clientMessageId)
    }
    if (activeConversationIdRef.current === turn.conversationId) {
      turn.messages = cloneMessages(messagesRef.current)
    }
    turn.controller = null
    setTurnStatus(turn, 'detached')
    persistTurnMessages(turn)
  }, [persistTurnMessages, setTurnStatus])

  const resumeTurn = useCallback((turn: StreamTurn) => {
    if (!agentId || turn.status !== 'detached') return
    setTurnStatus(turn, 'resuming')
    const controller = sendPublicChatMessage(
      channelToken,
      turn.userText,
      turn.conversationId,
      createTurnHandlers(() => turn.clientMessageId),
      embedToken,
      null,
      undefined,
      undefined,
      {
        requestId: turn.requestId,
        clientMessageId: turn.clientMessageId,
        lastEventId: turn.lastEventId,
        resume: true,
      },
    )
    turn.controller = controller
    abortRef.current = controller
    void controller.completion.finally(() => {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (turn.controller === controller) {
        turn.controller = null
      }
    })
  }, [agentId, channelToken, createTurnHandlers, embedToken, setTurnStatus])

  const cancelActiveStream = useCallback(async () => {
    const controller = abortRef.current
    if (!controller) return
    const turn = turnsByClientMessageIdRef.current.get(controller.clientMessageId)
    const snapshot = controller.getSnapshot()
    abortRef.current = null
    controller.abort()
    await cancelPublicChatMessage(channelToken, controller.clientMessageId)

    if (!turn) return
    turn.requestId = snapshot.requestId
    turn.lastEventId = snapshot.lastEventId
    turn.conversationId = snapshot.conversationId ?? turn.conversationId
    turn.controller = null
    setTurnStatus(turn, 'cancelled')
    updateTurnMessages(turn, prev => prev.map((m) => {
      if (m.id !== turn.assistantMessageId) return m
      const thinkBlocks = m.thinkingBlocks.map(b =>
        b.isStreaming ? { ...b, isStreaming: false } : b
      )
      const contentBlocks = m.contentBlocks.map(b =>
        b.isStreaming ? { ...b, isStreaming: false } : b
      )
      return { ...m, isStreaming: false, thinkingBlocks: thinkBlocks, contentBlocks, retryStatus: null }
    }))
  }, [channelToken, setTurnStatus, updateTurnMessages])

  const handleNewMessage = useCallback(async (message: AppendMessage) => {
    if (message.content[0]?.type !== 'text') return
    const text = message.content[0].text.trim()
    if (!text || !agentId) return

    const existingTurnId = conversationId == null
      ? null
      : turnByConversationIdRef.current.get(conversationId)
    const existingTurn = existingTurnId
      ? turnsByClientMessageIdRef.current.get(existingTurnId)
      : null
    if (existingTurn && isPendingTurn(existingTurn.status)) {
      if (existingTurn.status === 'detached') resumeTurn(existingTurn)
      return
    }

    if (abortRef.current) {
      detachActiveStream()
    }

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
    const nextMessages = [...cloneMessages(messagesRef.current), userMsg, assistantMsg]
    messagesRef.current = nextMessages
    setMessages(nextMessages)
    setIsStreaming(true)

    let clientMessageId = ''
    const controller = sendPublicChatMessage(
      channelToken,
      text,
      conversationId,
      createTurnHandlers(() => clientMessageId),
      embedToken,
      embedToken
        ? (
            isTest || channelSource
              ? {
                  ...(isTest ? { is_test: true } : {}),
                  ...(channelSource ? { channel_source: channelSource } : {}),
                }
              : null
          )
        : {
            external_user_id: anonUserId,
            source: 'websdk',
            ...(channelSource ? { channel_source: channelSource } : {}),
            ...(isTest ? { is_test: true } : {}),
          },
    )
    clientMessageId = controller.clientMessageId
    const snapshot = controller.getSnapshot()
    const turn: StreamTurn = {
      clientMessageId: controller.clientMessageId,
      requestId: controller.requestId,
      conversationId: snapshot.conversationId,
      userText: text,
      userMessageId: userMsg.id,
      assistantMessageId: assistantId,
      messages: cloneMessages(nextMessages),
      lastEventId: snapshot.lastEventId,
      lastLlmStepId: null,
      timelineCounter: 0,
      status: 'active',
      controller,
      replayContentCursor: null,
      replayThinkingCursor: null,
    }
    turnsByClientMessageIdRef.current.set(turn.clientMessageId, turn)
    if (turn.conversationId != null) {
      turnByConversationIdRef.current.set(turn.conversationId, turn.clientMessageId)
    }
    abortRef.current = controller
    persistTurnMessages(turn)
    bumpTurnStatus()

    try {
      await controller.completion
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (turn.controller === controller) {
        turn.controller = null
      }
    }
  }, [
    agentId,
    anonUserId,
    bumpTurnStatus,
    channelSource,
    channelToken,
    conversationId,
    createTurnHandlers,
    detachActiveStream,
    embedToken,
    isEmbed,
    isTest,
    persistTurnMessages,
    resumeTurn,
  ])

  const handleCancel = useCallback(async () => {
    await cancelActiveStream()
  }, [cancelActiveStream])

  const handleFeedbackSubmitted = useCallback((
    messageId: string,
    feedback: StepFeedbackResponse,
  ) => {
    const applyFeedback = (items: ChatMessage[]) => items.map((item) =>
      item.id === messageId
        ? {
            ...item,
            feedbackRating: feedback.feedback_rating,
            feedbackComment: feedback.feedback_comment,
            feedbackUpdatedAt: feedback.feedback_updated_at,
          }
        : item
    )

    const nextMessages = applyFeedback(messagesRef.current)
    messagesRef.current = nextMessages
    setMessages(nextMessages)

    const activeId = activeConversationIdRef.current
    if (activeId != null) {
      setStoredConvs((convs) => convs.map((conv) =>
        conv.conversationId === activeId
          ? { ...conv, messages: applyFeedback(conv.messages) }
          : conv
      ))

      const turnId = turnByConversationIdRef.current.get(activeId)
      const turn = turnId ? turnsByClientMessageIdRef.current.get(turnId) : null
      if (turn) {
        turn.messages = applyFeedback(turn.messages)
      }
    }
  }, [])

  // Note: runtime is created inside ChatThreadView (keyed by activeConvId)
  // so it gets destroyed and recreated on conversation switch.

  const handleNewChat = useCallback(() => {
    if (abortRef.current) {
      detachActiveStream()
    }
    setActiveConversation(null)
    messagesRef.current = []
    setMessages([])
    setIsStreaming(false)
    setSidebarOpen(false)
  }, [detachActiveStream, setActiveConversation])

  const handleSwitchConv = useCallback((conv: StoredConv) => {
    if (conv.conversationId === conversationIdRef.current) return
    if (abortRef.current) {
      detachActiveStream()
    }
    const turnId = turnByConversationIdRef.current.get(conv.conversationId)
    const turn = turnId ? turnsByClientMessageIdRef.current.get(turnId) : null
    const nextMessages = turn && isPendingTurn(turn.status)
      ? cloneMessages(turn.messages)
      : cloneMessages(conv.messages)
    messagesRef.current = nextMessages
    setMessages(nextMessages)
    setActiveConversation(conv.conversationId)
    setIsStreaming(turn ? isLiveTurn(turn.status) : false)
    setSidebarOpen(false)
    if (turn?.status === 'detached') {
      resumeTurn(turn)
    }
  }, [detachActiveStream, resumeTurn, setActiveConversation])

  const handleClose = useCallback(() => {
    if (isEmbed && typeof window !== 'undefined') {
      window.parent.postMessage({ type: 'openagent-close' }, '*')
    }
  }, [isEmbed])

  const defaultUserRadius = isEmbed ? '16 16 4 16' : '14 14 4 14'
  const defaultAgentRadius = isEmbed ? '4 16 16 16' : '4 14 14 14'
  const conversationStatuses = useMemo(() => {
    void turnStatusVersion
    const statuses = new Map<number, StreamTurnStatus>()
    for (const turn of turnsByClientMessageIdRef.current.values()) {
      if (turn.conversationId != null && turn.status !== 'done' && turn.status !== 'cancelled') {
        statuses.set(turn.conversationId, turn.status)
      }
    }
    return statuses
  }, [turnStatusVersion])

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
            samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
            isEmbed={isEmbed}
            storedConvs={storedConvs}
            activeConvId={activeConvId}
            conversationStatuses={conversationStatuses}
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
              samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
              isEmbed={isEmbed}
              storedConvs={storedConvs}
              activeConvId={activeConvId}
              conversationStatuses={conversationStatuses}
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
                      samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
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
          conversationSettings={conversationSettings}
          channelToken={channelToken}
          samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
          feedbackEnabled={behavior.feedbackEnabled === true}
          onFeedbackSubmitted={handleFeedbackSubmitted}
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
  conversationSettings,
  channelToken,
  samePageNavigationUrlAllowlist,
  feedbackEnabled,
  onFeedbackSubmitted,
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
  conversationSettings: ConversationSettingsConfig
  channelToken: string
  samePageNavigationUrlAllowlist: readonly string[]
  feedbackEnabled: boolean
  onFeedbackSubmitted: (messageId: string, feedback: StepFeedbackResponse) => void
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
  const visibleWelcomeBlocks = useMemo(() => {
    const welcome = conversationSettings.welcome_message
    if (!welcome.enabled) return []
    return welcome.blocks.filter(isValidWelcomeBlock)
  }, [conversationSettings])
  const showWelcomeMessage = visibleWelcomeBlocks.length > 0
  const visibleAIDisclaimer = useMemo(() => {
    const disclaimer = conversationSettings.ai_disclaimer
    const content = disclaimer.content.trim()
    if (!disclaimer.enabled || !content) return ''
    return content
  }, [conversationSettings])

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
            {/* ── Empty state: welcome message or centered logo + title ── */}
            <AuiIf condition={(s) => s.thread.isEmpty}>
              {showWelcomeMessage ? (
                <>
                  <div className={cn(
                    'w-full shrink-0',
                    isEmbed ? 'px-4 pb-5 pt-4' : 'px-4 pb-6 pt-6 md:px-0',
                  )}>
                    <div className={cn('mx-auto w-full', isEmbed ? '' : 'max-w-[740px]')}>
                      <ChatWelcomeMessage
                        blocks={visibleWelcomeBlocks}
                        appearance={appearance}
                        isEmbed={isEmbed}
                        defaultRadius={defaultAgentRadius}
                        samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
                      />
                    </div>
                  </div>
                  <div className="min-h-6 grow" />
                </>
              ) : (
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
              )}
            </AuiIf>

            {/* ── Has messages: message list ── */}
            <AuiIf condition={(s) => !s.thread.isEmpty}>
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
                          channelToken={channelToken}
                          samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
                          feedbackEnabled={feedbackEnabled}
                          aiDisclaimer={visibleAIDisclaimer}
                          onFeedbackSubmitted={onFeedbackSubmitted}
                          isEmbed={isEmbed}
                          defaultRadius={defaultAgentRadius}
                        />
                      )
                    }}
                  </ThreadPrimitive.Messages>
                </div>
              </div>

              <div className="min-h-6 grow" />
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
  const hasLogo = Boolean(logoSrc)
  const hasTitle = Boolean(titleText)
  return (
    <div
      className={cn(
        // Match message column width so wide empty-state art can use full canvas
        'flex w-full max-w-[740px] flex-col items-center justify-center',
        hasTitle ? 'gap-4' : 'gap-0',
      )}
    >
      {hasLogo ? (
        <img
          key={logoSrc}
          src={logoSrc}
          alt=""
          className={cn(
            'h-auto w-auto max-w-full shrink-0 object-contain',
            isEmbed
              ? 'max-h-[min(36vh,240px)]'
              : 'max-h-[min(42vh,360px)] md:max-h-[min(48vh,420px)]',
          )}
        />
      ) : null}
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

function ChatWelcomeMessage({
  blocks,
  appearance,
  isEmbed,
  defaultRadius,
  samePageNavigationUrlAllowlist,
}: {
  blocks: WelcomeMessageBlock[]
  appearance: AppearanceCfg
  isEmbed: boolean
  defaultRadius: string
  samePageNavigationUrlAllowlist: readonly string[]
}) {
  const bubbleTextColor = appearance.agentBubbleTextColor || (isEmbed ? '#3F3F46' : '#1A1A1A')
  const configuredAgentAvatar = (appearance.agentAvatar || '').trim()
  const [agentAvatarFailed, setAgentAvatarFailed] = useState(false)
  const showAgentAvatar = Boolean(configuredAgentAvatar) && !agentAvatarFailed

  useEffect(() => {
    setAgentAvatarFailed(false)
  }, [configuredAgentAvatar])

  return (
    <div className={cn('flex w-full', showAgentAvatar && 'gap-2.5')}>
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
        <div
          className={cn(
            'w-fit max-w-full min-w-0 self-start break-words',
            '[&_p]:m-0 [&_p+p]:mt-2 [&_ul]:my-1 [&_ol]:my-1',
            '[&>div]:min-h-[26px] [&>div]:leading-[26px]',
            '[&_p]:leading-[26px] [&_li]:leading-[26px]',
            isEmbed ? '[&>div]:text-[13px]' : '[&>div]:text-sm',
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
          <div className="space-y-3">
            {blocks.map((block, index) =>
              block.type === 'markdown' ? (
                <MarkdownContent
                  key={`welcome-md-${index}`}
                  source={block.content}
                  style={{ color: bubbleTextColor }}
                  samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
                />
              ) : (
                <WelcomeEmbedFrame
                  key={`welcome-embed-${index}`}
                  title={`welcome embed ${index + 1}`}
                  embedCode={block.embed_code}
                  className="block w-full rounded-lg border border-[#E4E4E7] bg-white"
                  style={{
                    height: block.height,
                    maxHeight: isEmbed ? '45vh' : '520px',
                  }}
                />
              ),
            )}
          </div>
        </div>
      </div>
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
  channelToken,
  samePageNavigationUrlAllowlist,
  feedbackEnabled,
  aiDisclaimer,
  onFeedbackSubmitted,
  isEmbed,
  defaultRadius,
}: {
  message: ChatMessage
  appearance: AppearanceCfg
  channelToken: string
  samePageNavigationUrlAllowlist: readonly string[]
  feedbackEnabled: boolean
  aiDisclaimer: string
  onFeedbackSubmitted: (messageId: string, feedback: StepFeedbackResponse) => void
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
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackRating | null>(
    message.feedbackRating ?? null,
  )
  const [feedbackDraft, setFeedbackDraft] = useState(message.feedbackComment ?? '')
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [feedbackError, setFeedbackError] = useState('')
  const [feedbackSaved, setFeedbackSaved] = useState(false)

  useEffect(() => {
    setAgentAvatarFailed(false)
  }, [configuredAgentAvatar])

  useEffect(() => {
    setSelectedFeedback(message.feedbackRating ?? null)
    setFeedbackDraft(message.feedbackComment ?? '')
    setFeedbackError('')
    setFeedbackSaved(false)
    setFeedbackOpen(false)
  }, [message.id, message.feedbackRating, message.feedbackComment])

  const canShowFeedback =
    feedbackEnabled &&
    !message.isStreaming &&
    Boolean(bottomTextTrimmed) &&
    message.assistantStepId != null

  const handleFeedbackSelect = (rating: FeedbackRating) => {
    if (feedbackSubmitting) return
    setSelectedFeedback(rating)
    setFeedbackOpen(true)
    setFeedbackError('')
    setFeedbackSaved(false)
  }

  const handleFeedbackCancel = () => {
    if (feedbackSubmitting) return
    setSelectedFeedback(message.feedbackRating ?? null)
    setFeedbackDraft(message.feedbackComment ?? '')
    setFeedbackOpen(false)
    setFeedbackError('')
  }

  const handleFeedbackSubmit = async () => {
    if (!selectedFeedback || !message.assistantStepId) return
    if (feedbackDraft.length > 500) {
      setFeedbackError('评价内容不能超过 500 个字符')
      return
    }

    setFeedbackSubmitting(true)
    setFeedbackError('')
    setFeedbackSaved(false)
    try {
      const feedback = await submitPublicStepFeedback(
        channelToken,
        message.assistantStepId,
        {
          rating: selectedFeedback,
          comment: feedbackDraft.trim() || null,
        },
      )
      onFeedbackSubmitted(message.id, feedback)
      setSelectedFeedback(feedback.feedback_rating)
      setFeedbackDraft(feedback.feedback_comment ?? '')
      setFeedbackOpen(false)
      setFeedbackSaved(true)
      window.setTimeout(() => setFeedbackSaved(false), 1800)
    } catch (err) {
      const message = await getErrorMessage(err)
      setFeedbackError(message || '提交失败，请重试')
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  return (
    <>
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

        <IntermediateSteps
          thinkingBlocks={message.thinkingBlocks}
          toolBlocks={message.toolBlocks}
          inlineContentBlocks={inlineContentBlocks}
          isStreaming={message.isStreaming}
          samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
        />

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
                samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
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

        {!message.isStreaming && bottomTextTrimmed && aiDisclaimer && (
          <div
            className={cn(
              'flex max-w-full items-start gap-1.5 self-start whitespace-pre-wrap break-words leading-relaxed text-[#8A8A8A]',
              isEmbed ? 'text-[11px]' : 'text-[12px]',
            )}
          >
            <IconInfoCircle size={13} className="mt-[2px] shrink-0 text-[#A3A3A3]" />
            <span className="min-w-0">{aiDisclaimer}</span>
          </div>
        )}

        {!message.isStreaming && bottomTextTrimmed && (
          <div className="mt-0.5 flex min-h-[18px] items-center gap-2 pb-0.5 text-[11px] text-[#A3A3A3]">
            {message.timestamp && <span>{message.timestamp}</span>}
            <ActionBarPrimitive.Root hideWhenRunning className="flex items-center gap-2">
              <ActionBarPrimitive.Copy className="group/copy flex items-center justify-center text-[#A3A3A3] transition-colors hover:text-[#71717A]">
                <IconCopy size={12} className="group-data-[copied]/copy:hidden" />
                <IconCheck size={12} className="hidden text-[#059669] group-data-[copied]/copy:block" />
              </ActionBarPrimitive.Copy>
              {canShowFeedback && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className={cn(
                      'flex h-[18px] w-[18px] items-center justify-center rounded transition-colors hover:bg-black/5 disabled:opacity-50',
                      selectedFeedback === 'like' ? 'text-[#8A8A8A]' : 'text-[#A3A3A3]',
                    )}
                    onClick={() => handleFeedbackSelect('like')}
                    disabled={feedbackSubmitting}
                    title="赞"
                    aria-label="赞"
                  >
                    {selectedFeedback === 'like'
                      ? <IconThumbUpFilled size={13} />
                      : <IconThumbUp size={12} />}
                  </button>
                  <button
                    type="button"
                    className={cn(
                      'flex h-[18px] w-[18px] items-center justify-center rounded transition-colors hover:bg-black/5 disabled:opacity-50',
                      selectedFeedback === 'dislike' ? 'text-[#8A8A8A]' : 'text-[#A3A3A3]',
                    )}
                    onClick={() => handleFeedbackSelect('dislike')}
                    disabled={feedbackSubmitting}
                    title="踩"
                    aria-label="踩"
                  >
                    {selectedFeedback === 'dislike'
                      ? <IconThumbDownFilled size={13} />
                      : <IconThumbDown size={12} />}
                  </button>
                  {feedbackSaved && (
                    <span className="text-[#059669]">已提交</span>
                  )}
                </div>
              )}
            </ActionBarPrimitive.Root>
          </div>
        )}

        </div>
      </MessagePrimitive.Root>

      {canShowFeedback && feedbackOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 px-4 py-6"
          role="dialog"
          aria-modal="true"
          aria-label="提交评价"
          onClick={handleFeedbackCancel}
        >
          <div
            className="w-full max-w-[420px] rounded-xl border border-[#E5E5E5] bg-white p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-[#18181B]">提交评价</h3>
                  <span
                    className="flex h-7 w-7 items-center justify-center rounded-md text-[#8A8A8A]"
                    aria-label={selectedFeedback === 'like' ? '已选赞' : '已选踩'}
                  >
                    {selectedFeedback === 'like'
                      ? <IconThumbUpFilled size={18} />
                      : <IconThumbDownFilled size={18} />}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#A3A3A3] transition-colors hover:bg-[#F4F4F5] hover:text-[#525252] disabled:opacity-50"
                onClick={handleFeedbackCancel}
                disabled={feedbackSubmitting}
                aria-label="关闭评价弹窗"
              >
                <IconX size={16} />
              </button>
            </div>

            <textarea
              value={feedbackDraft}
              onChange={(e) => {
                setFeedbackDraft(e.target.value)
                if (feedbackError) setFeedbackError('')
              }}
              placeholder="请输入您的评价..."
              className="mt-4 min-h-[108px] w-full resize-none rounded-md border border-[#E5E5E5] bg-[#FAFAFA] px-3 py-2 text-[13px] leading-relaxed text-[#18181B] outline-none placeholder:text-[#A3A3A3] focus:border-[#A1A1AA]"
              disabled={feedbackSubmitting}
              autoFocus
            />
            <div className="mt-2 flex items-center gap-2">
              <span
                className={cn(
                  'min-w-0 flex-1 text-[12px]',
                  feedbackError ? 'text-[#DC2626]' : 'text-[#A3A3A3]',
                )}
              >
                {feedbackError || `${feedbackDraft.length}/500`}
              </span>
              <button
                type="button"
                className="rounded-md border border-[#E5E5E5] bg-white px-3 py-1.5 text-[13px] text-[#525252] transition-colors hover:bg-[#F7F7F7] disabled:opacity-50"
                onClick={handleFeedbackCancel}
                disabled={feedbackSubmitting}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-md px-3 py-1.5 text-[13px] font-medium transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                style={{
                  backgroundColor: appearance.sendMessageButtonBgColor || '#1A1A1A',
                  color: appearance.sendMessageButtonIconColor || '#FFFFFF',
                }}
                onClick={handleFeedbackSubmit}
                disabled={!selectedFeedback || feedbackSubmitting}
              >
                {feedbackSubmitting ? '提交中...' : '提交'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
