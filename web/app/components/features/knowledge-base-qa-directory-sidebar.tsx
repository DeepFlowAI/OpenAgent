'use client'

import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
  IconCheck, IconChevronDown, IconChevronRight, IconDotsVertical,
  IconFolder, IconFolderOpen, IconGripVertical, IconPlus,
} from '@tabler/icons-react'
import { cn } from '@/utils/classnames'
import { useQaDirectoryCopy } from '@/app/components/features/knowledge-base-qa-copy'
import type { KnowledgeBaseQaDirectory, UpdateKnowledgeBaseQaDirectoryPayload } from '@/models/knowledge-base-qa-directory'

type DropPosition = 'before' | 'inside' | 'after'
type SidebarProps = {
  directories: KnowledgeBaseQaDirectory[]
  totalQaCount: number
  selectedId: number | null
  canManage: boolean
  loading: boolean
  onSelect: (id: number | null) => void
  onCreate: (parentId: number | null) => void
  onEdit: (item: KnowledgeBaseQaDirectory) => void
  onDelete: (item: KnowledgeBaseQaDirectory) => void
  onMove: (id: number, data: UpdateKnowledgeBaseQaDirectoryPayload) => Promise<void>
}

export function KnowledgeBaseQaDirectorySidebar(props: SidebarProps) {
  const { directories, totalQaCount, selectedId, canManage, loading, onSelect, onCreate, onEdit, onDelete, onMove } = props
  const t = useQaDirectoryCopy()
  const [adjusting, setAdjusting] = useState(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [menuId, setMenuId] = useState<number | null>(null)
  const [draggedId, setDraggedId] = useState<number | null>(null)
  const [drop, setDrop] = useState<{ id: number; position: DropPosition } | null>(null)
  const seenIds = useRef(new Set<number>())

  useEffect(() => {
    setExpanded((old) => {
      const next = new Set(old)
      for (const item of directories) {
        if (!seenIds.current.has(item.id) && item.depth < 3) next.add(item.id)
        seenIds.current.add(item.id)
      }
      return next
    })
  }, [directories])

  useEffect(() => {
    if (menuId === null) return
    const close = () => setMenuId(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [menuId])

  const children = useMemo(() => {
    const result = new Map<number | null, KnowledgeBaseQaDirectory[]>()
    for (const item of directories) {
      const values = result.get(item.parent_id) ?? []
      values.push(item)
      result.set(item.parent_id, values)
    }
    for (const values of result.values()) values.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
    return result
  }, [directories])

  const move = async (target: KnowledgeBaseQaDirectory, position: DropPosition) => {
    if (draggedId === null || draggedId === target.id) return
    const parentId = position === 'inside' ? target.id : target.parent_id
    const siblings = directories
      .filter((item) => item.parent_id === parentId && item.id !== draggedId)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
    const targetIndex = siblings.findIndex((item) => item.id === target.id)
    const sortOrder = position === 'inside' ? siblings.length : Math.max(0, targetIndex + (position === 'after' ? 1 : 0))
    try {
      await onMove(draggedId, { parent_id: parentId, sort_order: sortOrder })
      if (parentId !== null) setExpanded((old) => new Set(old).add(parentId))
    } finally {
      setDraggedId(null)
      setDrop(null)
    }
  }

  const renderBranch = (parentId: number | null): React.ReactNode =>
    (children.get(parentId) ?? []).map((item) => (
      <div key={item.id}>
        <DirectoryRow
          item={item}
          selected={selectedId === item.id}
          expanded={expanded.has(item.id)}
          hasChildren={(children.get(item.id)?.length ?? 0) > 0}
          adjusting={adjusting}
          menuOpen={menuId === item.id}
          dropPosition={drop?.id === item.id ? drop.position : null}
          onToggle={() => setExpanded((old) => { const next = new Set(old); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })}
          onSelect={() => onSelect(item.id)}
          onMenu={(event) => { event.stopPropagation(); setMenuId((old) => old === item.id ? null : item.id) }}
          onCreate={() => { setMenuId(null); onCreate(item.id) }}
          onEdit={() => { setMenuId(null); onEdit(item) }}
          onDelete={() => { setMenuId(null); onDelete(item) }}
          onDragStart={() => setDraggedId(item.id)}
          onDragOver={(event) => {
            event.preventDefault()
            const rect = event.currentTarget.getBoundingClientRect()
            const ratio = (event.clientY - rect.top) / rect.height
            const position: DropPosition = item.depth >= 3
              ? ratio < 0.5 ? 'before' : 'after'
              : ratio > 0.75 ? 'after' : ratio < 0.25 ? 'before' : 'inside'
            setDrop({ id: item.id, position })
          }}
          onDrop={(event) => { event.preventDefault(); void move(item, drop?.id === item.id ? drop.position : 'after') }}
          copy={t}
        />
        {expanded.has(item.id) && renderBranch(item.id)}
      </div>
    ))

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-[#FAFAFA] p-3">
      <div className="mb-3 flex h-9 items-center justify-between px-2">
        <h2 className="text-sm font-semibold text-foreground">{t.title}</h2>
        {canManage && <div className="flex items-center gap-0.5"><button type="button" title={t.create} aria-label={t.create} className="rounded-md p-1.5 text-[#404040] hover:bg-[#F0F0F0]" onClick={() => onCreate(null)}><IconPlus size={17} /></button><button type="button" title={adjusting ? t.finish : t.adjust} aria-label={adjusting ? t.finish : t.adjust} className="rounded-md p-1.5 text-[#404040] hover:bg-[#F0F0F0]" onClick={() => setAdjusting((value) => !value)}>{adjusting ? <IconCheck size={17} /> : <IconGripVertical size={17} />}</button></div>}
      </div>
      <button type="button" className={cn('mb-1 flex h-9 w-full items-center gap-2 rounded-lg px-2 text-sm', selectedId === null ? 'bg-[#F0F0F0] font-medium text-foreground' : 'text-muted-foreground hover:bg-[#F0F0F0]')} onClick={() => onSelect(null)}><IconFolderOpen size={17} /><span className="min-w-0 flex-1 truncate text-left">{t.all}</span><span className="text-xs">{totalQaCount}</span></button>
      {loading ? <div className="space-y-2 px-2 py-3"><div className="h-8 animate-pulse rounded-lg bg-[#E5E5E5]" /><div className="h-8 animate-pulse rounded-lg bg-[#E5E5E5]" /></div> : directories.length === 0 ? <div className="px-2 py-10 text-center text-xs text-muted-foreground"><p>{t.empty}</p>{canManage && <button type="button" className="mt-3 font-medium text-foreground underline-offset-4 hover:underline" onClick={() => onCreate(null)}>{t.create}</button>}</div> : renderBranch(null)}
    </aside>
  )
}

type RowProps = {
  item: KnowledgeBaseQaDirectory; selected: boolean; expanded: boolean; hasChildren: boolean; adjusting: boolean
  menuOpen: boolean; dropPosition: DropPosition | null; copy: ReturnType<typeof useQaDirectoryCopy>
  onToggle: () => void; onSelect: () => void; onMenu: (event: React.MouseEvent) => void
  onCreate: () => void; onEdit: () => void; onDelete: () => void; onDragStart: () => void
  onDragOver: (event: DragEvent<HTMLDivElement>) => void; onDrop: (event: DragEvent<HTMLDivElement>) => void
}

function DirectoryRow(props: RowProps) {
  const { item, selected, expanded, hasChildren, adjusting, menuOpen, dropPosition, copy: t } = props
  const indent = item.depth === 1 ? 'pl-2' : item.depth === 2 ? 'pl-6' : 'pl-10'
  return (
    <div className={cn('group relative flex h-9 items-center rounded-lg pr-1 text-sm text-muted-foreground hover:bg-[#F0F0F0]', indent, selected && 'bg-[#F0F0F0] font-medium text-foreground', dropPosition === 'inside' && 'ring-1 ring-foreground')} draggable={adjusting} onDragStart={props.onDragStart} onDragOver={props.onDragOver} onDrop={props.onDrop}>
      {dropPosition === 'before' && <span className="absolute inset-x-1 top-0 h-0.5 bg-foreground" />}{dropPosition === 'after' && <span className="absolute inset-x-1 bottom-0 h-0.5 bg-foreground" />}
      {adjusting && <IconGripVertical size={15} className="mr-1 shrink-0 cursor-grab" />}
      <button type="button" aria-label={expanded ? 'Collapse' : 'Expand'} className={cn('mr-0.5 rounded p-0.5', !hasChildren && 'invisible')} onClick={props.onToggle}>{expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}</button>
      <button type="button" className="flex min-w-0 flex-1 items-center gap-1.5" onClick={props.onSelect}><IconFolder size={16} className="shrink-0" /><span className="truncate" title={item.path.join(' / ')}>{item.name}</span></button>
      <span className="ml-1 text-xs text-muted-foreground">{item.qa_count}</span>
      {!adjusting && <button type="button" aria-label="More" className="ml-0.5 rounded p-1 opacity-0 hover:bg-white group-hover:opacity-100" onClick={props.onMenu}><IconDotsVertical size={15} /></button>}
      {menuOpen && <div className="absolute right-0 top-8 z-30 w-36 overflow-hidden rounded-lg border border-border bg-white py-1 text-sm font-normal text-foreground shadow-lg" onClick={(event) => event.stopPropagation()}>{item.depth < 3 && <button type="button" className="block w-full px-3 py-2 text-left hover:bg-[#F5F5F5]" onClick={props.onCreate}>{t.createChild}</button>}<button type="button" className="block w-full px-3 py-2 text-left hover:bg-[#F5F5F5]" onClick={props.onEdit}>{t.rename}</button><button type="button" className="block w-full px-3 py-2 text-left text-[#DC2626] hover:bg-[#FEF2F2]" onClick={props.onDelete}>{t.delete}</button></div>}
    </div>
  )
}
