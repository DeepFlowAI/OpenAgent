'use client'

import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAgentTool, useUpdateAgentTool } from '@/service/use-agent-tool'
import { useKnowledgeBases, useKBMetaFields, useKBMetaSchema } from '@/service/use-knowledge-base'
import type { FieldDefinition } from '@/service/use-knowledge-base'
import { useAuthStore } from '@/context/auth-store'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Switch } from '@/app/components/base/switch'
import type { AgentTool } from '@/models/agent-tool'
import {
  IconArrowLeft,
  IconFileText,
  IconDatabase,
  IconAdjustmentsHorizontal,
  IconPlug,
  IconSearch,
  IconStack2,
  IconFileExport,
  IconSettings,
  IconPlus,
  IconX,
  IconLock,
  IconChevronDown,
} from '@tabler/icons-react'
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxValue,
  useComboboxAnchor,
} from '@/app/components/base/combobox'

/* ═══════════════ Type Definitions ═══════════════ */

type FilterRow = {
  level: string
  field: string
  op: string
  value: string
}

type CategoryGroup = {
  name: string
  filters: FilterRow[]
}

type MetaFieldCategory = 'doc_meta' | 'slice_meta' | 'extra'

type MetaField = {
  name: string
  category: MetaFieldCategory
}

/* ═══════════════ Type-safe Config Accessors ═══════════════ */

function cfgStr(obj: Record<string, unknown>, key: string, fallback = ''): string {
  const v = obj[key]
  return typeof v === 'string' ? v : fallback
}

function cfgNum(obj: Record<string, unknown>, key: string, fallback: number): number {
  const v = obj[key]
  return typeof v === 'number' ? v : fallback
}

function cfgBool(obj: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const v = obj[key]
  return typeof v === 'boolean' ? v : fallback
}

function cfgRecord(obj: Record<string, unknown>, key: string): Record<string, unknown> {
  const v = obj[key]
  return v !== null && v !== undefined && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {}
}

function cfgStrArr(obj: Record<string, unknown>, key: string): string[] {
  const v = obj[key]
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}

function cfgFilterRows(obj: Record<string, unknown>, key: string): FilterRow[] {
  const v = obj[key]
  if (!Array.isArray(v)) return []
  return v.filter(
    (item): item is FilterRow =>
      typeof item === 'object' &&
      item !== null &&
      'level' in item &&
      'field' in item &&
      'op' in item &&
      'value' in item,
  )
}

function cfgCategoryGroups(obj: Record<string, unknown>, key: string): CategoryGroup[] {
  const v = obj[key]
  if (!Array.isArray(v)) return []
  return v.filter(
    (item): item is CategoryGroup =>
      typeof item === 'object' &&
      item !== null &&
      'name' in item &&
      'filters' in item,
  )
}

// Immutably set a value at a nested path within a config record
function setNested(
  config: Record<string, unknown>,
  path: string[],
  value: unknown,
): Record<string, unknown> {
  if (path.length === 0) return config
  if (path.length === 1) return { ...config, [path[0]]: value }
  const [head, ...rest] = path
  const child = cfgRecord(config, head)
  return { ...config, [head]: setNested(child, rest, value) }
}

/* ═══════════════ Constants ═══════════════ */

/* ═══════════════ Type-driven Operator Config ═══════════════ */

type OperatorDef = { value: string; label: string }

const ALL_OPERATORS: OperatorDef[] = [
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'contains', label: '包含' },
  { value: 'in', label: '在列表中' },
  { value: 'gt', label: '大于' },
  { value: 'ge', label: '≥' },
  { value: 'lt', label: '小于' },
  { value: 'le', label: '≤' },
  { value: 'has_any', label: '包含任一' },
  { value: 'has_all', label: '包含全部' },
]

const OPERATORS_BY_TYPE: Record<string, string[]> = {
  keyword: ['eq', 'ne', 'contains'],
  enum: ['eq', 'ne', 'in'],
  'keyword[]': ['has_any', 'has_all'],
  'integer[]': ['has_any', 'has_all'],
  integer: ['eq', 'ne', 'gt', 'ge', 'lt', 'le'],
  float: ['eq', 'ne', 'gt', 'ge', 'lt', 'le'],
  date: ['eq', 'gt', 'ge', 'lt', 'le'],
  boolean: ['eq'],
  text: ['contains'],
}

const OP_MAP = new Map(ALL_OPERATORS.map((o) => [o.value, o]))

function getOperatorsForType(fieldType: string | undefined): OperatorDef[] {
  if (!fieldType) return ALL_OPERATORS
  const allowed = OPERATORS_BY_TYPE[fieldType]
  if (!allowed) return ALL_OPERATORS
  return allowed.map((v) => OP_MAP.get(v)).filter((o): o is OperatorDef => !!o)
}

const OP_COMPAT_MAP: Record<string, string> = { gte: 'ge', lte: 'le' }

function normaliseOp(op: string): string {
  return OP_COMPAT_MAP[op] ?? op
}

const SEARCH_MODE_OPTIONS = [
  { value: 'hybrid', label: '混合搜索' },
  { value: 'bm25', label: 'BM25' },
  { value: 'vector', label: '向量搜索' },
]

const SEARCH_LEVEL_OPTIONS = [
  { value: 'doc-meta', label: 'doc-meta' },
  { value: 'slice-meta', label: 'slice-meta' },
]

const DOC_ONLY_LEVEL_OPTIONS = [
  { value: 'doc-meta', label: 'doc-meta' },
]

const PAGE_TITLE_MAP: Partial<Record<AgentTool['tool_type'], string>> = {
  search: '搜索工具配置',
  doc_query: '文档查询工具配置',
}

const INPUT_CLS =
  'w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none placeholder:text-[#A1A1AA] focus:border-[#18181B]'

/* ═══════════════ Reusable Sub-components ═══════════════ */

function SectionHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[#18181B]">{icon}</span>
      <h3 className="text-[16px] font-semibold leading-6 text-[#18181B]">{title}</h3>
    </div>
  )
}

function SectionDivider() {
  return <hr className="border-t border-[#E4E4E7]" />
}

function DescriptionText({ children }: { children: ReactNode }) {
  return <p className="text-[13px] leading-5 text-[#A1A1AA]">{children}</p>
}

function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
      {children}
    </label>
  )
}

