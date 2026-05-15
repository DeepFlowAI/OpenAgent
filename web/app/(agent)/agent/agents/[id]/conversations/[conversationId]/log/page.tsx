'use client'

import { useState, useMemo, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { useParams, useRouter } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { stripMarkdownHeadingAnchorsRehypeRewrite } from '@/utils/strip-markdown-heading-anchors'
import { Badge } from '@/app/components/base/badge'
import { useConversation } from '@/service/use-conversation'
import { useConversationTimeline, useStepDetail } from '@/service/use-conversation-step'
import { LlmDetailModal } from '@/app/components/features/llm-detail-modal'
import { STATUS_LABELS, SOURCE_LABELS } from '@/models/conversation'
import type { StepTimelineItem } from '@/models/conversation'
import {
  IconArrowLeft,
  IconMessageChatbot,
  IconChevronDown,
  IconChevronRight,
  IconSearch,
  IconCopy,
  IconCheck,
  IconTool,
  IconDownload,
} from '@tabler/icons-react'

const MarkdownPreview = dynamic(() => import('@uiw/react-markdown-preview'), {
  ssr: false,
})

type RoundGroup = {
  roundNumber: number
  userMessage: StepTimelineItem | null
  agentSteps: StepTimelineItem[]
}

type ConversationExportRow = {
  externalId: string
  conversationId: number
  startedAt: string
  roundNumber: number
  userStepId: number
  clientMessageId: string
  userCreatedAt: string
  userContent: string
  thinkingContent: string
  assistantContent: string
  inputTokens: number
  outputTokens: number
  roundHasError: boolean
}

const EXPORT_COLUMNS = [
  '会话 ID',
  '会话内部 ID',
  '会话开始时间',
  '轮次',
  '用户消息 Step ID',
  '客户端消息 ID',
  '用户消息发送时间',
  '用户消息内容',
  'Agent 推理过程',
  'Agent 消息内容',
  '输入 Token',
  '输出 Token',
  'round_has_error',
] as const

function formatExportTimestamp(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
  ].join('')
}

