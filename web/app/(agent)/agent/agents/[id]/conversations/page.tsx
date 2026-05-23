'use client'

import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  exportConversations,
  useConversationChannelOptions,
  useConversations,
  type ConversationChannelOption,
  type ConversationListParams,
} from '@/service/use-conversation'
import { getErrorMessage } from '@/service/base'
import { useAuthStore } from '@/context/auth-store'
import { useToast } from '@/app/components/base/toast'
import { Badge } from '@/app/components/base/badge'
import {
  SOURCE_OPTIONS,
  STATUS_LABELS,
  getSourceLabel,
} from '@/models/conversation'
import type { Conversation } from '@/models/conversation'
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  ComboboxValue,
  useComboboxAnchor,
} from '@/app/components/base/combobox'
import {
  IconChevronLeft,
  IconChevronRight,
  IconChevronDown,
  IconCopy,
  IconCheck,
  IconDownload,
  IconSearch,
} from '@tabler/icons-react'
import { ConversationDrawer } from '@/app/components/features/conversation-drawer'

const DEFAULT_PAGE_SIZE = 20
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const SOURCE_VALUES = SOURCE_OPTIONS.map((option) => option.value)
const SOURCE_LABEL_BY_VALUE = Object.fromEntries(
  SOURCE_OPTIONS.map((option) => [option.value, option.label])
)
const CONTROL_CHAR_RE = /[\u0000-\u001F\u007F]/

type FilterState = {
  startTime: string
  endTime: string
  source: string
  channelId: string
  channelSource: string
  messageContent: string
  conversationId: string
  externalUserId: string
}

type SearchParamReader = {
  get: (name: string) => string | null
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function toDateTimeLocal(date: Date) {
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
    'T',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes()),
    ':',
    pad(date.getSeconds()),
  ].join('')
}

function parseDateTimeLocal(raw: string | null | undefined) {
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  return toDateTimeLocal(date)
}

function getDefaultDateRange() {
  const end = new Date()
  end.setHours(23, 59, 59, 0)
  const start = new Date(end)
  start.setDate(end.getDate() - 6)
  start.setHours(0, 0, 0, 0)
  return {
    startTime: toDateTimeLocal(start),
    endTime: toDateTimeLocal(end),
  }
}

function normalizeSourceFilter(raw: string | null | undefined): string {
  if (!raw) return ''
  const values = raw
    .split(',')
    .map((value) => value.trim())
    .filter((value): value is (typeof SOURCE_VALUES)[number] =>
      SOURCE_VALUES.includes(value as (typeof SOURCE_VALUES)[number])
    )
  return Array.from(new Set(values)).join(',')
}

function normalizeChannelIdFilter(raw: string | null | undefined): string {
  if (!raw) return ''
  const values: string[] = []
  for (const part of raw.split(',')) {
    const value = part.trim()
    if (!/^\d+$/.test(value)) continue
    const parsed = Number(value)
    if (parsed > 0 && !values.includes(String(parsed))) {
      values.push(String(parsed))
    }
  }
  return values.join(',')
}

function createInitialFilters(searchParams: SearchParamReader): FilterState {
  const defaults = getDefaultDateRange()
  const parsedStart = parseDateTimeLocal(searchParams.get('start_time'))
  const parsedEnd = parseDateTimeLocal(searchParams.get('end_time'))
  const hasTimeQuery = !!searchParams.get('start_time') || !!searchParams.get('end_time')

  return {
    startTime: hasTimeQuery && parsedStart && parsedEnd ? parsedStart : defaults.startTime,
    endTime: hasTimeQuery && parsedStart && parsedEnd ? parsedEnd : defaults.endTime,
    source: normalizeSourceFilter(searchParams.get('source')),
    channelId: normalizeChannelIdFilter(searchParams.get('channel_id')),
    channelSource: searchParams.get('channel_source')?.trim() ?? '',
    messageContent: searchParams.get('message_content')?.trim() ?? '',
    conversationId: searchParams.get('conversation_id')?.trim() ?? '',
    externalUserId: searchParams.get('external_user_id')?.trim() ?? '',
  }
}

function serializeFilters(filters: FilterState) {
  return JSON.stringify(filters)
}

function dateTimeLocalToApi(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return undefined
  return date.toISOString()
}