function FieldHint({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-xs text-[#A1A1AA]">{children}</p>
}

/* ═══════════════ Type-driven Value Editors ═══════════════ */

function EnumValueSelect({
  value,
  options,
  multi,
  onChange,
}: {
  value: string
  options: string[]
  multi?: boolean
  onChange: (v: string) => void
}) {
  if (multi) {
    const selected = value ? value.split(',').filter(Boolean) : []
    const anchor = useComboboxAnchor()

    return (
      <div className="w-[200px] shrink-0">
        <Combobox
          multiple
          autoHighlight
          items={options}
          value={selected}
          onValueChange={(vals: string[]) => onChange(vals.join(','))}
        >
          <ComboboxChips ref={anchor}>
            <ComboboxValue>
              {(vals: string[] | null) => (
                <>
                  {(vals ?? []).map((v: string) => (
                    <ComboboxChip key={v}>{v}</ComboboxChip>
                  ))}
                  <ComboboxChipsInput placeholder="搜索..." />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <ComboboxContent anchor={anchor}>
            <ComboboxEmpty>无匹配项</ComboboxEmpty>
            <ComboboxList>
              {(item: string) => (
                <ComboboxItem key={item} value={item}>
                  {item}
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </div>
    )
  }

  return (
    <div className="w-[200px] shrink-0">
      <Combobox
        items={options}
        value={value || null}
        onValueChange={(v: string | null) => onChange(v ?? '')}
      >
        <ComboboxInput placeholder="选择值" />
        <ComboboxContent>
          <ComboboxEmpty>无匹配项</ComboboxEmpty>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item}>
                {item}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

function BooleanValueSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] bg-white px-2 text-xs text-[#18181B] outline-none"
    >
      <option value="">选择值</option>
      <option value="true">true</option>
      <option value="false">false</option>
    </select>
  )
}

function TagValueInput({
  value,
  suggestions,
  onChange,
}: {
  value: string
  suggestions?: string[]
  onChange: (v: string) => void
}) {
  const tags = value ? value.split(',').filter(Boolean) : []
  const anchor = useComboboxAnchor()

  const hasSuggestions = suggestions && suggestions.length > 0

  if (hasSuggestions) {
    return (
      <Combobox
        multiple
        autoHighlight
        items={suggestions}
        value={tags}
        onValueChange={(vals: string[]) => onChange(vals.join(','))}
      >
        <ComboboxChips ref={anchor}>
          <ComboboxValue>
            {(vals: string[] | null) => (
              <>
                {(vals ?? []).map((v: string) => (
                  <ComboboxChip key={v}>{v}</ComboboxChip>
                ))}
                <ComboboxChipsInput placeholder="搜索..." />
              </>
            )}
          </ComboboxValue>
        </ComboboxChips>
        <ComboboxContent anchor={anchor}>
          <ComboboxEmpty>无匹配项</ComboboxEmpty>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item}>
                {item}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    )
  }

  return <FreeTagInput value={value} onChange={onChange} />
}

function FreeTagInput({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const tags = value ? value.split(',').filter(Boolean) : []
  const [inputVal, setInputVal] = useState('')

  const addTag = (tag: string) => {
    const trimmed = tag.trim()
    if (!trimmed || tags.includes(trimmed)) return
    onChange([...tags, trimmed].join(','))
    setInputVal('')
  }

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag).join(','))
  }

  return (
    <div className="flex min-h-[32px] flex-wrap items-center gap-1 rounded-lg border border-[#E4E4E7] bg-white px-2 py-1 transition-colors focus-within:border-[#18181B] focus-within:ring-2 focus-within:ring-[#18181B]/10">
      {tags.map((tag) => (
        <span
          key={tag}
          className="flex h-[22px] max-w-full items-center gap-0.5 rounded bg-[#F4F4F5] py-px pl-1.5 pr-0.5 text-[10px] leading-tight text-[#18181B]"
        >
          <span className="min-w-0 truncate">{tag}</span>
          <button
            type="button"
            onClick={() => removeTag(tag)}
            className="shrink-0 rounded-sm p-px text-[#A1A1AA] hover:text-[#18181B]"
          >
            <IconX size={10} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={inputVal}
        onChange={(e) => setInputVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            addTag(inputVal)
          }
        }}
        onBlur={() => { if (inputVal.trim()) addTag(inputVal) }}
        placeholder="输入后回车"
        className="min-w-[4rem] flex-1 bg-transparent text-[10px] text-[#18181B] outline-none placeholder:text-[#A1A1AA]"
      />
    </div>
  )
}

/* ═══════════════ Filter Row Editor ═══════════════ */

function FilterRowEditor({
  row,
  index,
  onUpdate,
  onRemove,
  levelOptions,
  fieldOptions,
  fieldDefs,
}: {
  row: FilterRow
  index: number
  onUpdate: (index: number, updated: FilterRow) => void
  onRemove: (index: number) => void
  levelOptions: { value: string; label: string }[]
  fieldOptions: string[]
  fieldDefs?: FieldDefinition[]
}) {
  const hasFieldOptions = fieldOptions.length > 0
  const currentFieldDef = fieldDefs?.find((d) => d.name === row.field)
  const fieldType = currentFieldDef?.type
  const operators = getOperatorsForType(fieldType)
  const normalisedOp = normaliseOp(row.op)

  const handleFieldChange = (field: string) => {
    const nextDef = fieldDefs?.find((d) => d.name === field)
    const nextOps = getOperatorsForType(nextDef?.type)
    onUpdate(index, {
      ...row,
      field,
      op: nextOps[0]?.value ?? 'eq',
      value: '',
    })
  }

  const renderValueInput = () => {
    if (fieldType === 'enum' && currentFieldDef?.values?.length) {
      return (
        <EnumValueSelect
          value={row.value}
          options={currentFieldDef.values}
          multi={normalisedOp === 'in'}
          onChange={(v) => onUpdate(index, { ...row, value: v })}
        />
      )
    }
    if (fieldType === 'boolean') {
      return (
        <BooleanValueSelect
          value={row.value}
          onChange={(v) => onUpdate(index, { ...row, value: v })}
        />
      )
    }
    if (fieldType === 'integer' || fieldType === 'float') {
      return (
        <input
          type="number"
          value={row.value}
          onChange={(e) => onUpdate(index, { ...row, value: e.target.value })}
          step={fieldType === 'float' ? '0.01' : '1'}
          placeholder="值"
          className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] px-2 text-xs text-[#18181B] outline-none placeholder:text-[#A1A1AA]"
        />
      )
    }
    if (fieldType === 'date') {
      return (
        <input
          type="date"
          value={row.value}
          onChange={(e) => onUpdate(index, { ...row, value: e.target.value })}
          className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] px-2 text-xs text-[#18181B] outline-none"
        />
      )
    }
    if (fieldType === 'keyword[]' || fieldType === 'integer[]') {
      return (
        <TagValueInput
          value={row.value}
          suggestions={currentFieldDef?.values}
          onChange={(v) => onUpdate(index, { ...row, value: v })}
        />
      )
    }
    return (
      <input
        type="text"
        value={row.value}
        onChange={(e) => onUpdate(index, { ...row, value: e.target.value })}
        placeholder="值"
        className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] px-2 text-xs text-[#18181B] outline-none placeholder:text-[#A1A1AA]"
      />
    )
  }

  return (
    <div className="flex min-h-[48px] items-center gap-2 border-b border-[#E4E4E7] px-4 last:border-b-0">
      <select
        value={row.level}
        onChange={(e) => onUpdate(index, { ...row, level: e.target.value, field: '', value: '' })}
        className="h-8 w-[130px] shrink-0 rounded border border-[#E4E4E7] bg-white px-2 text-xs text-[#18181B] outline-none"
      >
        {levelOptions.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {hasFieldOptions ? (
        <select
          value={row.field}
          onChange={(e) => handleFieldChange(e.target.value)}
          className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] bg-white px-2 text-xs text-[#18181B] outline-none"
        >
          <option value="">选择字段</option>
          {fieldOptions.map((f) => {
            const def = fieldDefs?.find((d) => d.name === f)
            const typeLabel = def?.type ? ` (${def.type})` : ''
            return (
              <option key={f} value={f}>{f}{typeLabel}</option>
            )
          })}
        </select>
      ) : (
        <input
          type="text"
          value={row.field}
          onChange={(e) => onUpdate(index, { ...row, field: e.target.value })}
          placeholder="字段名"
          className="h-8 min-w-0 flex-1 rounded border border-[#E4E4E7] px-2 text-xs text-[#18181B] outline-none placeholder:text-[#A1A1AA]"
        />
      )}
      <select
        value={normalisedOp}
        onChange={(e) => onUpdate(index, { ...row, op: e.target.value })}
        className="h-8 w-[110px] shrink-0 rounded border border-[#E4E4E7] bg-white px-2 text-xs text-[#18181B] outline-none"
      >
        {operators.map((op) => (
          <option key={op.value} value={op.value}>{op.label}</option>
        ))}
      </select>
      {renderValueInput()}
      <button
        onClick={() => onRemove(index)}
        className="shrink-0 rounded p-1 text-[#A1A1AA] hover:bg-[#F4F4F5] hover:text-[#18181B]"
      >
        <IconX size={14} />
      </button>
    </div>
  )
}

/* ═══════════════ Filter Builder ═══════════════ */

function FilterBuilder({
  filters,
  onChange,
  levelOptions,
  fieldOptionsForLevel,
  fieldDefsForLevel,
}: {
  filters: FilterRow[]
  onChange: (filters: FilterRow[]) => void
  levelOptions: { value: string; label: string }[]
  fieldOptionsForLevel?: (level: string) => string[]
  fieldDefsForLevel?: (level: string) => FieldDefinition[]
}) {
  const handleUpdate = (index: number, updated: FilterRow) => {
    const next = [...filters]
    next[index] = updated
    onChange(next)
  }

  const handleRemove = (index: number) => {
    onChange(filters.filter((_, i) => i !== index))
  }

  const handleAdd = () => {
    onChange([
      ...filters,
      { level: levelOptions[0].value, field: '', op: 'eq', value: '' },
    ])
  }

  return (
    <div>
      {filters.length > 0 && (
        <div className="rounded-lg border border-[#E4E4E7]">
          {filters.map((row, i) => (
            <FilterRowEditor
              key={i}
              row={row}
              index={i}
              onUpdate={handleUpdate}
              onRemove={handleRemove}
              levelOptions={levelOptions}
              fieldOptions={fieldOptionsForLevel ? fieldOptionsForLevel(row.level) : []}
              fieldDefs={fieldDefsForLevel ? fieldDefsForLevel(row.level) : undefined}
            />
          ))}
        </div>
      )}
      <button
        onClick={handleAdd}
        className="mt-2 flex items-center gap-1 text-[13px] font-medium text-[#18181B] hover:text-[#09090B]"
      >
        <IconPlus size={14} />
        添加条件
      </button>
    </div>
  )
}

/* ═══════════════ Meta Field Tags ═══════════════ */

const META_TAG_STYLES: Record<MetaFieldCategory, { bg: string; border: string }> = {
  doc_meta: { bg: 'bg-[#EFF6FF]', border: 'border-[#BFDBFE]' },
  slice_meta: { bg: 'bg-[#F0FDF4]', border: 'border-[#BBF7D0]' },
  extra: { bg: 'bg-[#FFF7ED]', border: 'border-[#FED7AA]' },
}

const META_TAG_LABELS: Record<MetaFieldCategory, string> = {
  doc_meta: 'doc',
  slice_meta: 'slice',
  extra: 'extra',
}

// System built-in fields that always belong to 'extra' category
const EXTRA_ONLY_FIELDS = new Set(['toc_ancestors', 'toc_path', 'source_url'])

/** Selectable extra response fields (same set as EXTRA_ONLY_FIELDS, stable order for UI) */
const EXTRA_FIELD_OPTIONS: string[] = ['toc_path', 'source_url', 'toc_ancestors']

function fieldOptionsForMetaCategory(
  category: MetaFieldCategory,
  metaFields: { doc_meta: string[]; slice_meta: string[] } | null | undefined,
): string[] {
  if (!metaFields) return []
  if (category === 'doc_meta') return metaFields.doc_meta
  if (category === 'slice_meta') return metaFields.slice_meta
  return []
}

function fieldDefsForMetaCategory(
  category: MetaFieldCategory,
  metaSchema: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null | undefined,
): FieldDefinition[] {
  if (!metaSchema) return []
  if (category === 'doc_meta') return metaSchema.doc_meta
  if (category === 'slice_meta') return metaSchema.slice_meta
  return []
}

function LockedTag({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded bg-[#F4F4F5] px-2 py-1 text-[13px] text-[#71717A]">
      <IconLock size={12} />
      {name}
    </span>
  )
}

function MetaTag({
  name,
  category,
  onRemove,
}: {
  name: string
  category: MetaFieldCategory
  onRemove: () => void
}) {
  const style = META_TAG_STYLES[category]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border ${style.bg} ${style.border} px-2 py-1 text-[13px] text-[#18181B]`}
    >
      <span className="text-[11px] text-[#A1A1AA]">{META_TAG_LABELS[category]}</span>
      {name}
      <button
        onClick={onRemove}
        className="rounded-sm p-0.5 text-[#A1A1AA] hover:text-[#18181B]"
      >
        <IconX size={12} />
      </button>
    </span>
  )
}

function MetaFieldEditor({
  fields,
  onChange,
  lockedFields,
  availableCategories,
  metaFields,
  metaSchema,
}: {
  fields: MetaField[]
  onChange: (fields: MetaField[]) => void
  lockedFields: string[]
  availableCategories: { value: MetaFieldCategory; label: string }[]
  metaFields?: { doc_meta: string[]; slice_meta: string[] } | null
  metaSchema?: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null
}) {
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [newCategory, setNewCategory] = useState<MetaFieldCategory>(
    availableCategories[0].value,
  )

  useEffect(() => {
    setNewName('')
  }, [newCategory])

  const takenInCategory = useMemo(
    () =>
      new Set(
        fields
          .filter((f) => f.category === newCategory)
          .map((f) => f.name),
      ),
    [fields, newCategory],
  )

  const selectableFieldNames = useMemo(() => {
    if (newCategory === 'extra') {
      return EXTRA_FIELD_OPTIONS.filter((n) => !takenInCategory.has(n))
    }
    if (newCategory === 'doc_meta' || newCategory === 'slice_meta') {
      return fieldOptionsForMetaCategory(newCategory, metaFields).filter(
        (n) => !takenInCategory.has(n),
      )
    }
    return []
  }, [newCategory, metaFields, takenInCategory])

  const useFieldSelect = selectableFieldNames.length > 0
  const fieldDefs = useMemo(
    () => fieldDefsForMetaCategory(newCategory, metaSchema),
    [newCategory, metaSchema],
  )

  const handleAdd = () => {
    const trimmed = newName.trim()
    if (!trimmed) return
    const effectiveCategory = EXTRA_ONLY_FIELDS.has(trimmed) ? 'extra' : newCategory
    if (fields.some((f) => f.name === trimmed && f.category === effectiveCategory)) return
    onChange([...fields, { name: trimmed, category: effectiveCategory }])
    setNewName('')
    setAdding(false)
  }

  const handleRemove = (index: number) => {
    onChange(fields.filter((_, i) => i !== index))
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {lockedFields.map((n) => (
        <LockedTag key={n} name={n} />
      ))}
      {fields.map((field, i) => (
        <MetaTag
          key={`${field.category}-${field.name}`}
          name={field.name}
          category={field.category}
          onRemove={() => handleRemove(i)}
        />
      ))}
      {adding ? (
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1">
          {availableCategories.length > 1 && (
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value as MetaFieldCategory)}
              className="h-7 shrink-0 rounded border border-[#E4E4E7] bg-white px-1 text-xs outline-none"
            >
              {availableCategories.map((cat) => (
                <option key={cat.value} value={cat.value}>{cat.label}</option>
              ))}
            </select>
          )}
          {useFieldSelect ? (
            <select
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd()
                if (e.key === 'Escape') { setAdding(false); setNewName('') }
              }}
              className="h-7 min-w-[120px] max-w-[min(100%,280px)] flex-1 rounded border border-[#E4E4E7] bg-white px-2 text-xs text-[#18181B] outline-none focus:border-[#18181B]"
            >
              <option value="">选择字段</option>
              {selectableFieldNames.map((f) => {
                if (newCategory === 'extra') {
                  return (
                    <option key={f} value={f}>{f}</option>
                  )
                }
                const def = fieldDefs.find((d) => d.name === f)
                const typeLabel = def?.type ? ` (${def.type})` : ''
                return (
                  <option key={f} value={f}>{f}{typeLabel}</option>
                )
              })}
            </select>
          ) : (
            <input
              autoFocus
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd()
                if (e.key === 'Escape') { setAdding(false); setNewName('') }
              }}
              placeholder="字段名"
              className="h-7 w-32 min-w-[6rem] max-w-[200px] flex-1 rounded border border-[#E4E4E7] px-2 text-xs outline-none focus:border-[#18181B]"
            />
          )}
          <button
            type="button"
            onClick={handleAdd}
            disabled={!newName.trim()}
            className="h-7 shrink-0 rounded bg-[#18181B] px-2 text-xs text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            确认
          </button>
          <button
            type="button"
            onClick={() => { setAdding(false); setNewName('') }}
            className="h-7 shrink-0 rounded px-2 text-xs text-[#71717A] hover:text-[#18181B]"
          >
            取消
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setNewName('')
            setNewCategory(availableCategories[0].value)
            setAdding(true)
          }}
          className="flex items-center gap-1 text-[13px] font-medium text-[#18181B] hover:text-[#09090B]"
        >
          <IconPlus size={14} />
          添加字段
        </button>
      )}
    </div>
  )
}

