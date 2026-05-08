'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { Input } from '@/app/components/base/input'
import { Textarea } from '@/app/components/base/textarea'
import { Modal, ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage, uploadImage } from '@/service/base'
import {
  useHelpCenter,
  useUpdateHelpCenter,
  useCheckSlug,
} from '@/service/use-help-center'
import { SLUG_REGEX } from '@/models/help-center'
import { useUnsavedChangesGuard } from '@/utils/use-unsaved-changes'
import {
  IconArrowLeft,
  IconCopy,
  IconImageInPicture,
  IconLoader2,
  IconX,
} from '@tabler/icons-react'
import { TabSection } from './_components/tab-section'

type FormState = {
  name: string
  description: string
  publicSlug: string
  siteName: string
  publisherLogoUrl: string
}

const EMPTY: FormState = {
  name: '',
  description: '',
  publicSlug: '',
  siteName: '',
  publisherLogoUrl: '',
}

export default function HelpCenterDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { toast } = useToast()
  const idNum = Number(params?.id)
  const { data, isLoading, isError } = useHelpCenter(
    Number.isFinite(idNum) ? idNum : null
  )
  const updateMutation = useUpdateHelpCenter()
  const checkSlugMutation = useCheckSlug()

  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({})
  const [slugAvailable, setSlugAvailable] = useState<boolean | null>(null)
  const [showSlugConfirm, setShowSlugConfirm] = useState(false)
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)
  const [pendingNav, setPendingNav] = useState<string | null>(null)
  const slugCheckTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Resolve the visitor root URL from the browser's actual origin, not the
  // backend's PUBLIC_DOCS_HOST. The host the admin is currently using is
  // also where they can reach the visitor site (admin and /hc/* live in the
  // same Next.js app), so this is the URL they would actually share. We
  // populate it after mount to avoid SSR / hydration mismatch.
  const [origin, setOrigin] = useState<string>('')
  useEffect(() => {
    setOrigin(window.location.origin)
  }, [])
  const rootUrl = useMemo(() => {
    if (!origin || !data?.public_slug) return null
    return `${origin}/hc/${data.public_slug}`
  }, [origin, data?.public_slug])

  const pristine: FormState = useMemo(() => {
    if (!data) return EMPTY
    return {
      name: data.name ?? '',
      description: data.description ?? '',
      publicSlug: data.public_slug ?? '',
      siteName: data.site_name ?? '',
      publisherLogoUrl: data.publisher_logo_url ?? '',
    }
  }, [data])

  // Reset local form to pristine whenever the server snapshot changes
  // (initial load, after a successful save).
  useEffect(() => {
    if (data) setForm(pristine)
  }, [pristine, data])

  const dirty = useMemo(
    () => JSON.stringify(form) !== JSON.stringify(pristine),
    [form, pristine]
  )

  useUnsavedChangesGuard(dirty)

  // Debounced slug availability check — purely UX sugar, server re-validates on save.
  useEffect(() => {
    if (slugCheckTimer.current) clearTimeout(slugCheckTimer.current)
    setSlugAvailable(null)
    const slug = form.publicSlug.trim()
    if (!slug || !SLUG_REGEX.test(slug) || slug.length < 3) return
    if (slug === pristine.publicSlug) return

    slugCheckTimer.current = setTimeout(() => {
      checkSlugMutation
        .mutateAsync({ slug, excludeId: data?.id })
        .then((r) => setSlugAvailable(r.available))
        .catch(() => setSlugAvailable(null))
    }, 300)

    return () => {
      if (slugCheckTimer.current) clearTimeout(slugCheckTimer.current)
    }
    // checkSlugMutation is stable; intentionally left out of deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.publicSlug, data?.id, pristine.publicSlug])

  const validate = (): Partial<Record<keyof FormState, string>> => {
    const next: Partial<Record<keyof FormState, string>> = {}

    if (!form.name.trim()) next.name = '请输入名称'
    else if (form.name.length > 64) next.name = '不超过 64 个字符'

    const slug = form.publicSlug.trim()
    if (slug) {
      if (slug.length < 3 || slug.length > 48) {
        next.publicSlug = '长度 3–48 个字符'
      } else if (!SLUG_REGEX.test(slug)) {
        next.publicSlug = '仅允许小写字母、数字、连字符'
      } else if (slugAvailable === false) {
        next.publicSlug = '该标识已被使用'
      }
    }

    if (slug && !form.siteName.trim()) {
      next.siteName = '设置公开标识后必填'
    }

    return next
  }

  const buildPayload = () => {
    return {
      name: form.name.trim(),
      description: form.description.trim() || null,
      public_slug: form.publicSlug.trim() || null,
      site_name: form.siteName.trim() || null,
      publisher_logo_url: form.publisherLogoUrl.trim() || null,
    }
  }

  const performSave = async () => {
    if (!data) return
    try {
      await updateMutation.mutateAsync({
        id: data.id,
        payload: buildPayload(),
      })
      toast('已保存', 'success')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const handleSave = async () => {
    const v = validate()
    setErrors(v)
    if (Object.keys(v).length > 0) {
      toast('请检查表单填写', 'error')
      return
    }
    // Slug change on an already-published Help Center is a destructive op.
    const slugChanged =
      pristine.publicSlug !== '' && form.publicSlug.trim() !== pristine.publicSlug
    if (slugChanged) {
      setShowSlugConfirm(true)
      return
    }
    await performSave()
  }

  const handleBack = () => {
    if (dirty) {
      setPendingNav('/system/help-centers')
      setShowLeaveConfirm(true)
      return
    }
    router.push('/system/help-centers')
  }

  if (isLoading) return <DetailSkeleton />
  if (isError || !data) {
    return (
      <div style={{ padding: '40px 48px' }}>
        <p className="text-sm text-[#737373]">加载失败或不存在。</p>
        <Link href="/system/help-centers">
          <Button variant="outline" size="sm" className="mt-4">
            返回列表
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#E4E4E7] bg-white px-12 py-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex items-center gap-1 text-sm text-[#737373] transition-colors hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            返回列表
          </button>
          <h1 className="text-lg font-semibold text-foreground">
            编辑：{data.name}
          </h1>
        </div>
        <Button
          onClick={handleSave}
          loading={updateMutation.isPending}
          disabled={!dirty}
        >
          保存
        </Button>
      </div>

      <div className="flex-1 overflow-auto" style={{ padding: '40px 48px' }}>
        {/* ── Basic info ── */}
        <Section title="基本信息">
          <div className="flex flex-col gap-6">
            <Input
              label="名称"
              required
              value={form.name}
              maxLength={64}
              error={errors.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Textarea
              label="描述"
              value={form.description}
              maxLength={500}
              placeholder="选填，用于内部识别或列表展示"
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
        </Section>

        <div className="my-6 h-px w-full bg-[#E4E4E7]" />

        {/* ── Public access ── */}
        <Section
          title="公开访问"
          description="发布后访客通过下方根链接进入站点。本期仅支持平台默认文档域。"
        >
          <div className="flex flex-col gap-6">
            <Input
              label="公开地址标识"
              required={!!form.publicSlug}
              value={form.publicSlug}
              maxLength={48}
              placeholder="例如 product-help"
              error={errors.publicSlug}
              hint={slugHint(form.publicSlug, slugAvailable, pristine.publicSlug)}
              onChange={(e) =>
                setForm({ ...form, publicSlug: e.target.value })
              }
            />

            <Input
              label="站点名称"
              required={!!form.publicSlug}
              value={form.siteName}
              maxLength={64}
              placeholder="对外展示的站点名称（用于浏览器标题等）"
              error={errors.siteName}
              onChange={(e) => setForm({ ...form, siteName: e.target.value })}
            />

            <PublisherLogoUpload
              value={form.publisherLogoUrl}
              error={errors.publisherLogoUrl}
              onChange={(url) => setForm({ ...form, publisherLogoUrl: url })}
              onError={(msg) => {
                setErrors({ ...errors, publisherLogoUrl: msg })
                toast(msg, 'error')
              }}
            />

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-[#1a1a1a]">
                默认访客根链接
              </span>
              <PublicRootUrl
                url={rootUrl}
                onCopied={() => toast('已复制', 'success')}
              />
              <p className="text-xs text-[#A3A3A3]">
                链接基于您当前访问的域名生成，可直接分享。
              </p>
            </div>
          </div>
        </Section>

        <div className="my-6 h-px w-full bg-[#E4E4E7]" />

        {/* ── Content tabs ── */}
        <Section
          title="内容版块"
          description="为帮助中心配置一个或多个对外展示的内容版块。每个版块绑定一个知识库，并可叠加 doc-meta 固定筛选。"
        >
          <TabSection helpCenterId={data.id} />
        </Section>
      </div>

      {/* ── Slug change confirmation (危险操作) ── */}
      <ConfirmModal
        open={showSlugConfirm}
        onClose={() => setShowSlugConfirm(false)}
        onConfirm={async () => {
          setShowSlugConfirm(false)
          await performSave()
        }}
        title="修改公开地址标识"
        description="修改后旧的公开地址将立即失效（暂不提供 301 跳转），外链与搜索收录会受影响，请确认是否继续。"
        confirmText="确认修改"
        variant="destructive"
        loading={updateMutation.isPending}
      />

      {/* ── Unsaved leave confirmation ── */}
      <ConfirmModal
        open={showLeaveConfirm}
        onClose={() => {
          setShowLeaveConfirm(false)
          setPendingNav(null)
        }}
        onConfirm={() => {
          setShowLeaveConfirm(false)
          if (pendingNav) router.push(pendingNav)
          setPendingNav(null)
        }}
        title="离开此页？"
        description="有未保存的修改，确定离开吗？"
        confirmText="离开"
        cancelText="留在页面"
      />
    </div>
  )
}

// ── Layout helpers ──

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-4 flex flex-col gap-1">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {description && (
          <p className="text-sm text-[#737373]">{description}</p>
        )}
      </div>
      {children}
    </section>
  )
}

function PublicRootUrl({
  url,
  onCopied,
}: {
  url: string | null
  onCopied: () => void
}) {
  if (!url) {
    return (
      <div className="rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] px-3 py-2.5 text-sm text-[#A1A1AA]">
        保存公开地址标识后展示完整链接。
      </div>
    )
  }
  const handleCopy = async () => {
    await navigator.clipboard.writeText(url)
    onCopied()
  }
  return (
    <div className="flex items-center gap-2 rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] px-3 py-2.5">
      <code className="flex-1 break-all font-mono text-sm text-foreground">
        {url}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded p-1.5 text-[#737373] transition-colors hover:bg-white hover:text-foreground"
        title="复制"
      >
        <IconCopy size={16} />
      </button>
    </div>
  )
}

function PublisherLogoUpload({
  value,
  error,
  onChange,
  onError,
}: {
  value: string
  error?: string
  onChange: (url: string) => void
  onError: (msg: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setUploading(true)
    try {
      const { url } = await uploadImage(file)
      onChange(url)
    } catch (err) {
      const msg = await getErrorMessage(err)
      onError(msg)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-[#1a1a1a]">
        发布方 Logo
      </span>
      {value ? (
        <div className="group relative inline-flex h-[72px] w-fit items-center rounded-lg border border-[#E4E4E7] bg-white px-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={value}
            alt=""
            className="h-10 w-auto max-w-none object-contain"
          />
          <button
            type="button"
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#1A1A1A] text-white opacity-0 transition-opacity group-hover:opacity-100"
            onClick={() => onChange('')}
          >
            <IconX size={12} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="flex h-[72px] w-[120px] items-center justify-center rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] transition-colors hover:border-[#A1A1AA]"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? (
            <IconLoader2 size={24} className="animate-spin text-[#A1A1AA]" />
          ) : (
            <IconImageInPicture size={24} className="text-[#A1A1AA]" />
          )}
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFile}
      />
      <p className={error ? 'text-xs text-red-500' : 'text-xs text-[#A3A3A3]'}>
        {error || '选填，用于访客站顶栏、浏览器图标和搜索引擎 publisher 标识。'}
      </p>
    </div>
  )
}

function slugHint(
  slug: string,
  available: boolean | null,
  pristineSlug: string
): string | undefined {
  const trimmed = slug.trim()
  if (!trimmed) return '仅允许小写字母、数字、连字符；3–48 个字符'
  if (trimmed === pristineSlug) return undefined
  if (available === true) return '可用'
  return undefined
}

function DetailSkeleton() {
  return (
    <div style={{ padding: '40px 48px' }}>
      <div className="h-8 w-48 animate-pulse rounded bg-[#E4E4E7]" />
      <div className="mt-8 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-12 w-full max-w-[640px] animate-pulse rounded-lg bg-[#E4E4E7]"
          />
        ))}
      </div>
    </div>
  )
}
