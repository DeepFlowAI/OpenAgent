'use client'

import { use, useMemo, useState } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { cn } from '@/utils/classnames'
import { useDocument, useSlices } from '@/service/use-document'
import {
  IconArrowLeft,
  IconCode,
  IconFileText,
  IconStack2,
  IconBook,
  IconFile,
  IconDownload,
  IconExternalLink,
} from '@tabler/icons-react'

const tabs = [
  { key: 'data-md', label: '数据 Markdown', icon: IconCode },
  { key: 'doc-meta', label: 'doc-meta', icon: IconFileText },
  { key: 'slices', label: '切片', icon: IconStack2 },
  { key: 'read-md', label: '阅读 Markdown', icon: IconBook },
  { key: 'original', label: '原文档', icon: IconFile },
] as const

type TabKey = (typeof tabs)[number]['key']

export default function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string; docId: string }>
}) {
  const { id, docId } = use(params)
  const kbId = Number(id)
  const documentId = Number(docId)
  const [activeTab, setActiveTab] = useState<TabKey>('data-md')

  const { data: doc, isLoading } = useDocument(kbId, documentId)
  const { data: slicesData } = useSlices(kbId, documentId)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (!doc) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">文档不存在</p>
      </div>
    )
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleString('zh-CN')
  }

  return (
    <div className="flex h-full flex-col">
      {/* Top Bar — 56px, back arrow + title */}
      <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-6">
        <Link
          href={`/knowledge-space/${kbId}`}
          className="flex items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
        >
          <IconArrowLeft size={20} />
        </Link>
        <h1 className="text-base font-semibold text-foreground">
          {doc.title || doc.file_path}
        </h1>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="space-y-6 px-8 pt-8">
          {/* Metadata Card */}
          <div className="flex gap-8 rounded-lg bg-secondary px-5 py-4">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">标题</span>
              <span className="text-sm text-foreground">{doc.title || '(无标题)'}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">路径</span>
              <span className="text-sm text-muted-foreground/80">{doc.file_path}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">切片数</span>
              <span className="text-sm text-foreground">{doc.slice_count}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">更新时间</span>
              <span className="text-sm text-muted-foreground/80">{formatDate(doc.updated_at)}</span>
            </div>
          </div>

          {/* Tab Bar with icons */}
          <div className="border-b border-border">
            <div className="flex">
              {tabs.map((tab) => {
                const Icon = tab.icon
                const isActive = activeTab === tab.key
                return (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={cn(
                      'flex items-center gap-1.5 border-b-2 px-4 py-3 text-[13px] font-medium transition-colors',
                      isActive
                        ? 'border-foreground text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    )}
                  >
                    <Icon size={16} />
                    {tab.label}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Tab Content */}
        <div className="px-8 py-6">
          {activeTab === 'data-md' && <DataMarkdownTab content={doc.markdown_content} />}
          {activeTab === 'doc-meta' && <DocMetaTab meta={doc.doc_meta} />}
          {activeTab === 'slices' && <SlicesTab slices={slicesData?.items ?? []} />}
          {activeTab === 'read-md' && <ReadMarkdownTab content={doc.markdown_content} />}
          {activeTab === 'original' && (
            <OriginalTab docMeta={doc.doc_meta} sourceUrl={doc.source_url} />
          )}
        </div>
      </div>
    </div>
  )
}

function DataMarkdownTab({ content }: { content: string | null }) {
  const { lines, gutterCh } = useMemo(() => {
    if (!content) return { lines: [] as string[], gutterCh: 2 }
    const ls = content.split(/\r?\n/)
    return {
      lines: ls,
      gutterCh: Math.max(2, String(ls.length).length) + 2,
    }
  }, [content])

  if (!content) return <p className="text-sm text-muted-foreground">无内容</p>

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between bg-[#1e1e1e] px-4 py-2">
        <span className="text-xs text-gray-400">data.md</span>
      </div>
      <div className="overflow-auto bg-[#1e1e1e] p-4 text-sm leading-relaxed">
        <div className="font-mono">
          {lines.map((line, i) => (
            <div key={i} className="flex min-w-0">
              <span
                className="shrink-0 select-none border-r border-gray-700 pr-3 text-right text-xs text-gray-500 tabular-nums"
                style={{ width: `${gutterCh}ch` }}
              >
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words pl-3 text-gray-200">
                {line}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function DocMetaTab({ meta }: { meta: Record<string, unknown> | null }) {
  if (!meta || Object.keys(meta).length === 0) {
    return <p className="text-sm text-muted-foreground">无 doc-meta 数据</p>
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-[#FAFAFA]">
            <th className="px-4 py-3 text-left font-medium text-muted-foreground w-48">字段</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">类型</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">值</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(meta).map(([key, value]) => (
            <tr key={key} className="border-b border-border last:border-b-0">
              <td className="px-4 py-2 font-medium text-foreground">{key}</td>
              <td className="px-4 py-2 text-muted-foreground">{typeof value}</td>
              <td className="px-4 py-2 text-foreground">
                {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SlicesTab({
  slices,
}: {
  slices: Array<{
    id: number; content: string; toc_path: string[] | null
    slice_meta: Record<string, unknown> | null; slice_order: number
  }>
}) {
  if (slices.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无切片</p>
  }
  return (
    <div className="space-y-3">
      {slices.map((slice) => (
        <div key={slice.id} className="rounded-lg border border-border p-4">
          <div className="mb-2 flex items-center gap-3">
            <span className="rounded bg-[#F5F5F5] px-2 py-0.5 text-xs font-medium text-foreground">
              {slice.slice_order}
            </span>
            {slice.toc_path && slice.toc_path.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {slice.toc_path.join(' > ')}
              </span>
            )}
          </div>
          <pre className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">
            {slice.content}
          </pre>
          {slice.slice_meta && Object.keys(slice.slice_meta).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(slice.slice_meta).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
                >
                  {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const MarkdownPreview = dynamic(() => import('@uiw/react-markdown-preview'), {
  ssr: false,
  loading: () => <p className="text-sm text-muted-foreground">加载中...</p>,
})

const PdfViewerEmbed = dynamic(
  () =>
    import('@/app/components/features/pdf-viewer-embed').then(
      (m) => m.PdfViewerEmbed,
    ),
  {
    ssr: false,
    loading: () => (
      <p className="py-12 text-center text-sm text-muted-foreground">
        加载 PDF 查看器…
      </p>
    ),
  },
)

function ReadMarkdownTab({ content }: { content: string | null }) {
  if (!content) return <p className="text-sm text-muted-foreground">无内容</p>
  const cleaned = content
    .replace(/^---\s*\n[\s\S]*?\n---\s*\n/, '')
    .replace(/<slice-meta>[\s\S]*?<\/slice-meta>/g, '')
    .replace(/^\+\+\+\s*$/gm, '')

  return (
    <div data-color-mode="light">
      <MarkdownPreview
        source={cleaned}
        style={{ background: 'transparent' }}
      />
    </div>
  )
}

/** Prefer frontmatter `source` in doc_meta; API also mirrors it as source_url. */
function resolveOriginalSourceUrl(
  docMeta: Record<string, unknown> | null,
  sourceUrl: string | null,
): string | null {
  const fromMeta = docMeta?.source
  if (typeof fromMeta === 'string' && fromMeta.trim()) return fromMeta.trim()
  if (typeof sourceUrl === 'string' && sourceUrl.trim()) return sourceUrl.trim()
  return null
}

function isLikelyPdfUrl(url: string): boolean {
  try {
    const u = new URL(url)
    const path = u.pathname.toLowerCase()
    return path.endsWith('.pdf')
  } catch {
    const base = url.split('?')[0]?.toLowerCase() ?? ''
    return base.endsWith('.pdf')
  }
}

/*
 * Same-origin API proxy for PDF (inline Content-Disposition; avoids TOS attachment / some iframe limits).
 * Kept for reference — switch viewer + links to this when you need backend streaming again.
 *
 * function originalFileProxyUrl(
 *   kbId: number,
 *   documentId: number,
 *   download: boolean,
 * ): string {
 *   const base = (
 *     process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
 *   ).replace(/\/$/, '')
 *   const q = download ? '?download=true' : ''
 *   return `${base}/v1/knowledge-bases/${kbId}/documents/${documentId}/original-file${q}`
 * }
 */

function OriginalTab({
  docMeta,
  sourceUrl,
}: {
  docMeta: Record<string, unknown> | null
  sourceUrl: string | null
}) {
  const url = resolveOriginalSourceUrl(docMeta, sourceUrl)
  if (!url) {
    return (
      <p className="text-sm text-muted-foreground">
        未配置原文链接：请在 doc-meta（frontmatter）中提供 <code className="rounded bg-muted px-1">source</code>{' '}
        字段，或同步后应带有 <code className="rounded bg-muted px-1">source_url</code>。
      </p>
    )
  }

  const isPdf = isLikelyPdfUrl(url)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
        >
          <IconExternalLink size={16} aria-hidden />
          在新标签页打开
        </a>
        <a
          href={url}
          download={!isPdf}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
        >
          <IconDownload size={16} aria-hidden />
          {isPdf ? '下载 PDF' : '下载原文档'}
        </a>
      </div>
      <p className="break-all text-xs text-muted-foreground" title={url}>
        {url}
      </p>

      {isPdf ? (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            下方使用 EmbedPDF 直接加载原始链接（meta 中的 source / source_url）。若对象存储限制跨域或强制下载导致预览失败，请用「在新标签页打开」或「下载 PDF」。
          </p>
          <div className="h-[min(85vh,920px)] w-full overflow-hidden rounded-lg border border-border bg-background">
            <PdfViewerEmbed key={url} src={url} className="h-full w-full" />
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-secondary/40 px-6 py-10 text-center">
          <p className="text-sm text-foreground">当前链接不是 PDF（路径未以 .pdf 结尾）</p>
          <p className="mt-2 text-sm text-muted-foreground">
            请使用上方按钮在新窗口打开或下载查看原文档。
          </p>
        </div>
      )}
    </div>
  )
}