// Convert MetaField array into the API config shape
function metaFieldsToConfig(
  fields: MetaField[],
  categories: MetaFieldCategory[],
): Record<string, string[]> {
  const result: Record<string, string[]> = {}
  for (const cat of categories) {
    result[cat] = fields.filter((f) => f.category === cat).map((f) => f.name)
  }
  return result
}

// Parse API config shape back into MetaField array
function configToMetaFields(
  configObj: Record<string, unknown>,
  categories: MetaFieldCategory[],
): MetaField[] {
  const fields: MetaField[] = []
  for (const cat of categories) {
    for (const name of cfgStrArr(configObj, cat)) {
      // Auto-correct system fields that were mis-categorized
      const effectiveCategory = EXTRA_ONLY_FIELDS.has(name) ? 'extra' : cat
      // Avoid duplicates when correcting category
      if (fields.some((f) => f.name === name && f.category === effectiveCategory)) continue
      fields.push({ name, category: effectiveCategory })
    }
  }
  return fields
}

/* ═══════════════ Section 1: Basic Info ═══════════════ */

type FilterDimensions = {
  doc_ids: boolean
  doc_meta: boolean
  slice_meta: boolean
}

const FILTER_DIMENSION_LABELS: { key: keyof FilterDimensions; label: string }[] = [
  { key: 'doc_ids', label: '允许 LLM 使用文档 ID 筛选（doc_ids）' },
  { key: 'doc_meta', label: '允许 LLM 使用文档元数据筛选（doc_meta）' },
  { key: 'slice_meta', label: '允许 LLM 使用切片元数据筛选（slice_meta）' },
]

