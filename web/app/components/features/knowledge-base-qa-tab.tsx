'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconBan, IconCircleCheck, IconEye, IconPencil, IconPlus, IconRefresh, IconTrash } from '@tabler/icons-react'
import { Badge } from '@/app/components/base/badge'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { useAuthStore } from '@/context/auth-store'
import { getErrorMessage } from '@/service/base'
import { KnowledgeBaseQaDirectorySidebar } from '@/app/components/features/knowledge-base-qa-directory-sidebar'
import { DeleteKnowledgeBaseQaDirectoryModal, KnowledgeBaseQaDirectoryModal } from '@/app/components/features/knowledge-base-qa-directory-modal'
import { useQaDirectoryCopy } from '@/app/components/features/knowledge-base-qa-copy'
import {
  useCreateKnowledgeBaseQaDirectory, useDeleteKnowledgeBaseQaDirectory,
  useKnowledgeBaseQaDirectories, useUpdateKnowledgeBaseQaDirectory,
} from '@/service/use-knowledge-base-qa-directory'
import {
  useDeleteKnowledgeBaseQa, useKnowledgeBaseQas, useRetryKnowledgeBaseQa,
  useToggleKnowledgeBaseQa,
} from '@/service/use-knowledge-base-qa'
import type { KnowledgeBaseQa, QaProcessStatus } from '@/models/knowledge-base-qa'
import type { KnowledgeBaseQaDirectory } from '@/models/knowledge-base-qa-directory'

