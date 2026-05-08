'use client'

import { useMemo, useState } from 'react'
import { Button } from '@/app/components/base/button'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  IconArrowDown,
  IconArrowUp,
  IconPencil,
  IconPlus,
  IconTable,
  IconTrash,
} from '@tabler/icons-react'
import {
  useDeleteHelpCenterTab,
  useHelpCenterTabs,
  useReorderHelpCenterTabs,
} from '@/service/use-help-center-tab'
import type { HelpCenterTab } from '@/models/help-center'
import { TabDrawer } from './tab-drawer'

export function TabSection({ helpCenterId }: { helpCenterId: number }) {
  const { toast } = useToast()
  const { data, isLoading } = useHelpCenterTabs(helpCenterId)
  const reorderMutation = useReorderHelpCenterTabs(helpCenterId)
  const deleteMutation = useDeleteHelpCenterTab(helpCenterId)

  const items = useMemo(() => data?.items ?? [], [data])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<HelpCenterTab | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<HelpCenterTab | null>(null)

  const openCreate = () => {
    setEditing(null)
    setDrawerOpen(true)
  }
  const openEdit = (tab: HelpCenterTab) => {
    setEditing(tab)
    setDrawerOpen(true)
  }

  const move = async (idx: number, dir: -1 | 1) => {
    const next = [...items]
    const j = idx + dir
    if (j < 0 || j >= next.length) return
    ;[next[idx], next[j]] = [next[j], next[idx]]
    try {
      await reorderMutation.mutateAsync(next.map((t) => t.id))
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast('已删除', 'success')
      setDeleteTarget(null)
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-end">
        <Button size="sm" onClick={openCreate}>
          <IconPlus size={16} className="mr-1.5" />
          添加 Tab
        </Button>
      </div>

      {isLoading ? (
        <TabsSkeleton />
      ) : items.length === 0 ? (
        <EmptyTabs onCreate={openCreate} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
          <table className="w-full text-left text-sm">
            <thead className="h-12 bg-[#FAFAFA] text-[#737373]">
              <tr>
                <th className="w-[60px] px-4 font-medium">序号</th>
                <th className="px-4 font-medium">显示名</th>
                <th className="px-4 font-medium">知识库</th>
                <th className="w-[200px] px-4 font-medium">URL 段</th>
                <th className="w-[180px] px-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((tab, idx) => (
                <tr key={tab.id} className="border-t border-[#E4E4E7]">
                  <td className="px-4 py-3 text-[#737373]">{idx + 1}</td>
                  <td className="px-4 font-medium text-foreground">{tab.display_name}</td>
                  <td className="px-4 text-[#737373]">
                    {tab.knowledge_base_name || `#${tab.knowledge_base_id}`}
                  </td>
                  <td className="px-4">
                    {tab.tab_slug ? (
                      <code className="rounded bg-[#F5F5F5] px-1.5 py-0.5 font-mono text-xs">
                        /{tab.tab_slug}
                      </code>
                    ) : (
                      <span className="text-xs text-[#A1A1AA]">自动生成</span>
                    )}
                  </td>
                  <td className="px-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <IconBtn
                        title="上移"
                        disabled={idx === 0 || reorderMutation.isPending}
                        onClick={() => move(idx, -1)}
                      >
                        <IconArrowUp size={16} />
                      </IconBtn>
                      <IconBtn
                        title="下移"
                        disabled={idx === items.length - 1 || reorderMutation.isPending}
                        onClick={() => move(idx, 1)}
                      >
                        <IconArrowDown size={16} />
                      </IconBtn>
                      <IconBtn title="编辑" onClick={() => openEdit(tab)}>
                        <IconPencil size={16} />
                      </IconBtn>
                      <IconBtn
                        title="删除"
                        onClick={() => setDeleteTarget(tab)}
                        danger
                      >
                        <IconTrash size={16} />
                      </IconBtn>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TabDrawer
        open={drawerOpen}
        helpCenterId={helpCenterId}
        initialTab={editing}
        onClose={() => setDrawerOpen(false)}
      />

      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="删除内容 Tab"
        description={`确定删除 “${deleteTarget?.display_name}”？删除后访客站对应板块将下线。`}
        confirmText="确认删除"
        variant="destructive"
        loading={deleteMutation.isPending}
      />
    </>
  )
}

function IconBtn({
  children,
  onClick,
  title,
  disabled,
  danger,
}: {
  children: React.ReactNode
  onClick: () => void
  title: string
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={
        'rounded-md p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ' +
        (danger
          ? 'text-[#737373] hover:bg-[#FEE2E2] hover:text-[#DC2626]'
          : 'text-[#737373] hover:bg-[#F0F0F0] hover:text-foreground')
      }
    >
      {children}
    </button>
  )
}

function EmptyTabs({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] py-16">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white">
        <IconTable size={24} className="text-[#A1A1AA]" />
      </div>
      <p className="mt-4 text-sm text-[#737373]">尚未添加内容版块</p>
      <Button size="sm" className="mt-4" onClick={onCreate}>
        <IconPlus size={16} className="mr-1.5" />
        添加 Tab
      </Button>
    </div>
  )
}

function TabsSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
      <div className="h-12 bg-[#FAFAFA]" />
      {Array.from({ length: 2 }).map((_, i) => (
        <div
          key={i}
          className="flex h-14 items-center gap-4 border-t border-[#E4E4E7] px-4"
        >
          <div className="h-4 w-12 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-40 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-32 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="ml-auto h-4 w-24 animate-pulse rounded bg-[#E4E4E7]" />
        </div>
      ))}
    </div>
  )
}
