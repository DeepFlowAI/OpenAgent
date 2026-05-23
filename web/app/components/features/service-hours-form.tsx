'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useCreateServiceHours,
  useUpdateServiceHours,
} from '@/service/use-service-hours'
import type {
  CreateServiceHoursPayload,
  ServiceHours,
  ServiceHoursDateTimeRange,
  WeeklyServicePeriod,
} from '@/models/service-hours'
import { cn } from '@/utils/classnames'
import { useUnsavedChangesGuard } from '@/utils/use-unsaved-changes'
import {
  IconArrowLeft,
  IconClock,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'

type FormRange = {
  name: string
  start_at: string
  end_at: string
}

type FormState = {
  name: string
  description: string
  timezone: string
  weekly_periods: WeeklyServicePeriod[]
  holidays: FormRange[]
  makeup_days: FormRange[]
}

type ServiceHoursFormProps = {
  mode: 'new' | 'edit'
  serviceHours?: ServiceHours | null
  loading?: boolean
}

const DAYS = [
  { value: 0, label: '周一' },
  { value: 1, label: '周二' },
  { value: 2, label: '周三' },
  { value: 3, label: '周四' },
  { value: 4, label: '周五' },
  { value: 5, label: '周六' },
  { value: 6, label: '周日' },
]

const DEFAULT_TIMEZONE = 'Asia/Shanghai'
const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: '中国标准时间 (Asia/Shanghai)' },
  { value: 'Asia/Hong_Kong', label: '香港时间 (Asia/Hong_Kong)' },
  { value: 'Asia/Singapore', label: '新加坡时间 (Asia/Singapore)' },
  { value: 'Asia/Tokyo', label: '日本时间 (Asia/Tokyo)' },
  { value: 'UTC', label: '协调世界时 (UTC)' },
  { value: 'America/Los_Angeles', label: '太平洋时间 (America/Los_Angeles)' },
  { value: 'America/New_York', label: '美东时间 (America/New_York)' },
  { value: 'Europe/London', label: '英国时间 (Europe/London)' },
  { value: 'Europe/Berlin', label: '中欧时间 (Europe/Berlin)' },
]

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  timezone: DEFAULT_TIMEZONE,
  weekly_periods: [],
  holidays: [],
  makeup_days: [],
}

const TIME_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/

function toDateTimeLocal(value: string | null | undefined): string {
  if (!value) return ''
  return value.slice(0, 16)
}

function formFromServiceHours(item: ServiceHours | null | undefined): FormState {
  if (!item) return EMPTY_FORM
  return {
    name: item.name ?? '',
    description: item.description ?? '',
    timezone: item.timezone ?? DEFAULT_TIMEZONE,
    weekly_periods: item.weekly_periods ?? [],
    holidays: (item.holidays ?? []).map((range) => ({
      name: range.name ?? '',
      start_at: toDateTimeLocal(range.start_at),
      end_at: toDateTimeLocal(range.end_at),
    })),
    makeup_days: (item.makeup_days ?? []).map((range) => ({
      name: range.name ?? '',
      start_at: toDateTimeLocal(range.start_at),
      end_at: toDateTimeLocal(range.end_at),
    })),
  }
}

function minutes(value: string): number {
  const [hour, minute] = value.split(':').map(Number)
  return hour * 60 + minute
}

function normalizeRange(range: FormRange): ServiceHoursDateTimeRange {
  return {
    name: range.name.trim() || null,
    start_at: range.start_at,
    end_at: range.end_at,
  }
}

function buildPayload(form: FormState): CreateServiceHoursPayload {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    timezone: form.timezone,
    weekly_periods: form.weekly_periods.map((period) => ({
      day_of_week: period.day_of_week,
      start: period.start,
      end: period.end,
    })),
    holidays: form.holidays.map(normalizeRange),
    makeup_days: form.makeup_days.map(normalizeRange),
  }
}

function inputClass(error?: string, className?: string): string {
  return cn(
    'h-10 rounded-lg border bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A]',
    error ? 'border-[#DC2626]' : 'border-[#E4E4E7]',
    className
  )
}

