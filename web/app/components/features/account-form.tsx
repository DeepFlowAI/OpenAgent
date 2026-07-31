'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconCopy,
  IconEye,
  IconEyeOff,
  IconRefresh,
} from '@tabler/icons-react'
import type { ZodIssue } from 'zod'

import { Alert } from '@/app/components/base/alert'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Modal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { useAccountCopy } from '@/app/components/features/account-copy'
import { ResourceMultiSelect } from '@/app/components/features/resource-multi-select'
import type { AccountPayload, AccountRole } from '@/models/account'
import { getErrorMessage } from '@/service/base'
import {
  useAccount,
  useAccountResourceOptions,
  useCreateAccount,
  useUpdateAccount,
} from '@/service/use-account'
import { useUnsavedChangesGuard } from '@/utils/use-unsaved-changes'
import {
  createAccountSchema,
  updateAccountSchema,
} from '@/utils/validators'

type AccountFormState = {
  username: string
  email: string
  role: AccountRole
  password: string
  agent_ids: number[]
  knowledge_base_ids: number[]
}

const EMPTY_FORM: AccountFormState = {
  username: '',
  email: '',
  role: 'quality_inspector',
  password: '',
  agent_ids: [],
  knowledge_base_ids: [],
}

function generatePassword(): string {
  const uppercase = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const lowercase = 'abcdefghijkmnopqrstuvwxyz'
  const digits = '23456789'
  const all = uppercase + lowercase + digits
  const randomIndex = (length: number) => {
    const values = new Uint32Array(1)
    crypto.getRandomValues(values)
    return values[0] % length
  }
  const characters = [
    uppercase[randomIndex(uppercase.length)],
    lowercase[randomIndex(lowercase.length)],
    digits[randomIndex(digits.length)],
  ]
  while (characters.length < 16) {
    characters.push(all[randomIndex(all.length)])
  }
  for (let index = characters.length - 1; index > 0; index -= 1) {
    const swapIndex = randomIndex(index + 1)
    ;[characters[index], characters[swapIndex]] = [
      characters[swapIndex],
      characters[index],
    ]
  }
  return characters.join('')
}

