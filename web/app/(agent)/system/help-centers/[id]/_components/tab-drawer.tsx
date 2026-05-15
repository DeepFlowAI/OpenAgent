'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  IconArrowLeft,
  IconChevronDown,
  IconPlus,
  IconX,
} from '@tabler/icons-react'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { useAuthStore } from '@/context/auth-store'
import { useKnowledgeBases, useKBMetaSchema } from '@/service/use-knowledge-base'
import {
  useCheckTabSlug,
  useCreateHelpCenterTab,
  useUpdateHelpCenterTab,
} from '@/service/use-help-center-tab'
import {
  FILTER_OPS,
  SLUG_REGEX,
  type FilterOp,
  type HelpCenterTab,
  type TabCreatePayload,
  type TabFilterCondition,
} from '@/models/help-center'
import { cn } from '@/utils/classnames'

type FilterRowState = {
  field: string
  op: FilterOp
  value: string
}

type FormState = {
  displayName: string
  tabSlug: string
  kbId: number | null
  filters: FilterRowState[]
}

const EMPTY: FormState = {
  displayName: '',
  tabSlug: '',
  kbId: null,
  filters: [],
}

const OP_LABELS: Record<FilterOp, string> = {
  eq: '等于',
  ne: '不等于',
  gt: '大于',
  ge: '≥',
  lt: '小于',
  le: '≤',
  in: '在列表中',
}

