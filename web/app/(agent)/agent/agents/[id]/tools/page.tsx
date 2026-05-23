'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Switch } from '@/app/components/base/switch'
import { Button } from '@/app/components/base/button'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useAgentTools,
  useToggleAgentTool,
  useDeleteAgentTool,
  useCreateAgentTool,
} from '@/service/use-agent-tool'
import { TOOL_TYPE_LABELS } from '@/models/agent-tool'
import type { AgentTool, CreateAgentToolPayload } from '@/models/agent-tool'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { AddToolModal } from '@/app/components/features/add-tool-modal'

export default function ToolManagementPage() {
  const params = useParams()
  const router = useRouter()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const { data, isLoading } = useAgentTools(agentId)
  const toggleMutation = useToggleAgentTool(agentId)
  const deleteMutation = useDeleteAgentTool(agentId)
  const createMutation = useCreateAgentTool(agentId)

  const [deleteTarget, setDeleteTarget] = useState<AgentTool | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)

  const tools = data?.items ?? []
  const systemTools = tools.filter((t) => t.is_system)
  const customTools = tools.filter((t) => !t.is_system)

  const handleToggle = async (tool: AgentTool, enabled: boolean) => {
    try {
      await toggleMutation.mutateAsync({
        toolId: tool.id,
        data: { is_enabled: enabled },
      })
      toast(enabled ? '工具已启用' : '工具已禁用', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast('工具已移除', 'success')
      setDeleteTarget(null)
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  const handleAddTool = async (payload: CreateAgentToolPayload) => {
    try {
      const created = await createMutation.mutateAsync(payload)
      toast('工具已添加', 'success')
      setShowAddModal(false)
      router.push(`/agent/agents/${agentId}/tools/${created.id}`)
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-[#71717A]">加载中...</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#ECECEC] bg-white/80 px-6 py-4 backdrop-blur-sm">
        <h2 className="text-base font-semibold text-[#18181B]">工具管理</h2>
      </div>

      <div className="flex-1 space-y-8 p-8">
        {/* System Tools */}
        <section>
          <h3 className="mb-4 text-sm font-semibold text-[#18181B]">系统工具</h3>
          <ToolTable
            tools={systemTools}
            onToggle={handleToggle}
            showDelete={false}
            canOpen={(tool) => tool.tool_type === 'human_handoff'}
            onRowClick={(tool) => router.push(`/agent/agents/${agentId}/tools/${tool.id}`)}
          />
        </section>

        {/* Custom Tools */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#18181B]">自定义工具</h3>
            <Button
              size="sm"
              onClick={() => setShowAddModal(true)}
              className="gap-1"
            >
              <IconPlus size={14} />
              添加工具
            </Button>
          </div>
          {customTools.length > 0 ? (
            <ToolTable
              tools={customTools}
              onToggle={handleToggle}
              showDelete
              onDelete={setDeleteTarget}
              onRowClick={(tool) => router.push(`/agent/agents/${agentId}/tools/${tool.id}`)}
            />
          ) : (
            <div className="rounded-lg border border-dashed border-[#E4E4E7] py-12 text-center">
              <p className="text-sm text-[#71717A]">暂无自定义工具</p>
              <button
                onClick={() => setShowAddModal(true)}
                className="mt-2 text-sm font-medium text-[#18181B] underline-offset-4 hover:underline"
              >
                添加工具
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Delete confirmation modal */}
      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="移除工具"
        description={`确定从该 Agent 中移除工具「${deleteTarget?.name ?? ''}」？`}
        confirmText="确定移除"
        variant="destructive"
        loading={deleteMutation.isPending}
      />

      {/* Add tool modal */}
      <AddToolModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAddTool}
        loading={createMutation.isPending}
        existingNames={tools.map((t) => t.name)}
      />
    </div>
  )
}

function ToolTable({
  tools,
  onToggle,
  showDelete,
  onDelete,
  onRowClick,
  canOpen,
}: {
  tools: AgentTool[]
  onToggle: (tool: AgentTool, enabled: boolean) => void
  showDelete: boolean
  onDelete?: (tool: AgentTool) => void
  onRowClick?: (tool: AgentTool) => void
  canOpen?: (tool: AgentTool) => boolean
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#E4E4E7] bg-[#FAFAFA]">
            <th className="px-4 py-3 text-left font-medium text-[#71717A]">工具名称</th>
            <th className="px-4 py-3 text-left font-medium text-[#71717A]">类型</th>
            <th className="px-4 py-3 text-left font-medium text-[#71717A]">描述</th>
            <th className="px-4 py-3 text-left font-medium text-[#71717A]">状态</th>
            <th className="px-4 py-3 text-right font-medium text-[#71717A]">操作</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((tool) => {
            const clickable = !!onRowClick && (canOpen ? canOpen(tool) : true)
            return (
              <tr
                key={tool.id}
                className={`border-b border-[#E4E4E7] last:border-b-0 ${
                  clickable ? 'cursor-pointer hover:bg-[#FAFAFA]' : ''
                }`}
                onClick={() => {
                  if (clickable) onRowClick?.(tool)
                }}
              >
                <td className="px-4 py-3 font-medium text-[#18181B]">{tool.name}</td>
                <td className="px-4 py-3">
                  <ToolTypeBadge type={tool.tool_type} isSystem={tool.is_system} />
                </td>
                <td className="max-w-[300px] truncate px-4 py-3 text-[#71717A]">
                  {tool.description || '—'}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      tool.is_enabled
                        ? 'bg-green-50 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {tool.is_enabled ? '已启用' : '已禁用'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                    <Switch
                      checked={tool.is_enabled}
                      onChange={(checked) => onToggle(tool, checked)}
                    />
                    {showDelete && onDelete && (
                      <button
                        onClick={() => onDelete(tool)}
                        className="rounded-md p-1.5 text-[#A1A1AA] transition-colors hover:bg-[#F4F4F5] hover:text-[#EF4444]"
                      >
                        <IconTrash size={16} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ToolTypeBadge({ type, isSystem }: { type: AgentTool['tool_type']; isSystem: boolean }) {
  const label = isSystem && type !== 'human_handoff' ? '系统工具' : (TOOL_TYPE_LABELS[type]?.zh ?? type)
  const colors = isSystem
    ? 'bg-blue-50 text-blue-700'
    : 'bg-purple-50 text-purple-700'

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}>
      {label}
    </span>
  )
}
