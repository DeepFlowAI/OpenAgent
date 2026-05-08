'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { cn } from '@/utils/classnames'
import { stripMarkdownHeadingAnchorsRehypeRewrite } from '@/utils/strip-markdown-heading-anchors'
import { Badge } from '@/app/components/base/badge'
import { useConversation } from '@/service/use-conversation'
import { useConversationTimeline, useStepDetail } from '@/service/use-conversation-step'
import { LlmDetailModal } from '@/app/components/features/llm-detail-modal'
import { STATUS_LABELS, SOURCE_LABELS } from '@/models/conversation'
import type { Conversation, StepTimelineItem } from '@/models/conversation'
import {
  IconX,
  IconMessageChatbot,
  IconChevronDown,
  IconChevronRight,
  IconSearch,
  IconCopy,
  IconCheck,
  IconTool,
} from '@tabler/icons-react'

const MarkdownPreview = dynamic(() => import('@uiw/react-markdown-preview'), {
  ssr: false,
})

type ConversationDrawerProps = {
  agentId: number
  conversation: Conversation | null
  onClose: () => void
}

type RoundGroup = {
  roundNumber: number
  userMessage: StepTimelineItem | null
  agentSteps: StepTimelineItem[]
}

export function ConversationDrawer({
  agentId,
  conversation,
  onClose,
}: ConversationDrawerProps) {
  const open = !!conversation
  const conversationId = conversation?.id ?? 0

  const { data: detail } = useConversation(agentId, conversationId)
  const { data: timeline, isLoading: timelineLoading } = useConversationTimeline(agentId, conversationId)

  const [selectedStepId, setSelectedStepId] = useState<number | null>(null)
  const { data: stepDetail, isLoading: stepDetailLoading } = useStepDetail(
    agentId,
    conversationId,
    selectedStepId ?? 0,
  )

  const [expandedThinking, setExpandedThinking] = useState<Set<number>>(new Set())
  const [copiedField, setCopiedField] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  useEffect(() => {
    if (!open) {
      setSelectedStepId(null)
      setExpandedThinking(new Set())
      setCopiedField(null)
    }
  }, [open])

  const handleCopy = useCallback((text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 1500)
  }, [])

  const toggleThinking = useCallback((stepId: number) => {
    setExpandedThinking((prev) => {
      const next = new Set(prev)
      if (next.has(stepId)) next.delete(stepId)
      else next.add(stepId)
      return next
    })
  }, [])

  const rounds: RoundGroup[] = useMemo(() => {
    if (!timeline?.steps) return []
    const roundMap = new Map<number, RoundGroup>()
    for (const step of timeline.steps) {
      if (!roundMap.has(step.round_number)) {
        roundMap.set(step.round_number, {
          roundNumber: step.round_number,
          userMessage: null,
          agentSteps: [],
        })
      }
      const group = roundMap.get(step.round_number)!
      if (step.step_type === 'user_message') {
        group.userMessage = step
      } else {
        group.agentSteps.push(step)
      }
    }
    return Array.from(roundMap.values()).sort((a, b) => a.roundNumber - b.roundNumber)
  }, [timeline])

  const findParentLlm = useCallback(
    (step: StepTimelineItem): StepTimelineItem | null => {
      if (!step.parent_step_id || !timeline?.steps) return null
      return timeline.steps.find((s) => s.id === step.parent_step_id) ?? null
    },
    [timeline],
  )

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return ''
    return new Date(dateStr).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const formatTokens = (n: number | null | undefined) => {
    if (n === null || n === undefined) return '—'
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
  }

  const formatDuration = () => {
    if (!detail?.duration_seconds) return '—'
    const s = detail.duration_seconds
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    const sec = s % 60
    if (m < 60) return `${m}m ${sec}s`
    const h = Math.floor(m / 60)
    return `${h}h ${m % 60}m`
  }

  const renderAgentSteps = (steps: StepTimelineItem[]) => {
    const elements: React.ReactNode[] = []

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i]

      if (step.step_type === 'llm_call') {
        if (step.thinking_content) {
          const isExpanded = expandedThinking.has(step.id)
          elements.push(
            <div key={`thinking-${step.id}`} className="mb-2">
              <div
                className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-[#F8F8F8] px-3 py-2 transition-colors hover:bg-[#F0F0F0]"
                onClick={() => toggleThinking(step.id)}
              >
                {isExpanded ? (
                  <IconChevronDown size={14} className="text-[#737373]" />
                ) : (
                  <IconChevronRight size={14} className="text-[#737373]" />
                )}
                <span className="text-[13px] font-medium text-[#737373]">思考</span>
                <div className="flex-1" />
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setSelectedStepId(step.id)
                  }}
                  className="text-[#A3A3A3] transition-colors hover:text-[#404040]"
                  title="查看 LLM 请求/响应"
                >
                  <IconSearch size={14} />
                </button>
              </div>
              {isExpanded && (
                <div className="mt-1 rounded-lg bg-[#FAFAFA] px-4 py-3">
                  <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-[#404040]">
                    {step.thinking_content}
                  </p>
                </div>
              )}
            </div>,
          )
        }

        // Intermediate content: LLM produced content before calling tools
        if (step.content && step.response_tool_calls && (step.response_tool_calls as unknown[]).length > 0) {
          elements.push(
            <div key={`llm-content-${step.id}`} className="mb-2 rounded-lg bg-[#F5F5F5] px-4 py-3" data-color-mode="light">
              <MarkdownPreview
                source={step.content}
                style={{ background: 'transparent', fontSize: 14 }}
                rehypeRewrite={stripMarkdownHeadingAnchorsRehypeRewrite}
              />
            </div>,
          )
        }
      }

      if (step.step_type === 'tool_call') {
        elements.push(
          <div
            key={`tool-${step.id}`}
            className="mb-2 flex items-center gap-2 rounded-lg border border-[#F0F0F0] px-3 py-2"
          >
            <IconTool size={16} className="shrink-0 text-[#737373]" />
            <span className="flex-1 truncate text-[13px] text-[#404040]">
              {step.brief || `使用工具：${step.tool_name || 'unknown'}`}
            </span>
            {step.status === 'error' && <Badge variant="danger">错误</Badge>}
            <button
              onClick={() => {
                const parentLlm = findParentLlm(step)
                if (parentLlm) setSelectedStepId(parentLlm.id)
              }}
              className="shrink-0 text-[#A3A3A3] transition-colors hover:text-[#404040]"
              title="查看关联 LLM 调用"
            >
              <IconSearch size={14} />
            </button>
          </div>,
        )
      }

      if (step.step_type === 'assistant_message') {
        elements.push(
          <div key={`assistant-${step.id}`} className="mb-2">
            <div className="rounded-lg bg-[#F5F5F5] px-4 py-3" data-color-mode="light">
              {step.content ? (
                <MarkdownPreview
                  source={step.content}
                  style={{ background: 'transparent', fontSize: 14 }}
                  rehypeRewrite={stripMarkdownHeadingAnchorsRehypeRewrite}
                />
              ) : (
                <span className="text-sm text-[#A1A1AA]">(空回复)</span>
              )}
            </div>
            <div className="mt-1.5 flex items-center gap-2 text-xs text-[#A3A3A3]">
              <span>{formatTime(step.created_at)}</span>
              {step.parent_step_id && (
                <>
                  <span>·</span>
                  <span>
                    Token{' '}
                    {formatTokens(
                      timeline?.steps.find((s) => s.id === step.parent_step_id)?.total_tokens,
                    )}
                  </span>
                </>
              )}
              <button
                onClick={() => handleCopy(step.content || '', `content-${step.id}`)}
                className="text-[#A3A3A3] transition-colors hover:text-[#404040]"
              >
                {copiedField === `content-${step.id}` ? (
                  <IconCheck size={12} className="text-[#059669]" />
                ) : (
                  <IconCopy size={12} />
                )}
              </button>
              {step.parent_step_id && (
                <button
                  onClick={() => setSelectedStepId(step.parent_step_id!)}
                  className="text-[#A3A3A3] transition-colors hover:text-[#404040]"
                  title="查看 LLM 请求/响应"
                >
                  <IconSearch size={14} />
                </button>
              )}
            </div>
          </div>,
        )
      }
    }

    return elements
  }

  const infoSource = detail ?? conversation

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className={cn(
          'fixed right-0 top-0 z-50 flex h-full w-[min(calc(100vw-40px),1100px)] flex-col bg-white shadow-xl transition-transform duration-300',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#ECECEC] px-6 py-4">
          <h2 className="text-base font-semibold text-[#18181B]">会话日志详情</h2>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1a1a1a]"
          >
            <IconX size={18} />
          </button>
        </div>

        {/* Main content: two-column layout */}
        {conversation && (
          <div className="flex flex-1 overflow-hidden">
            {/* Left: conversation timeline */}
            <div className="flex-1 overflow-auto px-6 py-6">
              {timelineLoading ? (
                <div className="py-20 text-center text-sm text-[#737373]">加载中...</div>
              ) : rounds.length === 0 ? (
                <div className="py-20 text-center text-sm text-[#737373]">暂无日志数据</div>
              ) : (
                <div className="space-y-8">
                  {rounds.map((round) => (
                    <div key={round.roundNumber}>
                      <div className="mb-4 flex items-center gap-3">
                        <div className="h-px flex-1 bg-[#F0F0F0]" />
                        <span className="text-xs font-medium text-[#A3A3A3]">
                          轮次 {round.roundNumber}
                        </span>
                        <div className="h-px flex-1 bg-[#F0F0F0]" />
                      </div>

                      {round.userMessage && (
                        <div className="mb-4 flex justify-end">
                          <div className="max-w-[85%]">
                            <div className="rounded-lg bg-[#1a1a1a] px-4 py-3 text-sm leading-relaxed text-white">
                              {round.userMessage.content}
                            </div>
                            <div className="mt-1 text-right text-xs text-[#A3A3A3]">
                              {formatTime(round.userMessage.created_at)}
                            </div>
                          </div>
                        </div>
                      )}

                      {round.agentSteps.length > 0 && (
                        <div className="flex gap-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#F0F0F0]">
                            <IconMessageChatbot size={16} className="text-[#737373]" />
                          </div>
                          <div className="min-w-0 flex-1">
                            {renderAgentSteps(round.agentSteps)}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right: conversation info panel */}
            <div className="w-[280px] shrink-0 overflow-auto border-l border-[#ECECEC] bg-[#FAFAFA] px-5 py-6">
              <h3 className="mb-4 text-sm font-semibold text-[#18181B]">会话信息</h3>

              {infoSource ? (
                <div className="space-y-3.5">
                  <SideInfoRow label="会话 ID">
                    <div className="flex items-center gap-1">
                      <span className="max-w-[140px] truncate font-mono text-xs text-[#737373]">
                        {infoSource.external_id}
                      </span>
                      <button
                        onClick={() => handleCopy(infoSource.external_id, 'sidebar-id')}
                        className="text-[#A3A3A3] hover:text-[#404040]"
                      >
                        {copiedField === 'sidebar-id' ? (
                          <IconCheck size={12} className="text-[#059669]" />
                        ) : (
                          <IconCopy size={12} />
                        )}
                      </button>
                    </div>
                  </SideInfoRow>

                  <SideInfoRow label="用户标识">
                    <span className="text-xs text-[#1a1a1a]">
                      {infoSource.external_user_id || '—'}
                    </span>
                  </SideInfoRow>

                  <SideInfoRow label="状态">
                    <Badge variant={infoSource.status === 'active' ? 'success' : 'default'}>
                      {STATUS_LABELS[infoSource.status] || infoSource.status}
                    </Badge>
                  </SideInfoRow>

                  <SideInfoRow label="来源">
                    <Badge variant={infoSource.source === 'api' ? 'warning' : 'default'}>
                      {SOURCE_LABELS[infoSource.source] || infoSource.source}
                    </Badge>
                  </SideInfoRow>

                  <SideInfoRow label="开始时间">
                    <span className="text-xs text-[#1a1a1a]">
                      {infoSource.started_at
                        ? new Date(infoSource.started_at).toLocaleString('zh-CN')
                        : '—'}
                    </span>
                  </SideInfoRow>

                  <SideInfoRow label="持续时长">
                    <span className="text-xs text-[#1a1a1a]">{formatDuration()}</span>
                  </SideInfoRow>

                  {/* 会员信息 */}
                  {(infoSource.display_name || infoSource.email || infoSource.phone || infoSource.avatar_url) && (
                    <>
                      <div className="h-px bg-[#E5E5E5]" />
                      <h4 className="text-xs font-semibold text-[#18181B]">会员信息</h4>

                      {infoSource.display_name && (
                        <SideInfoRow label="昵称">
                          <div className="flex items-center gap-1.5">
                            {infoSource.avatar_url && (
                              <img
                                src={infoSource.avatar_url}
                                alt=""
                                className="h-5 w-5 shrink-0 rounded-full object-cover"
                              />
                            )}
                            <span className="text-xs text-[#1a1a1a]">{infoSource.display_name}</span>
                          </div>
                        </SideInfoRow>
                      )}

                      {infoSource.email && (
                        <SideInfoRow label="邮箱">
                          <span className="max-w-[140px] truncate text-xs text-[#1a1a1a]" title={infoSource.email}>
                            {infoSource.email}
                          </span>
                        </SideInfoRow>
                      )}

                      {infoSource.phone && (
                        <SideInfoRow label="手机号">
                          <span className="text-xs text-[#1a1a1a]">{infoSource.phone}</span>
                        </SideInfoRow>
                      )}
                    </>
                  )}

                  <div className="h-px bg-[#E5E5E5]" />

                  <SideInfoRow label="轮数">
                    <span className="text-xs text-[#1a1a1a]">{infoSource.round_count}</span>
                  </SideInfoRow>

                  <SideInfoRow label="LLM 调用">
                    <span className="text-xs text-[#1a1a1a]">{infoSource.llm_call_count}</span>
                  </SideInfoRow>

                  <SideInfoRow label="工具调用">
                    <span className="text-xs text-[#1a1a1a]">{infoSource.tool_call_count}</span>
                  </SideInfoRow>

                  <div className="h-px bg-[#E5E5E5]" />

                  <SideInfoRow label="输入 Token">
                    <span className="text-xs text-[#1a1a1a]">
                      {formatTokens(infoSource.total_input_tokens)}
                    </span>
                  </SideInfoRow>

                  <SideInfoRow label="输出 Token">
                    <span className="text-xs text-[#1a1a1a]">
                      {formatTokens(infoSource.total_output_tokens)}
                    </span>
                  </SideInfoRow>

                  <SideInfoRow label="总 Token">
                    <span className="text-xs font-semibold text-[#1a1a1a]">
                      {formatTokens(infoSource.total_tokens)}
                    </span>
                  </SideInfoRow>
                </div>
              ) : (
                <div className="text-xs text-[#737373]">加载中...</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* LLM Detail Modal */}
      <LlmDetailModal
        open={!!selectedStepId}
        onClose={() => setSelectedStepId(null)}
        step={stepDetail ?? null}
        isLoading={stepDetailLoading}
      />
    </>
  )
}

function SideInfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="shrink-0 text-xs text-[#737373]">{label}</span>
      <div className="text-right">{children}</div>
    </div>
  )
}
