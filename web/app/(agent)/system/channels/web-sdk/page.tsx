'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useChannels, useDeleteChannel } from '@/service/use-channel'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import type { Channel } from '@/models/channel'
import {
  IconPlus,
  IconPencil,
  IconTrash,
  IconBroadcast,
} from '@tabler/icons-react'

export default function WebSdkChannelListPage() {
  const router = useRouter()
  const { toast } = useToast()
  const user = useAuthStore((s) => s.user)
  const tenantId = user?.tenant_id ?? ''

  const [page, setPage] = useState(1)
  const perPage = 10
  const { data, isLoading } = useChannels({ tenant_id: tenantId, page, per_page: perPage })

  const deleteMutation = useDeleteChannel()
  const [deleteTarget, setDeleteTarget] = useState<Channel | null>(null)

  const handleDelete = async () => {
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

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  return (
    <div className="px-12 py-10" style={{ padding: '40px 48px' }}>
      {/* Title */}
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold text-foreground">渠道</h1>
      </div>

      <div className="my-6 h-px w-full bg-[#E4E4E7]" />

      {/* Action bar */}
      <div className="mb-4 flex items-center justify-between">
        <div />
        <Button size="sm" onClick={() => router.push('/system/channels/web-sdk/new')}>
          <IconPlus size={16} className="mr-1.5" />
          新建 Web SDK
        </Button>
      </div>

      {/* Table or Empty */}
      {isLoading ? (
        <TableSkeleton />
      ) : items.length === 0 ? (
        <EmptyState onNew={() => router.push('/system/channels/web-sdk/new')} />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
            <table className="w-full text-left text-sm">
              <thead className="h-12 bg-[#FAFAFA] text-[#737373]">
                <tr>
                  <th className="px-4 font-medium">名称</th>
                  <th className="px-4 font-medium">描述</th>
                  <th className="w-[100px] px-4 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((ch) => (
                  <tr
                    key={ch.id}
                    className="h-14 cursor-pointer border-t border-[#E4E4E7] transition-colors hover:bg-[#FAFAFA]"
                    onClick={() => router.push(`/system/channels/web-sdk/${ch.id}`)}
                  >
                    <td className="px-4 font-medium text-foreground">{ch.name}</td>
                    <td className="px-4 text-[#737373]">{ch.description || '—'}</td>
                    <td className="px-4 text-right">
                      <div
                        className="flex items-center justify-end gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#F0F0F0] hover:text-foreground"
                          onClick={() => router.push(`/system/channels/web-sdk/${ch.id}`)}
                          title="编辑"
                        >
                          <IconPencil size={16} />
                        </button>
                        <button
                          type="button"
                          className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
                          onClick={() => setDeleteTarget(ch)}
                          title="删除"
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

          {/* Pagination */}
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
                <span>
                  {page} / {totalPages}
                </span>
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

      {/* Delete modal */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="删除 Web SDK"
        footer={
          <>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleteMutation.isPending}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete} loading={deleteMutation.isPending}>
              确定删除
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-[#737373]">
            确定删除以下渠道？删除后用户侧会话链接将不可用，请谨慎操作。
          </p>
          <div className="rounded-lg bg-[#F5F5F5] p-3">
            <p className="font-medium text-foreground">{deleteTarget?.name}</p>
            <p className="mt-1 text-[#737373]">{deleteTarget?.description || '—'}</p>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5]">
        <IconBroadcast size={24} className="text-[#A1A1AA]" />
      </div>
      <p className="mt-4 text-sm text-[#737373]">暂无 Web SDK 渠道</p>
      <Button size="sm" className="mt-4" onClick={onNew}>
        <IconPlus size={16} className="mr-1.5" />
        新建 Web SDK
      </Button>
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
        </div>
      ))}
    </div>
  )
}
