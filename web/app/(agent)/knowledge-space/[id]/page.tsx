'use client'

import { use, useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { cn } from '@/utils/classnames'
import { Button } from '@/app/components/base/button'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { useKnowledgeBase } from '@/service/use-knowledge-base'
import {
  useDocuments,
  useSyncLogs,
  useTriggerSync,
} from '@/service/use-document'
import type { SyncMode } from '@/service/use-document'
import { knowledgeBaseKeys } from '@/service/use-knowledge-base'
import { useQueryClient } from '@tanstack/react-query'
import { IconArrowLeft, IconRefresh, IconChevronDown } from '@tabler/icons-react'
import { PermissionRulesTab } from '@/app/components/features/permission-rules-tab'

const tabs = [
  { key: 'documents', label: '文档列表' },
  { key: 'sync', label: '同步与解析' },
  { key: 'config', label: '配置概览' },
  { key: 'permissions', label: '权限引擎' },
] as const

type TabKey = (typeof tabs)[number]['key']

export default function KnowledgeBaseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const kbId = Number(id)
  const [activeTab, setActiveTab] = useState<TabKey>('documents')
  const [syncDropdownOpen, setSyncDropdownOpen] = useState(false)
  const syncDropdownRef = useRef<HTMLDivElement>(null)
  const { toast } = useToast()
  const qc = useQueryClient()

  const { data: kb, isLoading: kbLoading } = useKnowledgeBase(kbId)
  const { data: logsData } = useSyncLogs(kbId)
  const syncMutation = useTriggerSync()

  useEffect(() => {
    if (!syncDropdownOpen) return
    const onClickOutside = (e: MouseEvent) => {
      if (syncDropdownRef.current && !syncDropdownRef.current.contains(e.target as Node)) {
        setSyncDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [syncDropdownOpen])

  const handleSync = useCallback(async (mode: SyncMode = 'auto') => {
    setSyncDropdownOpen(false)
    try {
      const res = await syncMutation.mutateAsync({ kbId, syncMode: mode })
      const status = typeof res?.status === 'string' ? res.status : ''
      qc.invalidateQueries({ queryKey: knowledgeBaseKeys.detail(kbId) })
      if (status === 'failed') {
        const err =
          typeof res?.error === 'string' && res.error
            ? res.error
            : '同步失败'
        toast(err, 'error')
        return
      }
      if (status === 'partial_success') {
        toast('同步结束：部分文件解析失败，请查看解析日志', 'error')
        return
      }
      toast(mode === 'full' ? '全量同步完成' : '同步完成', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }, [kbId, syncMutation, qc, toast])

  if (kbLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (!kb) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">知识库不存在</p>
      </div>
    )
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleString('zh-CN')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 border-b border-border bg-background px-8 pt-4">
        <div className="flex items-center justify-between pb-4">
          <div className="flex items-center gap-3">
            <Link
              href="/knowledge-space"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <IconArrowLeft size={18} />
            </Link>
            <h1 className="text-lg font-semibold text-foreground">{kb.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Link href={`/knowledge-space/${kbId}/edit`}>
              <Button variant="outline">编辑</Button>
            </Link>
            <div className="relative" ref={syncDropdownRef}>
              <div className="flex">
                <Button
                  variant="default"
                  className="rounded-r-none"
                  onClick={() => handleSync('auto')}
                  disabled={syncMutation.isPending}
                  aria-busy={syncMutation.isPending}
                >
                  <IconRefresh
                    size={16}
                    className={cn('mr-1.5', syncMutation.isPending && 'animate-spin')}
                    aria-hidden
                  />
                  同步并解析
                </Button>
                <button
                  type="button"
                  className={cn(
                    'inline-flex items-center rounded-r-lg border-l border-white/20 bg-[#1a1a1a] px-2 text-white transition-colors hover:bg-[#333]',
                    'disabled:bg-[#D4D4D4] disabled:text-[#A3A3A3]',
                  )}
                  disabled={syncMutation.isPending}
                  onClick={() => setSyncDropdownOpen((v) => !v)}
                  aria-label="更多同步选项"
                >
                  <IconChevronDown size={14} />
                </button>
              </div>
              {syncDropdownOpen && (
                <div className="absolute right-0 top-full z-20 mt-1 w-36 overflow-hidden rounded-lg border border-border bg-white shadow-lg">
                  <button
                    type="button"
                    className="w-full px-4 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[#F5F5F5]"
                    onClick={() => handleSync('full')}
                  >
                    全量同步
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'border-b-2 pb-2 text-sm font-medium transition-colors',
                activeTab === tab.key
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-8">
        {activeTab === 'documents' && (
          <DocumentsTab kbId={kbId} formatDate={formatDate} />
        )}
        {activeTab === 'sync' && (
          <SyncTab kb={kb} logs={logsData?.items ?? []} formatDate={formatDate} />
        )}
        {activeTab === 'config' && <ConfigTab kb={kb} />}
        {activeTab === 'permissions' && (
          <PermissionRulesTab kbId={kbId} tenantId={kb.tenant_id} />
        )}
      </div>
    </div>
  )
}

const DOC_LIST_PER_PAGE = 20

function DocumentsTab({
  kbId,
  formatDate,
}: {
  kbId: number
  formatDate: (d: string | null) => string
}) {
  const router = useRouter()
  const [page, setPage] = useState(1)

  useEffect(() => {
    setPage(1)
  }, [kbId])

  const { data: docsData, isLoading: docsLoading } = useDocuments(kbId, {
    page,
    per_page: DOC_LIST_PER_PAGE,
  })

  useEffect(() => {
    if (!docsData) return
    const pages = docsData.pages
    if (pages > 0 && page > pages) {
      setPage(pages)
    }
  }, [docsData, page])

  const docs = docsData?.items ?? []
  const totalPages = docsData?.pages ?? 0

  if (docsLoading) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">加载中...</div>
    )
  }
  if (docs.length === 0) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        暂无文档，请先执行同步操作
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-[#FAFAFA]">
              <th className="whitespace-nowrap px-4 py-3 text-left font-medium text-muted-foreground">
                标题
              </th>
              <th className="whitespace-nowrap px-4 py-3 text-left font-medium text-muted-foreground">
                路径
              </th>
              <th className="whitespace-nowrap px-4 py-3 text-left font-medium text-muted-foreground">
                切片数
              </th>
              <th className="whitespace-nowrap px-4 py-3 text-left font-medium text-muted-foreground">
                更新时间
              </th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr
                key={doc.id}
                className="cursor-pointer border-b border-border last:border-b-0 transition-colors hover:bg-[#FAFAFA]"
                onClick={() => router.push(`/knowledge-space/${kbId}/documents/${doc.id}`)}
              >
                <td className="px-4 py-3 font-medium text-foreground">{doc.title || '(无标题)'}</td>
                <td className="max-w-[280px] truncate px-4 py-3 text-muted-foreground">{doc.file_path}</td>
                <td className="whitespace-nowrap px-4 py-3 text-muted-foreground tabular-nums">
                  {doc.slice_count}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                  {formatDate(doc.updated_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}

function SyncTab({
  kb,
  logs,
  formatDate,
}: {
  kb: { last_synced_at: string | null; document_count: number }
  logs: Array<{
    id: number; status: string; started_at: string; finished_at: string | null
    total_files: number | null; success_count: number | null; error_count: number | null
    details: {
      sync_mode?: string; schema_changed?: boolean
      added_count?: number; modified_count?: number; unchanged_count?: number; deleted_count?: number
      files?: Array<{ file: string; status: string; error?: string; slice_count?: number }>
    } | Array<{ file: string; status: string; error?: string; slice_count?: number }> | null
  }>
  formatDate: (d: string | null) => string
}) {
  const MAX_PARSE_LOG_ROWS = 10
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())
  const [expandedDetailLogs, setExpandedDetailLogs] = useState<Set<number>>(
    new Set()
  )

  const toggleDetailList = (logId: number) => {
    setExpandedDetailLogs((prev) => {
      const next = new Set(prev)
      if (next.has(logId)) next.delete(logId)
      else next.add(logId)
      return next
    })
  }

  const toggleError = (key: string) => {
    setExpandedErrors((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const logStatusColor: Record<string, string> = {
    running: 'bg-blue-50 text-blue-600 ring-1 ring-blue-200',
    success: 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200',
    partial_success:
      'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
    failed: 'bg-red-50 text-red-600 ring-1 ring-red-200',
  }
  const logStatusText: Record<string, string> = {
    running: '运行中',
    success: '成功',
    partial_success: '部分成功',
    failed: '失败',
  }

  return (
    <div className="space-y-6">
      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-xs font-medium text-muted-foreground">上次同步时间</p>
          <p className="mt-1.5 text-sm font-semibold text-foreground">{formatDate(kb.last_synced_at)}</p>
        </div>
        <div className="rounded-xl border border-border bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-xs font-medium text-muted-foreground">文档数</p>
          <p className="mt-1.5 text-sm font-semibold text-foreground">{kb.document_count}</p>
        </div>
        <div className="rounded-xl border border-border bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-xs font-medium text-muted-foreground">同步次数</p>
          <p className="mt-1.5 text-sm font-semibold text-foreground">{logs.length}</p>
        </div>
      </div>

      {/* Sync logs */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-foreground">解析日志</h3>
        {logs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-16 text-center">
            <p className="text-sm text-muted-foreground">暂无同步记录</p>
          </div>
        ) : (
          <div className="space-y-4">
            {logs.map((log) => (
              <div key={log.id} className="overflow-hidden rounded-xl border border-border shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
                {/* Log header */}
                <div className="flex items-center gap-3 border-b border-border bg-[#FAFBFC] px-5 py-3">
                  <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', logStatusColor[log.status] || 'bg-gray-50 text-gray-600 ring-1 ring-gray-200')}>
                    {logStatusText[log.status] || log.status}
                  </span>
                  {(() => {
                    const d = log.details && !Array.isArray(log.details) ? log.details : null
                    const mode = d?.sync_mode
                    if (!mode) return null
                    return (
                      <span className={cn(
                        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                        mode === 'incremental'
                          ? 'bg-sky-50 text-sky-600 ring-1 ring-sky-200'
                          : 'bg-violet-50 text-violet-600 ring-1 ring-violet-200',
                      )}>
                        {mode === 'incremental' ? '增量同步' : '全量同步'}
                      </span>
                    )
                  })()}
                  <span className="text-xs text-muted-foreground">{formatDate(log.started_at)}</span>
                  {log.total_files != null && (
                    <span className="text-xs text-muted-foreground">
                      共 {log.total_files} 个文件
                      {log.success_count != null && <> · <span className="text-emerald-600">{log.success_count} 成功</span></>}
                      {(log.error_count ?? 0) > 0 && <> · <span className="text-red-500">{log.error_count} 失败</span></>}
                    </span>
                  )}
                </div>
                {/* Log detail rows */}
                {log.details && (() => {
                  const rawList: Array<{ file: string; status: string; error?: string; slice_count?: number }> =
                    Array.isArray(log.details) ? log.details : (log.details.files ?? [])
                  const detailsList = rawList.filter((d) => d.status !== 'unchanged')
                  if (detailsList.length === 0) return null
                  const listExpanded = expandedDetailLogs.has(log.id)
                  const rowsToShow =
                    detailsList.length <= MAX_PARSE_LOG_ROWS || listExpanded
                      ? detailsList
                      : detailsList.slice(0, MAX_PARSE_LOG_ROWS)

                  return (
                  <>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/60 bg-[#FAFBFC]">
                        <th className="w-[40%] px-5 py-2.5 text-left text-xs font-medium text-muted-foreground">文件路径</th>
                        <th className="w-[80px] px-5 py-2.5 text-left text-xs font-medium text-muted-foreground">状态</th>
                        <th className="px-5 py-2.5 text-left text-xs font-medium text-muted-foreground">详情</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rowsToShow.map((detail, i) => {
                        const errKey = `${log.id}-${i}`
                        const isExpanded = expandedErrors.has(errKey)
                        const isError = detail.status === 'failed' || detail.status === 'error' || !!detail.error
                        const fileStatusMap: Record<string, { label: string; cls: string }> = {
                          added: { label: '新增', cls: 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200' },
                          modified: { label: '修改', cls: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200' },
                          deleted: { label: '删除', cls: 'bg-gray-100 text-gray-500 ring-1 ring-gray-200' },
                          unchanged: { label: '未变更', cls: 'bg-slate-50 text-slate-400 ring-1 ring-slate-200' },
                          success: { label: '成功', cls: 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200' },
                          error: { label: '失败', cls: 'bg-red-50 text-red-600 ring-1 ring-red-200' },
                          failed: { label: '失败', cls: 'bg-red-50 text-red-600 ring-1 ring-red-200' },
                        }
                        const fallback = isError
                          ? { label: '失败', cls: 'bg-red-50 text-red-600 ring-1 ring-red-200' }
                          : { label: detail.status || '—', cls: 'bg-gray-50 text-gray-600 ring-1 ring-gray-200' }
                        const st = fileStatusMap[detail.status] ?? fallback
                        return (
                          <tr key={errKey} className={cn(
                            'border-b border-border/40 last:border-b-0 transition-colors',
                            isError ? 'bg-red-50/40' : 'hover:bg-[#FAFBFC]'
                          )}>
                            <td className="px-5 py-2.5">
                              <code className="text-xs text-foreground/80">{detail.file}</code>
                            </td>
                            <td className="px-5 py-2.5">
                              <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', st.cls)}>{st.label}</span>
                            </td>
                            <td className="px-5 py-2.5">
                              {detail.error ? (
                                <div className="flex flex-col gap-1">
                                  <div
                                    className={cn(
                                      'cursor-pointer text-xs text-red-600/90 leading-relaxed',
                                      !isExpanded && 'line-clamp-2'
                                    )}
                                    onClick={() => toggleError(errKey)}
                                  >
                                    {detail.error}
                                  </div>
                                  {detail.error.length > 100 && (
                                    <button
                                      onClick={() => toggleError(errKey)}
                                      className="self-start text-xs text-muted-foreground hover:text-foreground transition-colors"
                                    >
                                      {isExpanded ? '收起' : '展开详情'}
                                    </button>
                                  )}
                                </div>
                              ) : detail.slice_count !== undefined ? (
                                <span className="text-xs text-muted-foreground">{detail.slice_count} 个切片</span>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  {detailsList.length > MAX_PARSE_LOG_ROWS && (
                    <div className="flex justify-center border-t border-border bg-[#FAFBFC] px-5 py-2.5">
                      <button
                        type="button"
                        onClick={() => toggleDetailList(log.id)}
                        className="text-xs font-medium text-primary hover:underline"
                      >
                        {listExpanded
                          ? '收起'
                          : `展开全部（另有 ${detailsList.length - MAX_PARSE_LOG_ROWS} 条）`}
                      </button>
                    </div>
                  )}
                  </>
                  )
                })()}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ConfigTab({
  kb,
}: {
  kb: {
    name: string; description: string | null; git_url: string; git_branch: string
    auth_type: string; status: string; document_count: number
    last_synced_at: string | null; created_at: string; updated_at: string
  }
}) {
  const rows = [
    { label: '知识库名称', value: kb.name },
    { label: '描述', value: kb.description || '—' },
    { label: 'Git 仓库地址', value: kb.git_url },
    { label: '分支', value: kb.git_branch },
    { label: '认证方式', value: kb.auth_type === 'token' ? 'Token' : '无' },
    { label: '文档数', value: String(kb.document_count) },
    { label: '上次同步', value: kb.last_synced_at ? new Date(kb.last_synced_at).toLocaleString('zh-CN') : '—' },
    { label: '创建时间', value: new Date(kb.created_at).toLocaleString('zh-CN') },
    { label: '更新时间', value: new Date(kb.updated_at).toLocaleString('zh-CN') },
  ]

  return (
    <div className="max-w-[640px] space-y-6">
      <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start gap-4">
            <span className="w-28 shrink-0 text-sm text-muted-foreground">{row.label}</span>
            <span className="text-sm text-foreground break-all">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
