'use client'

import { useState, useCallback, useEffect, useMemo } from 'react'
import { cn } from '@/utils/classnames'
import { Button } from '@/app/components/base/button'
import { Switch } from '@/app/components/base/switch'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { useChannels } from '@/service/use-channel'
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
import { SOURCE_OPTIONS, getSourceLabel } from '@/models/conversation'
import type { Channel } from '@/models/channel'
import { IconPlus, IconPencil, IconTrash, IconX } from '@tabler/icons-react'

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
const SOURCE_VALUE_SET = new Set<string>(SOURCE_OPTIONS.map((item) => item.value))
const SYSTEM_SOURCE_FIELD = 'system.source'
const SYSTEM_CHANNEL_ID_FIELD = 'system.channel_id'
const SYSTEM_CHANNEL_SOURCE_FIELD = 'system.channel_source'
const CHANNEL_SOURCE_MAX_LENGTH = 64

type SystemConditionField =
  | typeof SYSTEM_SOURCE_FIELD
  | typeof SYSTEM_CHANNEL_ID_FIELD
  | typeof SYSTEM_CHANNEL_SOURCE_FIELD

const SYSTEM_CONDITION_FIELDS: {
  value: SystemConditionField
  label: string
  operators: UserConditionOperator[]
  defaultOperator: UserConditionOperator
}[] = [
  {
    value: SYSTEM_SOURCE_FIELD,
    label: '来源渠道',
    operators: ['equals', 'not_equals', 'in', 'not_in', 'is_empty', 'is_not_empty'],
    defaultOperator: 'equals',
  },
  {
    value: SYSTEM_CHANNEL_ID_FIELD,
    label: '渠道配置',
    operators: ['equals', 'not_equals', 'in', 'not_in', 'is_empty', 'is_not_empty'],
    defaultOperator: 'equals',
  },
  {
    value: SYSTEM_CHANNEL_SOURCE_FIELD,
    label: '自定义渠道',
    operators: USER_CONDITION_OPERATORS.map((op) => op.value),
    defaultOperator: 'equals',
  },
]

const LEGACY_SYSTEM_FIELD_LABELS: Record<string, string> = {
  channel: '渠道配置',
}

function getSystemFieldDef(field: string) {
  const canonicalField = field === 'channel' ? SYSTEM_CHANNEL_ID_FIELD : field
  return SYSTEM_CONDITION_FIELDS.find((item) => item.value === canonicalField)
}

function getFieldLabel(field: string): string {
  return getSystemFieldDef(field)?.label ?? LEGACY_SYSTEM_FIELD_LABELS[field] ?? field
}

function getAllowedOperators(field: string): UserConditionOperator[] {
  return getSystemFieldDef(field)?.operators ?? USER_CONDITION_OPERATORS.map((op) => op.value)
}

function getDefaultOperator(field: string): UserConditionOperator {
  return getSystemFieldDef(field)?.defaultOperator ?? 'not_equals'
}

function getDefaultValue(operator: UserConditionOperator): string | string[] | null {
  if (NO_VALUE_OPERATORS.includes(operator)) return null
  if (MULTI_VALUE_OPERATORS.includes(operator)) return []
  return ''
}

function createEmptyMetadataCondition(): UserCondition {
  return { field: '', operator: 'not_equals', value: '' }
}

function createEmptyChannelCondition(): UserCondition {
  return {
    field: SYSTEM_SOURCE_FIELD,
    operator: 'equals',
    value: '',
  }
}

function normalizeChannelCondition(condition: UserCondition): UserCondition {
  const field = getSystemFieldDef(condition.field)?.value ?? SYSTEM_SOURCE_FIELD
  const allowedOperators = getAllowedOperators(field)
  const operator = allowedOperators.includes(condition.operator)
    ? condition.operator
    : getDefaultOperator(field)

  return {
    ...condition,
    field,
    operator,
    value: allowedOperators.includes(condition.operator)
      ? condition.value
      : getDefaultValue(operator),
  }
}

