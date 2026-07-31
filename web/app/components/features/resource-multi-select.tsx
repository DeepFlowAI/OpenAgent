'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  IconCheck,
  IconChevronDown,
  IconSearch,
  IconX,
} from '@tabler/icons-react'

import type { AccountResourceOption } from '@/models/account'
import { useAccountCopy } from '@/app/components/features/account-copy'
import { cn } from '@/utils/classnames'

type ResourceMultiSelectProps = {
  label: string
  options: AccountResourceOption[]
  value: number[]
  onChange: (value: number[]) => void
  disabled?: boolean
  disabledText?: string
}

export function ResourceMultiSelect({
  label,
  options,
  value,
  onChange,
  disabled = false,
  disabledText,
}: ResourceMultiSelectProps) {
  const copy = useAccountCopy()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = useMemo(
    () => options.filter((option) => value.includes(option.id)),
    [options, value]
  )
  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return query
      ? options.filter((option) =>
          option.name.toLocaleLowerCase().includes(query)
        )
      : options
  }, [options, search])

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const toggle = (id: number) => {
    onChange(
      value.includes(id)
        ? value.filter((item) => item !== id)
        : [...value, id]
    )
  }

  return (
    <div ref={rootRef} className="relative space-y-1.5">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          'flex min-h-11 w-full items-center justify-between rounded-lg border border-input bg-background px-3 text-left text-sm transition-colors',
          'focus:border-foreground focus:outline-none focus:ring-2 focus:ring-ring/10',
          disabled && 'cursor-not-allowed bg-muted text-muted-foreground'
        )}
      >
        <span>
          {disabled
            ? disabledText
            : selected.length
              ? copy.selected(selected.length)
              : copy.select}
        </span>
        <IconChevronDown size={16} className="text-muted-foreground" />
      </button>

      {!disabled && selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.slice(0, 6).map((option) => (
            <span
              key={option.id}
              className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs text-foreground"
            >
              {option.name}
              <button
                type="button"
                onClick={() => toggle(option.id)}
                aria-label={copy.remove(option.name)}
              >
                <IconX size={12} />
              </button>
            </span>
          ))}
          {selected.length > 6 && (
            <span className="px-2 py-1 text-xs text-muted-foreground">
              +{selected.length - 6}
            </span>
          )}
        </div>
      )}

      {open && !disabled && (
        <div className="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-border bg-background shadow-lg">
          <div className="relative border-b border-border p-2">
            <IconSearch
              size={16}
              className="absolute left-5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={copy.search}
              className="h-9 w-full rounded-md bg-muted pl-9 pr-3 text-sm outline-none"
            />
          </div>
          <div className="max-h-56 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <p className="py-5 text-center text-sm text-muted-foreground">
                {copy.noResults}
              </p>
            ) : (
              filtered.map((option) => {
                const checked = value.includes(option.id)
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => toggle(option.id)}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
                  >
                    <span
                      className={cn(
                        'flex h-4 w-4 items-center justify-center rounded border border-border',
                        checked && 'border-foreground bg-foreground text-background'
                      )}
                    >
                      {checked && <IconCheck size={12} />}
                    </span>
                    <span className="min-w-0 flex-1 truncate">
                      {option.name}
                    </span>
                    {option.status === 'inactive' && (
                      <span className="text-xs text-muted-foreground">
                        {copy.inactive}
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {disabled
          ? copy.adminFutureAccess(disabledText ?? '')
          : copy.emptyAccessAllowed}
      </p>
    </div>
  )
}
