import { notFound, redirect } from 'next/navigation'
import type { Metadata } from 'next'
import { serverGet, ServerApiError } from '@/utils/server-api'
import type { PublicHelpCenterBundle } from '@/models/help-center'

const PUBLIC_DOCS_HOST =
  process.env.NEXT_PUBLIC_DOCS_HOST ?? process.env.PUBLIC_DOCS_HOST ?? ''

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

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const bundle = await fetchBundle(slug)
  const canonicalUrl = PUBLIC_DOCS_HOST
    ? `https://${PUBLIC_DOCS_HOST}/hc/${encodeURIComponent(slug)}`
    : undefined

  return {
    title: bundle.site_name,
    description: bundle.site_name,
    alternates: canonicalUrl ? { canonical: canonicalUrl } : undefined,
    openGraph: {
      title: bundle.site_name,
      description: bundle.site_name,
      url: canonicalUrl,
      type: 'website',
      images: bundle.publisher_logo_url ? [bundle.publisher_logo_url] : undefined,
    },
    twitter: {
      card: 'summary_large_image',
      title: bundle.site_name,
      description: bundle.site_name,
    },
  }
}

export default async function SiteEntryPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const bundle = await fetchBundle(slug)

  // Redirect to the first (default) tab if any tab exists; otherwise show
  // a friendly empty-state.
  const defaultTab = bundle.tabs[0]
  if (defaultTab) {
    redirect(
      `/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(defaultTab.tab_slug)}`,
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-[800px] flex-col items-center gap-3 px-6 py-24 text-center">
      <h1 className="text-2xl font-semibold text-[#1a1a1a]">
        {bundle.site_name}
      </h1>
      <p className="text-sm text-[#737373]">
        本站点暂无内容。
        <br />
        <span className="text-xs text-[#A3A3A3]">
          This site has no content yet.
        </span>
      </p>
    </div>
  )
}
