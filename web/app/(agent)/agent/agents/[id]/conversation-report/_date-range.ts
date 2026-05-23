import { MAX_RANGE_DAYS } from './_constants'

export type QuickRangePresetId =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'last_30_days'
  | 'this_week'
  | 'this_month'
  | 'last_366_days'

export type DateRangeDraft = {
  startDate: string
  endDate: string
}

export const QUICK_RANGE_PRESETS: { id: QuickRangePresetId; label: string }[] = [
  { id: 'today', label: '今天' },
  { id: 'yesterday', label: '昨天' },
  { id: 'last_7_days', label: '近 7 天' },
  { id: 'last_30_days', label: '近 30 天' },
  { id: 'this_week', label: '本周' },
  { id: 'this_month', label: '本月' },
  { id: 'last_366_days', label: '近 366 天' },
]

const MS_PER_DAY = 24 * 60 * 60 * 1000

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function formatDateInput(date: Date): string {
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
  ].join('')
}

export function parseDateInput(raw: string | null | undefined): Date | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed) return null

  // YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    const d = new Date(`${trimmed}T00:00:00`)
    return Number.isNaN(d.getTime()) ? null : d
  }

  const d = new Date(trimmed)
  if (Number.isNaN(d.getTime())) return null
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return startOfDay(next)
}

function startOfWeekMonday(date: Date): Date {
  const d = startOfDay(date)
  const weekday = d.getDay()
  const diff = weekday === 0 ? 6 : weekday - 1
  d.setDate(d.getDate() - diff)
  return d
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

export function resolvePresetRange(id: QuickRangePresetId, now = new Date()): DateRangeDraft {
  const today = startOfDay(now)

  switch (id) {
    case 'today':
      return { startDate: formatDateInput(today), endDate: formatDateInput(today) }
    case 'yesterday': {
      const y = addDays(today, -1)
      return { startDate: formatDateInput(y), endDate: formatDateInput(y) }
    }
    case 'last_7_days':
      return {
        startDate: formatDateInput(addDays(today, -6)),
        endDate: formatDateInput(today),
      }
    case 'last_30_days':
      return {
        startDate: formatDateInput(addDays(today, -29)),
        endDate: formatDateInput(today),
      }
    case 'this_week':
      return {
        startDate: formatDateInput(startOfWeekMonday(today)),
        endDate: formatDateInput(today),
      }
    case 'this_month':
      return {
        startDate: formatDateInput(startOfMonth(today)),
        endDate: formatDateInput(today),
      }
    case 'last_366_days':
      return {
        startDate: formatDateInput(addDays(today, -(MAX_RANGE_DAYS - 1))),
        endDate: formatDateInput(today),
      }
    default:
      return getDefaultDateRange(now)
  }
}

export function getDefaultDateRange(now = new Date()): DateRangeDraft {
  return resolvePresetRange('today', now)
}

export function matchPreset(range: DateRangeDraft, now = new Date()): QuickRangePresetId | null {
  for (const preset of QUICK_RANGE_PRESETS) {
    const resolved = resolvePresetRange(preset.id, now)
    if (resolved.startDate === range.startDate && resolved.endDate === range.endDate) {
      return preset.id
    }
  }
  return null
}

export function inclusiveDayCount(startDate: string, endDate: string): number | null {
  const start = parseDateInput(startDate)
  const end = parseDateInput(endDate)
  if (!start || !end) return null
  return Math.floor((end.getTime() - start.getTime()) / MS_PER_DAY) + 1
}

export function validateDateRange(range: DateRangeDraft): string | null {
  if (!range.startDate || !range.endDate) {
    return '请同时选择开始与结束日期'
  }
  const start = parseDateInput(range.startDate)
  const end = parseDateInput(range.endDate)
  if (!start || !end) return '请同时选择开始与结束日期'
  if (start.getTime() > end.getTime()) return '开始日期不能晚于结束日期'

  const days = inclusiveDayCount(range.startDate, range.endDate)
  if (days !== null && days > MAX_RANGE_DAYS) {
    return `查询区间不能超过 ${MAX_RANGE_DAYS} 天`
  }
  return null
}

/** API range: local start-of-day inclusive, end exclusive at next day 00:00. */
export function dateRangeToApi(range: DateRangeDraft): {
  startedAtFrom: string
  startedAtTo: string
} {
  const start = parseDateInput(range.startDate)!
  const end = parseDateInput(range.endDate)!
  const endExclusive = addDays(end, 1)
  return {
    startedAtFrom: new Date(
      start.getFullYear(),
      start.getMonth(),
      start.getDate(),
      0,
      0,
      0,
      0,
    ).toISOString(),
    startedAtTo: new Date(
      endExclusive.getFullYear(),
      endExclusive.getMonth(),
      endExclusive.getDate(),
      0,
      0,
      0,
      0,
    ).toISOString(),
  }
}

export function parseDateRangeFromQuery(
  fromRaw: string | null,
  toRaw: string | null,
): DateRangeDraft | null {
  if (!fromRaw || !toRaw) return null

  const fromDate = parseDateInput(fromRaw)
  const toDate = parseDateInput(toRaw)
  if (!fromDate || !toDate) return null

  return {
    startDate: formatDateInput(fromDate),
    endDate: formatDateInput(toDate),
  }
}
