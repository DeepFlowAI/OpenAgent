'use client'

import { IconCalendar } from '@tabler/icons-react'

import {
  QUICK_RANGE_PRESETS,
  type DateRangeDraft,
  type QuickRangePresetId,
} from '../_date-range'

type FilterBarProps = {
  range: DateRangeDraft
  activePreset: QuickRangePresetId | null
  onRangeChange: (next: DateRangeDraft) => void
  onPresetSelect: (preset: QuickRangePresetId) => void
}

const inputClassName =
  'h-9 min-w-0 flex-1 border-0 bg-transparent px-1 text-sm text-[#18181B] outline-none [color-scheme:light]'

export function FilterBar({
  range,
  activePreset,
  onRangeChange,
  onPresetSelect,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium text-[#52525B]">会话开始时间</span>

      <div className="flex h-9 min-w-[280px] items-center gap-1 rounded-lg border border-[#E4E4E7] bg-white px-2">
        <IconCalendar size={16} className="shrink-0 text-[#A1A1AA]" aria-hidden />
        <input
          type="date"
          value={range.startDate}
          onChange={(e) =>
            onRangeChange({ startDate: e.target.value, endDate: range.endDate })
          }
          aria-label="开始日期"
          className={inputClassName}
        />
        <span className="shrink-0 px-0.5 text-sm text-[#71717A]">~</span>
        <input
          type="date"
          value={range.endDate}
          onChange={(e) =>
            onRangeChange({ startDate: range.startDate, endDate: e.target.value })
          }
          aria-label="结束日期"
          className={inputClassName}
        />
        <IconCalendar size={16} className="shrink-0 text-[#A1A1AA]" aria-hidden />
      </div>

      <select
        value={activePreset ?? ''}
        onChange={(e) => {
          const value = e.target.value as QuickRangePresetId
          if (value) onPresetSelect(value)
        }}
        aria-label="快捷选择时间范围"
        className="h-9 min-w-[120px] cursor-pointer rounded-lg border border-[#E4E4E7] bg-white px-3 text-sm text-[#18181B] outline-none focus:border-[#A1A1AA]"
      >
        <option value="" disabled hidden={activePreset !== null}>
          快捷选择
        </option>
        {QUICK_RANGE_PRESETS.map((preset) => (
          <option key={preset.id} value={preset.id}>
            {preset.label}
          </option>
        ))}
      </select>
    </div>
  )
}
