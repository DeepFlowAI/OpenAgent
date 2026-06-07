'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { cn } from '@/utils/classnames'
import {
  IconX,
  IconCopy,
  IconCheck,
  IconSearch,
  IconArrowUp,
  IconMessagePlus,
  IconMessageChatbot,
  IconArrowDown,
} from '@tabler/icons-react'
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
import { sendChatMessage } from '@/service/use-chat'
import { endConversation } from '@/service/use-conversation'
import { LlmDetailModal } from '@/app/components/features/llm-detail-modal'
import { useStepDetail } from '@/service/use-conversation-step'
import {
  IntermediateSteps,
  MarkdownContent,
  StreamingMarkdownContent,
  StreamingThinkingPlaceholder,
} from '@/app/components/features/chat-message-blocks'
import type { ChatMessage, ToolBlock } from '@/models/conversation'
import {
  DEFAULT_CONVERSATION_SETTINGS,
  type ConversationSettingsConfig,
} from '@/models/agent'

type ChatTestDrawerProps = {
  open: boolean
  onClose: () => void
  agentId: number
  conversationSettings: ConversationSettingsConfig
}

let msgCounter = 0
function genId() {
  return `msg_${Date.now()}_${++msgCounter}`
}

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

export function ChatTestDrawer({
  open,
  onClose,
  agentId,
  conversationSettings,
}: ChatTestDrawerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [externalId, setExternalId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState(false)

  const [modalOpen, setModalOpen] = useState(false)
  const [modalStepId, setModalStepId] = useState<number | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const currentAssistantRef = useRef<string | null>(null)
  const lastLlmStepIdRef = useRef<number | null>(null)
  const timelineCounterRef = useRef(0)
  const drawerRef = useRef<HTMLDivElement>(null)

  const handleClose = useCallback(() => {
    if (conversationId) {
      endConversation(agentId, conversationId).catch(() => {})
    }
    onClose()
  }, [conversationId, agentId, onClose])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !modalOpen) handleClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, handleClose, modalOpen])

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort()
      setMessages([])
      setConversationId(null)
      setExternalId(null)
      setIsStreaming(false)
      currentAssistantRef.current = null
      lastLlmStepIdRef.current = null
      timelineCounterRef.current = 0
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setTimeout(() => {
        drawerRef.current?.querySelector('textarea')?.focus()
      }, 300)
    }
  }, [open])

  const handleCopyId = useCallback(() => {
    if (!externalId) return
    navigator.clipboard.writeText(externalId)
    setCopiedId(true)
    setTimeout(() => setCopiedId(false), 1500)
  }, [externalId])

  const handleInspect = useCallback((stepId: number) => {
    setModalStepId(stepId)
    setModalOpen(true)
  }, [])

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

  // ── SSE send handler (business logic unchanged) ──

  const handleNewMessage = useCallback(async (message: AppendMessage) => {
    if (message.content[0]?.type !== 'text') return
    const text = message.content[0].text.trim()
    if (!text) return

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

    const controller = sendChatMessage(agentId, text, conversationId, {
      onConversationCreated: (data) => {
        setConversationId(data.conversation_id)
        setExternalId(data.external_id)
      },
      onThinkingDelta: (data) => {
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const blocks = [...m.thinkingBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = {
              ...lastBlock,
              content: lastBlock.content + data.content,
            }
            return { ...m, thinkingBlocks: blocks }
          } else {
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
            return { ...m, thinkingBlocks: blocks, contentBlocks: closedContentBlocks }
          }
        }))
      },
      onContentDelta: (data) => {
        setMessages(prev => prev.map(m => {
          if (m.id !== currentAssistantRef.current) return m
          const blocks = [...m.contentBlocks]
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock && lastBlock.isStreaming) {
            blocks[blocks.length - 1] = {
              ...lastBlock,
              content: lastBlock.content + data.content,
            }
          } else {
            blocks.push({
              id: `content_${Date.now()}`,
              content: data.content,
              llmStepId: lastLlmStepIdRef.current,
              isStreaming: true,
              timelineIndex: ++timelineCounterRef.current,
            })
          }
          return { ...m, content: m.content + data.content, contentBlocks: blocks }
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
          return { ...m, thinkingBlocks: thinkBlocks, contentBlocks, toolBlocks: [...m.toolBlocks, toolBlock] }
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
        setMessages(prev => prev.map(m => {
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
          }
        }))
        setIsStreaming(false)
        currentAssistantRef.current = null
      },
      onRoundStart: (data) => {
        // Step-replay reconnect (sub-req 4): the server reattached us to an
        // existing round and is about to re-emit ALL its events from the top.
        // Without a wipe here the buffer-cold reconnect would render every
        // delta twice (once from the original stream, once from the replay).
        //
        // Buffer fast-path doesn't reach this branch: it slices `seq > cursor`
        // and never re-emits the round_start frame, so we keep the existing
        // bubble and just append the missing tail. THAT is the case the old
        // onRetry-wipe used to break — wiping there threw away pixels that
        // the server was about to confirm via increments.
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
          }
        }))
      },
      onRetry: () => {
        // Sub-req 4: do NOT wipe the bubble here. SDK retries now carry
        // `last_event_id`, so the server's buffer fast-path replays just
        // the missing tail without re-sending what the user already saw.
        // Wiping would create the very flash this work was meant to remove.
        // The step-replay path (cold buffer) clears via `onRoundStart`
        // above; the in-stream RESET case clears via `onAssistantReset`.
      },
      onAssistantReset: () => {
        // Server-side stream retry (stream-level retry spec): the LLM stream broke mid-
        // round and the engine is about to re-stream the SAME tool round
        // from scratch. Wipe the partial bubble so the new deltas land on
        // a clean slate.
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
          }
        }))
      },
      onError: (data) => {
        // Keep any partial reply intact; surface the failure via errorMessage
        // so the UI can render a dedicated banner instead of overwriting content.
        const targetId = currentAssistantRef.current
        const isToolLimit = isToolCallLimitError(data)
        const toolLimitReply = isToolLimit
          ? getToolCallLimitReply(data, conversationSettings)
          : null
        setMessages(prev => prev.map(m => {
          if (m.id !== targetId) return m
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
              llmStepId: lastLlmStepIdRef.current,
              isStreaming: false,
              timelineIndex: ++timelineCounterRef.current,
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
            errorMessage: isToolLimit ? null : data.message || '连接中断，请稍后重试',
          }
        }))
        setIsStreaming(false)
        currentAssistantRef.current = null
      },
    }, { source: 'testchat' }, undefined, externalId)

    abortRef.current = controller
    await controller.completion
  }, [agentId, conversationId, conversationSettings, externalId])

  const handleCancel = useCallback(async () => {
    abortRef.current?.abort()
    const targetId = currentAssistantRef.current
    if (targetId) {
      setMessages(prev => prev.map(m => {
        if (m.id !== targetId) return m
        const thinkBlocks = m.thinkingBlocks.map(b =>
          b.isStreaming ? { ...b, isStreaming: false } : b
        )
        const contentBlocks = m.contentBlocks.map(b =>
          b.isStreaming ? { ...b, isStreaming: false } : b
        )
        return { ...m, isStreaming: false, thinkingBlocks: thinkBlocks, contentBlocks }
      }))
      currentAssistantRef.current = null
    }
    setIsStreaming(false)
  }, [])

  const runtime = useExternalStoreRuntime({
    isRunning: isStreaming,
    messages,
    convertMessage,
    onNew: handleNewMessage,
    onCancel: handleCancel,
  })

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity duration-300',
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={handleClose}
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        className={cn(
          'fixed right-0 top-0 z-50 flex h-full w-[660px] flex-col bg-[#FAFAFA] shadow-[-8px_0_32px_rgba(0,0,0,0.12)] transition-transform duration-300',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-[#E4E4E7] bg-white px-5">
          <div className="flex items-center gap-3">
            <span className="text-[15px] font-semibold text-[#1A1A1A]">对话测试</span>
            {externalId && (
              <>
                <div className="h-4 w-px bg-[#E4E4E7]" />
                <div className="flex items-center gap-1">
                  <span className="font-mono text-xs text-[#A1A1AA]">ID:</span>
                  <span className="font-mono text-xs text-[#A1A1AA]">{externalId}</span>
                  <button onClick={handleCopyId} className="text-[#A1A1AA] hover:text-[#71717A]">
                    {copiedId ? <IconCheck size={12} className="text-[#059669]" /> : <IconCopy size={12} />}
                  </button>
                </div>
              </>
            )}
          </div>
          <button
            onClick={handleClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#F5F5F5]"
          >
            <IconX size={18} />
          </button>
        </div>

        {/* assistant-ui Thread */}
        <AssistantRuntimeProvider runtime={runtime}>
          <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
            <ThreadPrimitive.Viewport autoScroll className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-[#FAFAFA]">
                <AuiIf condition={(s) => s.thread.isEmpty}>
                  <div className="flex min-h-full flex-col">
                    <EmptyState />
                  </div>
                </AuiIf>

                <AuiIf condition={(s) => !s.thread.isEmpty}>
                  <div className="min-h-8 grow" />
                </AuiIf>

                <div className="px-5 py-5">
                  <div className="flex flex-col gap-4">
                    <ThreadPrimitive.Messages>
                      {({ message }) => {
                        // Read from React state directly instead of metadata.custom
                        // because useExternalStoreRuntime updates its store in useEffect
                        // (after render), so metadata.custom may be stale during render.
                        const original = messages.find(m => m.id === message.id)
                        if (!original) return null
                        if (original.role === 'user') return <UserMessage message={original} />
                        return <AssistantMessage message={original} onInspect={handleInspect} />
                      }}
                    </ThreadPrimitive.Messages>
                  </div>
                </div>

              {/* Composer */}
              <ThreadPrimitive.ViewportFooter className="shrink-0 bg-[#FAFAFA] px-4 pb-4 pt-0">
                <div className="relative w-full">
                  <ThreadPrimitive.ScrollToBottom className="absolute bottom-full left-1/2 z-10 mb-1 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-[#E4E4E7] bg-white text-[#71717A] shadow-sm transition-all hover:bg-[#F5F5F5] disabled:pointer-events-none disabled:opacity-0">
                    <IconArrowDown size={14} />
                  </ThreadPrimitive.ScrollToBottom>

                  <ComposerPrimitive.Root className="relative z-0 w-full rounded-full border border-[#E5E5E5] bg-white p-3 shadow-[0_-4px_16px_rgba(0,0,0,0.1)]">
                  <div className="flex items-end gap-2">
                    <ComposerPrimitive.Input
                      placeholder="输入测试问题..."
                      rows={1}
                      className="max-h-[120px] min-h-[20px] flex-1 resize-none bg-transparent px-3 py-[6px] text-sm leading-[1.5] text-[#1A1A1A] placeholder-[#A1A1AA] outline-none"
                    />
                    <AuiIf condition={(s) => !s.thread.isRunning}>
                      <ComposerPrimitive.Send className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1A1A1A] text-white transition-colors hover:bg-[#333] disabled:bg-[#E4E4E7] disabled:text-[#A1A1AA]">
                        <IconArrowUp size={16} />
                      </ComposerPrimitive.Send>
                    </AuiIf>
                    <AuiIf condition={(s) => s.thread.isRunning}>
                      <ComposerPrimitive.Cancel className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#DC2626] text-white transition-colors hover:bg-[#B91C1C]">
                        <span className="block h-3 w-3 rounded-[2px] bg-current" />
                      </ComposerPrimitive.Cancel>
                    </AuiIf>
                  </div>
                </ComposerPrimitive.Root>
                </div>
              </ThreadPrimitive.ViewportFooter>
            </ThreadPrimitive.Viewport>
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      </div>

      {/* LLM Detail Modal */}
      {modalStepId && conversationId && (
        <LlmModalWrapper
          open={modalOpen}
          onClose={() => { setModalOpen(false); setModalStepId(null) }}
          agentId={agentId}
          conversationId={conversationId}
          stepId={modalStepId}
        />
      )}
    </>
  )
}

// ── Sub-components (rendering logic unchanged) ──

function EmptyState() {
  return (
    <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-4">
      <div className="flex h-16 w-16 items-center justify-center rounded-[32px] bg-[#F4F4F5]">
        <IconMessagePlus size={28} className="text-[#A1A1AA]" />
      </div>
      <span className="text-base font-semibold text-[#1A1A1A]">开始测试对话</span>
      <span className="max-w-[280px] text-center text-[13px] text-[#71717A]">
        在下方输入框发送消息，开始与当前 Agent 进行测试对话
      </span>
    </div>
  )
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <MessagePrimitive.Root className="group flex flex-col items-end gap-1">
      <div className="max-w-[420px] rounded-[14px_14px_4px_14px] bg-[#1A1A1A] px-[14px] py-[10px]">
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-white">
          {message.content}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <ActionBarPrimitive.Root hideWhenRunning autohide="not-last" className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 data-[floating]:opacity-100">
          <ActionBarPrimitive.Copy className="flex items-center justify-center text-[#A1A1AA] transition-colors hover:text-[#71717A]">
            <IconCopy size={12} className="group-data-[copied]:hidden" />
            <IconCheck size={12} className="hidden text-[#059669] group-data-[copied]:block" />
          </ActionBarPrimitive.Copy>
        </ActionBarPrimitive.Root>
        <span className="text-[11px] text-[#A1A1AA]">{message.timestamp}</span>
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage({
  message,
  onInspect,
}: {
  message: ChatMessage
  onInspect: (stepId: number) => void
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

  return (
    <MessagePrimitive.Root className="group flex gap-[10px]">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[14px] bg-[#1A1A1A]">
        <IconMessageChatbot size={16} className="text-white" />
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-[6px]">
        <IntermediateSteps
          thinkingBlocks={message.thinkingBlocks}
          toolBlocks={message.toolBlocks}
          inlineContentBlocks={inlineContentBlocks}
          isStreaming={message.isStreaming}
          onInspect={onInspect}
        />

        {message.errorMessage && !message.isStreaming && (
          <div
            className="w-fit max-w-full self-start break-words rounded-md border border-[#FCA5A5] bg-[#FEF2F2] px-3 py-2 text-[12px] text-[#B91C1C]"
            role="alert"
          >
            {message.errorMessage}
          </div>
        )}

        {showReplyBubble && (
          <div className="w-fit max-w-full min-w-0 self-start break-words rounded-[14px] bg-white px-[14px] py-[10px] shadow-sm">
            {bottomTextTrimmed ? (
              <StreamingMarkdownContent source={bottomBlock!.content} isStreaming={bottomBlock!.isStreaming} />
            ) : (
              message.isStreaming && (
                <StreamingThinkingPlaceholder className="text-sm text-[#1A1A1A]" />
              )
            )}
            {!message.isStreaming && bottomTextTrimmed && (
              <div className="mt-2 flex items-center justify-between text-[11px] text-[#A1A1AA]">
                <span>{message.timestamp}</span>
                <ActionBarPrimitive.Root hideWhenRunning className="flex items-center gap-2">
                  <ActionBarPrimitive.Copy className="group/copy flex items-center justify-center text-[#A1A1AA] transition-colors hover:text-[#71717A]">
                    <IconCopy size={13} className="group-data-[copied]/copy:hidden" />
                    <IconCheck size={13} className="hidden text-[#059669] group-data-[copied]/copy:block" />
                  </ActionBarPrimitive.Copy>
                  {message.llmStepId && (
                    <button
                      onClick={() => onInspect(message.llmStepId!)}
                      className="flex items-center justify-center text-[#A1A1AA] transition-colors hover:text-[#71717A]"
                      title="检视 LLM 请求/响应"
                    >
                      <IconSearch size={13} />
                    </button>
                  )}
                </ActionBarPrimitive.Root>
              </div>
            )}
          </div>
        )}
      </div>
    </MessagePrimitive.Root>
  )
}


function LlmModalWrapper({
  open,
  onClose,
  agentId,
  conversationId,
  stepId,
}: {
  open: boolean
  onClose: () => void
  agentId: number
  conversationId: number
  stepId: number
}) {
  const { data: step, isLoading } = useStepDetail(agentId, conversationId, stepId)

  return (
    <LlmDetailModal
      open={open}
      onClose={onClose}
      step={step ?? null}
      isLoading={isLoading}
    />
  )
}
