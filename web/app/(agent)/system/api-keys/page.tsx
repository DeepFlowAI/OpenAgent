'use client'

import { useState, useCallback } from 'react'
import { Button } from '@/app/components/base/button'
import { Modal, ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useApiKeyList,
  useApiKeyFullById,
  useCreateApiKey,
  useRotateApiKey,
  useRevokeApiKey,
} from '@/service/use-api-key'
import type { ApiKeyItem } from '@/models/api-key'
import {
  IconPlus,
  IconCopy,
  IconRefresh,
  IconTrash,
  IconKey,
} from '@tabler/icons-react'

const AVAILABLE_SCOPES = ['chat', 'config'] as const

export default function ApiKeysPage() {
  const { toast } = useToast()
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApiKeyList(page)

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createdKeyValue, setCreatedKeyValue] = useState<string | null>(null)
  const [rotateTarget, setRotateTarget] = useState<ApiKeyItem | null>(null)
  const [rotatedKeyValue, setRotatedKeyValue] = useState<string | null>(null)
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyItem | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  return (
    <div className="px-12 py-10" style={{ padding: '40px 48px' }}>
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold text-foreground">API 密钥</h1>
        <p className="text-sm text-[#737373]">
          用于调用开放接口时的鉴权；请妥善保管，勿泄露给未授权方。
        </p>
      </div>

      <div className="my-6 h-px w-full bg-[#E4E4E7]" />

      <div className="mb-4 flex items-center justify-between">
        <div />
        <Button size="sm" onClick={() => setShowCreateModal(true)}>
          <IconPlus size={16} className="mr-1.5" />
          新建密钥
        </Button>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : items.length === 0 ? (
        <EmptyState onNew={() => setShowCreateModal(true)} />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
            <table className="w-full text-left text-sm">
              <thead className="h-12 bg-[#FAFAFA] text-[#737373]">
                <tr>
                  <th className="px-4 font-medium">名称</th>
                  <th className="px-4 font-medium">密钥</th>
                  <th className="px-4 font-medium">权限范围</th>
                  <th className="px-4 font-medium">创建时间</th>
                  <th className="px-4 font-medium">状态</th>
                  <th className="w-[120px] px-4 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <KeyRow
                    key={item.id}
                    item={item}
                    onRotate={() => setRotateTarget(item)}
                    onRevoke={() => setRevokeTarget(item)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-[#737373]">
              <span>共 {total} 条</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </Button>
                <span>{page} / {totalPages}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <CreateKeyModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={(keyValue) => {
          setShowCreateModal(false)
          setCreatedKeyValue(keyValue)
        }}
      />

      <KeyRevealModal
        open={!!createdKeyValue}
        keyValue={createdKeyValue ?? ''}
        title="密钥创建成功"
        onClose={() => setCreatedKeyValue(null)}
      />

      <RotateKeyModal
        target={rotateTarget}
        onClose={() => setRotateTarget(null)}
        onRotated={(keyValue) => {
          setRotateTarget(null)
          setRotatedKeyValue(keyValue)
        }}
      />

      <KeyRevealModal
        open={!!rotatedKeyValue}
        keyValue={rotatedKeyValue ?? ''}
        title="密钥轮换成功"
        onClose={() => setRotatedKeyValue(null)}
      />

      <RevokeKeyModal
        target={revokeTarget}
        onClose={() => setRevokeTarget(null)}
      />
    </div>
  )
}

// ── Table Row ──

function KeyRow({
  item,
  onRotate,
  onRevoke,
}: {
  item: ApiKeyItem
  onRotate: () => void
  onRevoke: () => void
}) {
  const { toast } = useToast()
  const copyFullMutation = useApiKeyFullById()
  const isRevoked = item.status === 'revoked'

  const handleCopyFullKey = async () => {
    if (isRevoked) return
    try {
      const { key_value } = await copyFullMutation.mutateAsync(item.id)
      await navigator.clipboard.writeText(key_value)
      toast('已复制到剪贴板', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <tr className="h-14 border-t border-[#E4E4E7] transition-colors hover:bg-[#FAFAFA]">
      <td className="px-4">
        <div className="flex flex-col">
          <span className="font-medium text-foreground">{item.name || '—'}</span>
          {item.description && (
            <span className="text-xs text-[#A1A1AA]">{item.description}</span>
          )}
        </div>
      </td>
      <td className="px-4">
        <div className="flex items-center gap-1.5">
          <code className="font-mono text-sm text-foreground">{item.masked_key}</code>
          <button
            type="button"
            disabled={isRevoked || copyFullMutation.isPending}
            className="rounded p-1 text-[#A1A1AA] transition-colors hover:bg-[#F0F0F0] hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
            onClick={handleCopyFullKey}
            title="复制完整密钥"
          >
            <IconCopy size={14} />
          </button>
        </div>
      </td>
      <td className="px-4">
        <div className="flex gap-1.5">
          {item.scopes.map((s) => (
            <ScopeTag key={s} scope={s} />
          ))}
        </div>
      </td>
      <td className="px-4 text-[#737373]">
        {item.created_at ? formatDateTime(item.created_at) : '—'}
      </td>
      <td className="px-4">
        <StatusBadge status={item.status} />
      </td>
      <td className="px-4 text-right">
        {!isRevoked && (
          <div className="flex items-center justify-end gap-2">
            <button
              className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#F0F0F0] hover:text-foreground"
              onClick={onRotate}
              title="轮换"
            >
              <IconRefresh size={16} />
            </button>
            <button
              className="rounded-md p-1.5 text-[#737373] transition-colors hover:bg-[#FEE2E2] hover:text-[#DC2626]"
              onClick={onRevoke}
              title="吊销"
            >
              <IconTrash size={16} />
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

// ── Create Key Modal ──

function CreateKeyModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (keyValue: string) => void
}) {
  const { toast } = useToast()
  const createMutation = useCreateApiKey()
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['chat'])
  const [description, setDescription] = useState('')

  const resetForm = useCallback(() => {
    setName('')
    setScopes(['chat'])
    setDescription('')
  }, [])

  const handleClose = () => {
    resetForm()
    onClose()
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast('请输入密钥名称', 'error')
      return
    }
    if (scopes.length === 0) {
      toast('至少选择一个权限范围', 'error')
      return
    }
    try {
      const result = await createMutation.mutateAsync({
        name: name.trim(),
        scopes,
        description: description.trim() || undefined,
      })
      resetForm()
      onCreated(result.key_value)
      toast('密钥已创建', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const toggleScope = (scope: string) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]
    )
  }

  return (
    <Modal open={open} onClose={handleClose} title="新建密钥" footer={
      <>
        <Button variant="outline" onClick={handleClose} disabled={createMutation.isPending}>
          取消
        </Button>
        <Button onClick={handleSubmit} loading={createMutation.isPending}>
          创建
        </Button>
      </>
    }>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">名称</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="便于区分环境或应用"
            className="h-10 rounded-lg border border-[#E4E4E7] bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1a1a1a]"
            maxLength={128}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">权限范围</label>
          <div className="flex gap-3">
            {AVAILABLE_SCOPES.map((scope) => (
              <label key={scope} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                  className="h-4 w-4 rounded border-[#D4D4D4] accent-[#1a1a1a]"
                />
                <ScopeTag scope={scope} />
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">
            说明 <span className="font-normal text-[#A1A1AA]">（可选）</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="备注用途"
            rows={2}
            className="rounded-lg border border-[#E4E4E7] bg-white px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1a1a1a] resize-none"
            maxLength={500}
          />
        </div>
      </div>
    </Modal>
  )
}

// ── Key Reveal Modal (create / rotate result) ──

function KeyRevealModal({
  open,
  keyValue,
  title,
  onClose,
}: {
  open: boolean
  keyValue: string
  title: string
  onClose: () => void
}) {
  const { toast } = useToast()

  const handleCopy = async () => {
    await navigator.clipboard.writeText(keyValue)
    toast('已复制到剪贴板', 'success')
  }

  return (
    <Modal open={open} onClose={onClose} title={title} footer={
      <Button onClick={onClose}>关闭</Button>
    }>
      <div className="flex flex-col gap-4">
        <div className="rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] p-3">
          <code className="break-all font-mono text-sm text-foreground">{keyValue}</code>
        </div>
        <Button variant="outline" size="sm" onClick={handleCopy} className="self-start">
          <IconCopy size={16} className="mr-1.5" />
          复制密钥
        </Button>
        <p className="text-xs text-[#DC2626]">
          请立即保存此密钥。关闭弹窗后仍可在列表中通过「复制」获取完整密钥。
        </p>
      </div>
    </Modal>
  )
}

// ── Rotate Key Modal ──

function RotateKeyModal({
  target,
  onClose,
  onRotated,
}: {
  target: ApiKeyItem | null
  onClose: () => void
  onRotated: (keyValue: string) => void
}) {
  const { toast } = useToast()
  const rotateMutation = useRotateApiKey()

  const handleConfirm = async () => {
    if (!target) return
    try {
      const result = await rotateMutation.mutateAsync(target.id)
      onRotated(result.key_value)
      toast('密钥已轮换', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <Modal
      open={!!target}
      onClose={onClose}
      title="轮换密钥"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={rotateMutation.isPending}>
            取消
          </Button>
          <Button onClick={handleConfirm} loading={rotateMutation.isPending}>
            确定轮换
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-[#737373]">
          轮换后旧密钥立即失效，使用该密钥的请求将无法通过鉴权。
        </p>
        <div className="rounded-lg bg-[#F5F5F5] p-3">
          <p className="font-medium text-foreground">{target?.name || '未命名'}</p>
          <p className="mt-1 font-mono text-xs text-[#737373]">{target?.masked_key}</p>
        </div>
      </div>
    </Modal>
  )
}

// ── Revoke Key Modal ──

function RevokeKeyModal({
  target,
  onClose,
}: {
  target: ApiKeyItem | null
  onClose: () => void
}) {
  const { toast } = useToast()
  const revokeMutation = useRevokeApiKey()

  const handleConfirm = async () => {
    if (!target) return
    try {
      await revokeMutation.mutateAsync(target.id)
      toast('密钥已吊销', 'success')
      onClose()
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  return (
    <ConfirmModal
      open={!!target}
      onClose={onClose}
      onConfirm={handleConfirm}
      title="吊销密钥"
      description={`确定吊销密钥「${target?.name || '未命名'}」（${target?.masked_key}）？吊销后该密钥将无法用于鉴权。`}
      confirmText="确定吊销"
      variant="destructive"
      loading={revokeMutation.isPending}
    />
  )
}

// ── Shared Components ──

function ScopeTag({ scope }: { scope: string }) {
  const colorMap: Record<string, string> = {
    chat: 'bg-[#DBEAFE] text-[#1D4ED8]',
    config: 'bg-[#FEF3C7] text-[#92400E]',
  }
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${colorMap[scope] ?? 'bg-[#F3F4F6] text-[#6B7280]'}`}
    >
      {scope}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-[#16A34A]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#16A34A]" />
        启用
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-sm text-[#A1A1AA]">
      <span className="h-1.5 w-1.5 rounded-full bg-[#A1A1AA]" />
      已吊销
    </span>
  )
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5]">
        <IconKey size={24} className="text-[#A1A1AA]" />
      </div>
      <p className="mt-4 text-sm text-[#737373]">尚无接入密钥，可创建用于第三方集成</p>
      <Button size="sm" className="mt-4" onClick={onNew}>
        <IconPlus size={16} className="mr-1.5" />
        新建密钥
      </Button>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E4E4E7]">
      <div className="h-12 bg-[#FAFAFA]" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex h-14 items-center gap-4 border-t border-[#E4E4E7] px-4">
          <div className="h-4 w-24 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-36 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-16 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-28 animate-pulse rounded bg-[#E4E4E7]" />
          <div className="h-4 w-12 animate-pulse rounded bg-[#E4E4E7]" />
        </div>
      ))}
    </div>
  )
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
