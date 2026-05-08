'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useHelpCenterList,
  useDeleteHelpCenter,
} from '@/service/use-help-center'
import type { HelpCenter } from '@/models/help-center'
import { IconPlus, IconBook2, IconPencil, IconTrash } from '@tabler/icons-react'

const PER_PAGE = 10

export default function HelpCentersListPage() {
  const { toast } = useToast()
  const [page, setPage] = useState(1)
  const { data, isLoading } = useHelpCenterList(page, PER_PAGE)
  const deleteMutation = useDeleteHelpCenter()
  const [deleteTarget, setDeleteTarget] = useState<HelpCenter | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast('已删除', 'success')
      setDeleteTarget(null)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <div style={{ padding: '40px 48px' }}>
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold text-foreground">帮助中心</h1>
        <p className="text-sm text-[#737373]">
          将知识库内容发布为帮助站点。
        </p>
      </div>

      <div className="my-6 h-px w-full bg-[#E4E4E7]" />

      <div className="mb-4 flex items-center justify-end">
        <Link href="/system/help-centers/new">
          <Button size="sm">
            <IconPlus size={16} className="mr-1.5" />
            新建 Help Center
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
            <table className="w-full text-left text-sm">
              <thead className="h-12 bg-[#FAFAFA] text-[#737373]">
                <tr>
                  <th className="px-4 font-medium">名称</th>
                  <th className="px-4 font-medium">描述</th>
                  <th className="w-[180px] px-4 font-medium">更新时间</th>
                  <th className="w-[120px] px-4 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <Row
                    key={item.id}
                    item={item}
                    onDelete={() => setDeleteTarget(item)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-[#737373]">
              <span>共 {total} 条</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </Button>
                <span>{page} / {totalPages}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <DeleteConfirmModal
        target={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  )
}

function Row({ item, onDelete }: { item: HelpCenter; onDelete: () => void }) {
  return (
    <tr className="border-t border-[#E4E4E7]">
      <td className="px-4 py-3">
        <Link
          href={`/system/help-centers/${item.id}`}
          className="font-medium text-foreground hover:underline"
        >
          {item.name}
        </Link>
      </td>
      <td className="max-w-[400px] truncate px-4 text-[#737373]" title={item.description ?? undefined}>
        {item.description || '—'}
      </td>
      <td className="px-4 text-[#737373]">{formatDateTime(item.updated_at)}</td>
      <td className="px-4 text-right">
        <div className="flex items-center justify-end gap-1">
          <Link href={`/system/help-centers/${item.id}`}>
            <button
              className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#F0F0F0] hover:text-foreground"
              title="编辑"
            >
              <IconPencil size={16} />
            </button>
          </Link>
          <button
            className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
            onClick={onDelete}
            title="删除"
          >
            <IconTrash size={16} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Delete confirm modal: shows name + description per design spec ──
function DeleteConfirmModal({
  target,
  onClose,
  onConfirm,
  loading,
}: {
  target: HelpCenter | null
  onClose: () => void
  onConfirm: () => void
  loading: boolean
}) {
  return (
    <Modal
      open={!!target}
      onClose={onClose}
      title="删除帮助中心"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="destructive" onClick={onConfirm} loading={loading}>
            确定删除
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-[#737373]">
          确定删除以下帮助中心？删除后已发布站点（若存在）将不可用，请谨慎操作。
        </p>
        <div className="rounded-lg bg-[#F5F5F5] p-3">
          <div>
            <span className="text-xs text-[#A1A1AA]">名称</span>
            <p className="font-medium text-foreground">{target?.name}</p>
          </div>
          <div className="mt-2">
            <span className="text-xs text-[#A1A1AA]">描述</span>
            <p className="text-sm text-foreground">{target?.description || '—'}</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5]">
        <IconBook2 size={24} className="text-[#A1A1AA]" />
      </div>
      <p className="mt-4 text-sm text-[#737373]">暂无帮助中心</p>
      <Link href="/system/help-centers/new" className="mt-4">
        <Button size="sm">
          <IconPlus size={16} className="mr-1.5" />
          新建 Help Center
        </Button>
      </Link>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
      <div className="h-12 bg-[#FAFAFA]" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex h-14 items-center gap-4 border-t border-[#E4E4E7] px-4">
          <div className="h-4 w-32 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-48 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="ml-auto h-4 w-12 animate-pulse rounded bg-[#E4E4E7]" />
        </div>
      ))}
    </div>
  )
}

function formatDateTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
