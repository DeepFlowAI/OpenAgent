'use client'

import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/utils/classnames'
import { Badge } from '@/app/components/base/badge'
import type { StepDetail, ToolCallStepItem } from '@/models/conversation'
import {
  IconX,
  IconCopy,
  IconCheck,
  IconBrain,
  IconChevronDown,
  IconChevronRight,
} from '@tabler/icons-react'

type LlmDetailModalProps = {
  open: boolean
  onClose: () => void
  step: StepDetail | null
  isLoading?: boolean
}

type TabKey = 'request' | 'response'
type ViewMode = 'formatted' | 'json'

export function LlmDetailModal({ open, onClose, step, isLoading }: LlmDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('request')
  const [viewMode, setViewMode] = useState<ViewMode>('formatted')
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
    return () => { document.body.style.overflow = '' }
  }, [open])

  useEffect(() => {
    setActiveTab('request')
    setViewMode('formatted')
  }, [step?.id])

  const handleCopy = useCallback((text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 1500)
  }, [])

  if (!open) return null

  const formatMs = (ms: number | null) => {
    if (!ms) return '—'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const formatTokens = (n: number | null) => {
    if (n === null || n === undefined) return '—'
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-10 flex h-[min(90vh,800px)] w-[min(95vw,1200px)] flex-col rounded-xl border border-[#E5E5E5] bg-white shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#ECECEC] px-6 py-4">
          <div className="flex items-center gap-2">
            <IconBrain size={20} className="text-[#737373]" />
            <h2 className="text-base font-semibold text-[#18181B]">LLM 请求/响应详情</h2>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-[#F5F5F5]"
          >
            <IconX size={18} />
          </button>
        </div>

        {isLoading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-[#737373]">
            加载中...
          </div>
        ) : step ? (
          <>
            {/* Meta summary */}
            <div className="flex flex-wrap items-center gap-4 border-b border-[#ECECEC] px-6 py-3">
              <MetaItem label="模型" value={step.model_name || '—'} />
              <MetaItem
                label="思考"
                value={step.thinking_enabled ? '开启' : '关闭'}
              />
              <MetaItem label="耗时" value={formatMs(step.duration_ms)} />
              <MetaItem
                label="状态"
                value={
                  <Badge
                    variant={step.status === 'success' ? 'success' : step.status === 'error' ? 'danger' : 'default'}
                  >
                    {step.status}
                  </Badge>
                }
              />
              <MetaItem label="输入" value={formatTokens(step.input_tokens)} />
              <MetaItem label="输出" value={formatTokens(step.output_tokens)} />
              <MetaItem
                label="总 Token"
                value={<span className="font-semibold">{formatTokens(step.total_tokens)}</span>}
              />
              {step.request_id && (
                <MetaItem
                  label="Request ID"
                  value={
                    <div className="flex items-center gap-1">
                      <span className="max-w-[160px] truncate font-mono text-xs">
                        {step.request_id}
                      </span>
                      <button
                        onClick={() => handleCopy(step.request_id!, 'request_id')}
                        className="text-[#A3A3A3] hover:text-[#404040]"
                      >
                        {copiedField === 'request_id' ? (
                          <IconCheck size={12} className="text-[#059669]" />
                        ) : (
                          <IconCopy size={12} />
                        )}
                      </button>
                    </div>
                  }
                />
              )}
            </div>

            {/* Tabs */}
            <div className="flex items-center justify-between border-b border-[#ECECEC] px-6">
              <div className="flex gap-0">
                {(['request', 'response'] as TabKey[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={cn(
                      'border-b-2 px-4 pb-3 pt-3 text-sm transition-colors',
                      activeTab === tab
                        ? 'border-[#1a1a1a] font-semibold text-[#1a1a1a]'
                        : 'border-transparent text-[#999] hover:text-[#1a1a1a]'
                    )}
                  >
                    {tab === 'request' ? '请求' : '响应'}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1 rounded-md border border-[#E5E5E5] p-0.5">
                {(['formatted', 'json'] as ViewMode[]).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setViewMode(mode)}
                    className={cn(
                      'rounded px-2.5 py-1 text-xs transition-colors',
                      viewMode === mode
                        ? 'bg-[#1a1a1a] text-white'
                        : 'text-[#737373] hover:text-[#1a1a1a]'
                    )}
                  >
                    {mode === 'formatted' ? '格式化' : 'JSON'}
                  </button>
                ))}
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
              {activeTab === 'request' ? (
                <RequestContent step={step} viewMode={viewMode} onCopy={handleCopy} copiedField={copiedField} />
              ) : (
                <ResponseContent step={step} viewMode={viewMode} onCopy={handleCopy} copiedField={copiedField} />
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-[#737373]">
            无数据
          </div>
        )}
      </div>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-[#A3A3A3]">{label}</span>
      <span className="text-xs text-[#1a1a1a]">{typeof value === 'string' ? value : value}</span>
    </div>
  )
}

type ContentProps = {
  step: StepDetail
  viewMode: ViewMode
  onCopy: (text: string, field: string) => void
  copiedField: string | null
}

/** Preview length for history message body; full text available via expand/collapse. */
const HISTORY_MESSAGE_PREVIEW_CHARS = 800

function ExpandableLongText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const needsToggle = text.length > HISTORY_MESSAGE_PREVIEW_CHARS
  const shown = needsToggle && !expanded ? text.slice(0, HISTORY_MESSAGE_PREVIEW_CHARS) : text

  return (
    <div className="min-w-0">
      <div className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[#404040]">
        {shown}
      </div>
      {needsToggle && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 flex items-center gap-1 rounded-md text-xs font-medium text-[#2563EB] transition-colors hover:bg-[#EFF6FF] hover:text-[#1D4ED8]"
        >
          {expanded ? (
            <>
              <IconChevronDown size={14} className="shrink-0 -rotate-180" />
              收起
            </>
          ) : (
            <>
              <IconChevronRight size={14} className="shrink-0" />
              展开全文
            </>
          )}
        </button>
      )}
    </div>
  )
}

function RequestContent({ step, viewMode, onCopy, copiedField }: ContentProps) {
  if (viewMode === 'json') {
    const jsonData = {
      messages: step.request_messages,
      tools: step.request_tools,
      params: step.request_params,
    }
    return (
      <div className="px-6 py-4">
        <JsonBlock
          data={jsonData}
          onCopy={onCopy}
          copiedField={copiedField}
          copyKey="request_json"
        />
      </div>
    )
  }

  const messages = (step.request_messages as Array<{ role: string; content?: string; tool_calls?: unknown[]; tool_call_id?: string }>) ?? []

  const systemMsg = messages.find(m => m.role === 'system')
  const lastUserIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return i
    }
    return -1
  })()
  const currentUserMsg = lastUserIdx >= 0 ? messages[lastUserIdx] : null
  const historyMessages = messages.filter((m, idx) => {
    if (m.role === 'system') return false
    if (idx === lastUserIdx) return false
    return true
  })

  const tools = (step.request_tools as unknown[]) ?? []
  const params = step.request_params as Record<string, unknown> | null

  return (
    <div className="divide-y divide-[#F0F0F0]">
      {systemMsg && (
        <CollapsibleSection title="System 消息" defaultOpen={false}>
          <div className="whitespace-pre-wrap break-words font-mono text-[13px] leading-[1.6] text-[#374151]">
            {typeof systemMsg.content === 'string'
              ? systemMsg.content
              : JSON.stringify(systemMsg.content, null, 2)}
          </div>
        </CollapsibleSection>
      )}

      <CollapsibleSection
        title="历史消息"
        badge={historyMessages.length > 0 ? `${historyMessages.length} 条` : undefined}
        defaultOpen={false}
      >
        {historyMessages.length === 0 ? (
          <span className="text-xs text-[#A3A3A3]">无历史消息</span>
        ) : (
          <div className="space-y-3">
            {historyMessages.map((msg, idx) => (
              <div key={idx} className="min-w-0 rounded-md border border-[#F0F0F0] p-3">
                <div className="mb-1.5 flex items-center gap-2">
                  <Badge
                    variant={
                      msg.role === 'assistant' ? 'default'
                        : msg.role === 'tool' ? 'warning'
                          : 'success'
                    }
                  >
                    {msg.role}
                  </Badge>
                  {msg.tool_call_id && (
                    <span className="font-mono text-[11px] text-[#A3A3A3]">
                      {msg.tool_call_id}
                    </span>
                  )}
                </div>
                {msg.content == null ? (
                  !msg.tool_calls && (
                    <span className="italic text-[#A3A3A3]">(空)</span>
                  )
                ) : typeof msg.content === 'string' ? (
                  <ExpandableLongText text={msg.content} />
                ) : (
                  <ExpandableLongText text={JSON.stringify(msg.content, null, 2)} />
                )}
                {msg.tool_calls && (
                  <div className="mt-2 min-w-0 rounded bg-[#FAFAFA] p-2">
                    <span className="text-[10px] font-medium text-[#737373]">Tool Calls:</span>
                    <pre className="mt-1 max-w-full whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-[#404040]">
                      {JSON.stringify(msg.tool_calls, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CollapsibleSection>

      {currentUserMsg && (
        <CollapsibleSection title="当前用户消息" defaultOpen={false}>
          <div className="whitespace-pre-wrap break-words text-[13px] leading-[1.6] text-[#374151]">
            {typeof currentUserMsg.content === 'string'
              ? currentUserMsg.content
              : JSON.stringify(currentUserMsg.content, null, 2)}
          </div>
        </CollapsibleSection>
      )}

      <CollapsibleSection
        title="tools[]"
        titleMono
        badge={tools.length > 0 ? `${tools.length} 个工具` : undefined}
        defaultOpen={false}
      >
        {tools.length === 0 ? (
          <span className="text-xs text-[#A3A3A3]">无工具</span>
        ) : (
          <pre className="max-h-[400px] max-w-full overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[#404040]">
            {JSON.stringify(step.request_tools, null, 2)}
          </pre>
        )}
      </CollapsibleSection>

      <CollapsibleSection title="模型参数" defaultOpen={false}>
        {params && Object.keys(params).length > 0 ? (
          <div className="divide-y divide-[#F4F4F5]">
            {Object.entries(params).map(([key, value]) => (
              <div key={key} className="flex h-9 items-center">
                <span className="w-40 shrink-0 font-mono text-xs text-[#737373]">{key}</span>
                <span className={cn(
                  'font-mono text-xs',
                  value === true || value === 'enabled' ? 'text-[#16A34A]' : 'text-[#1a1a1a]'
                )}>
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <span className="text-xs text-[#A3A3A3]">无参数</span>
        )}
      </CollapsibleSection>
    </div>
  )
}

function CollapsibleSection({
  title,
  titleMono = false,
  badge,
  defaultOpen = false,
  children,
}: {
  title: string
  titleMono?: boolean
  badge?: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(defaultOpen)

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 bg-[#FAFAFA] px-6 py-3 text-left hover:bg-[#F5F5F5]"
      >
        {expanded
          ? <IconChevronDown size={15} className="shrink-0 text-[#737373]" />
          : <IconChevronRight size={15} className="shrink-0 text-[#737373]" />
        }
        <span className={cn(
          'text-[13px] font-semibold text-[#1a1a1a]',
          titleMono && 'font-mono'
        )}>
          {title}
        </span>
        {badge && (
          <span className="rounded bg-[#F4F4F5] px-2 py-0.5 text-[11px] text-[#71717A]">
            {badge}
          </span>
        )}
      </button>
      {expanded && (
        <div className="bg-white px-6 py-4">
          {children}
        </div>
      )}
    </div>
  )
}

function ResponseContent({ step, viewMode, onCopy, copiedField }: ContentProps) {
  if (viewMode === 'json') {
    const jsonData = {
      content: step.content,
      thinking_content: step.thinking_content,
      tool_calls: step.response_tool_calls,
      tool_call_steps: step.tool_call_steps,
      finish_reason: step.finish_reason,
      usage: {
        input_tokens: step.input_tokens,
        output_tokens: step.output_tokens,
        total_tokens: step.total_tokens,
      },
    }
    return (
      <div className="px-6 py-4">
        <JsonBlock
          data={jsonData}
          onCopy={onCopy}
          copiedField={copiedField}
          copyKey="response_json"
        />
      </div>
    )
  }

  return (
    <div className="divide-y divide-[#F0F0F0]">
      {/* Thinking */}
      {step.thinking_content && (
        <CollapsibleSection title="Thinking" defaultOpen={false}>
          <div className="whitespace-pre-wrap break-words font-mono text-[13px] leading-[1.6] text-[#374151]">
            {step.thinking_content}
          </div>
        </CollapsibleSection>
      )}

      {/* Content */}
      {step.content && (
        <CollapsibleSection title="Content" defaultOpen={true}>
          <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-[#404040]">
            {step.content}
          </div>
        </CollapsibleSection>
      )}

      {/* Tool Call Chain */}
      {step.tool_call_steps && step.tool_call_steps.length > 0 && (
        <CollapsibleSection
          title="工具调用链路"
          badge={`${step.tool_call_steps.length} 次调用`}
          defaultOpen={true}
        >
          <div className="-mx-6 divide-y divide-[#F0F0F0]">
            {step.tool_call_steps.map((tc, idx) => (
              <ToolCallItem
                key={tc.id}
                item={tc}
                index={idx}
                onCopy={onCopy}
                copiedField={copiedField}
              />
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* LLM declared tool_calls (fallback when no executed steps) */}
      {step.response_tool_calls && Array.isArray(step.response_tool_calls) && (step.response_tool_calls as unknown[]).length > 0 && (
        !(step.tool_call_steps && step.tool_call_steps.length > 0) && (
          <CollapsibleSection
            title="Tool Calls (LLM 返回)"
            badge={`${(step.response_tool_calls as unknown[]).length}`}
            defaultOpen={false}
          >
            <pre className="max-w-full whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[#404040]">
              {JSON.stringify(step.response_tool_calls, null, 2)}
            </pre>
          </CollapsibleSection>
        )
      )}

      {/* Finish Reason */}
      {step.finish_reason && (
        <div className="px-6 py-3">
          <span className="text-xs text-[#A3A3A3]">finish_reason: </span>
          <span className="font-mono text-xs text-[#1a1a1a]">{step.finish_reason}</span>
        </div>
      )}
    </div>
  )
}

function ToolCallItem({
  item,
  index,
  onCopy,
  copiedField,
}: {
  item: ToolCallStepItem
  index: number
  onCopy: (text: string, field: string) => void
  copiedField: string | null
}) {
  const [argsExpanded, setArgsExpanded] = useState(true)
  const [responseExpanded, setResponseExpanded] = useState(false)

  const statusColor = item.status === 'success'
    ? 'text-[#16A34A] bg-[#F0FDF4]'
    : item.status === 'error'
      ? 'text-[#DC2626] bg-[#FEF2F2]'
      : 'text-[#71717A] bg-[#F4F4F5]'

  const formatDuration = (ms: number | null) => {
    if (!ms) return '—'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const argsStr = item.tool_arguments ? JSON.stringify(item.tool_arguments, null, 2) : null
  const responseStr = item.tool_response || null
  const argsCopyKey = `tool_args_${item.id}`
  const responseCopyKey = `tool_response_${item.id}`

  return (
    <div className="px-4 py-3">
      {/* Tool call header */}
      <div className="flex items-center gap-3">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#F4F4F5] text-[10px] font-semibold text-[#71717A]">
          {index + 1}
        </span>
        <span className="font-mono text-[13px] font-semibold text-[#1a1a1a]">
          {item.tool_name || 'unknown'}
        </span>
        {item.tool_type && (
          <span className="rounded bg-[#F4F4F5] px-1.5 py-0.5 text-[10px] font-medium text-[#71717A]">
            {item.tool_type}
          </span>
        )}
        <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', statusColor)}>
          {item.status}
        </span>
        <span className="text-[11px] text-[#A3A3A3]">
          {formatDuration(item.duration_ms)}
        </span>
        {item.brief && (
          <span className="truncate text-xs text-[#71717A]">
            {item.brief}
          </span>
        )}
      </div>

      {/* Arguments section */}
      {argsStr && (
        <div className="mt-2 ml-8">
          <button
            onClick={() => setArgsExpanded(!argsExpanded)}
            className="flex items-center gap-1 text-xs font-medium text-[#737373] hover:text-[#1a1a1a]"
          >
            {argsExpanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
            输入参数
          </button>
          {argsExpanded && (
            <div className="relative mt-1 rounded-md bg-[#FAFAFA] p-3">
              <button
                onClick={() => onCopy(argsStr, argsCopyKey)}
                className="absolute right-2 top-2 rounded p-1 text-[#A3A3A3] hover:bg-white hover:text-[#404040]"
              >
                {copiedField === argsCopyKey ? (
                  <IconCheck size={12} className="text-[#059669]" />
                ) : (
                  <IconCopy size={12} />
                )}
              </button>
              <pre className="max-h-[200px] max-w-full overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[#404040]">
                {argsStr}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Response section */}
      {responseStr && (
        <div className="mt-2 ml-8">
          <button
            onClick={() => setResponseExpanded(!responseExpanded)}
            className="flex items-center gap-1 text-xs font-medium text-[#737373] hover:text-[#1a1a1a]"
          >
            {responseExpanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
            返回结果
            <span className="ml-1 text-[10px] text-[#A3A3A3]">
              ({responseStr.length} chars)
            </span>
          </button>
          {responseExpanded && (
            <div className="relative mt-1 rounded-md bg-[#FAFAFA] p-3">
              <button
                onClick={() => onCopy(responseStr, responseCopyKey)}
                className="absolute right-2 top-2 rounded p-1 text-[#A3A3A3] hover:bg-white hover:text-[#404040]"
              >
                {copiedField === responseCopyKey ? (
                  <IconCheck size={12} className="text-[#059669]" />
                ) : (
                  <IconCopy size={12} />
                )}
              </button>
              <pre className="max-h-[300px] max-w-full overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[#404040]">
                {responseStr}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Error message */}
      {item.error_message && (
        <div className="mt-2 ml-8 rounded-md bg-[#FEF2F2] p-2">
          <span className="text-xs font-medium text-[#DC2626]">Error: </span>
          <span className="text-xs text-[#DC2626]">{item.error_message}</span>
        </div>
      )}
    </div>
  )
}

function JsonBlock({
  data,
  onCopy,
  copiedField,
  copyKey,
}: {
  data: unknown
  onCopy: (text: string, field: string) => void
  copiedField: string | null
  copyKey: string
}) {
  const jsonStr = JSON.stringify(data, null, 2)
  return (
    <div className="relative">
      <button
        onClick={() => onCopy(jsonStr, copyKey)}
        className="absolute right-3 top-3 flex items-center gap-1 rounded-md bg-white/80 px-2 py-1 text-xs text-[#737373] backdrop-blur-sm transition-colors hover:text-[#1a1a1a]"
      >
        {copiedField === copyKey ? (
          <>
            <IconCheck size={12} className="text-[#059669]" />
            已复制
          </>
        ) : (
          <>
            <IconCopy size={12} />
            复制 JSON
          </>
        )}
      </button>
      <pre className="max-h-[60vh] max-w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-[#FAFAFA] p-4 font-mono text-xs leading-relaxed text-[#404040]">
        {jsonStr}
      </pre>
    </div>
  )
}
