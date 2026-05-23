'use client'

import { cn } from '@/utils/classnames'
import {
  METRIC_COLOR,
  METRIC_LABEL,
  RATE_METRICS,
  VOLUME_METRICS,
  type RateMetric,
  type VolumeMetric,
} from '../_constants'

type Props = {
  volumeSelected: Record<VolumeMetric, boolean>
  rateSelected: Record<RateMetric, boolean>
  onVolumeChange: (next: Record<VolumeMetric, boolean>) => void
  onRateChange: (next: Record<RateMetric, boolean>) => void
}

type CheckboxItemProps = {
  label: string
  color: string
  checked: boolean
  onToggle: () => void
}

function CheckboxItem({ label, color, checked, onToggle }: CheckboxItemProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center gap-1.5 text-[13px] text-[#52525B] transition-colors hover:text-[#18181B]"
    >
      <span
        className={cn(
          'flex h-4 w-4 items-center justify-center rounded border',
          checked ? 'border-[#18181B] bg-[#18181B]' : 'border-[#D4D4D8] bg-white',
        )}
      >
        {checked ? (
          <svg viewBox="0 0 10 10" width={8} height={8} fill="none">
            <path
              d="M1 5l2.5 2.5L9 2"
              stroke="#FFFFFF"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : null}
      </span>
      <span
        className="h-2.5 w-2.5 rounded-[2px]"
        style={{ backgroundColor: color }}
      />
      <span>{label}</span>
    </button>
  )
}

export function MetricToggles({
  volumeSelected,
  rateSelected,
  onVolumeChange,
  onRateChange,
}: Props) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
        <span className="text-[13px] font-medium text-[#52525B]">数量</span>
        {VOLUME_METRICS.map((m) => (
          <CheckboxItem
            key={m}
            label={METRIC_LABEL[m]}
            color={METRIC_COLOR[m]}
            checked={volumeSelected[m]}
            onToggle={() =>
              onVolumeChange({ ...volumeSelected, [m]: !volumeSelected[m] })
            }
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
        <span className="text-[13px] font-medium text-[#52525B]">比例</span>
        {RATE_METRICS.map((m) => (
          <CheckboxItem
            key={m}
            label={METRIC_LABEL[m]}
            color={METRIC_COLOR[m]}
            checked={rateSelected[m]}
            onToggle={() =>
              onRateChange({ ...rateSelected, [m]: !rateSelected[m] })
            }
          />
        ))}
      </div>
    </div>
  )
}