const META_FILTER_ITEM_SCHEMA = {
  type: 'object',
  properties: {
    field: { type: 'string' },
    op: {
      type: 'string',
      enum: ['eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in'],
      description: 'OData comparison operator; use ge/le (not gte/lte). Use in with value as array.',
    },
    value: { description: 'Scalar, or array when op is in' },
  },
  required: ['field', 'op', 'value'],
}

const FILTER_DIMENSION_SCHEMAS: Record<string, object> = {
  doc_ids: {
    type: 'array',
    items: { type: 'string' },
    description: 'Limit search to specific document IDs',
  },
  doc_meta: {
    type: 'array',
    items: META_FILTER_ITEM_SCHEMA,
    description: 'Document-level metadata filters. Array of conditions combined with implicit AND.',
  },
  slice_meta: {
    type: 'array',
    items: META_FILTER_ITEM_SCHEMA,
    description: 'Slice-level metadata filters. Array of conditions combined with implicit AND.',
  },
}

const FILTER_SINGLE_TOOL_CALL_HINT =
  'CRITICAL — one search tool call per user request: numeric or date ranges (e.g. 3.6–4.4) must ' +
  'appear in the SAME filter: use slice_meta/doc_meta as an array of two leaf nodes (implicit AND). ' +
  'Never invoke the tool twice for lower bound and upper bound alone.'