export function TabDrawer({
  open,
  helpCenterId,
  initialTab,
  onClose,
}: {
  open: boolean
  helpCenterId: number
  initialTab: HelpCenterTab | null
  onClose: () => void
}) {
  const { toast } = useToast()
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''
  const { data: kbList } = useKnowledgeBases(tenantId, { per_page: 20 })
  const createMutation = useCreateHelpCenterTab(helpCenterId)
  const updateMutation = useUpdateHelpCenterTab(helpCenterId)
  const checkSlugMutation = useCheckTabSlug(helpCenterId)

  const isEdit = !!initialTab

  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [slugAvailable, setSlugAvailable] = useState<boolean | null>(null)
  const [showSlugConfirm, setShowSlugConfirm] = useState(false)
  const slugCheckTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: metaSchema } = useKBMetaSchema(form.kbId)
  const docMetaFields = metaSchema?.doc_meta ?? []

  // Reset form whenever drawer opens (or the editing target changes)
  useEffect(() => {
    if (!open) return
    if (initialTab) {
      setForm({
        displayName: initialTab.display_name,
        tabSlug: initialTab.tab_slug ?? '',
        kbId: initialTab.knowledge_base_id,
        filters: (initialTab.fixed_filters ?? []).map((f) => ({
          field: f.field,
          op: f.op,
          value: serializeValue(f.value),
        })),
      })
    } else {
      setForm(EMPTY)
    }
    setErrors({})
    setSlugAvailable(null)
  }, [open, initialTab])

  // Lock body scroll while open
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  // ESC to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Debounced slug availability — UX hint only; server re-validates on save.
  useEffect(() => {
    if (slugCheckTimer.current) clearTimeout(slugCheckTimer.current)
    setSlugAvailable(null)
    const slug = form.tabSlug.trim()
    if (!slug || !SLUG_REGEX.test(slug) || slug.length < 3) return
    if (initialTab && slug === (initialTab.tab_slug ?? '')) return

    slugCheckTimer.current = setTimeout(() => {
      checkSlugMutation
        .mutateAsync({ slug, excludeId: initialTab?.id })
        .then((r) => setSlugAvailable(r.available))
        .catch(() => setSlugAvailable(null))
    }, 300)

    return () => {
      if (slugCheckTimer.current) clearTimeout(slugCheckTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.tabSlug, initialTab?.id])

  // ── Validation ─────────────────────────────────────────────────────────

  const validate = (): Record<string, string> => {
    const next: Record<string, string> = {}
    if (!form.displayName.trim()) next.displayName = '请输入显示名'
    else if (form.displayName.length > 32) next.displayName = '不超过 32 个字符'

    const slug = form.tabSlug.trim()
    if (slug) {
      if (slug.length < 3 || slug.length > 48) next.tabSlug = '长度 3–48'
      else if (!SLUG_REGEX.test(slug))
        next.tabSlug = '仅允许小写字母、数字、连字符'
      else if (slugAvailable === false) next.tabSlug = '该标识已被使用'
    }

    if (!form.kbId) next.kbId = '请选择知识库'

    form.filters.forEach((row, i) => {
      if (!row.field) next[`filter_${i}_field`] = '选择字段'
      if (!row.op) next[`filter_${i}_op`] = '选择运算符'
      if (row.value.trim() === '') next[`filter_${i}_value`] = '输入值'
      else if (row.op === 'in') {
        const parts = row.value
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        if (parts.length === 0) next[`filter_${i}_value`] = '至少 1 项'
      }
    })
    return next
  }

  const buildFilters = (): TabFilterCondition[] => {
    return form.filters.map((row) => {
      const def = docMetaFields.find((d) => d.name === row.field)
      const type = def?.type ?? 'keyword'
      let value: unknown
      if (row.op === 'in') {
        value = row.value
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => coerceValue(s, type))
      } else {
        value = coerceValue(row.value.trim(), type)
      }
      return { field: row.field, op: row.op, value }
    })
  }

  const performSave = async () => {
    if (!form.kbId) return
    const payload: TabCreatePayload = {
      display_name: form.displayName.trim(),
      tab_slug: form.tabSlug.trim() || null,
      knowledge_base_id: form.kbId,
      fixed_filters: buildFilters(),
    }
    try {
      if (initialTab) {
        await updateMutation.mutateAsync({
          tabId: initialTab.id,
          payload,
        })
        toast('已保存', 'success')
      } else {
        await createMutation.mutateAsync(payload)
        toast('已添加', 'success')
      }
      onClose()
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }

  const handleSubmit = async () => {
    const v = validate()
    setErrors(v)
    if (Object.keys(v).length > 0) {
      toast('请检查表单填写', 'error')
      return
    }
    const slugChanged =
      isEdit &&
      (initialTab?.tab_slug ?? '') !== '' &&
      form.tabSlug.trim() !== (initialTab?.tab_slug ?? '')
    if (slugChanged) {
      setShowSlugConfirm(true)
      return
    }
    await performSave()
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="absolute inset-y-0 right-0 flex h-full w-[min(92vw,720px)] flex-col bg-white shadow-2xl">
        {/* Top bar */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#E4E4E7] px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-[#71717A] transition-colors hover:bg-[#F4F4F5] hover:text-foreground"
              title="关闭"
            >
              <IconArrowLeft size={20} />
            </button>
            <h2 className="text-base font-semibold text-foreground">
              {isEdit ? '编辑内容 Tab' : '添加内容 Tab'}
            </h2>
          </div>
          <Button onClick={handleSubmit} loading={isPending}>
            确定
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-8 py-7">
          <div className="flex flex-col gap-6">
            <Input
              label="显示名"
              required
              value={form.displayName}
              maxLength={32}
              error={errors.displayName}
              onChange={(e) =>
                setForm({ ...form, displayName: e.target.value })
              }
            />

            <Input
              label="URL 段（可选）"
              value={form.tabSlug}
              maxLength={48}
              placeholder="留空时由系统自动生成短码"
              error={errors.tabSlug}
              hint={slugHint(
                form.tabSlug,
                slugAvailable,
                initialTab?.tab_slug ?? ''
              )}
              onChange={(e) => setForm({ ...form, tabSlug: e.target.value })}
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#1a1a1a]">
                知识库<span className="ml-0.5 text-[#DC2626]">*</span>
              </label>
              <div className="relative">
                <select
                  value={form.kbId ?? ''}
                  onChange={(e) => {
                    const v = e.target.value ? Number(e.target.value) : null
                    // Reset filter values when KB changes — schema will be different.
                    setForm({ ...form, kbId: v, filters: [] })
                  }}
                  className={cn(
                    'h-11 w-full appearance-none rounded-lg border border-[#E5E5E5] bg-white px-3 pr-9 text-sm text-[#1a1a1a] focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10',
                    errors.kbId &&
                      'border-[#DC2626] focus:border-[#DC2626] focus:ring-[#DC2626]/10'
                  )}
                >
                  <option value="">请选择知识库</option>
                  {(kbList?.items ?? []).map((kb) => (
                    <option key={kb.id} value={kb.id}>
                      {kb.name}
                    </option>
                  ))}
                </select>
                <IconChevronDown
                  size={16}
                  className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]"
                />
              </div>
              {errors.kbId && (
                <p className="text-xs text-[#DC2626]">{errors.kbId}</p>
              )}
            </div>

            <FilterEditor
              filters={form.filters}
              onChange={(filters) => setForm({ ...form, filters })}
              fields={docMetaFields}
              kbSelected={!!form.kbId}
              errors={errors}
            />
          </div>
        </div>
      </div>

      <ConfirmModal
        open={showSlugConfirm}
        onClose={() => setShowSlugConfirm(false)}
        onConfirm={async () => {
          setShowSlugConfirm(false)
          await performSave()
        }}
        title="修改 URL 段"
        description="修改后该 Tab 旧的公开地址将立即失效（暂不提供 301 跳转），外链与搜索收录会受影响，确认继续？"
        confirmText="确认修改"
        variant="destructive"
        loading={isPending}
      />
    </div>
  )
}

// ── Filter Editor ──────────────────────────────────────────────────────────

type FieldDef = {
  name: string
  type: string
  values?: string[]
  description?: string
}

function FilterEditor({
  filters,
  onChange,
  fields,
  kbSelected,
  errors,
}: {
  filters: FilterRowState[]
  onChange: (next: FilterRowState[]) => void
  fields: FieldDef[]
  kbSelected: boolean
  errors: Record<string, string>
}) {
  const addRow = () => {
    onChange([
      ...filters,
      { field: fields[0]?.name ?? '', op: 'eq', value: '' },
    ])
  }
  const updateRow = (i: number, patch: Partial<FilterRowState>) => {
    const next = [...filters]
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }
  const removeRow = (i: number) => {
    const next = [...filters]
    next.splice(i, 1)
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-medium text-[#1a1a1a]">固定筛选条件</h3>
        <p className="mt-1 text-xs text-[#A3A3A3]">
          基于 doc-meta
          的结构化筛选，访客侧以及 LLM 检索均生效。系统根据知识库 Schema 自动加载可选字段。
        </p>
      </div>

      {!kbSelected ? (
        <div className="rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] py-6 text-center text-xs text-[#A1A1AA]">
          请先选择知识库以加载可用字段
        </div>
      ) : (
        <>
          {filters.length === 0 && (
            <div className="rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] py-6 text-center text-xs text-[#A1A1AA]">
              暂无筛选条件
            </div>
          )}
          {filters.map((row, i) => (
            <FilterRow
              key={i}
              row={row}
              fields={fields}
              fieldError={errors[`filter_${i}_field`]}
              opError={errors[`filter_${i}_op`]}
              valueError={errors[`filter_${i}_value`]}
              onUpdate={(patch) => updateRow(i, patch)}
              onRemove={() => removeRow(i)}
            />
          ))}
          <button
            type="button"
            onClick={addRow}
            className="inline-flex w-fit items-center gap-1 text-sm text-[#1a1a1a] underline-offset-4 hover:underline"
          >
            <IconPlus size={14} />
            添加一行
          </button>
        </>
      )}
    </div>
  )
}

function FilterRow({
  row,
  fields,
  fieldError,
  opError,
  valueError,
  onUpdate,
  onRemove,
}: {
  row: FilterRowState
  fields: FieldDef[]
  fieldError?: string
  opError?: string
  valueError?: string
  onUpdate: (patch: Partial<FilterRowState>) => void
  onRemove: () => void
}) {
  const def = useMemo(
    () => fields.find((f) => f.name === row.field),
    [fields, row.field]
  )
  const allowedOps = useMemo<FilterOp[]>(
    () => allowedOpsForType(def?.type),
    [def?.type]
  )

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] p-3">
      <div className="flex flex-wrap items-start gap-2">
        {/* Field */}
        <SelectCell
          value={row.field}
          onChange={(v) => onUpdate({ field: v })}
          error={!!fieldError}
          className="min-w-[140px] flex-1"
        >
          <option value="">选择字段</option>
          {fields.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
              {f.type ? ` (${f.type})` : ''}
            </option>
          ))}
        </SelectCell>

        {/* Op */}
        <SelectCell
          value={row.op}
          onChange={(v) => onUpdate({ op: v as FilterOp, value: '' })}
          error={!!opError}
          className="w-[120px]"
        >
          {FILTER_OPS.filter((o) => allowedOps.includes(o)).map((o) => (
            <option key={o} value={o}>
              {OP_LABELS[o]}
            </option>
          ))}
        </SelectCell>

        {/* Value */}
        <ValueCell
          row={row}
          def={def}
          error={!!valueError}
          onChange={(v) => onUpdate({ value: v })}
        />

        {/* Remove */}
        <button
          type="button"
          onClick={onRemove}
          className="mt-1 rounded-md p-1.5 text-[#A1A1AA] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
          title="删除"
        >
          <IconX size={14} />
        </button>
      </div>
      {(fieldError || opError || valueError) && (
        <p className="text-xs text-[#DC2626]">
          {fieldError || opError || valueError}
        </p>
      )}
    </div>
  )
}