function splitConditionsForForm(rule?: KbPermissionRule): {
  channelConditions: UserCondition[]
  metadataConditions: UserCondition[]
} {
  if (!rule) {
    return {
      channelConditions: [],
      metadataConditions: [createEmptyMetadataCondition()],
    }
  }

  const channelConditions: UserCondition[] = []
  const metadataConditions: UserCondition[] = []

  for (const condition of rule.user_conditions) {
    if (getSystemFieldDef(condition.field)) {
      channelConditions.push(normalizeChannelCondition(condition))
    } else {
      metadataConditions.push(condition)
    }
  }

  return { channelConditions, metadataConditions }
}

function isReservedSystemField(field: string): boolean {
  return field === 'channel' || field.startsWith('system.')
}

function toValueArray(value: UserCondition['value']): string[] {
  if (Array.isArray(value)) return value.map(String)
  if (value === null || value === undefined || value === '') return []
  return String(value).split(',').map((v) => v.trim()).filter(Boolean)
}

function toSingleValue(value: UserCondition['value']): string {
  if (Array.isArray(value)) return value[0] ?? ''
  return value ?? ''
}

function buildChannelNameMap(channels: Channel[]): Map<string, string> {
  return new Map(channels.map((channel) => [String(channel.id), channel.name]))
}

function formatChannelLabel(value: string, channelNameMap: Map<string, string>): string {
  return channelNameMap.get(String(value)) ?? `已删除渠道配置（${value}）`
}

function formatConditionValue(c: UserCondition, channelNameMap: Map<string, string>): string {
  if (NO_VALUE_OPERATORS.includes(c.operator)) return ''

  const values = MULTI_VALUE_OPERATORS.includes(c.operator)
    ? toValueArray(c.value)
    : [toSingleValue(c.value)].filter(Boolean)

  if (c.field === SYSTEM_SOURCE_FIELD) {
    return values.map((value) => getSourceLabel(value)).join(', ')
  }
  if (c.field === SYSTEM_CHANNEL_ID_FIELD || c.field === 'channel') {
    return values.map((value) => formatChannelLabel(value, channelNameMap)).join(', ')
  }
  return values.join(', ')
}

function formatConditionSummary(c: UserCondition, channelNameMap: Map<string, string>): string {
  const opDef = USER_CONDITION_OPERATORS.find((o) => o.value === c.operator)
  const sym = opDef?.symbol ?? c.operator
  const fieldLabel = getFieldLabel(c.field)

  if (NO_VALUE_OPERATORS.includes(c.operator)) {
    return `${fieldLabel} ${sym}`
  }
  if (MULTI_VALUE_OPERATORS.includes(c.operator)) {
    return `${fieldLabel} ${sym} {${formatConditionValue(c, channelNameMap)}}`
  }
  return `${fieldLabel} ${sym} ${formatConditionValue(c, channelNameMap)}`
}

function formatScopeSummary(operator: string, labels: string[] | null): string {
  const opDef = SCOPE_OPERATORS.find((o) => o.value === operator)
  const opLabel = opDef?.label ?? operator
  if (labels && labels.length > 0) {
    return `${opLabel}\u00b7${labels.join(', ')}`
  }
  return opLabel
}

function hasControlCharacter(value: string): boolean {
  return /[\u0000-\u001F\u007F]/.test(value)
}

function isValidChannelSourceValue(value: string): boolean {
  const trimmed = value.trim()
  return (
    trimmed.length > 0 &&
    trimmed.length <= CHANNEL_SOURCE_MAX_LENGTH &&
    !hasControlCharacter(trimmed)
  )
}

function getConditionValuesForSubmit(
  operator: UserConditionOperator,
  value: UserCondition['value']
): string | string[] | null {
  if (NO_VALUE_OPERATORS.includes(operator)) return null
  if (MULTI_VALUE_OPERATORS.includes(operator)) return toValueArray(value)
  return toSingleValue(value).trim()
}

