'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useKnowledgeBases,
  useDeleteKnowledgeBase,
} from '@/service/use-knowledge-base'
import { useAuthStore } from '@/context/auth-store'
import { IconPlus, IconPencil, IconTrash } from '@tabler/icons-react'
import type { KnowledgeBase } from '@/models/knowledge-base'

export default function KnowledgeSpacePage() {
  const router = useRouter()
  const { toast } = useToast()
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''
  const { data, isLoading } = useKnowledgeBases(tenantId)
  const deleteMutation = useDeleteKnowledgeBase()

  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null)

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast('删除成功', 'success')
      setDeleteTarget(null)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const items = data?.items ?? []

  return (
    <div className="px-12 py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-lg font-bold text-foreground">知识空间</h1>
        <Link href="/knowledge-space/new">
          <Button>
            <IconPlus size={16} className="mr-1.5" />
            新建知识库
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="mb-4 text-sm text-muted-foreground">
            暂无知识库，绑定 Git 仓库即可开始
          </p>
          <Link href="/knowledge-space/new">
            <Button>
              <IconPlus size={16} className="mr-1.5" />
              新建知识库
            </Button>
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-[#FAFAFA]">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  名称
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  Git 仓库
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  分支
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  最后同步
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  文档数
                </th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((kb) => (
                <tr
                  key={kb.id}
                  className="cursor-pointer border-b border-border last:border-b-0 transition-colors hover:bg-[#FAFAFA]"
                  onClick={() => router.push(`/knowledge-space/${kb.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    <span>{kb.name}</span>
                  </td>
                  <td className="max-w-[240px] truncate px-4 py-3 text-muted-foreground">
                    {kb.git_url}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-md bg-[#F5F5F5] px-2 py-0.5 text-xs font-medium text-foreground">
                      {kb.git_branch}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDate(kb.last_synced_at)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {kb.document_count}
                  </td>
                  <td className="px-4 py-3">
                    <div
                      className="flex items-center justify-end gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Link href={`/knowledge-space/${kb.id}/edit`}>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                        >
                          <IconPencil size={16} />
                        </button>
                      </Link>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(kb)}
                        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600"
                      >
                        <IconTrash size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="删除知识库"
        description={`确定删除知识库「${deleteTarget?.name}」？删除后，其文档与切片数据将被清除，且不可恢复。`}
        confirmText="确定删除"
        variant="destructive"
        loading={deleteMutation.isPending}
      />
    </div>
  )
}