function SelectCell({
  value,
  onChange,
  error,
  className,
  children,
}: {
  value: string | number
  onChange: (v: string) => void
  error?: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('relative', className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-9 w-full appearance-none rounded-md border bg-white px-2.5 pr-7 text-sm text-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10',
          error
            ? 'border-[#DC2626] focus:ring-[#DC2626]/10'
            : 'border-[#E4E4E7] focus:border-[#1a1a1a]'
        )}
      >
        {children}
      </select>
      <IconChevronDown
        size={14}
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[#A1A1AA]"
      />
    </div>
  )
}

function ValueCell({
  row,
  def,
  error,
  onChange,
}: {
  row: FilterRowState
  def?: FieldDef
  error?: boolean
  onChange: (v: string) => void
}) {
  const type = def?.type ?? 'keyword'

  // Boolean: dropdown
  if (row.op !== 'in' && type === 'boolean') {
    return (
      <SelectCell
        value={row.value}
        onChange={onChange}
        error={error}
        className="w-[180px]"
      >
        <option value="">选择值</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </SelectCell>
    )
  }

  // Enum + single op (eq/ne): dropdown of values
  if (
    row.op !== 'in' &&
    type === 'enum' &&
    def?.values &&
    def.values.length > 0
  ) {
    return (
      <SelectCell
        value={row.value}
        onChange={onChange}
        error={error}
        className="w-[200px]"
      >
        <option value="">选择值</option>
        {def.values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </SelectCell>
    )
  }

  const placeholder = row.op === 'in' ? '逗号分隔多个值' : '输入值'

  return (
    <input
      type="text"
      value={row.value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(
        'h-9 min-w-[180px] flex-1 rounded-md border bg-white px-2.5 text-sm text-[#1a1a1a] placeholder:text-[#A1A1AA] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10',
        error
          ? 'border-[#DC2626] focus:ring-[#DC2626]/10'
          : 'border-[#E4E4E7] focus:border-[#1a1a1a]'
      )}
    />
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────

function allowedOpsForType(type: string | undefined): FilterOp[] {
  switch (type) {
    case 'integer':
    case 'float':
    case 'date':
      return ['eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in']
    case 'boolean':
      return ['eq']
    case 'enum':
      return ['eq', 'ne', 'in']
    default:
      // keyword / text / unknown — restrict to operators that make sense.
      return ['eq', 'ne', 'in']
  }
}

function coerceValue(raw: string, type: string): unknown {
  switch (type) {
    case 'integer': {
      const n = parseInt(raw, 10)
      return Number.isNaN(n) ? raw : n
    }
    case 'float': {
      const n = parseFloat(raw)
      return Number.isNaN(n) ? raw : n
    }
    case 'boolean':
      return raw === 'true'
    default:
      return raw
  }
}

function serializeValue(v: unknown): string {
  if (Array.isArray(v)) return v.map(String).join(',')
  if (v === null || v === undefined) return ''
  return String(v)
}

function slugHint(
  slug: string,
  available: boolean | null,
  initial: string
): string | undefined {
  const trimmed = slug.trim()
  if (!trimmed) return '留空将由系统生成；3–48 个字符，仅小写字母、数字、连字符'
  if (trimmed === initial) return undefined
  if (available === true) return '可用'
  return undefined
}
