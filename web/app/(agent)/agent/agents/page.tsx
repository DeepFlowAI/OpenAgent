'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { ConfirmModal } from '@/app/components/base/modal'
import { AgentFormModal } from '@/app/components/features/agent-form-modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useAgents,
  useCreateAgent,
  useUpdateAgent,
  useUpdateAgentStatus,
} from '@/service/use-agent'
import { useAuthStore } from '@/context/auth-store'
import {
  IconPlus,
  IconPencil,
  IconBan,
  IconCircleCheck,
} from '@tabler/icons-react'
import type { Agent } from '@/models/agent'

type TabKey = 'active' | 'inactive'

export default function AgentListPage() {
  const router = useRouter()
  const { toast } = useToast()
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''

  const [activeTab, setActiveTab] = useState<TabKey>('active')
  const { data, isLoading } = useAgents(tenantId, activeTab)

  const createMutation = useCreateAgent()
  const updateMutation = useUpdateAgent()
  const statusMutation = useUpdateAgentStatus()

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Agent | null>(null)
  const [statusTarget, setStatusTarget] = useState<Agent | null>(null)

  const items = data?.items ?? []

  const handleCreate = async (formData: { name: string; description: string }) => {
    try {
      const agent = await createMutation.mutateAsync({
        tenant_id: tenantId,
        name: formData.name,
        description: formData.description || undefined,
      })
      toast('Agent 创建成功')
      setCreateModalOpen(false)
      router.push(`/agent/agents/${agent.id}`)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const handleUpdate = async (formData: { name: string; description: string }) => {
    if (!editTarget) return
    try {
      await updateMutation.mutateAsync({
        id: editTarget.id,
        data: {
          name: formData.name,
          description: formData.description || undefined,
        },
      })
      toast('保存成功')
      setEditTarget(null)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const handleStatusChange = async () => {
    if (!statusTarget) return
    const newStatus = statusTarget.status === 'active' ? 'inactive' : 'active'
    try {
      await statusMutation.mutateAsync({
        id: statusTarget.id,
        data: { status: newStatus },
      })
      toast(newStatus === 'active' ? 'Agent 已启用' : 'Agent 已停用')
      setStatusTarget(null)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'active', label: '可用 Agent' },
    { key: 'inactive', label: '停用 Agent' },
  ]

  return (
    <div className="px-10 py-8">
      {/* Header */}
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Agent</h1>
        <Button onClick={() => setCreateModalOpen(true)}>
          <IconPlus size={16} className="mr-2" />
          新建 Agent
        </Button>
      </div>

      {/* Tabs */}
      <div className="mb-5 flex gap-0 border-b border-[#ECECEC]">
        {tabs.map((tab, index) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={
              activeTab === tab.key
                ? `border-b-2 border-foreground pb-3 text-sm font-semibold text-foreground ${index === 0 ? 'pr-4' : 'px-4'}`
                : `pb-3 text-sm text-[#999] transition-colors hover:text-foreground ${index === 0 ? 'pr-4' : 'px-4'}`
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="mb-4 text-sm text-muted-foreground">
            {activeTab === 'active'
              ? '暂无可用 Agent，创建一个开始使用'
              : '暂无停用 Agent'}
          </p>
          {activeTab === 'active' && (
            <Button onClick={() => setCreateModalOpen(true)}>
              <IconPlus size={16} className="mr-2" />
              新建 Agent
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#ECECEC]">
          <table className="w-full">
            <thead>
              <tr className="bg-[#F8F8F8]">
                <th className="h-12 px-6 text-left text-[13px] font-semibold text-[#404040]">
                  名称
                </th>
                <th className="h-12 px-6 text-left text-[13px] font-semibold text-[#404040]">
                  描述
                </th>
                <th className="h-12 w-[140px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                  创建时间
                </th>
                <th className="h-12 w-[140px] px-6 text-left text-[13px] font-semibold text-[#404040]">
                  更新时间
                </th>
                <th className="h-12 w-20 px-6 text-center text-[13px] font-semibold text-[#404040]">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((agent) => (
                <tr
                  key={agent.id}
                  className="cursor-pointer border-t border-[#F0F0F0] transition-colors hover:bg-[#FAFAFA]"
                  onClick={() => router.push(`/agent/agents/${agent.id}`)}
                >
                  <td className="h-14 px-6">
                    <span className="text-sm font-medium text-foreground">
                      {agent.name}
                    </span>
                  </td>
                  <td className="h-14 max-w-[300px] truncate px-6 text-sm text-muted-foreground">
                    {agent.description || '—'}
                  </td>
                  <td className="h-14 w-[140px] px-6 text-sm text-muted-foreground">
                    {formatDate(agent.created_at)}
                  </td>
                  <td className="h-14 w-[140px] px-6 text-sm text-muted-foreground">
                    {formatDate(agent.updated_at)}
                  </td>
                  <td className="h-14 w-20 px-6">
                    <div
                      className="flex items-center justify-center gap-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        onClick={() => setEditTarget(agent)}
                        className="text-[#404040] transition-colors hover:text-foreground"
                        title="编辑"
                      >
                        <IconPencil size={18} />
                      </button>
                      {activeTab === 'active' ? (
                        <button
                          type="button"
                          onClick={() => setStatusTarget(agent)}
                          className="text-[#404040] transition-colors hover:text-destructive"
                          title="停用"
                        >
                          <IconBan size={18} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setStatusTarget(agent)}
                          className="text-[#404040] transition-colors hover:text-emerald-600"
                          title="启用"
                        >
                          <IconCircleCheck size={18} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      <AgentFormModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onSubmit={handleCreate}
        title="新建 Agent"
        loading={createMutation.isPending}
      />

      {/* Edit Modal */}
      <AgentFormModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSubmit={handleUpdate}
        title="编辑 Agent"
        initialValues={
          editTarget
            ? { name: editTarget.name, description: editTarget.description ?? '' }
            : undefined
        }
        loading={updateMutation.isPending}
      />

      {/* Disable/Enable Confirm Modal */}
      <ConfirmModal
        open={!!statusTarget}
        onClose={() => setStatusTarget(null)}
        onConfirm={handleStatusChange}
        title={
          statusTarget?.status === 'active' ? '停用 Agent' : '启用 Agent'
        }
        description={
          statusTarget?.status === 'active'
            ? `停用后，该 Agent 将无法被调用。确定停用「${statusTarget?.name}」？`
            : `确定启用「${statusTarget?.name}」？启用后该 Agent 可正常被调用。`
        }
        confirmText={
          statusTarget?.status === 'active' ? '确定停用' : '确定启用'
        }
        loading={statusMutation.isPending}
      />
    </div>
  )
}
