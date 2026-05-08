'use client'

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/utils/classnames'
import { Button } from '@/app/components/base/button'
import { Switch } from '@/app/components/base/switch'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useKbPermissionRules,
  useCreateKbPermissionRule,
  useUpdateKbPermissionRule,
  useDeleteKbPermissionRule,
  useToggleKbPermissionRule,
} from '@/service/use-kb-permission-rule'
import type {
  KbPermissionRule,
  UserCondition,
  UserConditionOperator,
  ScopeOperator,
  CreateKbPermissionRulePayload,
} from '@/models/kb-permission-rule'
import { IconPlus, IconPencil, IconTrash, IconX } from '@tabler/icons-react'

// ── Constants ──

const USER_CONDITION_OPERATORS: { value: UserConditionOperator; label: string; symbol: string }[] = [
  { value: 'equals', label: '等于', symbol: '=' },
  { value: 'not_equals', label: '不等于', symbol: '\u2260' },
  { value: 'contains', label: '包含', symbol: '\u2283' },
  { value: 'not_contains', label: '不包含', symbol: '\u2285' },
  { value: 'starts_with', label: '开头是', symbol: '^=' },
  { value: 'ends_with', label: '结尾是', symbol: '$=' },
  { value: 'in', label: '在集合中', symbol: '\u2208' },
  { value: 'not_in', label: '不在集合中', symbol: '\u2209' },
  { value: 'is_empty', label: '为空', symbol: '= \u2205' },
  { value: 'is_not_empty', label: '非空', symbol: '\u2260 \u2205' },
]

const SCOPE_OPERATORS: { value: ScopeOperator; label: string; needsLabels: boolean }[] = [
  { value: 'equals', label: '等于', needsLabels: true },
  { value: 'not_equals', label: '不等于', needsLabels: true },
  { value: 'contains_any', label: '包含任意', needsLabels: false },
  { value: 'not_contains_any', label: '不包含任意', needsLabels: false },
]

const NO_VALUE_OPERATORS: UserConditionOperator[] = ['is_empty', 'is_not_empty']
const MULTI_VALUE_OPERATORS: UserConditionOperator[] = ['in', 'not_in']

// ── Helpers for summary display ──

function formatConditionSummary(c: UserCondition): string {
  const opDef = USER_CONDITION_OPERATORS.find((o) => o.value === c.operator)
  const sym = opDef?.symbol ?? c.operator

  if (NO_VALUE_OPERATORS.includes(c.operator)) {
    return `${c.field} ${sym}`
  }
  if (MULTI_VALUE_OPERATORS.includes(c.operator)) {
    const vals = Array.isArray(c.value) ? c.value.join(', ') : c.value ?? ''
    return `${c.field} ${sym} {${vals}}`
  }
  return `${c.field} ${sym} ${c.value ?? ''}`
}

function formatScopeSummary(operator: string, labels: string[] | null): string {
  const opDef = SCOPE_OPERATORS.find((o) => o.value === operator)
  const opLabel = opDef?.label ?? operator
  if (labels && labels.length > 0) {
    return `${opLabel}\u00b7${labels.join(', ')}`
  }
  return opLabel
}

// ── Main Tab Component ──