function escapeCsvCell(value: string | number | boolean) {
  const text = String(value)
  if (!/[",\n\r]/.test(text)) return text
  return `"${text.replaceAll('"', '""')}"`
}

function buildAgentReasoningExport(orderedAgentSteps: StepTimelineItem[]): string {
  const segments: string[] = []
  for (const step of orderedAgentSteps) {
    if (step.step_type === 'llm_call') {
      const t = step.thinking_content?.trim() ?? ''
      if (t) segments.push(t)
    } else if (step.step_type === 'tool_call') {
      const brief = step.brief?.trim() ?? ''
      const toolName = step.tool_name?.trim() ?? ''
      segments.push(`tool：${brief || toolName || 'unknown'}`)
    }
  }
  return segments.join('\n\n---\n\n')
}

function buildConversationExportRows(
  conversation: { id: number; external_id: string; started_at: string | null },
  rounds: RoundGroup[]
): ConversationExportRow[] {
  return rounds.flatMap((round) => {
    if (!round.userMessage) return []

    const orderedAgentSteps = [...round.agentSteps].sort((a, b) => a.step_order - b.step_order)
    const llmSteps = orderedAgentSteps.filter((step) => step.step_type === 'llm_call')
    const assistantSteps = orderedAgentSteps.filter((step) => step.step_type === 'assistant_message')
    const roundSteps = [round.userMessage, ...orderedAgentSteps]

    return [{
      externalId: conversation.external_id,
      conversationId: conversation.id,
      startedAt: conversation.started_at ?? '',
      roundNumber: round.roundNumber,
      userStepId: round.userMessage.id,
      clientMessageId: round.userMessage.client_message_id ?? '',
      userCreatedAt: round.userMessage.created_at ?? '',
      userContent: round.userMessage.content ?? '',
      thinkingContent: buildAgentReasoningExport(orderedAgentSteps),
      assistantContent: assistantSteps
        .map((step) => step.content?.trim() ?? '')
        .filter(Boolean)
        .join('\n\n'),
      inputTokens: llmSteps.reduce((sum, step) => sum + (step.input_tokens ?? 0), 0),
      outputTokens: llmSteps.reduce((sum, step) => sum + (step.output_tokens ?? 0), 0),
      roundHasError: roundSteps.some((step) => step.status !== 'success'),
    }]
  })
}

function buildConversationExportCsv(rows: ConversationExportRow[]) {
  const lines = [
    EXPORT_COLUMNS.join(','),
    ...rows.map((row) => [
      row.externalId,
      row.conversationId,
      row.startedAt,
      row.roundNumber,
      row.userStepId,
      row.clientMessageId,
      row.userCreatedAt,
      row.userContent,
      row.thinkingContent,
      row.assistantContent,
      row.inputTokens,
      row.outputTokens,
      row.roundHasError,
    ].map(escapeCsvCell).join(',')),
  ]

  return `\uFEFF${lines.join('\n')}`
}

export default function ConversationLogPage() {
  const params = useParams()
  const router = useRouter()
  const agentId = Number(params.id)
  const conversationId = Number(params.conversationId)

  const { data: conversation } = useConversation(agentId, conversationId)
  const { data: timeline, isLoading: timelineLoading } = useConversationTimeline(agentId, conversationId)

  // LLM detail modal
  const [selectedStepId, setSelectedStepId] = useState<number | null>(null)
  const { data: stepDetail, isLoading: stepDetailLoading } = useStepDetail(
    agentId,
    conversationId,
    selectedStepId ?? 0
  )

  // Thinking block collapse state
  const [expandedThinking, setExpandedThinking] = useState<Set<number>>(new Set())

  // Copy state
  const [copiedField, setCopiedField] = useState<string | null>(null)

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

  // Group steps by round
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

  const exportRows = useMemo(() => {
    if (!conversation) return []
    return buildConversationExportRows(conversation, rounds)
  }, [conversation, rounds])

  const handleExport = useCallback(() => {
    if (!conversation || exportRows.length === 0) return

    const csv = buildConversationExportCsv(exportRows)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const safeExternalId = conversation.external_id.replace(/[^a-zA-Z0-9._-]/g, '_')
    link.href = url
    link.download = `conversation-${safeExternalId}-${formatExportTimestamp(new Date())}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }, [conversation, exportRows])

  // Find parent LLM step for a tool call
  const findParentLlm = useCallback(
    (step: StepTimelineItem): StepTimelineItem | null => {
      if (!step.parent_step_id || !timeline?.steps) return null
      return timeline.steps.find((s) => s.id === step.parent_step_id) ?? null
    },
    [timeline]
  )

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return ''
    return new Date(dateStr).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const formatMs = (ms: number | null) => {
    if (!ms) return ''
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const formatTokens = (n: number | null | undefined) => {
    if (n === null || n === undefined) return '—'
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
  }

  const formatDuration = () => {
    if (!conversation?.duration_seconds) return '—'
    const s = conversation.duration_seconds
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    const sec = s % 60
    if (m < 60) return `${m}m ${sec}s`
    const h = Math.floor(m / 60)
    return `${h}h ${m % 60}m`
  }

  // Render thinking + tool/assistant blocks interleaved
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
            </div>
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
            </div>
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
            {step.status === 'error' && (
              <Badge variant="danger">错误</Badge>
            )}
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
          </div>
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
                  <span>Token {formatTokens(
                    timeline?.steps.find(s => s.id === step.parent_step_id)?.total_tokens
                  )}</span>
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
          </div>
        )
      }
    }

    return elements
  }

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-[#ECECEC] bg-white/80 px-6 py-3 backdrop-blur-sm">
        <button
          onClick={() => router.push(`/agent/agents/${agentId}/conversations`)}
          className="flex items-center gap-1 text-sm text-[#737373] transition-colors hover:text-[#1a1a1a]"
        >
          <IconArrowLeft size={16} />
          返回
        </button>
        <h1 className="text-base font-semibold text-[#18181B]">会话日志详情</h1>
        <div className="flex-1" />
        <button
          onClick={handleExport}
          disabled={!conversation || timelineLoading || exportRows.length === 0}
          className="flex items-center gap-1.5 rounded-md border border-[#E5E5E5] bg-white px-3 py-1.5 text-sm text-[#404040] transition-colors hover:bg-[#F7F7F7] disabled:cursor-not-allowed disabled:opacity-50"
          title={exportRows.length === 0 ? '暂无可导出的用户消息' : '导出当前会话 CSV'}
        >
          <IconDownload size={16} />
          导出当前会话
        </button>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: conversation timeline */}
        <div className="flex-1 overflow-auto px-8 py-6" style={{ maxWidth: '680px', minWidth: '480px' }}>
          {timelineLoading ? (
            <div className="py-20 text-center text-sm text-[#737373]">加载中...</div>
          ) : rounds.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#737373]">暂无日志数据</div>
          ) : (
            <div className="space-y-8">
              {rounds.map((round) => (
                <div key={round.roundNumber}>
                  {/* Round divider */}
                  <div className="mb-4 flex items-center gap-3">
                    <div className="h-px flex-1 bg-[#F0F0F0]" />
                    <span className="text-xs font-medium text-[#A3A3A3]">
                      轮次 {round.roundNumber}
                    </span>
                    <div className="h-px flex-1 bg-[#F0F0F0]" />
                  </div>

                  {/* User message */}
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

                  {/* Agent response */}
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
        <div className="w-[300px] shrink-0 overflow-auto border-l border-[#ECECEC] bg-[#FAFAFA] px-5 py-6">
          <h3 className="mb-4 text-sm font-semibold text-[#18181B]">会话信息</h3>

          {conversation ? (
            <div className="space-y-3.5">
              <SideInfoRow label="会话 ID">
                <div className="flex items-center gap-1">
                  <span className="max-w-[160px] truncate font-mono text-xs text-[#737373]">
                    {conversation.external_id}
                  </span>
                  <button
                    onClick={() => handleCopy(conversation.external_id, 'sidebar-id')}
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
                  {conversation.external_user_id || '—'}
                </span>
              </SideInfoRow>

              <SideInfoRow label="状态">
                <Badge variant={conversation.status === 'active' ? 'success' : 'default'}>
                  {STATUS_LABELS[conversation.status] || conversation.status}
                </Badge>
              </SideInfoRow>

              <SideInfoRow label="来源">
                <Badge variant={conversation.source === 'api' ? 'warning' : 'default'}>
                  {SOURCE_LABELS[conversation.source] || conversation.source}
                </Badge>
              </SideInfoRow>

              <SideInfoRow label="开始时间">
                <span className="text-xs text-[#1a1a1a]">
                  {conversation.started_at
                    ? new Date(conversation.started_at).toLocaleString('zh-CN')
                    : '—'}
                </span>
              </SideInfoRow>

              <SideInfoRow label="持续时长">
                <span className="text-xs text-[#1a1a1a]">{formatDuration()}</span>
              </SideInfoRow>

              <div className="h-px bg-[#E5E5E5]" />

              <SideInfoRow label="轮数">
                <span className="text-xs text-[#1a1a1a]">{conversation.round_count}</span>
              </SideInfoRow>

              <SideInfoRow label="LLM 调用">
                <span className="text-xs text-[#1a1a1a]">{conversation.llm_call_count}</span>
              </SideInfoRow>

              <SideInfoRow label="工具调用">
                <span className="text-xs text-[#1a1a1a]">{conversation.tool_call_count}</span>
              </SideInfoRow>

              <div className="h-px bg-[#E5E5E5]" />

              <SideInfoRow label="输入 Token">
                <span className="text-xs text-[#1a1a1a]">
                  {formatTokens(conversation.total_input_tokens)}
                </span>
              </SideInfoRow>

              <SideInfoRow label="输出 Token">
                <span className="text-xs text-[#1a1a1a]">
                  {formatTokens(conversation.total_output_tokens)}
                </span>
              </SideInfoRow>

              <SideInfoRow label="总 Token">
                <span className="text-xs font-semibold text-[#1a1a1a]">
                  {formatTokens(conversation.total_tokens)}
                </span>
              </SideInfoRow>
            </div>
          ) : (
            <div className="text-xs text-[#737373]">加载中...</div>
          )}
        </div>
      </div>

      {/* LLM Detail Modal */}
      <LlmDetailModal
        open={!!selectedStepId}
        onClose={() => setSelectedStepId(null)}
        step={stepDetail ?? null}
        isLoading={stepDetailLoading}
      />
    </div>
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
