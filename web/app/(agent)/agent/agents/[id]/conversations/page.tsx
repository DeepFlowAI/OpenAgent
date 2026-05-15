'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  exportConversations,
  useConversations,
  type ConversationListParams,
} from '@/service/use-conversation'
import { getErrorMessage } from '@/service/base'
import { useAuthStore } from '@/context/auth-store'
import { Badge } from '@/app/components/base/badge'
import { SOURCE_LABELS, STATUS_LABELS } from '@/models/conversation'
import type { Conversation } from '@/models/conversation'
import {
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconCheck,
  IconDownload,
} from '@tabler/icons-react'
import { ConversationDrawer } from '@/app/components/features/conversation-drawer'

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

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

export default function ConversationsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const agentId = Number(params.id)
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''

  // Filters from URL
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [perPage, setPerPage] = useState(Number(searchParams.get('pageSize')) || 20)
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || '')
  const [sourceFilter, setSourceFilter] = useState(searchParams.get('source') || '')
  const [conversationIdFilter, setConversationIdFilter] = useState(searchParams.get('conversation_id') || '')
  const [userIdFilter, setUserIdFilter] = useState(searchParams.get('external_user_id') || '')

  const debouncedConversationId = useDebounce(conversationIdFilter, 300)
  const debouncedUserId = useDebounce(userIdFilter, 300)

  // Drawer
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null)
  const [exporting, setExporting] = useState(false)

  const exportParams: Omit<ConversationListParams, 'page' | 'per_page'> = useMemo(() => ({
    ...(statusFilter ? { status_filter: statusFilter } : {}),
    ...(sourceFilter ? { source: sourceFilter } : {}),
    ...(debouncedConversationId ? { conversation_id: debouncedConversationId.trim() } : {}),
    ...(debouncedUserId ? { external_user_id: debouncedUserId.trim() } : {}),
  }), [statusFilter, sourceFilter, debouncedConversationId, debouncedUserId])

  // Build query params
  const queryParams = useMemo(() => ({
    page,
    per_page: perPage,
    ...exportParams,
  }), [page, perPage, exportParams])

  const { data, isLoading } = useConversations(agentId, tenantId, queryParams)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 0

  // Sync filters to URL
  useEffect(() => {
    const params = new URLSearchParams()
    if (page > 1) params.set('page', String(page))
    if (perPage !== 20) params.set('pageSize', String(perPage))
    if (statusFilter) params.set('status', statusFilter)
    if (sourceFilter) params.set('source', sourceFilter)
    if (debouncedConversationId) params.set('conversation_id', debouncedConversationId)
    if (debouncedUserId) params.set('external_user_id', debouncedUserId)
    const qs = params.toString()
    const url = qs ? `?${qs}` : window.location.pathname
    window.history.replaceState({}, '', url)
  }, [page, perPage, statusFilter, sourceFilter, debouncedConversationId, debouncedUserId])

  // Reset page on filter change
  useEffect(() => { setPage(1) }, [statusFilter, sourceFilter, debouncedConversationId, debouncedUserId, perPage])

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

  const [copiedId, setCopiedId] = useState<string | null>(null)
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
      window.alert(await getErrorMessage(error))
    } finally {
      setExporting(false)
    }
  }, [agentId, tenantId, total, exportParams])

  // Page range for pagination
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
      {/* Sticky header */}
      <div className="sticky top-0 z-10 flex items-center border-b border-[#ECECEC] bg-white/80 px-8 py-3 backdrop-blur-sm">
        <h1 className="text-base font-semibold text-[#18181B]">会话记录</h1>
      </div>

      <div className="flex-1 overflow-auto px-8 py-6">
        {/* Filters */}
        <div className="mb-5 flex flex-wrap items-center gap-3">
          {/* Status */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] outline-none focus:border-[#1a1a1a]"
          >
            <option value="">全部状态</option>
            <option value="active">进行中</option>
            <option value="ended">已结束</option>
          </select>

          {/* Source */}
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="h-9 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] outline-none focus:border-[#1a1a1a]"
          >
            <option value="">全部来源</option>
            <option value="chat">对话窗口</option>
            <option value="api">API</option>
          </select>

          {/* Conversation ID */}
          <input
            type="text"
            value={conversationIdFilter}
            onChange={(e) => setConversationIdFilter(e.target.value)}
            placeholder="会话 ID"
            className="h-9 w-48 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
          />

          {/* User ID */}
          <input
            type="text"
            value={userIdFilter}
            onChange={(e) => setUserIdFilter(e.target.value)}
            placeholder="搜索用户"
            className="h-9 w-40 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] placeholder:text-[#A3A3A3] outline-none focus:border-[#1a1a1a]"
          />

          <button
            type="button"
            onClick={handleExport}
            disabled={isLoading || exporting || total === 0}
            className="ml-auto flex h-9 items-center gap-1.5 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#404040] transition-colors hover:bg-[#F7F7F7] disabled:cursor-not-allowed disabled:opacity-50"
            title="导出当前筛选条件下的全部会话消息"
          >
            <IconDownload size={16} />
            {exporting ? '导出中...' : '导出消息'}
          </button>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="py-20 text-center text-sm text-[#737373]">加载中...</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-sm text-[#737373]">
              {statusFilter || sourceFilter || debouncedConversationId || debouncedUserId
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
                          {SOURCE_LABELS[conv.source] || conv.source}
                        </Badge>
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

            {/* Pagination */}
            <div className="mt-4 flex items-center justify-between">
              <div className="flex items-center gap-3 text-sm text-[#737373]">
                <span>共 {total} 条</span>
                <select
                  value={perPage}
                  onChange={(e) => setPerPage(Number(e.target.value))}
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

      {/* Drawer */}
      <ConversationDrawer
        agentId={agentId}
        conversation={selectedConversation}
        onClose={() => setSelectedConversation(null)}
      />
    </div>
  )
}