function validateForm(form: FormState): Record<string, string> {
  const errors: Record<string, string> = {}

  if (!form.name.trim()) errors.name = '请输入名称'
  else if (form.name.length > 64) errors.name = '名称不能超过 64 个字符'
  if (form.description.length > 256) {
    errors.description = '描述不能超过 256 个字符'
  }
  if (!form.timezone) {
    errors.timezone = '请选择时区'
  }

  const byDay = new Map<number, Array<{ index: number; start: number; end: number }>>()
  form.weekly_periods.forEach((period, index) => {
    const startKey = `weekly.${index}.start`
    const endKey = `weekly.${index}.end`
    if (!TIME_RE.test(period.start)) errors[startKey] = '请输入开始时间'
    if (!TIME_RE.test(period.end)) errors[endKey] = '请输入结束时间'
    if (!TIME_RE.test(period.start) || !TIME_RE.test(period.end)) return

    const start = minutes(period.start)
    const end = minutes(period.end)
    if (start >= end) {
      errors[endKey] = '结束时间必须晚于开始时间'
      return
    }
    const items = byDay.get(period.day_of_week) ?? []
    items.push({ index, start, end })
    byDay.set(period.day_of_week, items)
  })

  byDay.forEach((items) => {
    const sorted = [...items].sort((a, b) => a.start - b.start)
    let previous: { index: number; end: number } | null = null
    sorted.forEach((item) => {
      if (previous && item.start < previous.end) {
        errors[`weekly.${item.index}.start`] = '时段不能重叠'
      }
      previous = { index: item.index, end: item.end }
    })
  })

  validateDateRangeGroup(form.holidays, 'holidays', errors)
  validateDateRangeGroup(form.makeup_days, 'makeup_days', errors)

  return errors
}

function validateDateRangeGroup(
  ranges: FormRange[],
  key: 'holidays' | 'makeup_days',
  errors: Record<string, string>
): void {
  const validRanges: Array<{ index: number; start: string; end: string }> = []
  ranges.forEach((range, index) => {
    if (range.name.length > 32) {
      errors[`${key}.${index}.name`] = '名称不能超过 32 个字符'
    }
    if (!range.start_at) errors[`${key}.${index}.start_at`] = '请输入开始时间'
    if (!range.end_at) errors[`${key}.${index}.end_at`] = '请输入结束时间'
    if (!range.start_at || !range.end_at) return
    if (range.start_at >= range.end_at) {
      errors[`${key}.${index}.end_at`] = '结束时间必须晚于开始时间'
      return
    }
    validRanges.push({ index, start: range.start_at, end: range.end_at })
  })

  const sorted = [...validRanges].sort((a, b) => a.start.localeCompare(b.start))
  let previous: { index: number; end: string } | null = null
  sorted.forEach((item) => {
    if (previous && item.start < previous.end) {
      errors[`${key}.${item.index}.start_at`] = '时段不能重叠'
    }
    previous = { index: item.index, end: item.end }
  })
}