function buildConversationParams(
  filters: FilterState,
  page: number,
  perPage: number
): ConversationListParams {
  const params: ConversationListParams = {
    page,
    per_page: perPage,
  }
  const startTime = filters.startTime ? dateTimeLocalToApi(filters.startTime) : undefined
  const endTime = filters.endTime ? dateTimeLocalToApi(filters.endTime) : undefined

  if (startTime) params.start_time = startTime
  if (endTime) params.end_time = endTime
  if (filters.source) params.source = filters.source
  if (filters.channelId) params.channel_id = filters.channelId
  if (filters.channelSource) params.channel_source = filters.channelSource
  if (filters.messageContent) params.message_content = filters.messageContent
  if (filters.conversationId) params.conversation_id = filters.conversationId
  if (filters.externalUserId) params.external_user_id = filters.externalUserId

  return params
}

function buildUrlSearchParams(
  filters: FilterState,
  page: number,
  perPage: number
) {
  const params = new URLSearchParams()
  const listParams = buildConversationParams(filters, page, perPage)

  if (page > 1) params.set('page', String(page))
  if (perPage !== DEFAULT_PAGE_SIZE) params.set('pageSize', String(perPage))
  if (listParams.start_time) params.set('start_time', listParams.start_time)
  if (listParams.end_time) params.set('end_time', listParams.end_time)
  if (filters.source) params.set('source', filters.source)
  if (filters.channelId) params.set('channel_id', filters.channelId)
  if (filters.channelSource) params.set('channel_source', filters.channelSource)
  if (filters.messageContent) params.set('message_content', filters.messageContent)
  if (filters.conversationId) params.set('conversation_id', filters.conversationId)
  if (filters.externalUserId) params.set('external_user_id', filters.externalUserId)

  return params
}

function normalizeDraftFilters(filters: FilterState): FilterState {
  return {
    startTime: filters.startTime,
    endTime: filters.endTime,
    source: normalizeSourceFilter(filters.source),
    channelId: normalizeChannelIdFilter(filters.channelId),
    channelSource: filters.channelSource.trim(),
    messageContent: filters.messageContent.trim(),
    conversationId: filters.conversationId.trim(),
    externalUserId: filters.externalUserId.trim(),
  }
}

function validateFilters(filters: FilterState): string | null {
  const hasStart = !!filters.startTime
  const hasEnd = !!filters.endTime
  if (hasStart !== hasEnd) return '请同时选择开始与结束时间'

  if (hasStart && hasEnd) {
    const start = new Date(filters.startTime)
    const end = new Date(filters.endTime)
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return '请同时选择开始与结束时间'
    }
    if (start.getTime() > end.getTime()) return '开始时间不能晚于结束时间'
  }

  const channelSource = filters.channelSource.trim()
  if (
    channelSource &&
    (Array.from(channelSource).length > 64 || CONTROL_CHAR_RE.test(channelSource))
  ) {
    return '自定义渠道标识格式不正确'
  }

  return null
}

function hasActiveFilters(filters: FilterState) {
  return Boolean(
    filters.startTime ||
      filters.endTime ||
      filters.source ||
      filters.channelId ||
      filters.channelSource ||
      filters.messageContent ||
      filters.conversationId ||
      filters.externalUserId
  )
}

function formatExportTimestamp(date: Date) {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
  ].join('')
}