function buildSearchParametersPreview(dims: FilterDimensions): Record<string, unknown> {
  const schema: Record<string, unknown> = {
    type: 'object',
    properties: {
      brief: { type: 'string', description: 'One-line summary for session log display; distinct from query/filter content' },
      query: { type: 'string', description: 'Search keywords or natural language query' },
    },
    required: ['query', 'brief'],
  }

  const filterProps: Record<string, object> = {}
  for (const [k, v] of Object.entries(FILTER_DIMENSION_SCHEMAS)) {
    if (dims[k as keyof FilterDimensions]) filterProps[k] = v
  }
  if (Object.keys(filterProps).length > 0) {
    ;(schema.properties as Record<string, unknown>).filter = {
      type: 'object',
      description:
        'Structured filters. Multiple conditions in doc_meta/slice_meta arrays ' +
        'are combined with implicit AND. ' +
        FILTER_SINGLE_TOOL_CALL_HINT,
      properties: filterProps,
    }
  }
  return schema
}

function BasicInfoSection({
  name,
  description,
  parametersSchema,
  isSearch,
  filterDimensions,
  onFilterDimensionsChange,
  onNameChange,
  onDescriptionChange,
}: {
  name: string
  description: string
  parametersSchema: Record<string, unknown> | null
  isSearch?: boolean
  filterDimensions?: FilterDimensions
  onFilterDimensionsChange?: (dims: FilterDimensions) => void
  onNameChange: (v: string) => void
  onDescriptionChange: (v: string) => void
}) {
  const previewSchema = useMemo(() => {
    if (isSearch && filterDimensions) return buildSearchParametersPreview(filterDimensions)
    return parametersSchema
  }, [isSearch, filterDimensions, parametersSchema])

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconFileText size={20} />} title="基础信息" />
      <div>
        <FieldLabel>name</FieldLabel>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="tool_name"
          maxLength={128}
          className={INPUT_CLS}
        />
        <FieldHint>工具名称，供 LLM function call 时指定</FieldHint>
      </div>
      <div>
        <FieldLabel>description</FieldLabel>
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder="工具描述..."
          rows={3}
          className={`${INPUT_CLS} resize-y`}
        />
        <FieldHint>说明用途与使用场景，供 LLM 选择工具时参考</FieldHint>
      </div>

      {isSearch && filterDimensions && onFilterDimensionsChange && (
        <div className="space-y-3">
          <FieldLabel>LLM 可调用的 filter 维度</FieldLabel>
          <DescriptionText>
            开启后，自动生成的 parameters 会在 filter 中包含对应字段；关闭后 LLM 无法在 function call 中传入该维度。固定筛选和工具输入变量不受此开关影响。
          </DescriptionText>
          <div className="flex flex-col gap-3">
            {FILTER_DIMENSION_LABELS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-3">
                <Switch
                  checked={filterDimensions[key]}
                  onChange={(checked) =>
                    onFilterDimensionsChange({ ...filterDimensions, [key]: checked })
                  }
                />
                <span className="text-sm text-[#18181B]">{label}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div>
        <FieldLabel>parameters (只读，自动生成)</FieldLabel>
        <div className="min-h-[120px] rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] p-4">
          <pre className="whitespace-pre-wrap font-mono text-xs text-[#18181B]">
            {previewSchema ? JSON.stringify(previewSchema, null, 2) : '暂无'}
          </pre>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════ Section 2: KB Binding ═══════════════ */

function KBBindingSection({
  config,
  onConfigChange,
  knowledgeBases,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
  knowledgeBases: { id: number; name: string }[]
}) {
  const currentId = (() => {
    const v = config.knowledge_base_id
    if (typeof v === 'number') return v
    if (typeof v === 'string' && v) return Number(v) || 0
    return 0
  })()

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconDatabase size={20} />} title="知识库绑定" />
      <div>
        <FieldLabel>知识库</FieldLabel>
        <div className="relative">
          <select
            value={currentId}
            onChange={(e) => {
              const val = Number(e.target.value)
              onConfigChange({ ...config, knowledge_base_id: val || undefined })
            }}
            className={`${INPUT_CLS} appearance-none pr-9`}
          >
            <option value={0}>请选择知识库</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </select>
          <IconChevronDown
            size={16}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]"
          />
        </div>
        {currentId > 0 && (
          <FieldHint>ID: {currentId}</FieldHint>
        )}
      </div>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] font-medium text-[#18181B]">启用 ID引用</div>
          <div className="mt-0.5 text-xs text-[#A1A1AA]">
            启用后搜索结果落库并生成 response_id
          </div>
        </div>
        <Switch
          checked={cfgBool(config, 'enable_placeholder', true)}
          onChange={(v) => onConfigChange({ ...config, enable_placeholder: v })}
        />
      </div>
    </section>
  )
}

/* ═══════════════ Section 3: Fixed Filters ═══════════════ */

function FixedFiltersSection({
  config,
  onConfigChange,
  docMetaOnly,
  metaFields,
  metaSchema,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
  docMetaOnly?: boolean
  metaFields?: { doc_meta: string[]; slice_meta: string[] } | null
  metaSchema?: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null
}) {
  const levelOptions = docMetaOnly ? DOC_ONLY_LEVEL_OPTIONS : SEARCH_LEVEL_OPTIONS

  const descText = docMetaOnly
    ? '搜索时始终生效的结构化筛选，不暴露给 LLM。仅支持 doc-meta 层级筛选。'
    : '搜索时始终生效的结构化筛选，不暴露给 LLM。系统根据知识库 Schema 自动加载可选字段。'

  const fieldOptionsForLevel = (level: string): string[] => {
    if (!metaFields) return []
    if (level === 'doc-meta') return metaFields.doc_meta
    if (level === 'slice-meta') return metaFields.slice_meta
    return []
  }

  const fieldDefsForLevel = (level: string): FieldDefinition[] => {
    if (!metaSchema) return []
    if (level === 'doc-meta') return metaSchema.doc_meta
    if (level === 'slice-meta') return metaSchema.slice_meta
    return []
  }

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconAdjustmentsHorizontal size={20} />} title="固定筛选条件" />
      <DescriptionText>{descText}</DescriptionText>
      <FilterBuilder
        filters={cfgFilterRows(config, 'fixed_filters')}
        onChange={(filters) => onConfigChange({ ...config, fixed_filters: filters })}
        levelOptions={levelOptions}
        fieldOptionsForLevel={fieldOptionsForLevel}
        fieldDefsForLevel={fieldDefsForLevel}
      />
    </section>
  )
}