export function ServiceHoursForm({
  mode,
  serviceHours,
  loading,
}: ServiceHoursFormProps) {
  const router = useRouter()
  const { toast } = useToast()
  const createMutation = useCreateServiceHours()
  const updateMutation = useUpdateServiceHours()

  const [form, setForm] = useState<FormState>(() => formFromServiceHours(serviceHours))
  const [pristine, setPristine] = useState<FormState>(() =>
    formFromServiceHours(serviceHours)
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)

  useEffect(() => {
    if (mode === 'edit' && serviceHours) {
      const next = formFromServiceHours(serviceHours)
      setForm(next)
      setPristine(next)
      setErrors({})
    }
  }, [mode, serviceHours])

  const dirty = useMemo(
    () => JSON.stringify(form) !== JSON.stringify(pristine),
    [form, pristine]
  )

  useUnsavedChangesGuard(dirty)

  const isSaving = createMutation.isPending || updateMutation.isPending
  const title = mode === 'new' ? '新建服务时间' : `编辑：${serviceHours?.name ?? form.name}`

  const updateWeeklyPeriod = (
    index: number,
    patch: Partial<WeeklyServicePeriod>
  ) => {
    setForm((prev) => ({
      ...prev,
      weekly_periods: prev.weekly_periods.map((period, i) =>
        i === index ? { ...period, ...patch } : period
      ),
    }))
  }

  const removeWeeklyPeriod = (index: number) => {
    setForm((prev) => ({
      ...prev,
      weekly_periods: prev.weekly_periods.filter((_, i) => i !== index),
    }))
  }

  const addWeeklyPeriod = (day: number) => {
    setForm((prev) => ({
      ...prev,
      weekly_periods: [
        ...prev.weekly_periods,
        { day_of_week: day, start: '', end: '' },
      ],
    }))
  }

  const updateRange = (
    group: 'holidays' | 'makeup_days',
    index: number,
    patch: Partial<FormRange>
  ) => {
    setForm((prev) => ({
      ...prev,
      [group]: prev[group].map((range, i) =>
        i === index ? { ...range, ...patch } : range
      ),
    }))
  }

  const addRange = (group: 'holidays' | 'makeup_days') => {
    setForm((prev) => ({
      ...prev,
      [group]: [...prev[group], { name: '', start_at: '', end_at: '' }],
    }))
  }

  const removeRange = (group: 'holidays' | 'makeup_days', index: number) => {
    setForm((prev) => ({
      ...prev,
      [group]: prev[group].filter((_, i) => i !== index),
    }))
  }

  const handleBack = () => {
    if (dirty) {
      setShowLeaveConfirm(true)
      return
    }
    router.push('/system/service-hours')
  }

  const handleSave = async () => {
    const nextErrors = validateForm(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      toast('请检查表单填写', 'error')
      return
    }

    try {
      const payload = buildPayload(form)
      if (mode === 'new') {
        const created = await createMutation.mutateAsync(payload)
        toast('已保存', 'success')
        router.replace(`/system/service-hours/${created.id}`)
        return
      }
      if (!serviceHours) return
      const updated = await updateMutation.mutateAsync({
        id: serviceHours.id,
        payload,
      })
      const next = formFromServiceHours(updated)
      setForm(next)
      setPristine(next)
      toast('已保存', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#E4E4E7] border-t-[#1A1A1A]" />
      </div>
    )
  }

  const errorSummary = Array.from(new Set(Object.values(errors))).slice(0, 4)

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#E4E4E7] bg-white px-12 py-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex items-center gap-1 text-sm text-[#737373] transition-colors hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            返回列表
          </button>
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
        </div>
        <Button onClick={handleSave} loading={isSaving} disabled={!dirty}>
          保存
        </Button>
      </div>

      <div className="flex-1 overflow-auto px-12 py-10">
        <div className="flex max-w-[720px] flex-col gap-6">
          {errorSummary.length > 0 && (
            <div className="rounded-lg border border-[#FCA5A5] bg-[#FEF2F2] px-4 py-3 text-sm text-[#DC2626]">
              {errorSummary.join('；')}
            </div>
          )}

          <div className="flex max-w-[560px] flex-col gap-5">
            <Field label="名称" required error={errors.name}>
              <input
                className={inputClass(errors.name)}
                placeholder="请输入服务时间名称"
                value={form.name}
                maxLength={64}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, name: event.target.value }))
                }
              />
            </Field>
            <Field label="描述" error={errors.description}>
              <textarea
                className={cn(
                  inputClass(errors.description),
                  'min-h-[120px] resize-none py-2'
                )}
                placeholder="选填，用于区分多组配置用途"
                value={form.description}
                maxLength={256}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    description: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="时区" required error={errors.timezone}>
              <select
                className={inputClass(errors.timezone)}
                value={form.timezone}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, timezone: event.target.value }))
                }
              >
                {TIMEZONE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Section
            title="每周服务时间"
            description="按周一到周日配置多段开始-结束时间（精确到分钟）；未配置的日期视为非服务日。"
          >
            <div className="flex flex-col gap-3">
              {DAYS.map((day) => {
                const periods = form.weekly_periods
                  .map((period, index) => ({ period, index }))
                  .filter(({ period }) => period.day_of_week === day.value)
                return (
                  <div
                    key={day.value}
                    className="flex min-h-10 items-center gap-3 py-1"
                  >
                    <div className="w-12 shrink-0 text-sm font-medium text-[#404040]">
                      {day.label}
                    </div>
                    <div className="flex flex-1 flex-wrap items-center gap-2">
                      {periods.map(({ period, index }) => (
                        <div key={index} className="flex items-center gap-2">
                          <TimeInput
                            value={period.start}
                            error={errors[`weekly.${index}.start`]}
                            onChange={(value) =>
                              updateWeeklyPeriod(index, { start: value })
                            }
                          />
                          <span className="text-sm text-[#A1A1AA]">-</span>
                          <TimeInput
                            value={period.end}
                            error={errors[`weekly.${index}.end`]}
                            onChange={(value) =>
                              updateWeeklyPeriod(index, { end: value })
                            }
                          />
                          <IconButton
                            title="删除时段"
                            onClick={() => removeWeeklyPeriod(index)}
                          />
                        </div>
                      ))}
                      <LinkButton onClick={() => addWeeklyPeriod(day.value)}>
                        <IconPlus size={15} />
                        添加时段
                      </LinkButton>
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>

          <Divider />

          <DateRangeSection
            title="放假时间"
            description="名称 + 开始日期时间-结束日期时间（精确到分钟），支持多条。"
            addText="添加放假时间"
            ranges={form.holidays}
            errors={errors}
            group="holidays"
            onAdd={() => addRange('holidays')}
            onUpdate={(index, patch) => updateRange('holidays', index, patch)}
            onRemove={(index) => removeRange('holidays', index)}
          />

          <Divider />

          <DateRangeSection
            title="补班时间"
            description="名称 + 开始日期时间-结束日期时间（精确到分钟），支持多条。"
            addText="添加补班时间"
            ranges={form.makeup_days}
            errors={errors}
            group="makeup_days"
            onAdd={() => addRange('makeup_days')}
            onUpdate={(index, patch) => updateRange('makeup_days', index, patch)}
            onRemove={(index) => removeRange('makeup_days', index)}
          />
        </div>
      </div>

      <ConfirmModal
        open={showLeaveConfirm}
        onClose={() => setShowLeaveConfirm(false)}
        onConfirm={() => router.push('/system/service-hours')}
        title="有未保存的更改"
        description="有未保存的更改，确定离开？"
        confirmText="确定离开"
        cancelText="取消"
      />
    </div>
  )
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string
  required?: boolean
  error?: string
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-medium text-[#404040]">
        {label}
        {required && <span className="ml-1 text-[#DC2626]">*</span>}
      </span>
      {children}
      {error && <span className="text-xs text-[#DC2626]">{error}</span>}
    </label>
  )
}

function Section({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-[#18181B]">{title}</h2>
        <p className="text-xs leading-relaxed text-[#71717A]">{description}</p>
      </div>
      {children}
    </section>
  )
}

function Divider() {
  return <div className="h-px w-full bg-[#E4E4E7]" />
}

function TimeInput({
  value,
  error,
  onChange,
}: {
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="relative">
        <input
          type="time"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={inputClass(error, 'w-[112px] pr-8')}
        />
        <IconClock
          size={15}
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#A1A1AA]"
        />
      </div>
      {error && <span className="max-w-[112px] text-xs text-[#DC2626]">{error}</span>}
    </div>
  )
}

function LinkButton({
  children,
  onClick,
}: {
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-9 items-center gap-1 text-sm font-medium text-[#18181B] hover:underline"
    >
      {children}
    </button>
  )
}

function IconButton({
  title,
  onClick,
}: {
  title: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
    >
      <IconTrash size={16} />
    </button>
  )
}

function DateRangeSection({
  title,
  description,
  addText,
  ranges,
  errors,
  group,
  onAdd,
  onUpdate,
  onRemove,
}: {
  title: string
  description: string
  addText: string
  ranges: FormRange[]
  errors: Record<string, string>
  group: 'holidays' | 'makeup_days'
  onAdd: () => void
  onUpdate: (index: number, patch: Partial<FormRange>) => void
  onRemove: (index: number) => void
}) {
  return (
    <Section title={title} description={description}>
      <div className="flex flex-col gap-3">
        {ranges.map((range, index) => (
          <div key={index} className="flex flex-wrap items-start gap-2">
            <div className="flex flex-col gap-1">
              <input
                value={range.name}
                maxLength={32}
                placeholder="名称"
                onChange={(event) => onUpdate(index, { name: event.target.value })}
                className={inputClass(errors[`${group}.${index}.name`], 'w-[160px]')}
              />
              {errors[`${group}.${index}.name`] && (
                <span className="text-xs text-[#DC2626]">
                  {errors[`${group}.${index}.name`]}
                </span>
              )}
            </div>
            <DateTimeInput
              value={range.start_at}
              error={errors[`${group}.${index}.start_at`]}
              onChange={(value) => onUpdate(index, { start_at: value })}
            />
            <span className="pt-2.5 text-sm text-[#A1A1AA]">→</span>
            <DateTimeInput
              value={range.end_at}
              error={errors[`${group}.${index}.end_at`]}
              onChange={(value) => onUpdate(index, { end_at: value })}
            />
            <IconButton title={`删除${title}`} onClick={() => onRemove(index)} />
          </div>
        ))}
        <LinkButton onClick={onAdd}>
          <IconPlus size={15} />
          {addText}
        </LinkButton>
      </div>
    </Section>
  )
}

function DateTimeInput({
  value,
  error,
  onChange,
}: {
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <input
        type="datetime-local"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass(error, 'w-[196px]')}
      />
      {error && <span className="max-w-[196px] text-xs text-[#DC2626]">{error}</span>}
    </div>
  )
}
