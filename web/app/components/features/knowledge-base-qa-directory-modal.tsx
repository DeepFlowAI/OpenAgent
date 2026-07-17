'use client'

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { getErrorMessage } from '@/service/base'
import { useQaDirectoryCopy } from '@/app/components/features/knowledge-base-qa-copy'
import type {
  KnowledgeBaseQaDirectory,
  UpdateKnowledgeBaseQaDirectoryPayload,
} from '@/models/knowledge-base-qa-directory'
import { flattenKnowledgeBaseQaDirectoryTree } from '@/utils/knowledge-base-qa-directory'

type EditorProps = {
  open: boolean
  directory: KnowledgeBaseQaDirectory | null
  defaultParentId: number | null
  directories: KnowledgeBaseQaDirectory[]
  loading: boolean
  onClose: () => void
  onSubmit: (data: UpdateKnowledgeBaseQaDirectoryPayload & { name: string }) => Promise<void>
}

function descendantIds(id: number, directories: KnowledgeBaseQaDirectory[]) {
  const result = new Set<number>()
  const pending = [id]
  while (pending.length) {
    const current = pending.pop()
    if (current === undefined) continue
    for (const item of directories) {
      if (item.parent_id === current && !result.has(item.id)) {
        result.add(item.id)
        pending.push(item.id)
      }
    }
  }
  return result
}

function subtreeHeight(id: number, directories: KnowledgeBaseQaDirectory[]): number {
  const children = directories.filter((item) => item.parent_id === id)
  return 1 + Math.max(0, ...children.map((item) => subtreeHeight(item.id, directories)))
}

export function KnowledgeBaseQaDirectoryModal({
  open, directory, defaultParentId, directories, loading, onClose, onSubmit,
}: EditorProps) {
  const t = useQaDirectoryCopy()
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState<number | null>(null)
  const [error, setError] = useState<string>()

  useEffect(() => {
    if (!open) return
    setName(directory?.name ?? '')
    setParentId(directory?.parent_id ?? defaultParentId)
    setError(undefined)
  }, [defaultParentId, directory, open])

  const orderedDirectories = useMemo(
    () => flattenKnowledgeBaseQaDirectoryTree(directories),
    [directories],
  )

  const parentOptions = useMemo(() => {
    if (!directory) return orderedDirectories.filter((item) => item.depth < 3)
    const excluded = descendantIds(directory.id, directories)
    excluded.add(directory.id)
    const height = subtreeHeight(directory.id, directories)
    return orderedDirectories.filter(
      (item) => !excluded.has(item.id) && item.depth + height <= 3,
    )
  }, [directories, directory, orderedDirectories])

  const submit = async () => {
    const trimmed = name.trim()
    if (!trimmed) return setError(t.nameRequired)
    if (trimmed.length > 50) return setError(t.nameTooLong)
    try {
      await onSubmit({ name: trimmed, parent_id: parentId })
    } catch (reason) {
      const message = await getErrorMessage(reason)
      const normalized = message.toLowerCase()
      setError(
        normalized.includes('already exists') ? t.duplicate
          : normalized.includes('3 levels') ? t.depth
            : message,
      )
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={directory ? t.rename : t.create}
      footer={<><Button variant="outline" disabled={loading} onClick={onClose}>{t.cancel}</Button><Button loading={loading} onClick={submit}>{t.save}</Button></>}
    >
      <div className="space-y-5">
        <div className="space-y-1.5">
          <label htmlFor="qa-directory-name" className="text-sm font-medium">{t.name}<span className="ml-0.5 text-[#DC2626]">*</span></label>
          <input
            id="qa-directory-name"
            autoFocus
            value={name}
            maxLength={50}
            placeholder={t.namePlaceholder}
            className={`h-11 w-full rounded-lg border px-3 text-sm outline-none focus:ring-2 focus:ring-[#1a1a1a]/10 ${error ? 'border-[#DC2626]' : 'border-[#E5E5E5] focus:border-[#1a1a1a]'}`}
            onChange={(event) => { setName(event.target.value); setError(undefined) }}
          />
          {error && <p className="text-xs text-[#DC2626]">{error}</p>}
        </div>
        <div className="space-y-1.5">
          <label htmlFor="qa-directory-parent" className="text-sm font-medium">{t.parent}</label>
          <select
            id="qa-directory-parent"
            value={parentId ?? ''}
            className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm outline-none focus:border-[#1a1a1a]"
            onChange={(event) => setParentId(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">{t.root}</option>
            {parentOptions.map((item) => <option key={item.id} value={item.id}>{`${'　'.repeat(item.depth - 1)}${item.name}`}</option>)}
          </select>
        </div>
      </div>
    </Modal>
  )
}

export function DeleteKnowledgeBaseQaDirectoryModal({
  directory, loading, onClose, onConfirm,
}: {
  directory: KnowledgeBaseQaDirectory | null
  loading: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  const t = useQaDirectoryCopy()
  return (
    <Modal
      open={!!directory}
      onClose={onClose}
      title={t.deleteTitle}
      footer={<><Button variant="outline" disabled={loading} onClick={onClose}>{t.cancel}</Button><Button variant="destructive" loading={loading} onClick={onConfirm}>{t.deleteConfirm}</Button></>}
    >
      <p className="text-sm leading-relaxed text-muted-foreground">{t.deleteBody}</p>
      <div className="mt-4 space-y-3 rounded-lg bg-[#F8F8F8] p-4 text-sm">
        <div><p className="text-xs text-muted-foreground">{t.directoryName}</p><p className="mt-1 font-medium">{directory?.name}</p></div>
        <div><p className="text-xs text-muted-foreground">{t.directoryPath}</p><p className="mt-1 text-muted-foreground">{directory?.path.join(' / ')}</p></div>
      </div>
    </Modal>
  )
}
