'use client'

import { useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  IconInbox,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { MessagePreprocessingRuleModal } from '@/app/components/features/message-preprocessing-rule-modal'
import type { AgentMessagePreprocessingRule } from '@/models/agent-message-preprocessing-rule'
import { AGENT_MESSAGE_PREPROCESSING_ACTION_LABELS } from '@/models/agent-message-preprocessing-rule'
import { getErrorMessage } from '@/service/base'
import {
  useAgentMessagePreprocessingRules,
  useCreateAgentMessagePreprocessingRule,
  useDeleteAgentMessagePreprocessingRule,
  useUpdateAgentMessagePreprocessingRule,
} from '@/service/use-agent-message-preprocessing-rule'

function previewCondition(condition: string) {
  const normalized = condition.replace(/\s+/g, ' ')
  return normalized.length > 80 ? `${normalized.slice(0, 80)}...` : normalized
}

export default function PreprocessingPage() {
  const params = useParams()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const { data, isLoading, isError, refetch } =
    useAgentMessagePreprocessingRules(agentId)
  const createMutation = useCreateAgentMessagePreprocessingRule()
  const updateMutation = useUpdateAgentMessagePreprocessingRule()
  const deleteMutation = useDeleteAgentMessagePreprocessingRule()

  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] =
    useState<AgentMessagePreprocessingRule | null>(null)
  const [deletingRule, setDeletingRule] =
    useState<AgentMessagePreprocessingRule | null>(null)

  const rules = useMemo(() => data?.items ?? [], [data])
  const saving = createMutation.isPending || updateMutation.isPending

  const openCreate = () => {
    setEditingRule(null)
    setModalOpen(true)
  }

  const openEdit = (rule: AgentMessagePreprocessingRule) => {
    setEditingRule(rule)
    setModalOpen(true)
  }

  const handleSubmit = async (values: {
    condition: string
    action: 'prefix' | 'suffix'
    value?: string
  }) => {
    try {
      if (editingRule) {
        await updateMutation.mutateAsync({
          agentId,
          ruleId: editingRule.id,
          data: values,
        })
        toast('已更新规则', 'success')
      } else {
        await createMutation.mutateAsync({ agentId, data: values })
        toast('已添加规则', 'success')
      }
      setModalOpen(false)
      setEditingRule(null)
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  const handleDelete = async () => {
    if (!deletingRule) return
    try {
      await deleteMutation.mutateAsync({ agentId, ruleId: deletingRule.id })
      toast('已删除规则', 'success')
      setDeletingRule(null)
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex-1 overflow-auto p-6">
        <div className="space-y-6">
          <header className="space-y-2 pb-2">
            <h1 className="font-display text-[28px] font-bold text-[#18181B]">
              消息预处理
            </h1>
            <p className="text-[13px] text-[#71717A]">
              仅影响进入模型的用户文本；会话展示仍为原文。
            </p>
            <p className="text-[13px] text-[#71717A]">
              条件使用 Python regex module 语法，支持 (?i)、(?m)、(?s) 等内联标记。
            </p>
          </header>

          <div className="h-px bg-[#E4E4E7]" />

          <section className="overflow-hidden rounded-[10px] border border-[#ECECEC] bg-white">
            <div className="flex items-center justify-end px-5 py-3">
              <Button onClick={openCreate} size="sm" className="gap-2">
                <IconPlus size={16} />
                添加规则
              </Button>
            </div>

            <div className="overflow-x-auto pb-6">
              <table className="w-full min-w-[720px] table-fixed">
                <thead>
                  <tr className="h-[52px] border-y border-[#ECECEC] bg-[#F8F8F8] text-left text-sm font-semibold text-[#404040]">
                    <th className="w-[36%] px-6">条件</th>
                    <th className="w-[120px] px-6">动作</th>
                    <th className="px-6">值</th>
                    <th className="w-[96px] px-6 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading && (
                    <tr>
                      <td colSpan={4} className="px-6 py-12 text-center text-sm text-[#71717A]">
                        加载中...
                      </td>
                    </tr>
                  )}

                  {!isLoading && isError && (
                    <tr>
                      <td colSpan={4} className="px-6 py-12 text-center">
                        <div className="space-y-3">
                          <p className="text-sm text-[#71717A]">规则加载失败</p>
                          <Button variant="outline" size="sm" onClick={() => refetch()}>
                            重试
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {!isLoading && !isError && rules.length === 0 && (
                    <tr>
                      <td colSpan={4}>
                        <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#F4F4F5]">
                            <IconInbox size={18} className="text-[#71717A]" />
                          </div>
                          <h2 className="mt-3 text-sm font-semibold text-[#18181B]">
                            暂无预处理规则
                          </h2>
                          <p className="mt-1 max-w-[520px] text-[13px] leading-relaxed text-[#71717A]">
                            添加规则后，将在用户消息进入模型前按条件自动处理（展示侧仍为原文）。
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}

                  {!isLoading && !isError && rules.map((rule) => (
                    <tr
                      key={rule.id}
                      className="h-16 border-b border-[#ECECEC] last:border-b-0"
                    >
                      <td className="px-6">
                        <div
                          className="truncate text-sm text-[#18181B]"
                          title={rule.condition}
                        >
                          {rule.condition}
                        </div>
                      </td>
                      <td className="px-6">
                        <span className="inline-flex rounded-full bg-[#F4F4F5] px-2.5 py-0.5 text-xs font-medium text-[#52525B]">
                          {AGENT_MESSAGE_PREPROCESSING_ACTION_LABELS[rule.action].zh}
                        </span>
                      </td>
                      <td className="px-6">
                        <div
                          className="truncate text-sm text-[#71717A]"
                          title={rule.value}
                        >
                          {rule.value}
                        </div>
                      </td>
                      <td className="px-6">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => openEdit(rule)}
                            className="rounded-md p-1.5 text-[#404040] transition-colors hover:bg-[#F4F4F5] hover:text-[#18181B]"
                            aria-label="编辑规则"
                            title="编辑"
                          >
                            <IconPencil size={18} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeletingRule(rule)}
                            className="rounded-md p-1.5 text-[#404040] transition-colors hover:bg-[#FEF2F2] hover:text-[#DC2626]"
                            aria-label="删除规则"
                            title="删除"
                          >
                            <IconTrash size={18} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>

      <MessagePreprocessingRuleModal
        open={modalOpen}
        rule={editingRule}
        loading={saving}
        onClose={() => {
          setModalOpen(false)
          setEditingRule(null)
        }}
        onSubmit={handleSubmit}
      />

      <Modal
        open={!!deletingRule}
        onClose={() => {
          if (!deleteMutation.isPending) setDeletingRule(null)
        }}
        title="删除规则"
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => setDeletingRule(null)}
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
        <div className="space-y-4">
          <p className="text-sm leading-relaxed text-[#52525B]">
            确定删除该条消息预处理规则？删除后不可恢复。
          </p>
          {deletingRule && (
            <p className="rounded-lg bg-[#F8F8F8] px-3 py-2 text-[13px] text-[#18181B]">
              {previewCondition(deletingRule.condition)}
            </p>
          )}
        </div>
      </Modal>
    </div>
  )
}