/* ═══════════════ Section 4: Tool Input Variable ═══════════════ */

function ToolInputVariableSection({
  toolName,
  isDocQuery,
}: {
  toolName: string
  isDocQuery?: boolean
}) {
  const slotName = `tool_${toolName}_input`
  const descText = isDocQuery
    ? '每个工具自动拥有输入变量槽位，无需配置变量名。其他组件向槽位传入标准 filter 结构（doc_meta / doc_ids），系统自动合并，无需映射。对 LLM 透明。'
    : '每个搜索工具自动拥有输入变量槽位，无需配置变量名。其他组件向槽位传入标准 filter 结构（doc_meta / slice_meta / doc_ids），系统自动合并，无需映射。对 LLM 透明。'

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconPlug size={20} />} title="工具输入变量" />
      <DescriptionText>{descText}</DescriptionText>
      <div className="rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] px-4 py-3">
        <span className="font-mono text-sm text-[#18181B]">{slotName}</span>
      </div>
    </section>
  )
}

/* ═══════════════ Section 5 (Search): Search Config ═══════════════ */

function SearchConfigSection({
  config,
  onConfigChange,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
}) {
  const searchMode = cfgStr(config, 'search_mode', 'hybrid')
  const weights = cfgRecord(config, 'search_weights')
  const reranker = cfgRecord(config, 'reranker')
  const pagination = cfgRecord(config, 'pagination')

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconSearch size={20} />} title="检索配置" />

      {/* Search mode radio group */}
      <div>
        <FieldLabel>检索模式</FieldLabel>
        <div className="flex gap-4">
          {SEARCH_MODE_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm text-[#18181B]">
              <input
                type="radio"
                name="search_mode"
                value={opt.value}
                checked={searchMode === opt.value}
                onChange={() => onConfigChange({ ...config, search_mode: opt.value })}
                className="h-4 w-4 accent-[#18181B]"
              />
              {opt.label}
            </label>
          ))}
        </div>
      </div>

      {/* Weights — visible only when hybrid */}
      {searchMode === 'hybrid' && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <FieldLabel>BM25 权重</FieldLabel>
            <input
              type="number"
              value={cfgNum(weights, 'bm25', 0.5)}
              onChange={(e) =>
                onConfigChange(setNested(config, ['search_weights', 'bm25'], parseFloat(e.target.value) || 0))
              }
              step={0.1}
              min={0}
              max={1}
              className={INPUT_CLS}
            />
          </div>
          <div>
            <FieldLabel>向量权重</FieldLabel>
            <input
              type="number"
              value={cfgNum(weights, 'vector', 0.5)}
              onChange={(e) =>
                onConfigChange(setNested(config, ['search_weights', 'vector'], parseFloat(e.target.value) || 0))
              }
              step={0.1}
              min={0}
              max={1}
              className={INPUT_CLS}
            />
          </div>
        </div>
      )}

      {/* Reranker */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-[13px] font-medium text-[#18181B]">重排序</div>
          <div className="flex items-center gap-3">
            <Switch
              checked={cfgBool(reranker, 'enabled', false)}
              onChange={(v) => onConfigChange(setNested(config, ['reranker', 'enabled'], v))}
            />
          </div>
        </div>
        {cfgBool(reranker, 'enabled', false) && (
          <div className="pl-0 space-y-3">
            <div>
              <FieldLabel>Reranker Top N</FieldLabel>
              <input
                type="number"
                value={cfgNum(reranker, 'top_n', 5)}
                onChange={(e) =>
                  onConfigChange(setNested(config, ['reranker', 'top_n'], parseInt(e.target.value) || 5))
                }
                min={1}
                max={100}
                className={INPUT_CLS}
              />
            </div>
            <div>
              <FieldLabel>最小评分阈值</FieldLabel>
              <input
                type="number"
                value={reranker['min_score'] != null ? String(reranker['min_score']) : ''}
                onChange={(e) => {
                  const raw = e.target.value
                  if (raw === '') {
                    onConfigChange(setNested(config, ['reranker', 'min_score'], null))
                  } else {
                    const v = parseFloat(raw)
                    if (!isNaN(v) && v >= 0 && v <= 1) {
                      onConfigChange(setNested(config, ['reranker', 'min_score'], Math.round(v * 100) / 100))
                    }
                  }
                }}
                step={0.01}
                min={0}
                max={1}
                placeholder="不限制"
                className={INPUT_CLS}
              />
              <p className="mt-1 text-xs text-[#71717A]">仅保留 reranker 评分 ≥ 该值的结果，留空表示不限制（0.00～1.00）</p>
            </div>
          </div>
        )}
      </div>

      {/* Pagination limit */}
      <div>
        <FieldLabel>返回条数</FieldLabel>
        <input
          type="number"
          value={cfgNum(pagination, 'limit', 10)}
          onChange={(e) =>
            onConfigChange(setNested(config, ['pagination', 'limit'], parseInt(e.target.value) || 10))
          }
          min={1}
          max={100}
          className={INPUT_CLS}
        />
      </div>
    </section>
  )
}

/* ═══════════════ Section 6 (Search): Category Search ═══════════════ */