export function PermissionRulesTab({
  kbId,
  tenantId,
}: {
  kbId: number
  tenantId: string
}) {
  const { toast } = useToast()
  const { data: rules, isLoading } = useKbPermissionRules(kbId, tenantId)
  const {
    data: channelsData,
    isLoading: channelsLoading,
    isError: channelsError,
  } = useChannels({ tenant_id: tenantId, per_page: 100 })
  const toggleMutation = useToggleKbPermissionRule()
  const deleteMutation = useDeleteKbPermissionRule()

  const [editingRule, setEditingRule] = useState<KbPermissionRule | null>(null)
  const [showCreatePanel, setShowCreatePanel] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KbPermissionRule | null>(null)
  const channels = useMemo(() => channelsData?.items ?? [], [channelsData?.items])
  const channelNameMap = useMemo(() => buildChannelNameMap(channels), [channels])

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
                          {formatConditionSummary(c, channelNameMap)}
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

      {showPanel && (
        <RuleFormPanel
          kbId={kbId}
          tenantId={tenantId}
          channels={channels}
          channelsLoading={channelsLoading}
          channelsError={channelsError}
          rule={editingRule ?? undefined}
          onClose={() => {
            setShowCreatePanel(false)
            setEditingRule(null)
          }}
        />
      )}

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

function RuleFormPanel({
  kbId,
  tenantId,
  channels,
  channelsLoading,
  channelsError,
  rule,
  onClose,
}: {
  kbId: number
  tenantId: string
  channels: Channel[]
  channelsLoading: boolean
  channelsError: boolean
  rule?: KbPermissionRule
  onClose: () => void
}) {
  const isEdit = !!rule
  const { toast } = useToast()
  const createMutation = useCreateKbPermissionRule()
  const updateMutation = useUpdateKbPermissionRule()
  const initialConditions = useMemo(() => splitConditionsForForm(rule), [rule])

  const [name, setName] = useState(rule?.name ?? '')
  const [channelConditions, setChannelConditions] = useState<UserCondition[]>(
    initialConditions.channelConditions
  )
  const [metadataConditions, setMetadataConditions] = useState<UserCondition[]>(
    initialConditions.metadataConditions
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

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const addChannelCondition = () => {
    setChannelConditions((prev) => [...prev, createEmptyChannelCondition()])
  }

  const removeChannelCondition = (index: number) => {
    setChannelConditions((prev) => prev.filter((_, i) => i !== index))
  }

  const updateChannelCondition = (index: number, patch: Partial<UserCondition>) => {
    setChannelConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c))
    )
  }

  const addMetadataCondition = () => {
    setMetadataConditions((prev) => [...prev, createEmptyMetadataCondition()])
  }

  const removeMetadataCondition = (index: number) => {
    setMetadataConditions((prev) => prev.filter((_, i) => i !== index))
  }

  const updateMetadataCondition = (index: number, patch: Partial<UserCondition>) => {
    setMetadataConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c))
    )
  }

  const updateChannelConditionField = (index: number, fieldValue: string) => {
    const field = fieldValue as SystemConditionField
    const operator = getDefaultOperator(field)
    updateChannelCondition(index, {
      field,
      operator,
      value: getDefaultValue(operator),
    })
  }

  const updateChannelConditionOperator = (
    index: number,
    operator: UserConditionOperator
  ) => {
    updateChannelCondition(index, {
      operator,
      value: getDefaultValue(operator),
    })
  }

  const updateMetadataConditionOperator = (
    index: number,
    operator: UserConditionOperator
  ) => {
    updateMetadataCondition(index, {
      operator,
      value: getDefaultValue(operator),
    })
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast('请输入规则名称', 'error')
      return
    }
    if (channelConditions.length === 0 && metadataConditions.length === 0) {
      toast('请至少添加一个用户条件', 'error')
      return
    }

    const processedConditions: UserCondition[] = []
    for (const c of channelConditions) {
      const field = c.field === 'channel' ? SYSTEM_CHANNEL_ID_FIELD : c.field.trim()
      const isNoValueOperator = NO_VALUE_OPERATORS.includes(c.operator)
      const values = getConditionValuesForSubmit(c.operator, c.value)
      const valueList = Array.isArray(values) ? values : values ? [values] : []

      if (!getSystemFieldDef(field)) {
        toast('请选择渠道条件字段', 'error')
        return
      }
      if (!getAllowedOperators(field).includes(c.operator)) {
        toast('请选择渠道条件运算符', 'error')
        return
      }
      if (!isNoValueOperator && valueList.length === 0) {
        if (field === SYSTEM_SOURCE_FIELD) {
          toast('请选择来源渠道', 'error')
        } else if (field === SYSTEM_CHANNEL_ID_FIELD) {
          toast('请选择渠道配置', 'error')
        } else {
          toast('请输入用户条件的值', 'error')
        }
        return
      }
      if (!isNoValueOperator && field === SYSTEM_SOURCE_FIELD) {
        const hasInvalidSource = valueList.some((value) => !SOURCE_VALUE_SET.has(value))
        if (hasInvalidSource) {
          toast('请选择来源渠道', 'error')
          return
        }
      }
      if (!isNoValueOperator && field === SYSTEM_CHANNEL_ID_FIELD && channelsError) {
        toast('渠道配置加载失败，请重试', 'error')
        return
      }
      if (!isNoValueOperator && field === SYSTEM_CHANNEL_SOURCE_FIELD) {
        const hasInvalidChannelSource = valueList.some(
          (value) => !isValidChannelSourceValue(value)
        )
        if (hasInvalidChannelSource) {
          toast('自定义渠道需为 1-64 个可见字符', 'error')
          return
        }
      }

      processedConditions.push({
        field,
        operator: c.operator,
        value: values,
      })
    }

    for (const c of metadataConditions) {
      const field = c.field.trim()
      const isNoValueOperator = NO_VALUE_OPERATORS.includes(c.operator)
      const values = getConditionValuesForSubmit(c.operator, c.value)
      const valueList = Array.isArray(values) ? values : values ? [values] : []

      if (!field) {
        toast('用户条件的字段名不能为空', 'error')
        return
      }
      if (isReservedSystemField(field)) {
        toast('渠道相关字段请在渠道条件中配置', 'error')
        return
      }
      if (!isNoValueOperator && valueList.length === 0) {
        toast('请输入用户条件的值', 'error')
        return
      }

      processedConditions.push({
        field,
        operator: c.operator,
        value: values,
      })
    }

    if (needsLabels && !scopeLabelsStr.trim()) {
      toast('请选择标签', 'error')
      return
    }

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

  const renderChannelOptions = (selectedValues: string[], emptyLabel: string) => {
    const channelNameMap = buildChannelNameMap(channels)
    const missingValues = selectedValues.filter(
      (value) => value && !channelNameMap.has(value)
    )

    return (
      <>
        {channels.length === 0 && missingValues.length === 0 && (
          <option value="" disabled>
            {emptyLabel}
          </option>
        )}
        {missingValues.map((value) => (
          <option key={value} value={value}>
            {formatChannelLabel(value, channelNameMap)}
          </option>
        ))}
        {channels.map((channel) => (
          <option key={channel.id} value={String(channel.id)}>
            {channel.name}
          </option>
        ))}
      </>
    )
  }

  const renderValueControl = (
    cond: UserCondition,
    onChange: (patch: Partial<UserCondition>) => void
  ) => {
    if (NO_VALUE_OPERATORS.includes(cond.operator)) return null

    const isMulti = MULTI_VALUE_OPERATORS.includes(cond.operator)
    const field = cond.field === 'channel' ? SYSTEM_CHANNEL_ID_FIELD : cond.field

    if (field === SYSTEM_SOURCE_FIELD) {
      if (isMulti) {
        return (
          <select
            multiple
            className="h-20 w-[132px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 py-2 text-sm focus:border-[#1a1a1a] focus:outline-none"
            value={toValueArray(cond.value)}
            onChange={(e) =>
              onChange({
                value: Array.from(e.currentTarget.selectedOptions).map(
                  (option) => option.value
                ),
              })
            }
          >
            {SOURCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )
      }
      return (
        <select
          className="h-10 w-[132px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
          value={toSingleValue(cond.value)}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          <option value="">请选择来源渠道</option>
          {SOURCE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )
    }

    if (field === SYSTEM_CHANNEL_ID_FIELD) {
      const selectedValues = isMulti ? toValueArray(cond.value) : [toSingleValue(cond.value)].filter(Boolean)
      const emptyLabel = channelsLoading
        ? '渠道配置加载中...'
        : channelsError
          ? '渠道配置加载失败'
          : '请选择渠道配置'

      if (isMulti) {
        return (
          <select
            multiple
            className="h-20 w-[160px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 py-2 text-sm focus:border-[#1a1a1a] focus:outline-none"
            value={toValueArray(cond.value)}
            disabled={channelsLoading || channelsError}
            onChange={(e) =>
              onChange({
                value: Array.from(e.currentTarget.selectedOptions).map(
                  (option) => option.value
                ),
              })
            }
          >
            {renderChannelOptions(selectedValues, emptyLabel)}
          </select>
        )
      }
      return (
        <select
          className="h-10 w-[160px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
          value={toSingleValue(cond.value)}
          disabled={channelsLoading || channelsError}
          onChange={(e) => onChange({ value: e.target.value })}
        >
          <option value="">{emptyLabel}</option>
          {renderChannelOptions(selectedValues, emptyLabel)}
        </select>
      )
    }

    return (
      <input
        className="h-10 w-[132px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none"
        placeholder={isMulti ? '逗号分隔' : ''}
        value={Array.isArray(cond.value) ? cond.value.join(', ') : cond.value ?? ''}
        onChange={(e) => onChange({ value: e.target.value })}
      />
    )
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />

      <div className="flex h-full w-[520px] flex-col border-l border-border bg-white shadow-[-4px_0_24px_rgba(0,0,0,0.08)]">
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

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-8">
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

            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">
                渠道条件
              </label>
              {channelConditions.length > 0 && (
                <div className="space-y-3">
                  {channelConditions.map((cond, idx) => {
                    const allowedOperators = getAllowedOperators(cond.field)

                    return (
                      <div key={idx} className="flex items-start gap-2">
                        <select
                          className="h-10 w-[140px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
                          value={cond.field}
                          onChange={(e) =>
                            updateChannelConditionField(idx, e.target.value)
                          }
                        >
                          {SYSTEM_CONDITION_FIELDS.map((field) => (
                            <option key={field.value} value={field.value}>
                              {field.label}
                            </option>
                          ))}
                        </select>
                        <select
                          className="h-10 w-[112px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
                          value={cond.operator}
                          onChange={(e) =>
                            updateChannelConditionOperator(
                              idx,
                              e.target.value as UserConditionOperator
                            )
                          }
                        >
                          {USER_CONDITION_OPERATORS.filter((op) =>
                            allowedOperators.includes(op.value)
                          ).map((op) => (
                            <option key={op.value} value={op.value}>
                              {op.label}
                            </option>
                          ))}
                        </select>
                        {renderValueControl(cond, (patch) =>
                          updateChannelCondition(idx, patch)
                        )}
                        <button
                          type="button"
                          className="mt-2 shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
                          onClick={() => removeChannelCondition(idx)}
                        >
                          <IconX size={16} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
              <button
                type="button"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={addChannelCondition}
              >
                + 添加渠道条件
              </button>
            </div>

            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">
                用户条件（user metadata）
              </label>
              <div className="space-y-3">
                {metadataConditions.map((cond, idx) => {
                  const canRemove =
                    metadataConditions.length > 1 || channelConditions.length > 0

                  return (
                    <div key={idx} className="flex items-start gap-2">
                      <input
                        className="h-10 w-[160px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm placeholder:text-[#A3A3A3] focus:border-[#1a1a1a] focus:outline-none"
                        placeholder="输入字段名"
                        value={cond.field}
                        onChange={(e) =>
                          updateMetadataCondition(idx, { field: e.target.value })
                        }
                      />
                      <select
                        className="h-10 w-[112px] shrink-0 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm focus:border-[#1a1a1a] focus:outline-none"
                        value={cond.operator}
                        onChange={(e) =>
                          updateMetadataConditionOperator(
                            idx,
                            e.target.value as UserConditionOperator
                          )
                        }
                      >
                        {USER_CONDITION_OPERATORS.map((op) => (
                          <option key={op.value} value={op.value}>
                            {op.label}
                          </option>
                        ))}
                      </select>
                      {renderValueControl(cond, (patch) =>
                        updateMetadataCondition(idx, patch)
                      )}
                      <button
                        type="button"
                        className="mt-2 shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
                        onClick={() => (canRemove ? removeMetadataCondition(idx) : undefined)}
                      >
                        <IconX size={16} className={!canRemove ? 'opacity-30' : ''} />
                      </button>
                    </div>
                  )
                })}
              </div>
              <button
                type="button"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={addMetadataCondition}
              >
                + 添加条件
              </button>
            </div>

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
