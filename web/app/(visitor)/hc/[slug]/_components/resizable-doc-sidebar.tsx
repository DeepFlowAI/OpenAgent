'use client'

import { useEffect, useRef, useState } from 'react'
import type { NavEntry, PublicDocSummary } from '@/models/help-center'
import { DocTree } from './doc-tree'

const DEFAULT_WIDTH = 260
const MIN_WIDTH = 200
const MAX_WIDTH = 420

type Props = {
  slug: string
  tabSlug: string
  docs: PublicDocSummary[]
  nav: NavEntry[] | null
}

export function ResizableDocSidebar({ slug, tabSlug, docs, nav }: Props) {
  const asideRef = useRef<HTMLElement>(null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    if (!dragging) return

    const prevCursor = document.body.style.cursor
    const prevUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handlePointerMove = (event: PointerEvent) => {
      const left = asideRef.current?.getBoundingClientRect().left ?? 0
      setWidth(clamp(event.clientX - left, MIN_WIDTH, MAX_WIDTH))
    }
    const stopDragging = () => setDragging(false)

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)

    return () => {
      document.body.style.cursor = prevCursor
      document.body.style.userSelect = prevUserSelect
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
    }
  }, [dragging])

  return (
    <aside
      ref={asideRef}
      className="sticky top-16 hidden h-[calc(100vh-4rem)] shrink-0 overflow-y-auto bg-[#FAFAFA] px-3.5 py-5 pr-5 lg:block"
      style={{ width }}
    >
      <DocTree slug={slug} tabSlug={tabSlug} docs={docs} nav={nav} />
      <button
        type="button"
        aria-label="调整目录宽度"
        className="absolute inset-y-0 right-0 z-10 w-2 cursor-col-resize touch-none outline-none after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-[#E5E5E5] hover:after:bg-[#A1A1AA] focus-visible:after:bg-[#1A1A1A]"
        onPointerDown={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
      />
    </aside>
  )
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}
