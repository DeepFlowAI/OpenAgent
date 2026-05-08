'use client'

import * as React from 'react'
import { Combobox as ComboboxPrimitive } from '@base-ui/react'
import { IconCheck, IconChevronDown, IconX } from '@tabler/icons-react'
import { cn } from '@/utils/classnames'

const Combobox = ComboboxPrimitive.Root

function ComboboxValue({ ...props }: ComboboxPrimitive.Value.Props) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />
}

function ComboboxInput({
  className,
  disabled = false,
  ...props
}: ComboboxPrimitive.Input.Props) {
  return (
    <div
      className={cn(
        'flex h-9 w-full items-center rounded-lg border border-[#E4E4E7] bg-white text-xs shadow-xs transition-colors focus-within:border-[#18181B] focus-within:ring-2 focus-within:ring-[#18181B]/10',
        disabled && 'cursor-not-allowed bg-[#F5F5F5] opacity-60',
        className,
      )}
    >
      <ComboboxPrimitive.Input
        disabled={disabled}
        className="h-full min-w-0 flex-1 bg-transparent px-2.5 text-xs text-[#18181B] outline-none placeholder:text-[#A1A1AA]"
        {...props}
      />
      <ComboboxPrimitive.Trigger className="flex shrink-0 items-center px-2 text-[#A1A1AA]">
        <IconChevronDown size={14} />
      </ComboboxPrimitive.Trigger>
    </div>
  )
}

function ComboboxContent({
  className,
  side = 'bottom',
  sideOffset = 4,
  align = 'start',
  alignOffset = 0,
  anchor,
  ...props
}: ComboboxPrimitive.Popup.Props &
  Pick<
    ComboboxPrimitive.Positioner.Props,
    'side' | 'align' | 'sideOffset' | 'alignOffset' | 'anchor'
  >) {
  return (
    <ComboboxPrimitive.Portal>
      <ComboboxPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        anchor={anchor}
        className="z-50"
      >
        <ComboboxPrimitive.Popup
          data-slot="combobox-content"
          className={cn(
            'max-h-60 w-[var(--anchor-width)] overflow-hidden rounded-lg border border-[#E4E4E7] bg-white shadow-lg',
            'data-[open]:animate-in data-[open]:fade-in-0 data-[open]:zoom-in-95',
            'data-[closed]:animate-out data-[closed]:fade-out-0 data-[closed]:zoom-out-95',
            className,
          )}
          {...props}
        />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  )
}

function ComboboxList({ className, ...props }: ComboboxPrimitive.List.Props) {
  return (
    <ComboboxPrimitive.List
      data-slot="combobox-list"
      className={cn('max-h-56 overflow-y-auto p-1', className)}
      {...props}
    />
  )
}

function ComboboxItem({
  className,
  children,
  ...props
}: ComboboxPrimitive.Item.Props) {
  return (
    <ComboboxPrimitive.Item
      data-slot="combobox-item"
      className={cn(
        'relative flex w-full cursor-default items-center gap-2 rounded-md py-1.5 pr-8 pl-2 text-xs text-[#18181B] outline-none select-none data-[highlighted]:bg-[#F4F4F5]',
        className,
      )}
      {...props}
    >
      {children}
      <ComboboxPrimitive.ItemIndicator
        render={
          <span className="pointer-events-none absolute right-2 flex size-4 items-center justify-center" />
        }
      >
        <IconCheck size={14} className="text-[#18181B]" />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  )
}

function ComboboxEmpty({
  className,
  ...props
}: ComboboxPrimitive.Empty.Props) {
  return (
    <ComboboxPrimitive.Empty
      data-slot="combobox-empty"
      className={cn('py-3 text-center text-xs text-[#A1A1AA]', className)}
      {...props}
    />
  )
}

function ComboboxChips({
  className,
  ...props
}: React.ComponentPropsWithRef<typeof ComboboxPrimitive.Chips> &
  ComboboxPrimitive.Chips.Props) {
  return (
    <ComboboxPrimitive.Chips
      data-slot="combobox-chips"
      className={cn(
        'flex min-h-[32px] flex-wrap items-center gap-1 rounded-lg border border-[#E4E4E7] bg-white px-2 py-1 text-xs shadow-xs transition-[color,box-shadow] focus-within:border-[#18181B] focus-within:ring-2 focus-within:ring-[#18181B]/10',
        className,
      )}
      {...props}
    />
  )
}

function ComboboxChip({
  className,
  children,
  ...props
}: ComboboxPrimitive.Chip.Props) {
  return (
    <ComboboxPrimitive.Chip
      data-slot="combobox-chip"
      className={cn(
        'flex h-[22px] max-w-full items-center gap-0.5 rounded bg-[#F4F4F5] py-px pl-1.5 pr-0.5 text-[10px] leading-tight text-[#18181B]',
        className,
      )}
      {...props}
    >
      <span className="min-w-0 truncate">{children}</span>
      <ComboboxPrimitive.ChipRemove className="shrink-0 rounded-sm p-px text-[#A1A1AA] transition-colors hover:text-[#18181B]">
        <IconX size={10} />
      </ComboboxPrimitive.ChipRemove>
    </ComboboxPrimitive.Chip>
  )
}

function ComboboxChipsInput({
  className,
  ...props
}: ComboboxPrimitive.Input.Props) {
  return (
    <ComboboxPrimitive.Input
      data-slot="combobox-chips-input"
      className={cn(
        'min-w-[4rem] flex-1 bg-transparent text-[10px] text-[#18181B] outline-none placeholder:text-[#A1A1AA]',
        className,
      )}
      {...props}
    />
  )
}

function useComboboxAnchor() {
  return React.useRef<HTMLDivElement | null>(null)
}

export {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
  ComboboxChips,
  ComboboxChip,
  ComboboxChipsInput,
  ComboboxValue,
  useComboboxAnchor,
}