export function AccountForm({ accountId }: { accountId?: number }) {
  const router = useRouter()
  const { toast } = useToast()
  const copy = useAccountCopy()
  const isEdit = accountId !== undefined
  const {
    data: account,
    error: accountError,
    isLoading: accountLoading,
    refetch: refetchAccount,
  } = useAccount(accountId ?? null)
  const {
    data: options,
    error: optionsError,
    isLoading: optionsLoading,
    refetch: refetchOptions,
  } = useAccountResourceOptions()
  const createMutation = useCreateAccount()
  const updateMutation = useUpdateAccount()
  const [form, setForm] = useState<AccountFormState>(EMPTY_FORM)
  const [baseline, setBaseline] = useState<AccountFormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [pendingHref, setPendingHref] = useState<string | null>(null)
  const initializedId = useRef<number | null>(null)

  useEffect(() => {
    if (!isEdit || !account || initializedId.current === account.id) return
    const initial: AccountFormState = {
      username: account.username,
      email: account.email,
      role: account.role,
      password: '',
      agent_ids: account.agent_ids,
      knowledge_base_ids: account.knowledge_base_ids,
    }
    initializedId.current = account.id
    setForm(initial)
    setBaseline(initial)
  }, [account, isEdit])

  const dirty = useMemo(
    () => JSON.stringify(form) !== JSON.stringify(baseline),
    [baseline, form]
  )
  useUnsavedChangesGuard(dirty)

  useEffect(() => {
    if (!dirty) return
    const intercept = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest('a')
      if (!anchor || anchor.target === '_blank') return
      const url = new URL(anchor.href, window.location.href)
      if (url.origin !== window.location.origin) return
      event.preventDefault()
      event.stopPropagation()
      setPendingHref(`${url.pathname}${url.search}${url.hash}`)
    }
    document.addEventListener('click', intercept, true)
    return () => document.removeEventListener('click', intercept, true)
  }, [dirty])

  const setField = <K extends keyof AccountFormState>(
    field: K,
    value: AccountFormState[K]
  ) => {
    setForm((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: '' }))
    setApiError('')
  }

  const validateField = (field: keyof AccountFormState) => {
    const schema = isEdit ? updateAccountSchema : createAccountSchema
    const result = schema.safeParse(form)
    if (result.success) {
      setErrors((current) => ({ ...current, [field]: '' }))
      return
    }
    const issue = result.error.issues.find(
      (item) => item.path[0] === field
    )
    setErrors((current) => ({
      ...current,
      [field]: issue ? validationMessage(issue.message, copy) : '',
    }))
  }

  const submit = async () => {
    const schema = isEdit ? updateAccountSchema : createAccountSchema
    const result = schema.safeParse(form)
    if (!result.success) {
      const nextErrors: Record<string, string> = {}
      result.error.issues.forEach((issue: ZodIssue) => {
        const field = String(issue.path[0])
        if (!nextErrors[field]) {
          nextErrors[field] = validationMessage(issue.message, copy)
        }
      })
      setErrors(nextErrors)
      const first = Object.keys(nextErrors)[0]
      document
        .querySelector<HTMLElement>(
          `[data-account-field="${first}"] input, ` +
            `[data-account-field="${first}"] select`
        )
        ?.focus()
      return
    }

    const payload: AccountPayload = {
      username: result.data.username,
      email: result.data.email,
      role: result.data.role,
      password: result.data.password || undefined,
      agent_ids:
        result.data.role === 'admin' ? [] : result.data.agent_ids,
      knowledge_base_ids:
        result.data.role === 'admin'
          ? []
          : result.data.knowledge_base_ids,
    }
    try {
      if (isEdit && accountId) {
        const saved = await updateMutation.mutateAsync({
          id: accountId,
          data: payload,
        })
        const savedForm: AccountFormState = {
          username: saved.username,
          email: saved.email,
          role: saved.role,
          password: '',
          agent_ids: saved.agent_ids,
          knowledge_base_ids: saved.knowledge_base_ids,
        }
        setForm(savedForm)
        setBaseline(savedForm)
        toast(copy.accountSaved)
      } else {
        await createMutation.mutateAsync({
          ...payload,
          password: result.data.password || '',
        })
        toast(copy.accountCreated)
        router.push('/system/accounts')
      }
    } catch (error) {
      const message = await getErrorMessage(error)
      if (message === 'This username already exists') {
        setErrors((current) => ({
          ...current,
          username: copy.duplicateUsername,
        }))
      } else if (message === 'This email is already in use') {
        setErrors((current) => ({
          ...current,
          email: copy.duplicateEmail,
        }))
      } else if (
        message === 'At least one administrator must remain'
      ) {
        setErrors((current) => ({
          ...current,
          role: copy.lastAdmin,
        }))
      } else if (
        message ===
        'You cannot downgrade the account you are signed in with'
      ) {
        setErrors((current) => ({
          ...current,
          role: copy.currentCannotDowngrade,
        }))
      } else {
        setApiError(message)
      }
    }
  }

  if ((isEdit && accountLoading) || optionsLoading) {
    return (
      <div className="p-10">
        <div className="h-10 animate-pulse rounded bg-muted" />
        <div className="mt-8 h-80 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (accountError || optionsError) {
    return (
      <div className="flex h-full items-center justify-center px-10">
        <Alert variant="destructive">
          <div className="flex items-center gap-4">
            <span>{copy.formLoadFailed}</span>
            <Button
              variant="outline"
              onClick={() => {
                if (accountError) void refetchAccount()
                if (optionsError) void refetchOptions()
              }}
            >
              {copy.retry}
            </Button>
          </div>
        </Alert>
      </div>
    )
  }

  if (isEdit && !account) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {copy.accountNotFound}
      </div>
    )
  }

  const isAdmin = form.role === 'admin'
  const saving = createMutation.isPending || updateMutation.isPending
  const cannotDowngrade =
    account?.role === 'admin' &&
    (account.is_current || account.is_last_admin)

  return (
    <div className="min-h-full bg-background">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-6 py-3 backdrop-blur-sm">
        <button
          type="button"
          onClick={() =>
            dirty
              ? setPendingHref('/system/accounts')
              : router.push('/system/accounts')
          }
          className="flex items-center gap-2 text-base font-semibold text-foreground"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          {isEdit
            ? copy.editTitle(account?.username ?? '')
            : copy.newAccount}
        </button>
        <Button
          onClick={submit}
          disabled={!dirty || saving}
          loading={saving}
        >
          {copy.save}
        </Button>
      </div>

      <div className="max-w-[680px] space-y-8 px-10 py-8">
        <FormSection title={copy.basicInfo}>
          <div data-account-field="username">
            <Input
              label={copy.username}
              required
              value={form.username}
              onChange={(event) => setField('username', event.target.value)}
              onBlur={() => validateField('username')}
              placeholder={copy.usernamePlaceholder}
              maxLength={32}
              error={errors.username}
            />
          </div>
          <div data-account-field="email">
            <Input
              label={copy.email}
              type="email"
              required
              value={form.email}
              onChange={(event) => setField('email', event.target.value)}
              onBlur={() => validateField('email')}
              placeholder={copy.emailPlaceholder}
              maxLength={128}
              error={errors.email}
            />
          </div>
          <div className="space-y-1.5" data-account-field="role">
            <label htmlFor="account-role" className="text-sm font-medium">
              {copy.role}
              <span className="ml-0.5 text-destructive">*</span>
            </label>
            <select
              id="account-role"
              value={form.role}
              onChange={(event) =>
                setField('role', event.target.value as AccountRole)
              }
              onBlur={() => validateField('role')}
              className="h-11 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:border-foreground"
            >
              <option value="admin">{copy.admin}</option>
              <option
                value="quality_inspector"
                disabled={cannotDowngrade}
              >
                {copy.qualityInspector}
              </option>
            </select>
            {errors.role && (
              <p className="text-xs text-destructive">{errors.role}</p>
            )}
            {cannotDowngrade && (
              <p className="text-xs text-muted-foreground">
                {account?.is_current
                  ? copy.currentCannotDowngrade
                  : copy.lastAdmin}
              </p>
            )}
          </div>
          <PasswordField
            value={form.password}
            error={errors.password}
            isEdit={isEdit}
            visible={showPassword}
            onVisibilityChange={() => setShowPassword((current) => !current)}
            onChange={(value) => setField('password', value)}
            onBlur={() => validateField('password')}
            onGenerate={() => setField('password', generatePassword())}
            onCopy={async () => {
              await navigator.clipboard.writeText(form.password)
              toast(copy.passwordCopied)
            }}
          />
        </FormSection>

        <FormSection title={copy.resourceAccess}>
          <ResourceMultiSelect
            label={copy.agentAccess}
            options={options?.agents ?? []}
            value={form.agent_ids}
            onChange={(value) => setField('agent_ids', value)}
            disabled={isAdmin}
            disabledText={copy.allAgents}
          />
          <ResourceMultiSelect
            label={copy.knowledgeBaseAccess}
            options={options?.knowledge_bases ?? []}
            value={form.knowledge_base_ids}
            onChange={(value) => setField('knowledge_base_ids', value)}
            disabled={isAdmin}
            disabledText={copy.allKnowledgeBases}
          />
        </FormSection>

        {apiError && <Alert variant="destructive">{apiError}</Alert>}
      </div>

      <Modal
        open={pendingHref !== null}
        onClose={() => setPendingHref(null)}
        title={copy.leaveTitle}
        footer={
          <>
            <Button variant="outline" onClick={() => setPendingHref(null)}>
              {copy.stay}
            </Button>
            <Button
              onClick={() => {
                const href = pendingHref
                setBaseline(form)
                setPendingHref(null)
                if (href) router.push(href)
              }}
            >
              {copy.leave}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{copy.leaveBody}</p>
      </Modal>
    </div>
  )
}

function FormSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section>
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <div className="mt-5 space-y-6">{children}</div>
    </section>
  )
}

function PasswordField({
  value,
  error,
  isEdit,
  visible,
  onVisibilityChange,
  onChange,
  onBlur,
  onGenerate,
  onCopy,
}: {
  value: string
  error?: string
  isEdit: boolean
  visible: boolean
  onVisibilityChange: () => void
  onChange: (value: string) => void
  onBlur: () => void
  onGenerate: () => void
  onCopy: () => void
}) {
  const copy = useAccountCopy()

  return (
    <div className="space-y-1.5" data-account-field="password">
      <label htmlFor="account-password" className="text-sm font-medium">
        {isEdit ? copy.newPassword : copy.initialPassword}
        {!isEdit && <span className="ml-0.5 text-destructive">*</span>}
      </label>
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <input
            id="account-password"
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onBlur={onBlur}
            placeholder={
              isEdit
                ? copy.newPasswordPlaceholder
                : copy.initialPasswordPlaceholder
            }
            maxLength={32}
            className={`h-11 w-full rounded-lg border bg-background px-3 pr-10 text-sm outline-none focus:ring-2 ${
              error
                ? 'border-destructive focus:ring-destructive/10'
                : 'border-input focus:border-foreground focus:ring-ring/10'
            }`}
          />
          <button
            type="button"
            onClick={onVisibilityChange}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-label={
              visible ? copy.hidePassword : copy.showPassword
            }
          >
            {visible ? <IconEyeOff size={18} /> : <IconEye size={18} />}
          </button>
        </div>
        <Button type="button" variant="outline" onClick={onGenerate}>
          <IconRefresh size={16} className="mr-1.5" />
          {copy.generate}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={!value}
          onClick={onCopy}
          aria-label={copy.copyPassword}
        >
          <IconCopy size={16} />
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">
        {copy.passwordHint}
      </p>
    </div>
  )
}

function validationMessage(
  message: string,
  copy: ReturnType<typeof useAccountCopy>
): string {
  const messages: Record<string, string> = {
    请输入用户名: copy.validation.usernameRequired,
    '用户名为 4–32 位，仅支持字母、数字、点、下划线和短横线':
      copy.validation.usernameInvalid,
    请输入邮箱: copy.validation.emailRequired,
    请输入有效的邮箱地址: copy.validation.emailInvalid,
    '密码为 8–32 位，需包含大小写字母和数字':
      copy.validation.passwordInvalid,
  }
  return messages[message] ?? message
}