export function PermissionRulesTab({
  kbId,
  tenantId,
}: {
  kbId: number
  tenantId: string
}) {
  const { toast } = useToast()
  const { data: rules, isLoading } = useKbPermissionRules(kbId, tenantId)
  const toggleMutation = useToggleKbPermissionRule()
  const deleteMutation = useDeleteKbPermissionRule()

  const [editingRule, setEditingRule] = useState<KbPermissionRule | null>(null)
  const [showCreatePanel, setShowCreatePanel] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KbPermissionRule | null>(null)

  const handleToggle = useCallback(
    async (rule: KbPermissionRule) => {
      try {
        await toggleMutation.mutateAsync({ kbId, ruleId: rule.id, tenantId })
      } catch (err) {
        const msg = await getErrorMessage(err)
        toast(msg, 'error')
      }
    },
    [kbId, tenantId, toggleMutation, toast]
  )

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync({
        kbId,
        ruleId: deleteTarget.id,
        tenantId,
      })
      toast('删除成功', 'success')
      setDeleteTarget(null)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }, [kbId, tenantId, deleteTarget, deleteMutation, toast])

  if (isLoading) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        加载中...
      </div>
    )
  }

  const ruleList = rules ?? []
  const showPanel = showCreatePanel || !!editingRule

  return (
    <>
      <div className="space-y-6">
        {/* Info banner */}
        <div className="rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] px-5 py-4 text-sm leading-relaxed text-foreground">
          <p>
            默认全库可见；仅配置否定规则：对「用户条件」成立的主体，在「权限范围」内隐藏文档或切片。
          </p>
          <p className="mt-1.5 text-muted-foreground">
            多条规则为「任一命中即不可见」；与 2.8 会话字段对齐。
          </p>
          <p className="mt-1.5 text-muted-foreground">
            可编程文档：access_keywords 同字段；入库物化 effective_access_keywords。本页规则仅配置「不可见内容」与运算符；等于/不等于可选注册标签，包含任意与不包含任意不选标签；无目录/文档选择。
          </p>
          <p className="mt-1.5 text-muted-foreground">
            与 Git 一致：锚点在同步/解析与清洗管线写入；检索按 access_keywords 与 deny 求值。
          </p>
        </div>

        {/* Section header */}
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">否定规则</h3>
          <Button
            variant="default"
            size="sm"
            onClick={() => setShowCreatePanel(true)}
          >
            <IconPlus size={14} className="mr-1.5" />
            新建否定规则
          </Button>
        </div>

        {/* Rules table */}
        {ruleList.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-16 text-center">
            <p className="text-sm text-muted-foreground">
              暂无否定规则，所有内容对所有用户可见
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => setShowCreatePanel(true)}
            >
              新建否定规则
            </Button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-[#FAFAFA]">
                  <th className="whitespace-nowrap px-5 py-3 text-left font-medium text-muted-foreground">
                    规则名称
                  </th>
                  <th className="whitespace-nowrap px-5 py-3 text-left font-medium text-muted-foreground">
                    用户条件（摘要）
                  </th>
                  <th className="whitespace-nowrap px-5 py-3 text-left font-medium text-muted-foreground">
                    权限范围（否定）
                  </th>
                  <th className="whitespace-nowrap px-5 py-3 text-center font-medium text-muted-foreground">
                    状态
                  </th>
                  <th className="whitespace-nowrap px-5 py-3 text-center font-medium text-muted-foreground">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {ruleList.map((rule) => (
                  <tr
                    key={rule.id}
                    className="border-b border-border last:border-b-0 transition-colors hover:bg-[#FAFAFA]"
                  >
                    <td className="px-5 py-4 font-medium text-foreground">
                      {rule.name}
                    </td>
                    <td className="px-5 py-4 text-muted-foreground">
                      {rule.user_conditions.map((c, i) => (
                        <span key={i}>
                          {i > 0 && <span className="mx-1 text-[#D4D4D4]">&amp;</span>}
                          {formatConditionSummary(c)}
                        </span>
                      ))}
                    </td>
                    <td className="px-5 py-4 text-muted-foreground">
                      {formatScopeSummary(rule.scope_operator, rule.scope_labels)}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex justify-center">
                        <Switch
                          checked={rule.enabled}
                          onChange={() => handleToggle(rule)}
                        />
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-[#F5F5F5] hover:text-foreground"
                          onClick={() => setEditingRule(rule)}
                          title="编辑"
                        >
                          <IconPencil size={16} />
                        </button>
                        <button
                          className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600"
                          onClick={() => setDeleteTarget(rule)}
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
        )}
      </div>

      {/* Side panel for create/edit */}
      {showPanel && (
        <RuleFormPanel
          kbId={kbId}
          tenantId={tenantId}
          rule={editingRule ?? undefined}
          onClose={() => {
            setShowCreatePanel(false)
            setEditingRule(null)
          }}
        />
      )}

      {/* Delete confirm */}
      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="删除规则"
        description={`确定删除规则「${deleteTarget?.name ?? ''}」？删除后该规则将不再生效。`}
        confirmText="确定删除"
        variant="destructive"
        loading={deleteMutation.isPending}
      />
    </>
  )
}

// ── Rule Form Panel (slide-over drawer) ──

function RuleFormPanel({
  kbId,
  tenantId,
  rule,
  onClose,
}: {
  kbId: number
  tenantId: string
  rule?: KbPermissionRule
  onClose: () => void
}) {
  const isEdit = !!rule
  const { toast } = useToast()
  const createMutation = useCreateKbPermissionRule()
  const updateMutation = useUpdateKbPermissionRule()

  const [name, setName] = useState(rule?.name ?? '')
  const [conditions, setConditions] = useState<UserCondition[]>(
    rule?.user_conditions ?? [{ field: '', operator: 'not_equals', value: '' }]
  )
  const [scopeOperator, setScopeOperator] = useState<ScopeOperator>(
    rule?.scope_operator ?? 'contains_any'
  )
  const [scopeLabelsStr, setScopeLabelsStr] = useState(
    rule?.scope_labels?.join(', ') ?? ''
  )

  const needsLabels = SCOPE_OPERATORS.find(
    (o) => o.value === scopeOperator
  )?.needsLabels

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const addCondition = () => {
    setConditions((prev) => [
      ...prev,
      { field: '', operator: 'not_equals', value: '' },
    ])
  }

  const removeCondition = (index: number) => {
    setConditions((prev) => prev.filter((_, i) => i !== index))
  }

  const updateCondition = (index: number, patch: Partial<UserCondition>) => {
    setConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c))
    )
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast('请输入规则名称', 'error')
      return
    }
    if (conditions.length === 0) {
      toast('请至少添加一个用户条件', 'error')
      return
    }
    for (const c of conditions) {
      if (!c.field.trim()) {
        toast('用户条件的字段名不能为空', 'error')
        return
      }
    }
    if (needsLabels && !scopeLabelsStr.trim()) {
      toast('请选择标签', 'error')
      return
    }

    const processedConditions = conditions.map((c) => {
      if (NO_VALUE_OPERATORS.includes(c.operator)) {
        return { field: c.field, operator: c.operator, value: null }
      }
      if (MULTI_VALUE_OPERATORS.includes(c.operator)) {
        const vals =
          typeof c.value === 'string'
            ? c.value.split(',').map((v) => v.trim()).filter(Boolean)
            : c.value
        return { field: c.field, operator: c.operator, value: vals }
      }
      return c
    })

    const scopeLabels = needsLabels
      ? scopeLabelsStr.split(',').map((s) => s.trim()).filter(Boolean)
      : null

    const payload: CreateKbPermissionRulePayload = {
      name: name.trim(),
      enabled: rule?.enabled ?? true,
      user_conditions: processedConditions,
      scope_operator: scopeOperator,
      scope_labels: scopeLabels,
    }

    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          kbId,
          ruleId: rule!.id,
          tenantId,
          data: payload,
        })
        toast('更新成功', 'success')
      } else {
        await createMutation.mutateAsync({ kbId, tenantId, data: payload })
        toast('创建成功', 'success')
      }
      onClose()
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30" onClick={onClose} />

      {/* Panel */}
      <div className="flex h-full w-[520px] flex-col border-l border-border bg-white shadow-[-4px_0_24px_rgba(0,0,0,0.08)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold text-foreground">
            {isEdit ? '编辑否定规则' : '新建否定规则'}
          </h2>
          <div className="flex items-center gap-3">
            <Button onClick={handleSubmit} loading={isPending} size="sm">
              保存
            </Button>
            <button
              className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
              onClick={onClose}
            >
              <IconX size={20} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-8">
            {/* Rule name */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">规则名称</label>
              <input
                className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-foreground placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder=""
                maxLength={128}
              />
            </div>

            {/* User conditions */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">
                用户条件（user metadata）
              </label>
              <div className="space-y-3">
                {conditions.map((cond, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      className="h-10 w-[180px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none"
                      placeholder="输入字段名"
                      value={cond.field}
                      onChange={(e) =>
                        updateCondition(idx, { field: e.target.value })
                      }
                    />
                    <select
                      className="h-10 shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
                      value={cond.operator}
                      onChange={(e) =>
                        updateCondition(idx, {
                          operator: e.target.value as UserConditionOperator,
                        })
                      }
                    >
                      {USER_CONDITION_OPERATORS.map((op) => (
                        <option key={op.value} value={op.value}>
                          {op.label}
                        </option>
                      ))}
                    </select>
                    {!NO_VALUE_OPERATORS.includes(cond.operator) && (
                      <input
                        className="h-10 w-[140px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none"
                        placeholder={
                          MULTI_VALUE_OPERATORS.includes(cond.operator)
                            ? '逗号分隔'
                            : ''
                        }
                        value={
                          Array.isArray(cond.value)
                            ? cond.value.join(', ')
                            : cond.value ?? ''
                        }
                        onChange={(e) =>
                          updateCondition(idx, { value: e.target.value })
                        }
                      />
                    )}
                    <button
                      type="button"
                      className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
                      onClick={() =>
                        conditions.length > 1
                          ? removeCondition(idx)
                          : undefined
                      }
                    >
                      <IconX size={16} className={conditions.length <= 1 ? 'opacity-30' : ''} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={addCondition}
              >
                + 添加条件
              </button>
            </div>

            {/* Scope */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">
                权限范围（doc/slice access_keywords）
              </label>
              <div className="flex items-center gap-2">
                <span className="shrink-0 text-sm text-muted-foreground">不可见内容</span>
                <select
                  className="h-10 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
                  value={scopeOperator}
                  onChange={(e) =>
                    setScopeOperator(e.target.value as ScopeOperator)
                  }
                >
                  {SCOPE_OPERATORS.map((op) => (
                    <option key={op.value} value={op.value}>
                      {op.label}
                    </option>
                  ))}
                </select>
                <input
                  className={cn(
                    'h-10 flex-1 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none',
                    !needsLabels && 'cursor-not-allowed bg-[#F5F5F5] text-[#A3A3A3]'
                  )}
                  placeholder="选择标签"
                  value={scopeLabelsStr}
                  onChange={(e) => setScopeLabelsStr(e.target.value)}
                  disabled={!needsLabels}
                />
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                运算符：等于、不等于、包含任意、不包含任意。包含任意与不包含任意无需选择标签；等于、不等于需选择注册标签。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
