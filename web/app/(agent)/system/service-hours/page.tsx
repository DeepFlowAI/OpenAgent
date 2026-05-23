'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useDeleteServiceHours,
  useServiceHoursList,
} from '@/service/use-service-hours'
import type { ServiceHours } from '@/models/service-hours'
import {
  IconCalendarClock,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value || '—'
  return date.toLocaleString('zh-CN', { hour12: false })
}

export default function ServiceHoursListPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [page, setPage] = useState(1)
  const perPage = 10
  const { data, isLoading } = useServiceHoursList({ page, per_page: perPage })
  const deleteMutation = useDeleteServiceHours()
  const [deleteTarget, setDeleteTarget] = useState<ServiceHours | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

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

  return (
    <div className="px-12 py-10">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold text-foreground">服务时间</h1>
        <p className="text-sm text-[#737373]">
          多组可复用配置，供 IVR、会话与路由等按配置 id 引用
        </p>
      </div>

      <div className="my-6 h-px w-full bg-[#E4E4E7]" />

      <div className="mb-4 flex items-center justify-end">
        <Button size="sm" onClick={() => router.push('/system/service-hours/new')}>
          <IconPlus size={16} className="mr-1.5" />
          新建服务时间
        </Button>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : items.length === 0 ? (
        <EmptyState onNew={() => router.push('/system/service-hours/new')} />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
            <table className="w-full table-fixed text-left text-sm">
              <thead className="h-14 bg-[#F8F8F8] text-[#404040]">
                <tr>
                  <th className="px-6 font-semibold">名称</th>
                  <th className="px-6 font-semibold">描述</th>
                  <th className="w-[168px] px-6 font-semibold">更新时间</th>
                  <th className="w-[96px] px-6 text-right font-semibold">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="h-14 cursor-pointer border-t border-[#E4E4E7] transition-colors hover:bg-[#FAFAFA]"
                    onClick={() => router.push(`/system/service-hours/${item.id}`)}
                  >
                    <td className="truncate px-6 font-medium text-foreground">
                      {item.name}
                    </td>
                    <td className="truncate px-6 text-[#737373]">
                      {item.description || '—'}
                    </td>
                    <td className="px-6 text-xs text-[#737373]">
                      {formatDateTime(item.updated_at)}
                    </td>
                    <td className="px-6 text-right">
                      <div
                        className="flex items-center justify-end gap-2"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <button
                          type="button"
                          title="编辑"
                          className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#F0F0F0] hover:text-foreground"
                          onClick={() => router.push(`/system/service-hours/${item.id}`)}
                        >
                          <IconPencil size={16} />
                        </button>
                        <button
                          type="button"
                          title="删除"
                          className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
                          onClick={() => setDeleteTarget(item)}
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

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-[#737373]">
              <span>共 {total} 条</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
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
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="删除服务时间"
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              loading={deleteMutation.isPending}
            >
              确定删除
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-[#737373]">
            确定删除以下服务时间配置？删除后，引用该配置的下游需重新选择或回退为默认策略（若有）。
          </p>
          <div className="rounded-lg bg-[#F5F5F5] p-3">
            <p className="font-medium text-foreground">{deleteTarget?.name}</p>
            <p className="mt-1 text-[#737373]">
              {deleteTarget?.description || '—'}
            </p>
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
        <IconCalendarClock size={24} className="text-[#A1A1AA]" />
      </div>
      <p className="mt-4 text-sm text-[#737373]">暂无服务时间配置</p>
      <Button size="sm" className="mt-4" onClick={onNew}>
        <IconPlus size={16} className="mr-1.5" />
        新建服务时间
      </Button>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
      <div className="h-14 bg-[#F8F8F8]" />
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          key={index}
          className="flex h-14 items-center gap-6 border-t border-[#E4E4E7] px-6"
        >
          <div className="h-4 w-36 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-56 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-32 animate-pulse rounded bg-[#E4E4E7]" />
        </div>
      ))}
    </div>
  )
}