export default function ConversationsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const agentId = Number(params.id)
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''
  const { toast } = useToast()

  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [perPage, setPerPage] = useState(
    Number(searchParams.get('pageSize')) || DEFAULT_PAGE_SIZE
  )
  const [draftFilters, setDraftFilters] = useState<FilterState>(() =>
    createInitialFilters(searchParams)
  )
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(() =>
    createInitialFilters(searchParams)
  )

  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null)
  const [exporting, setExporting] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const syncedUrlKeyRef = useRef<string>('')

  const channelOptionsQuery = useConversationChannelOptions(agentId, tenantId)
  const channelOptions = channelOptionsQuery.data?.items ?? []

  const exportParams: Omit<ConversationListParams, 'page' | 'per_page'> = useMemo(() => {
    const { page: _page, per_page: _perPage, ...rest } = buildConversationParams(
      appliedFilters,
      page,
      perPage
    )
    return rest
  }, [appliedFilters, page, perPage])

  const queryParams = useMemo(
    () => buildConversationParams(appliedFilters, page, perPage),
    [appliedFilters, page, perPage]
  )

  const conversationsQuery = useConversations(agentId, tenantId, queryParams)
  const { data, isLoading, isSuccess, refetch } = conversationsQuery

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 0

  const appliedUrlKey = useMemo(
    () => JSON.stringify({ filters: appliedFilters, page, perPage }),
    [appliedFilters, page, perPage]
  )

  useEffect(() => {
    if (!isSuccess || syncedUrlKeyRef.current === appliedUrlKey) return
    syncedUrlKeyRef.current = appliedUrlKey
    const params = buildUrlSearchParams(appliedFilters, page, perPage)
    const qs = params.toString()
    const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname
    window.history.replaceState({}, '', url)
  }, [appliedFilters, appliedUrlKey, isSuccess, page, perPage])

  const updateDraft = useCallback(
    <K extends keyof FilterState,>(key: K, value: FilterState[K]) => {
      setDraftFilters((current) => ({ ...current, [key]: value }))
    },
    []
  )

  const handleQuery = useCallback(() => {
    const validationError = validateFilters(draftFilters)
    if (validationError) {
      toast(validationError, 'error')
      return
    }

    const nextFilters = normalizeDraftFilters(draftFilters)
    const nextKey = serializeFilters(nextFilters)
    const currentKey = serializeFilters(appliedFilters)

    if (nextKey === currentKey && page === 1) {
      void refetch()
      return
    }

    setAppliedFilters(nextFilters)
    setPage(1)
  }, [appliedFilters, draftFilters, page, refetch, toast])

  const formatDateTime = useCallback((dateStr: string | null) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }, [])

  const handleCopy = useCallback((text: string, e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text)
    setCopiedId(text)
    setTimeout(() => setCopiedId(null), 1500)
  }, [])

  const handleRowClick = useCallback((conv: Conversation) => {
    setSelectedConversation(conv)
  }, [])

  const handleExport = useCallback(async () => {
    if (!agentId || !tenantId || total === 0) return

    setExporting(true)
    try {
      const blob = await exportConversations(agentId, tenantId, exportParams)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `conversations-${agentId}-${formatExportTimestamp(new Date())}.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      toast(await getErrorMessage(error), 'error')
    } finally {
      setExporting(false)
    }
  }, [agentId, tenantId, total, exportParams, toast])

  const handlePerPageChange = useCallback((value: number) => {
    setPerPage(value)
    setPage(1)
  }, [])

  const pageRange = useMemo(() => {
    const range: number[] = []
    const maxVisible = 5
    let start = Math.max(1, page - Math.floor(maxVisible / 2))
    const end = Math.min(totalPages, start + maxVisible - 1)
    start = Math.max(1, end - maxVisible + 1)
    for (let i = start; i <= end; i++) range.push(i)
    return range
  }, [page, totalPages])

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center border-b border-[#ECECEC] bg-white/80 px-8 py-3 backdrop-blur-sm">
        <h1 className="text-base font-semibold text-[#18181B]">会话记录</h1>
      </div>

      <div className="flex-1 overflow-auto px-8 py-6">
        <div className="mb-5 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <input
                type="datetime-local"
                step={1}
                value={draftFilters.startTime}
                onChange={(e) => updateDraft('startTime', e.target.value)}
                aria-label="开始时间"
                className="h-10 w-[190px] rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] outline-none focus:border-[#1a1a1a]"
              />
              <span className="text-xs text-[#737373]">至</span>
              <input
                type="datetime-local"
                step={1}
                value={draftFilters.endTime}
                onChange={(e) => updateDraft('endTime', e.target.value)}
                aria-label="结束时间"
                className="h-10 w-[190px] rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] outline-none focus:border-[#1a1a1a]"
              />
            </div>

            <SourceFilterSelect
              value={draftFilters.source}
              onChange={(value) => updateDraft('source', value)}
            />

            <ChannelFilterSelect
              value={draftFilters.channelId}
              options={channelOptions}
              loading={channelOptionsQuery.isLoading}
              onChange={(value) => updateDraft('channelId', value)}
            />

            <input
              type="text"
              value={draftFilters.channelSource}
              onChange={(e) => updateDraft('channelSource', e.target.value)}
              placeholder="自定义渠道标识"
              className="h-10 w-56 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={draftFilters.conversationId}
              onChange={(e) => updateDraft('conversationId', e.target.value)}
              placeholder="会话 ID"
              className="h-10 w-48 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
            />

            <input
              type="text"
              value={draftFilters.externalUserId}
              onChange={(e) => updateDraft('externalUserId', e.target.value)}
              placeholder="搜索用户"
              className="h-10 w-44 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
            />

            <input
              type="text"
              value={draftFilters.messageContent}
              onChange={(e) => updateDraft('messageContent', e.target.value)}
              placeholder="搜索聊天内容"
              className="h-10 w-[320px] rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
            />

            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={handleQuery}
                className="flex h-10 items-center gap-1.5 rounded-lg bg-[#1a1a1a] px-4 text-sm text-white transition-colors hover:bg-[#2f2f2f]"
              >
                <IconSearch size={16} />
                查询
              </button>

              <button
                type="button"
                onClick={handleExport}
                disabled={isLoading || exporting || total === 0}
                className="flex h-10 items-center gap-1.5 rounded-lg border border-[#E5E5E5] bg-white px-4 text-sm text-[#404040] transition-colors hover:bg-[#F7F7F7] disabled:cursor-not-allowed disabled:opacity-50"
                title="导出当前筛选条件下的全部会话消息"
              >
                <IconDownload size={16} />
                {exporting ? '导出中...' : '导出'}
              </button>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="py-20 text-center text-sm text-[#737373]">加载中...</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-sm text-[#737373]">
              {hasActiveFilters(appliedFilters)
                ? '未找到匹配的会话记录，请调整筛选条件'
                : '暂无会话记录'}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border border-[#ECECEC]">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#F8F8F8]">
                    <th className="h-12 px-6 text-left text-[13px] font-semibold text-[#404040]">
                      会话 ID
                    </th>
                    <th className="h-12 w-[100px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      来源渠道
                    </th>
                    <th className="h-12 w-[150px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      渠道配置
                    </th>
                    <th className="h-12 w-[160px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      自定义渠道标识
                    </th>
                    <th className="h-12 w-[90px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      测试
                    </th>
                    <th className="h-12 w-[180px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      开始时间
                    </th>
                    <th className="h-12 px-6 text-left text-[13px] font-semibold text-[#404040]">
                      用户 ID
                    </th>
                    <th className="h-12 w-[100px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      会话轮次
                    </th>
                    <th className="h-12 w-[120px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                      状态
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((conv) => (
                    <tr
                      key={conv.id}
                      onClick={() => handleRowClick(conv)}
                      className="cursor-pointer border-t border-[#F0F0F0] transition-colors hover:bg-[#FAFAFA]"
                    >
                      <td className="h-14 px-6">
                        <div className="flex items-center gap-1.5">
                          <span className="max-w-[200px] truncate font-mono text-[13px] text-[#737373]">
                            {conv.external_id}
                          </span>
                          <button
                            onClick={(e) => handleCopy(conv.external_id, e)}
                            className="shrink-0 text-[#A3A3A3] transition-colors hover:text-[#404040]"
                            title="复制会话 ID"
                          >
                            {copiedId === conv.external_id ? (
                              <IconCheck size={14} className="text-[#059669]" />
                            ) : (
                              <IconCopy size={14} />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="h-14 w-[100px] px-6">
                        <Badge variant={conv.source === 'api' ? 'warning' : 'default'}>
                          {getSourceLabel(conv.source)}
                        </Badge>
                      </td>
                      <td className="h-14 w-[150px] px-6 text-[13px] text-[#737373]">
                        <span
                          className="block max-w-[130px] truncate"
                          title={conv.channel_name || undefined}
                        >
                          {conv.channel_name || '—'}
                        </span>
                      </td>
                      <td className="h-14 w-[160px] px-6 text-[13px] text-[#737373]">
                        <span
                          className="block max-w-[140px] truncate"
                          title={conv.channel_source || undefined}
                        >
                          {conv.channel_source || '—'}
                        </span>
                      </td>
                      <td className="h-14 w-[90px] px-6 text-[13px] text-[#737373]">
                        {conv.is_test ? '是' : '否'}
                      </td>
                      <td className="h-14 w-[180px] px-6 text-[13px] text-[#737373]">
                        {formatDateTime(conv.started_at)}
                      </td>
                      <td className="h-14 px-6 text-sm text-[#1a1a1a]">
                        {conv.external_user_id || '—'}
                      </td>
                      <td className="h-14 w-[100px] px-6 text-sm tabular-nums text-[#1a1a1a]">
                        {conv.round_count ?? 0}
                      </td>
                      <td className="h-14 w-[120px] px-6">
                        <Badge variant={conv.status === 'active' ? 'success' : 'default'}>
                          {STATUS_LABELS[conv.status] || conv.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <div className="flex items-center gap-3 text-sm text-[#737373]">
                <span>共 {total} 条</span>
                <select
                  value={perPage}
                  onChange={(e) => handlePerPageChange(Number(e.target.value))}
                  className="h-8 rounded-md border border-[#E5E5E5] bg-white px-2 text-sm outline-none"
                >
                  {PAGE_SIZE_OPTIONS.map((size) => (
                    <option key={size} value={size}>
                      {size} 条/页
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                >
                  <IconChevronLeft size={16} />
                </button>
                {pageRange.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={
                      p === page
                        ? 'flex h-8 w-8 items-center justify-center rounded-md bg-[#1a1a1a] text-sm font-medium text-white'
                        : 'flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E5E5] text-sm text-[#737373] transition-colors hover:bg-[#F5F5F5]'
                    }
                  >
                    {p}
                  </button>
                ))}
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                >
                  <IconChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <ConversationDrawer
        agentId={agentId}
        conversation={selectedConversation}
        onClose={() => setSelectedConversation(null)}
      />
    </div>
  )
}

function SourceFilterSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const selected = value ? value.split(',').filter(Boolean) : []
  const anchor = useComboboxAnchor()

  return (
    <div className="w-[180px] shrink-0">
      <Combobox
        multiple
        autoHighlight
        items={SOURCE_VALUES}
        value={selected}
        onValueChange={(values: string[]) => onChange(normalizeSourceFilter(values.join(',')))}
      >
        <div className="relative">
          <ComboboxChips
            ref={anchor}
            className="min-h-10 pr-8 text-sm"
          >
            <ComboboxValue>
              {(values: string[] | null) => (
                <>
                  {(values ?? []).map((item) => (
                    <ComboboxChip key={item} className="h-6 text-xs">
                      {SOURCE_LABEL_BY_VALUE[item] ?? item}
                    </ComboboxChip>
                  ))}
                  <ComboboxChipsInput
                    placeholder={selected.length ? '搜索...' : '全部来源'}
                    className="min-w-0 text-sm placeholder:text-[#737373]"
                  />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <IconChevronDown
            size={16}
            className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[#737373]"
          />
        </div>
        <ComboboxContent anchor={anchor}>
          <ComboboxEmpty className="text-sm">无匹配项</ComboboxEmpty>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item} className="py-2 text-sm">
                {SOURCE_LABEL_BY_VALUE[item] ?? item}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

function ChannelFilterSelect({
  value,
  options,
  loading,
  onChange,
}: {
  value: string
  options: ConversationChannelOption[]
  loading: boolean
  onChange: (value: string) => void
}) {
  const selected = value ? value.split(',').filter(Boolean) : []
  const optionValues = Array.from(
    new Set([...options.map((option) => String(option.id)), ...selected])
  )
  const labelByValue = Object.fromEntries(
    options.map((option) => [String(option.id), option.name])
  )
  const anchor = useComboboxAnchor()

  return (
    <div className="w-[200px] shrink-0">
      <Combobox
        multiple
        autoHighlight
        items={optionValues}
        value={selected}
        onValueChange={(values: string[]) => onChange(normalizeChannelIdFilter(values.join(',')))}
      >
        <div className="relative">
          <ComboboxChips
            ref={anchor}
            className="min-h-10 pr-8 text-sm"
          >
            <ComboboxValue>
              {(values: string[] | null) => (
                <>
                  {(values ?? []).map((item) => (
                    <ComboboxChip key={item} className="h-6 text-xs">
                      {labelByValue[item] ?? `#${item}`}
                    </ComboboxChip>
                  ))}
                  <ComboboxChipsInput
                    placeholder={
                      selected.length
                        ? '搜索...'
                        : loading
                          ? '加载渠道...'
                          : '全部渠道配置'
                    }
                    className="min-w-0 text-sm placeholder:text-[#737373]"
                  />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <IconChevronDown
            size={16}
            className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[#737373]"
          />
        </div>
        <ComboboxContent anchor={anchor}>
          <ComboboxEmpty className="text-sm">无匹配项</ComboboxEmpty>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item} className="py-2 text-sm">
                {labelByValue[item] ?? `#${item}`}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}
