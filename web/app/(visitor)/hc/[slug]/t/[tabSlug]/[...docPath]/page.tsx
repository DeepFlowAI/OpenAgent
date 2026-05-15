import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { serverGet, ServerApiError } from '@/utils/server-api'
import type {
  PublicDocDetail,
  PublicHelpCenterBundle,
} from '@/models/help-center'
import { MarkdownBody } from '../../../_components/markdown-body'
import { PageToc } from '../../../_components/page-toc'
import { CopyMarkdownButton } from '../../../_components/copy-markdown-button'
import {
  cleanReadingMarkdown,
  extractToc,
  stripLeadingDuplicateTitleHeading,
} from '../../../_components/markdown-utils'

const PUBLIC_DOCS_HOST =
  process.env.NEXT_PUBLIC_DOCS_HOST ?? process.env.PUBLIC_DOCS_HOST ?? ''

type Params = { slug: string; tabSlug: string; docPath: string[] }

function buildDocPath(parts: string[]): string {
  // Next.js 15 (App Router / Turbopack) hands catch-all segments back to
  // us still percent-encoded. Decode here so downstream callers can treat
  // the result as the original `file_path` (e.g. "操作手册/foo.md") and
  // do their own encoding when assembling URLs.
  return parts.map((p) => safeDecode(p)).join('/')
}

function safeDecode(part: string): string {
  try {
    return decodeURIComponent(part)
  } catch {
    return part
  }
}

function buildCanonical(
  slug: string,
  tabSlug: string,
  docPath: string,
): string | undefined {
  if (!PUBLIC_DOCS_HOST) return undefined
  const encoded = docPath.split('/').map(encodeURIComponent).join('/')
  return `https://${PUBLIC_DOCS_HOST}/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(tabSlug)}/${encoded}`
}

async function fetchBundle(slug: string): Promise<PublicHelpCenterBundle> {
  try {
    return await serverGet<PublicHelpCenterBundle>(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}`,
    )
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) notFound()
    throw err
  }
}

async function fetchDoc(
  slug: string,
  tabSlug: string,
  docPath: string,
): Promise<PublicDocDetail> {
  const encoded = docPath.split('/').map(encodeURIComponent).join('/')
  try {
    return await serverGet<PublicDocDetail>(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}/tabs/${encodeURIComponent(tabSlug)}/docs/${encoded}`,
    )
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) notFound()
    throw err
  }
}

function summarise(
  doc: PublicDocDetail,
  cleanedSource: string,
  max = 160,
): string {
  if (doc.description) return doc.description.slice(0, max)
  if (!cleanedSource) return doc.title
  // Strip rudimentary markdown punctuation; this is a best-effort summary
  // not a full HTML render.
  const plain = cleanedSource
    .replace(/^#+\s+/gm, '')
    .replace(/[*_`>]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.slice(0, max)
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>
}): Promise<Metadata> {
  const { slug, tabSlug, docPath } = await params
  const path = buildDocPath(docPath)

  const [bundle, doc] = await Promise.all([
    fetchBundle(slug),
    fetchDoc(slug, tabSlug, path),
  ])

  const title = `${doc.title} · ${bundle.site_name}`
  const readingMarkdown = stripLeadingDuplicateTitleHeading(
    cleanReadingMarkdown(doc.markdown_content),
    doc.title,
  )
  const desc = summarise(doc, readingMarkdown)
  const canonical = buildCanonical(slug, tabSlug, path)
  const ogImage = bundle.publisher_logo_url
    ? [bundle.publisher_logo_url]
    : undefined

  return {
    title,
    description: desc,
    alternates: canonical ? { canonical } : undefined,
    openGraph: {
      title,
      description: desc,
      url: canonical,
      type: 'article',
      images: ogImage,
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description: desc,
    },
  }
}

export default async function DocPage({
  params,
}: {
  params: Promise<Params>
}) {
  const { slug, tabSlug, docPath } = await params
  const path = buildDocPath(docPath)

  const [bundle, doc] = await Promise.all([
    fetchBundle(slug),
    fetchDoc(slug, tabSlug, path),
  ])

  const canonical = buildCanonical(slug, tabSlug, path)
  const lastmod = doc.updated_at ?? null
  const cleanedFull = cleanReadingMarkdown(doc.markdown_content)
  const cleanedSource = stripLeadingDuplicateTitleHeading(cleanedFull, doc.title)
  // Clipboard keeps a single `# title` line when we hide the duplicate heading in the UI.
  const clipboardMarkdown =
    cleanedSource !== cleanedFull && doc.title.trim().length > 0
      ? `# ${doc.title.trim()}\n\n${cleanedSource}`
      : cleanedFull
  const hasToc = extractToc(cleanedSource).length > 0

  // JSON-LD for GEO. Inlined into HTML so AI crawlers / search engines
  // pick it up on the first response.
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: doc.title,
    description: doc.description ?? undefined,
    url: canonical,
    dateModified: lastmod ?? undefined,
    publisher: {
      '@type': 'Organization',
      name: bundle.site_name,
      ...(bundle.publisher_logo_url
        ? { logo: { '@type': 'ImageObject', url: bundle.publisher_logo_url } }
        : {}),
    },
  }

  return (
    <div className="flex w-full">
      <div className="min-w-0 flex-1 px-6 py-10 lg:px-14">
        <article className="mx-auto w-full max-w-[760px]">
          <header className="mb-6 border-b border-[#E4E4E7] pb-6">
            <div className="flex items-start justify-between gap-6">
              <div className="min-w-0 flex-1">
                <h1 className="text-3xl font-semibold leading-tight tracking-tight text-[#1a1a1a]">
                  {doc.title}
                </h1>
                {doc.description && (
                  <p className="mt-3 text-base text-[#525252]">{doc.description}</p>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-[#A3A3A3]">
                  {lastmod && (
                    <time dateTime={lastmod}>
                      更新于 {new Date(lastmod).toLocaleDateString('zh-CN')}
                    </time>
                  )}
                </div>
              </div>
              {clipboardMarkdown.trim().length > 0 && (
                <CopyMarkdownButton markdown={clipboardMarkdown} />
              )}
            </div>
          </header>

          <MarkdownBody source={cleanedSource} />
        </article>
      </div>

      {hasToc && (
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-[232px] shrink-0 overflow-y-auto px-5 py-7 xl:block">
          <PageToc source={cleanedSource} />
        </aside>
      )}

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
    </div>
  )
}