function CategorySearchSection({
  config,
  onConfigChange,
  metaFields,
  metaSchema,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
  metaFields?: { doc_meta: string[]; slice_meta: string[] } | null
  metaSchema?: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null
}) {
  const catSearch = cfgRecord(config, 'category_search')
  const enabled = cfgBool(catSearch, 'enabled', false)
  const groups = cfgCategoryGroups(catSearch, 'groups')

  const updateCatSearch = (key: string, val: unknown) => {
    onConfigChange(setNested(config, ['category_search', key], val))
  }

  const updateGroup = (index: number, updated: CategoryGroup) => {
    const next = [...groups]
    next[index] = updated
    updateCatSearch('groups', next)
  }

  const removeGroup = (index: number) => {
    updateCatSearch('groups', groups.filter((_, i) => i !== index))
  }

  const addGroup = () => {
    updateCatSearch('groups', [...groups, { name: '', filters: [] }])
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader icon={<IconStack2 size={20} />} title="分类搜索" />
        <Switch
          checked={enabled}
          onChange={(v) => updateCatSearch('enabled', v)}
        />
      </div>
      <DescriptionText>
        启用后按分类组独立召回，每组召回数与重排序参数复用检索配置。与普通搜索并行执行。
      </DescriptionText>

      {enabled && (
        <div className="space-y-4">
          {/* Category groups */}
          <div>
            <FieldLabel>分类组</FieldLabel>
            <div className="space-y-3">
              {groups.map((group, gi) => (
                <div key={gi} className="rounded-lg border border-[#E4E4E7] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <input
                      type="text"
                      value={group.name}
                      onChange={(e) => updateGroup(gi, { ...group, name: e.target.value })}
                      placeholder="分类组名称"
                      className="flex-1 rounded-lg border border-[#E4E4E7] px-3 py-1.5 text-sm outline-none placeholder:text-[#A1A1AA] focus:border-[#18181B]"
                    />
                    <button
                      onClick={() => removeGroup(gi)}
                      className="rounded p-1 text-[#A1A1AA] hover:bg-[#F4F4F5] hover:text-[#18181B]"
                    >
                      <IconX size={16} />
                    </button>
                  </div>
                  <FilterBuilder
                    filters={group.filters}
                    onChange={(filters) => updateGroup(gi, { ...group, filters })}
                    levelOptions={SEARCH_LEVEL_OPTIONS}
                    fieldOptionsForLevel={(level) => {
                      if (!metaFields) return []
                      if (level === 'doc-meta') return metaFields.doc_meta
                      if (level === 'slice-meta') return metaFields.slice_meta
                      return []
                    }}
                    fieldDefsForLevel={(level) => {
                      if (!metaSchema) return []
                      if (level === 'doc-meta') return metaSchema.doc_meta
                      if (level === 'slice-meta') return metaSchema.slice_meta
                      return []
                    }}
                  />
                </div>
              ))}
            </div>
            <button
              onClick={addGroup}
              className="mt-2 flex items-center gap-1 text-[13px] font-medium text-[#18181B] hover:text-[#09090B]"
            >
              <IconPlus size={14} />
              添加分类组
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

/* ═══════════════ Section 7 (Search): Response Meta ═══════════════ */

function SearchResponseMetaSection({
  config,
  onConfigChange,
  metaFields,
  metaSchema,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
  metaFields?: { doc_meta: string[]; slice_meta: string[] } | null
  metaSchema?: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null
}) {
  const categories: MetaFieldCategory[] = ['doc_meta', 'slice_meta', 'extra']
  const metaObj = cfgRecord(config, 'response_meta_fields')
  const fields = configToMetaFields(metaObj, categories)

  const handleChange = (updated: MetaField[]) => {
    onConfigChange({
      ...config,
      response_meta_fields: metaFieldsToConfig(updated, categories),
    })
  }

  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconFileExport size={20} />} title="响应元数据" />
      <DescriptionText>
        配置搜索结果返回给 LLM 时，每条切片除内容外还携带哪些元数据字段。doc_id 和 slice_id
        始终返回。绑定知识库时 doc-meta / slice-meta 从 Schema
        下拉选择；无 Schema 或未列出的字段可手输。extra 为系统内置项。勾选越多 token 消耗越大。
      </DescriptionText>
      <MetaFieldEditor
        fields={fields}
        onChange={handleChange}
        lockedFields={['doc_id', 'slice_id']}
        availableCategories={[
          { value: 'doc_meta', label: 'doc-meta' },
          { value: 'slice_meta', label: 'slice-meta' },
          { value: 'extra', label: 'extra' },
        ]}
        metaFields={metaFields}
        metaSchema={metaSchema}
      />
    </section>
  )
}

/* ═══════════════ Section 5 (Doc Query): Search Config ═══════════════ */

function DocQuerySearchConfigSection({
  config,
  onConfigChange,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
}) {
  return (
    <section className="space-y-4">
      <SectionHeader icon={<IconSettings size={20} />} title="检索配置" />
      <DescriptionText>
        搜索模式与仅筛选模式分别拥有独立的返回条数上限。搜索返回条数在有 query
        时生效，筛选返回条数在仅筛选时生效。
      </DescriptionText>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <FieldLabel>搜索返回条数</FieldLabel>
          <input
            type="number"
            value={cfgNum(config, 'limit', 10)}
            onChange={(e) =>
              onConfigChange({ ...config, limit: parseInt(e.target.value) || 10 })
            }
            min={1}
            max={200}
            className={INPUT_CLS}
          />
        </div>
        <div>
          <FieldLabel>筛选返回条数</FieldLabel>
          <input
            type="number"
            value={cfgNum(config, 'filter_limit', 50)}
            onChange={(e) =>
              onConfigChange({ ...config, filter_limit: parseInt(e.target.value) || 50 })
            }
            min={1}
            max={500}
            className={INPUT_CLS}
          />
        </div>
      </div>
    </section>
  )
}

/* ═══════════════ Section 6 (Doc Query): Response Meta ═══════════════ */

function DocQueryResponseMetaSection({
  config,
  onConfigChange,
  metaFields,
  metaSchema,
}: {
  config: Record<string, unknown>
  onConfigChange: (c: Record<string, unknown>) => void
  metaFields?: { doc_meta: string[]; slice_meta: string[] } | null
  metaSchema?: { doc_meta: FieldDefinition[]; slice_meta: FieldDefinition[] } | null
}) {
  const categories: MetaFieldCategory[] = ['doc_meta', 'extra']
  const availCats: { value: MetaFieldCategory; label: string }[] = [
    { value: 'doc_meta', label: 'doc-meta' },
    { value: 'extra', label: 'extra' },
  ]

  // Search response meta fields
  const searchMetaObj = cfgRecord(config, 'search_response_meta_fields')
  const searchFields = configToMetaFields(searchMetaObj, categories)

  const handleSearchChange = (updated: MetaField[]) => {
    onConfigChange({
      ...config,
      search_response_meta_fields: metaFieldsToConfig(updated, categories),
    })
  }

  // Filter-only response meta fields
  const filterMetaObj = cfgRecord(config, 'filter_response_meta_fields')
  const filterFields = configToMetaFields(filterMetaObj, categories)

  const handleFilterChange = (updated: MetaField[]) => {
    onConfigChange({
      ...config,
      filter_response_meta_fields: metaFieldsToConfig(updated, categories),
    })
  }

  return (
    <section className="space-y-6">
      <SectionHeader icon={<IconFileExport size={20} />} title="响应元数据" />

      {/* Search response meta */}
      <div className="space-y-3">
        <h4 className="text-[14px] font-medium text-[#18181B]">搜索响应元数据</h4>
        <MetaFieldEditor
          fields={searchFields}
          onChange={handleSearchChange}
          lockedFields={['doc_id']}
          availableCategories={availCats}
          metaFields={metaFields}
          metaSchema={metaSchema}
        />
      </div>

      <hr className="border-t border-[#E4E4E7]" />

      {/* Filter-only response meta */}
      <div className="space-y-3">
        <h4 className="text-[14px] font-medium text-[#18181B]">仅筛选响应元数据</h4>
        <MetaFieldEditor
          fields={filterFields}
          onChange={handleFilterChange}
          lockedFields={['doc_id']}
          availableCategories={availCats}
          metaFields={metaFields}
          metaSchema={metaSchema}
        />
      </div>
    </section>
  )
}

/* ═══════════════ Main Page Component ═══════════════ */

export default function ToolDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  const user = useAuthStore((s) => s.user)
  const tenantId = user?.tenant_id ?? ''

  const agentId = Number(params.id)
  const toolId = Number(params.toolId)

  const { data: tool, isLoading } = useAgentTool(agentId, toolId)
  const updateMutation = useUpdateAgentTool(agentId)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const [filterDimensions, setFilterDimensions] = useState<FilterDimensions>({
    doc_ids: true, doc_meta: true, slice_meta: true,
  })
  const [initialized, setInitialized] = useState(false)

  const selectedKbId = (() => {
    const v = config.knowledge_base_id
    if (typeof v === 'number') return v
    if (typeof v === 'string' && v) return Number(v) || null
    return null
  })()

  const { data: kbList } = useKnowledgeBases(tenantId, { per_page: 20 })
  const { data: metaFields } = useKBMetaFields(selectedKbId)
  const { data: metaSchema } = useKBMetaSchema(selectedKbId)

  // Deep clone config on init to avoid mutating cached query data
  useEffect(() => {
    if (tool && !initialized) {
      setName(tool.name)
      setDescription(tool.description ?? '')
      const cloned = JSON.parse(JSON.stringify(tool.config ?? {}))
      setConfig(cloned)
      if (tool.tool_type === 'search' && cloned.filter_dimensions) {
        const fd = cloned.filter_dimensions as Record<string, unknown>
        setFilterDimensions({
          doc_ids: fd.doc_ids !== false,
          doc_meta: fd.doc_meta !== false,
          slice_meta: fd.slice_meta !== false,
        })
      }
      setInitialized(true)
    }
  }, [tool, initialized])

  const handleFilterDimensionsChange = useCallback((dims: FilterDimensions) => {
    setFilterDimensions(dims)
    setConfig(prev => ({ ...prev, filter_dimensions: dims }))
  }, [])

  const isDirty = useMemo(() => {
    if (!tool || !initialized) return false
    return (
      name !== tool.name ||
      description !== (tool.description ?? '') ||
      JSON.stringify(config) !== JSON.stringify(tool.config ?? {})
    )
  }, [tool, name, description, config, initialized])

  const handleSave = useCallback(async () => {
    try {
      await updateMutation.mutateAsync({
        toolId,
        data: {
          name: name.trim(),
          description: description.trim() || undefined,
          config,
        },
      })
      toast('保存成功', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }, [toolId, name, description, config, updateMutation, toast])

  if (isLoading || !tool) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-[#71717A]">加载中...</p>
      </div>
    )
  }

  const pageTitle = PAGE_TITLE_MAP[tool.tool_type] ?? '工具配置'
  const isSearch = tool.tool_type === 'search'
  const isDocQuery = tool.tool_type === 'doc_query'
  const isPythonCode = tool.tool_type === 'python_code'
  const showPlaceholder = !isSearch && !isDocQuery && !isPythonCode

  return (
    <div className="flex h-full flex-col">
      {/* Sticky top bar */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#E4E4E7] bg-white px-8 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/agent/agents/${agentId}/tools`)}
            className="rounded-md p-1 text-[#71717A] transition-colors hover:bg-[#F4F4F5] hover:text-[#18181B]"
          >
            <IconArrowLeft size={20} />
          </button>
          <h2 className="text-base font-semibold text-[#18181B]">{pageTitle}</h2>
        </div>
        <button
          disabled={!isDirty || updateMutation.isPending}
          onClick={handleSave}
          className="rounded-lg bg-[#18181B] px-5 py-2 text-[14px] font-medium text-white transition-opacity disabled:opacity-50"
        >
          {updateMutation.isPending ? '保存中...' : '保存'}
        </button>
      </div>

      {/* Scrollable content area */}
      <div className="flex-1 overflow-auto">
        <div className="mx-auto flex max-w-[960px] flex-col gap-7 p-8">
          {/* Python code tool placeholder */}
          {isPythonCode && (
            <div className="rounded-lg border border-dashed border-[#E4E4E7] py-12 text-center">
              <p className="text-sm text-[#71717A]">
                Python 代码工具配置将在后续版本中实现
              </p>
            </div>
          )}

          {/* Unsupported tool types (notebook, tool_response_fetch, etc.) */}
          {showPlaceholder && (
            <div className="rounded-lg border border-dashed border-[#E4E4E7] py-12 text-center">
              <p className="text-sm text-[#71717A]">
                该工具类型暂不支持可视化配置
              </p>
            </div>
          )}

          {/* ── Search Tool: 8 sections ── */}
          {isSearch && (
            <>
              <BasicInfoSection
                name={name}
                description={description}
                parametersSchema={tool.parameters_schema}
                isSearch
                filterDimensions={filterDimensions}
                onFilterDimensionsChange={handleFilterDimensionsChange}
                onNameChange={setName}
                onDescriptionChange={setDescription}
              />
              <SectionDivider />
              <KBBindingSection
                config={config}
                onConfigChange={setConfig}
                knowledgeBases={kbList?.items ?? []}
              />
              <SectionDivider />
              <FixedFiltersSection
                config={config}
                onConfigChange={setConfig}
                metaFields={metaFields}
                metaSchema={metaSchema}
              />
              <SectionDivider />
              <ToolInputVariableSection toolName={name} />
              <SectionDivider />
              <SearchConfigSection config={config} onConfigChange={setConfig} />
              <SectionDivider />
              <CategorySearchSection config={config} onConfigChange={setConfig} metaFields={metaFields} metaSchema={metaSchema} />
              <SectionDivider />
              <SearchResponseMetaSection
                config={config}
                onConfigChange={setConfig}
                metaFields={metaFields}
                metaSchema={metaSchema}
              />
            </>
          )}

          {/* ── Doc Query Tool: 6 sections ── */}
          {isDocQuery && (
            <>
              <BasicInfoSection
                name={name}
                description={description}
                parametersSchema={tool.parameters_schema}
                onNameChange={setName}
                onDescriptionChange={setDescription}
              />
              <SectionDivider />
              <KBBindingSection
                config={config}
                onConfigChange={setConfig}
                knowledgeBases={kbList?.items ?? []}
              />
              <SectionDivider />
              <FixedFiltersSection
                config={config}
                onConfigChange={setConfig}
                docMetaOnly
                metaFields={metaFields}
                metaSchema={metaSchema}
              />
              <SectionDivider />
              <ToolInputVariableSection toolName={name} isDocQuery />
              <SectionDivider />
              <DocQuerySearchConfigSection config={config} onConfigChange={setConfig} />
              <SectionDivider />
              <DocQueryResponseMetaSection
                config={config}
                onConfigChange={setConfig}
                metaFields={metaFields}
                metaSchema={metaSchema}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