const stripMarkdown = (value: string) => value.replace(/```[\s\S]*?```/g, ' ').replace(/[#>*_`~\[\]()!-]/g, ' ').replace(/\s+/g, ' ').trim()
const statusLabel: Record<QaProcessStatus, string> = { processing: '处理中', ready: '可检索', failed: '处理失败' }
type DirectoryEditor = { directory: KnowledgeBaseQaDirectory | null; parentId: number | null }

export function KnowledgeBaseQaTab({ kbId }: { kbId: number }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const t = useQaDirectoryCopy()
  const canManage = useAuthStore((state) => state.user?.role === 'admin')
  const [input, setInput] = useState('')
  const [search, setSearch] = useState('')
  const [enabled, setEnabled] = useState('all')
  const [processStatus, setProcessStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [deletingQa, setDeletingQa] = useState<KnowledgeBaseQa | null>(null)
  const [directoryEditor, setDirectoryEditor] = useState<DirectoryEditor | null>(null)
  const [deletingDirectory, setDeletingDirectory] = useState<KnowledgeBaseQaDirectory | null>(null)

  const directoryQuery = useKnowledgeBaseQaDirectories(kbId)
  const directories = directoryQuery.data?.items ?? []
  const directoryRaw = searchParams.get('directory')
  const directoryNumber = directoryRaw && /^\d+$/.test(directoryRaw) ? Number(directoryRaw) : null
  const selectedId = directoryNumber && directories.some((item) => item.id === directoryNumber) ? directoryNumber : null
  const directoryReady = directoryQuery.isSuccess

  useEffect(() => {
    if (!directoryReady || !directoryRaw || selectedId !== null) return
    const params = new URLSearchParams(searchParams.toString())
    params.delete('directory')
    router.replace(`/knowledge-space/${kbId}?${params.toString()}`, { scroll: false })
  }, [directoryRaw, directoryReady, kbId, router, searchParams, selectedId])

  const queryParams = useMemo(() => ({
    search: search || undefined,
    enabled: enabled === 'all' ? undefined : enabled === 'enabled',
    process_status: processStatus === 'all' ? undefined : processStatus as QaProcessStatus,
    directory_id: selectedId ?? undefined,
    page,
    per_page: perPage,
  }), [enabled, page, perPage, processStatus, search, selectedId])
  const { data, isLoading, isFetching } = useKnowledgeBaseQas(kbId, queryParams, directoryReady)
  const toggleMutation = useToggleKnowledgeBaseQa()
  const retryMutation = useRetryKnowledgeBaseQa()
  const deleteQaMutation = useDeleteKnowledgeBaseQa()
  const createDirectoryMutation = useCreateKnowledgeBaseQaDirectory()
  const updateDirectoryMutation = useUpdateKnowledgeBaseQaDirectory()
  const deleteDirectoryMutation = useDeleteKnowledgeBaseQaDirectory()

  useEffect(() => {
    const timer = window.setTimeout(() => { setSearch(input.trim()); setPage(1) }, 300)
    return () => window.clearTimeout(timer)
  }, [input])
  useEffect(() => { if (data?.pages && page > data.pages) setPage(data.pages) }, [data?.pages, page])

  const run = async (action: () => Promise<unknown>, message: string) => {
    try { await action(); toast(message, 'success'); return true }
    catch (error) { toast(await getErrorMessage(error), 'error'); return false }
  }
  const selectDirectory = (id: number | null) => {
    const params = new URLSearchParams(searchParams.toString())
    if (id === null) params.delete('directory'); else params.set('directory', String(id))
    params.set('tab', 'qa')
    setPage(1)
    router.replace(`/knowledge-space/${kbId}?${params.toString()}`, { scroll: false })
  }
  const newQaUrl = `/knowledge-space/${kbId}/qa/new${selectedId ? `?directory=${selectedId}` : ''}`
  const clearFilters = () => { setInput(''); setSearch(''); setEnabled('all'); setProcessStatus('all'); setPage(1) }
  const items = data?.items ?? []
  const hasFilters = !!search || enabled !== 'all' || processStatus !== 'all'
  const currentDirectory = directories.find((item) => item.id === selectedId)
  const noDirectories = directoryReady && directories.length === 0

  const requestDeleteDirectory = (item: KnowledgeBaseQaDirectory) => {
    const hasChildren = directories.some((candidate) => candidate.parent_id === item.id)
    if (hasChildren || item.qa_count > 0) return toast(t.nonEmpty, 'error')
    setDeletingDirectory(item)
  }

  return (
    <div className="flex min-h-full flex-col gap-4">
      <div className="rounded-lg border border-border bg-[#FAFAFA] px-4 py-3 text-sm text-muted-foreground">QA 由系统维护，不参与 Git 同步；同步和全量同步仅处理文档。</div>
      <div className="flex min-h-[560px] overflow-hidden rounded-lg border border-border bg-white">
        {directoryQuery.isError ? (
          <div className="flex min-h-[560px] flex-1 items-center justify-center">
            <EmptyState text="QA 目录加载失败，请重试">
              <Button variant="outline" loading={directoryQuery.isFetching} onClick={() => void directoryQuery.refetch()}>重试</Button>
            </EmptyState>
          </div>
        ) : (
          <>
            <KnowledgeBaseQaDirectorySidebar
              directories={directories}
              totalQaCount={directoryQuery.data?.total_qa_count ?? 0}
              selectedId={selectedId}
              canManage={canManage}
              loading={directoryQuery.isLoading}
              onSelect={selectDirectory}
              onCreate={(parentId) => setDirectoryEditor({ directory: null, parentId })}
              onEdit={(directory) => setDirectoryEditor({ directory, parentId: directory.parent_id })}
              onDelete={requestDeleteDirectory}
              onMove={async (directoryId, payload) => {
                try { await updateDirectoryMutation.mutateAsync({ kbId, directoryId, data: payload }) }
                catch { toast(t.sortFailed, 'error'); await directoryQuery.refetch() }
              }}
            />
            <main className="min-w-0 flex-1 p-5">
              <h2 className="mb-4 text-base font-semibold text-foreground">{currentDirectory?.name ?? t.all}</h2>
              {noDirectories ? <EmptyState text={t.noDirectoryHint}>{canManage && <Button onClick={() => setDirectoryEditor({ directory: null, parentId: null })}><IconPlus size={16} className="mr-1.5" />{t.create}</Button>}</EmptyState> : <>
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="搜索问题或答案" className="h-11 min-w-[240px] flex-1 rounded-lg border border-[#E5E5E5] px-3 text-sm outline-none focus:border-[#1a1a1a] focus:ring-2 focus:ring-[#1a1a1a]/10" />
                  <FilterSelect value={enabled} onChange={(value) => { setEnabled(value); setPage(1) }} options={[["all", "全部状态"], ["enabled", "已启用"], ["disabled", "已停用"]]} />
                  <FilterSelect value={processStatus} onChange={(value) => { setProcessStatus(value); setPage(1) }} options={[["all", "全部处理状态"], ["processing", "处理中"], ["ready", "可检索"], ["failed", "处理失败"]]} />
                  {canManage && <Button onClick={() => router.push(newQaUrl)}><IconPlus size={16} className="mr-1.5" />新建 QA</Button>}
                </div>
                <div className="relative overflow-x-auto rounded-lg border border-border">
                  {isFetching && !isLoading && <div className="absolute inset-x-0 top-0 z-10 h-0.5 animate-pulse bg-[#1a1a1a]" />}
                  {isLoading || !directoryReady ? <div className="py-20 text-center text-sm text-muted-foreground">加载中...</div> : items.length === 0 ? <EmptyState text={hasFilters ? '未找到匹配的 QA' : selectedId ? t.currentEmpty : '暂无 QA，新建后即可用于知识检索'}>{hasFilters ? <Button variant="outline" onClick={clearFilters}>清空筛选</Button> : canManage && <Button onClick={() => router.push(newQaUrl)}>{selectedId ? t.createHere : '新建 QA'}</Button>}</EmptyState> : <QaTable kbId={kbId} directoryId={selectedId} canManage={canManage} items={items} onDelete={setDeletingQa} onToggle={(qa) => run(() => toggleMutation.mutateAsync({ kbId, qaId: qa.id }), qa.enabled ? 'QA 已停用' : 'QA 已启用')} onRetry={(qa) => run(() => retryMutation.mutateAsync({ kbId, qaId: qa.id }), '已重新处理 QA')} directoryLabel={t.directoryColumn} />}
                </div>
                {!!data?.total && <Pagination page={page} pages={data.pages} total={data.total} perPage={perPage} onPage={setPage} onPerPage={(value) => { setPerPage(value); setPage(1) }} />}
              </>}
            </main>
          </>
        )}
      </div>
      <DeleteQaModal qa={deletingQa} loading={deleteQaMutation.isPending} onClose={() => setDeletingQa(null)} onConfirm={async () => { if (!deletingQa) return; if (await run(() => deleteQaMutation.mutateAsync({ kbId, qaId: deletingQa.id }), 'QA 已删除')) setDeletingQa(null) }} />
      <KnowledgeBaseQaDirectoryModal open={!!directoryEditor} directory={directoryEditor?.directory ?? null} defaultParentId={directoryEditor?.parentId ?? null} directories={directories} loading={createDirectoryMutation.isPending || updateDirectoryMutation.isPending} onClose={() => setDirectoryEditor(null)} onSubmit={async (payload) => {
        if (directoryEditor?.directory) { await updateDirectoryMutation.mutateAsync({ kbId, directoryId: directoryEditor.directory.id, data: payload }); toast(t.updated, 'success') }
        else { await createDirectoryMutation.mutateAsync({ kbId, data: { name: payload.name, parent_id: payload.parent_id ?? null } }); toast(t.created, 'success') }
        setDirectoryEditor(null)
      }} />
      <DeleteKnowledgeBaseQaDirectoryModal directory={deletingDirectory} loading={deleteDirectoryMutation.isPending} onClose={() => setDeletingDirectory(null)} onConfirm={async () => { if (!deletingDirectory) return; const deleted = deletingDirectory; if (await run(() => deleteDirectoryMutation.mutateAsync({ kbId, directoryId: deleted.id }), t.deleted)) { setDeletingDirectory(null); if (selectedId === deleted.id) selectDirectory(null) } }} />
    </div>
  )
}

function EmptyState({ text, children }: { text: string; children?: React.ReactNode }) { return <div className="flex flex-col items-center gap-3 py-20 text-sm text-muted-foreground"><p>{text}</p>{children}</div> }
function FilterSelect({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: Array<[string, string]> }) { return <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm outline-none focus:border-[#1a1a1a]">{options.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select> }

function QaTable({ kbId, directoryId, canManage, items, onDelete, onToggle, onRetry, directoryLabel }: { kbId: number; directoryId: number | null; canManage: boolean; items: KnowledgeBaseQa[]; onDelete: (qa: KnowledgeBaseQa) => void; onToggle: (qa: KnowledgeBaseQa) => void; onRetry: (qa: KnowledgeBaseQa) => void; directoryLabel: string }) {
  const router = useRouter()
  const detailUrl = (qaId: number) => `/knowledge-space/${kbId}/qa/${qaId}${directoryId ? `?directory=${directoryId}` : ''}`
  return <table className="min-w-[1050px] w-full table-fixed text-sm"><thead><tr className="h-14 border-b border-border bg-[#F8F8F8] text-left text-[#404040]"><th className="px-6 font-semibold">问题 / 答案</th><th className="w-[160px] px-3 font-semibold">{directoryLabel}</th><th className="w-[90px] px-3 font-semibold">状态</th><th className="w-[105px] px-3 font-semibold">处理状态</th><th className="w-[150px] px-3 font-semibold">权限标签</th><th className="w-[160px] px-3 font-semibold">更新时间</th><th className="w-[150px] px-3 font-semibold">操作</th></tr></thead><tbody>{items.map((qa) => <tr key={qa.id} className="h-20 border-b border-border last:border-0 hover:bg-[#FAFAFA]"><td className="cursor-pointer px-6" onClick={() => router.push(detailUrl(qa.id))}><p className="line-clamp-2 font-medium text-foreground">{qa.question}</p><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{stripMarkdown(qa.answer_markdown) || '—'}</p></td><td className="px-3"><span className="block truncate text-xs text-muted-foreground" title={qa.directory_path.join(' / ')}>{qa.directory_path.join(' / ')}</span></td><td className="px-3"><Badge variant={qa.enabled ? 'success' : 'danger'}>{qa.enabled ? '已启用' : '已停用'}</Badge></td><td className="px-3"><Badge variant={qa.process_status === 'ready' ? 'success' : qa.process_status === 'failed' ? 'danger' : 'warning'} title={qa.process_error ?? undefined}>{statusLabel[qa.process_status]}</Badge></td><td className="px-3"><span className="block truncate text-xs text-muted-foreground" title={qa.access_keywords.join(', ')}>{qa.access_keywords.length ? `${qa.access_keywords.slice(0, 2).join(', ')}${qa.access_keywords.length > 2 ? ` +${qa.access_keywords.length - 2}` : ''}` : '共享'}</span></td><td className="px-3 text-xs text-muted-foreground">{new Date(qa.updated_at).toLocaleString('zh-CN')}</td><td className="px-3"><div className="flex items-center gap-1"><IconAction label={canManage && qa.process_status !== 'processing' ? '编辑' : '查看'} onClick={() => router.push(detailUrl(qa.id))}>{canManage && qa.process_status !== 'processing' ? <IconPencil size={18} /> : <IconEye size={18} />}</IconAction>{canManage && <><IconAction label={qa.enabled ? '停用' : '启用'} disabled={qa.process_status === 'processing'} onClick={() => onToggle(qa)}>{qa.enabled ? <IconBan size={18} /> : <IconCircleCheck size={18} />}</IconAction>{qa.process_status === 'failed' && <IconAction label="重试" onClick={() => onRetry(qa)}><IconRefresh size={18} /></IconAction>}<IconAction label="删除" onClick={() => onDelete(qa)}><IconTrash size={18} /></IconAction></>}</div></td></tr>)}</tbody></table>
}

function IconAction({ label, disabled, onClick, children }: { label: string; disabled?: boolean; onClick: () => void; children: React.ReactNode }) { return <button type="button" title={label} aria-label={label} disabled={disabled} onClick={onClick} className="rounded-md p-2 text-[#404040] hover:bg-[#F0F0F0] disabled:cursor-not-allowed disabled:text-[#A3A3A3]">{children}</button> }
function Pagination({ page, pages, total, perPage, onPage, onPerPage }: { page: number; pages: number; total: number; perPage: number; onPage: (page: number) => void; onPerPage: (value: number) => void }) { return <div className="flex h-12 items-center justify-between border-t border-border px-2 text-sm text-muted-foreground"><div className="flex items-center gap-3"><span>共 {total} 条</span><select value={perPage} onChange={(event) => onPerPage(Number(event.target.value))} className="h-8 rounded-lg border border-border bg-white px-2 text-foreground"><option value={10}>10 条/页</option><option value={20}>20 条/页</option><option value={50}>50 条/页</option></select></div><div className="flex items-center gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>上一页</Button><span>{page} / {Math.max(pages, 1)}</span><Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>下一页</Button></div></div> }
function DeleteQaModal({ qa, loading, onClose, onConfirm }: { qa: KnowledgeBaseQa | null; loading: boolean; onClose: () => void; onConfirm: () => void }) { return <Modal open={!!qa} onClose={onClose} title="删除 QA" footer={<><Button variant="outline" disabled={loading} onClick={onClose}>取消</Button><Button variant="destructive" loading={loading} onClick={onConfirm}>确定删除</Button></>}><p className="text-sm text-muted-foreground">确定删除以下 QA？删除后不可恢复。</p><div className="mt-4 space-y-3 rounded-lg bg-[#F8F8F8] p-4 text-sm"><div><p className="text-xs text-muted-foreground">问题</p><p className="mt-1 font-medium">{qa?.question}</p></div><div><p className="text-xs text-muted-foreground">答案摘要</p><p className="mt-1 text-muted-foreground">{qa ? stripMarkdown(qa.answer_markdown).slice(0, 200) : ''}</p></div></div></Modal> }
