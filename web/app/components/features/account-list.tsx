'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconChevronLeft,
  IconChevronRight,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUsers,
  IconX,
} from '@tabler/icons-react'

import { Badge } from '@/app/components/base/badge'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import {
  useAccountCopy,
  type AccountCopy,
} from '@/app/components/features/account-copy'
import type { Account, AccountRole } from '@/models/account'
import { getErrorMessage } from '@/service/base'
import { useAccounts, useDeleteAccount } from '@/service/use-account'

const PER_PAGE_VALUES = [20, 50, 100] as const

export function AccountList() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const copy = useAccountCopy()
  const [deleteTarget, setDeleteTarget] = useState<Account | null>(null)
  const [listError, setListError] = useState('')
  const q = searchParams.get('q') ?? ''
  const roleValue = searchParams.get('role')
  const role: AccountRole | undefined =
    roleValue === 'admin' || roleValue === 'quality_inspector'
      ? roleValue
      : undefined
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const requestedPerPage = Number(searchParams.get('per_page'))
  const perPage = PER_PAGE_VALUES.includes(
    requestedPerPage as (typeof PER_PAGE_VALUES)[number]
  )
    ? (requestedPerPage as 20 | 50 | 100)
    : 20
  const [search, setSearch] = useState(q)

  useEffect(() => setSearch(q), [q])

  const updateQuery = (
    changes: Record<string, string | number | undefined>
  ) => {
    const next = new URLSearchParams(searchParams.toString())
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    router.replace(`/system/accounts?${next.toString()}`)
  }

  useEffect(() => {
    if (search === q) return
    const timer = window.setTimeout(
      () => updateQuery({ q: search.trim() || undefined, page: 1 }),
      300
    )
    return () => window.clearTimeout(timer)
  }, [q, search]) // eslint-disable-line react-hooks/exhaustive-deps

  const {
    data,
    error,
    isLoading,
    refetch,
  } = useAccounts({
    q: q || undefined,
    role,
    page,
    per_page: perPage,
  })
  useEffect(() => {
    let active = true
    if (!error) {
      setListError('')
      return
    }
    void getErrorMessage(error).then((message) => {
      if (active) setListError(message)
    })
    return () => {
      active = false
    }
  }, [error])
  const deleteMutation = useDeleteAccount()
  const pages = data?.pages ?? 0
  const pageNumbers = useMemo(() => {
    if (pages <= 1) return [1]
    const values = new Set([1, pages, page - 1, page, page + 1])
    return [...values]
      .filter((value) => value >= 1 && value <= pages)
      .sort((a, b) => a - b)
  }, [page, pages])

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast(copy.accountDeleted)
      setDeleteTarget(null)
      if ((data?.items.length ?? 0) === 1 && page > 1) {
        updateQuery({ page: page - 1 })
      }
    } catch (error) {
      const message = await getErrorMessage(error)
      toast(
        message === 'At least one administrator must remain'
          ? copy.lastAdmin
          : message ===
              'You cannot delete the account you are signed in with'
            ? copy.cannotDeleteCurrent
            : message,
        'error'
      )
    }
  }

  const hasFilters = Boolean(q || role)

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-auto px-12 py-10">
        <div>
          <h1 className="text-2xl font-bold tracking-[-0.5px] text-foreground">
            {copy.title}
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {copy.subtitle}
          </p>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <div className="relative min-w-0 flex-1">
            <IconSearch
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={copy.searchPlaceholder}
              className="h-11 w-full rounded-lg border border-input bg-background pl-10 pr-3 text-sm outline-none focus:border-foreground focus:ring-2 focus:ring-ring/10"
            />
          </div>
          <select
            value={role ?? ''}
            onChange={(event) =>
              updateQuery({
                role: event.target.value || undefined,
                page: 1,
              })
            }
            className="h-11 w-40 rounded-lg border border-input bg-background px-3 text-sm outline-none focus:border-foreground"
          >
            <option value="">{copy.allRoles}</option>
            <option value="admin">{copy.admin}</option>
            <option value="quality_inspector">
              {copy.qualityInspector}
            </option>
          </select>
          {hasFilters && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch('')
                updateQuery({ q: undefined, role: undefined, page: 1 })
              }}
            >
              <IconX size={16} className="mr-1.5" />
              {copy.clearFilters}
            </Button>
          )}
          <Button onClick={() => router.push('/system/accounts/new')}>
            <IconPlus size={16} className="mr-1.5" />
            {copy.newAccount}
          </Button>
        </div>

        <div className="mt-4 overflow-hidden rounded-lg border border-border">
          <table className="w-full table-fixed text-left text-sm">
            <thead className="h-12 bg-[#F8F8F8] text-[#404040]">
              <tr>
                <th className="px-6 font-semibold">{copy.username}</th>
                <th className="px-6 font-semibold">{copy.email}</th>
                <th className="w-[110px] px-6 font-semibold">{copy.role}</th>
                <th className="w-[150px] px-6 font-semibold">
                  {copy.agentAccess}
                </th>
                <th className="w-[170px] px-6 font-semibold">
                  {copy.knowledgeBaseAccess}
                </th>
                <th className="w-[160px] px-6 font-semibold">
                  {copy.updatedAt}
                </th>
                <th className="w-[90px] px-6 font-semibold">
                  {copy.actions}
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <tr key={index} className="h-14 border-t border-border">
                    <td colSpan={7} className="px-6">
                      <div className="h-4 animate-pulse rounded bg-muted" />
                    </td>
                  </tr>
                ))
              ) : listError ? (
                <tr>
                  <td colSpan={7}>
                    <div className="flex flex-col items-center py-16 text-center">
                      <p className="text-sm text-destructive">
                        {copy.listLoadFailed}
                      </p>
                      <Button
                        variant="outline"
                        className="mt-4"
                        onClick={() => void refetch()}
                      >
                        {copy.retry}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : data?.items.length ? (
                data.items.map((account) => (
                  <AccountRow
                    key={account.id}
                    account={account}
                    copy={copy}
                    onEdit={() =>
                      router.push(`/system/accounts/${account.id}`)
                    }
                    onDelete={() => setDeleteTarget(account)}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={7}>
                    <div className="flex flex-col items-center py-20 text-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                        <IconUsers size={22} />
                      </div>
                      <p className="mt-4 text-sm text-muted-foreground">
                        {hasFilters ? copy.noMatches : copy.noAccounts}
                      </p>
                      {!hasFilters && (
                        <Button
                          className="mt-4"
                          onClick={() => router.push('/system/accounts/new')}
                        >
                          {copy.newAccount}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex h-12 items-center justify-between border-t border-border px-8 text-sm text-muted-foreground">
        <div className="flex items-center gap-3">
          <span>{copy.total(data?.total ?? 0)}</span>
          <label className="flex items-center gap-2">
            {copy.perPage}
            <select
              value={perPage}
              onChange={(event) =>
                updateQuery({
                  per_page: Number(event.target.value),
                  page: 1,
                })
              }
              className="h-8 rounded-lg border border-border bg-background px-2 text-foreground"
            >
              {PER_PAGE_VALUES.map((value) => (
                <option key={value} value={value}>
                  {copy.perPageItems(value)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex items-center gap-1">
          <PageButton
            disabled={page <= 1}
            onClick={() => updateQuery({ page: page - 1 })}
          >
            <IconChevronLeft size={16} />
          </PageButton>
          {pageNumbers.map((value, index) => (
            <span key={value} className="flex items-center gap-1">
              {index > 0 && value - pageNumbers[index - 1] > 1 && (
                <span className="px-1">…</span>
              )}
              <PageButton
                active={value === page}
                onClick={() => updateQuery({ page: value })}
              >
                {value}
              </PageButton>
            </span>
          ))}
          <PageButton
            disabled={page >= Math.max(1, pages)}
            onClick={() => updateQuery({ page: page + 1 })}
          >
            <IconChevronRight size={16} />
          </PageButton>
        </div>
      </div>

      <DeleteAccountModal
        account={deleteTarget}
        copy={copy}
        loading={deleteMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}

function AccountRow({
  account,
  copy,
  onEdit,
  onDelete,
}: {
  account: Account
  copy: AccountCopy
  onEdit: () => void
  onDelete: () => void
}) {
  const deleteReason = account.is_current
    ? copy.cannotDeleteCurrent
    : account.is_last_admin
      ? copy.lastAdmin
      : undefined
  const accessLabel = (names: string[], admin: boolean) =>
    admin
      ? copy.all
      : names.length
        ? copy.granted(names.length)
        : copy.notGranted

  return (
    <tr className="h-14 border-t border-border hover:bg-[#FAFAFA]">
      <td className="truncate px-6 font-medium text-foreground">
        {account.username}
        {account.is_current && (
          <Badge className="ml-2">{copy.currentAccount}</Badge>
        )}
      </td>
      <td className="truncate px-6 text-muted-foreground">
        {account.email}
      </td>
      <td className="px-6">
        <Badge variant={account.role === 'admin' ? 'success' : 'default'}>
          {account.role === 'admin' ? copy.admin : copy.qualityInspector}
        </Badge>
      </td>
      <td
        className="px-6 text-muted-foreground"
        title={account.agent_names.join('、')}
      >
        {accessLabel(account.agent_names, account.role === 'admin')}
      </td>
      <td
        className="px-6 text-muted-foreground"
        title={account.knowledge_base_names.join('、')}
      >
        {accessLabel(
          account.knowledge_base_names,
          account.role === 'admin'
        )}
      </td>
      <td className="px-6 text-[13px] text-muted-foreground">
        {account.updated_at
          ? new Date(account.updated_at).toLocaleString()
          : '—'}
      </td>
      <td className="px-6">
        <div className="flex items-center gap-3">
          <button
            onClick={onEdit}
            title={copy.edit}
            aria-label={copy.editAccount}
          >
            <IconPencil size={18} className="text-[#404040]" />
          </button>
          <button
            disabled={Boolean(deleteReason)}
            onClick={onDelete}
            title={deleteReason ?? copy.delete}
            aria-label={copy.deleteAccount}
            className="disabled:cursor-not-allowed disabled:opacity-30"
          >
            <IconTrash size={18} className="text-[#404040]" />
          </button>
        </div>
      </td>
    </tr>
  )
}

function PageButton({
  active,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      {...props}
      className={`flex h-8 min-w-8 items-center justify-center rounded-md px-2 disabled:text-[#D4D4D8] ${
        active ? 'bg-foreground text-background' : 'hover:bg-muted'
      }`}
    />
  )
}

function DeleteAccountModal({
  account,
  copy,
  loading,
  onClose,
  onConfirm,
}: {
  account: Account | null
  copy: AccountCopy
  loading: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Modal
      open={Boolean(account)}
      onClose={onClose}
      title={copy.deleteAccount}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {copy.cancel}
          </Button>
          <Button variant="destructive" onClick={onConfirm} loading={loading}>
            {copy.confirmDelete}
          </Button>
        </>
      }
    >
      <p className="text-sm leading-relaxed text-muted-foreground">
        {copy.deleteBody}
      </p>
      <dl className="mt-4 grid grid-cols-[72px_1fr] gap-y-2 rounded-lg bg-muted p-4 text-sm">
        <dt className="text-muted-foreground">{copy.username}</dt>
        <dd>{account?.username}</dd>
        <dt className="text-muted-foreground">{copy.role}</dt>
        <dd>
          {account?.role === 'admin' ? copy.admin : copy.qualityInspector}
        </dd>
        <dt className="text-muted-foreground">{copy.email}</dt>
        <dd>{account?.email}</dd>
      </dl>
    </Modal>
  )
}
