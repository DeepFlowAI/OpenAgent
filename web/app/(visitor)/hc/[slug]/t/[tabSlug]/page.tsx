import { notFound, redirect } from 'next/navigation'
import type { Metadata } from 'next'
import { serverGet, ServerApiError } from '@/utils/server-api'
import type {
  PublicDocListResponse,
  PublicHelpCenterBundle,
  PublicTab,
} from '@/models/help-center'

const PUBLIC_DOCS_HOST =
  process.env.NEXT_PUBLIC_DOCS_HOST ?? process.env.PUBLIC_DOCS_HOST ?? ''

type Params = { slug: string; tabSlug: string }

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

async function fetchFirstDoc(
  slug: string,
  tabSlug: string,
): Promise<PublicDocListResponse> {
  try {
    return await serverGet<PublicDocListResponse>(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}/tabs/${encodeURIComponent(tabSlug)}/docs`,
      { searchParams: { per_page: 1 } },
    )
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) notFound()
    throw err
  }
}

function findTab(
  bundle: PublicHelpCenterBundle,
  tabSlug: string,
): PublicTab | undefined {
  return bundle.tabs.find((t) => t.tab_slug === tabSlug)
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>
}): Promise<Metadata> {
  const { slug, tabSlug } = await params
  const bundle = await fetchBundle(slug)
  const tab = findTab(bundle, tabSlug)
  if (!tab) notFound()

  const title = `${tab.display_name} · ${bundle.site_name}`
  const desc = `${bundle.site_name} — ${tab.display_name}`
  const canonicalUrl = PUBLIC_DOCS_HOST
    ? `https://${PUBLIC_DOCS_HOST}/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(tabSlug)}`
    : undefined

  return {
    title,
    description: desc,
    alternates: canonicalUrl ? { canonical: canonicalUrl } : undefined,
    openGraph: {
      title,
      description: desc,
      url: canonicalUrl,
      type: 'website',
      images: bundle.publisher_logo_url ? [bundle.publisher_logo_url] : undefined,
    },
    twitter: { card: 'summary_large_image', title, description: desc },
  }
}

export default async function TabRootPage({
  params,
}: {
  params: Promise<Params>
}) {
  const { slug, tabSlug } = await params
  const [bundle, docList] = await Promise.all([
    fetchBundle(slug),
    fetchFirstDoc(slug, tabSlug),
  ])
  const tab = findTab(bundle, tabSlug)
  if (!tab) notFound()

  // Spec 3.1 — visitor reading layout always renders an article in the
  // main column. We redirect the tab root to its first doc so the reader
  // lands on something readable, mirroring the site-entry → default-tab
  // redirect.
  const first = docList.items[0]
  if (first) {
    const encoded = first.file_path
      .split('/')
      .map(encodeURIComponent)
      .join('/')
    redirect(
      `/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(tabSlug)}/${encoded}`,
    )
  }

  return (
    <div className="mx-auto w-full max-w-[760px] px-10 py-12 text-center">
      <h1 className="text-2xl font-semibold text-[#1a1a1a]">
        {tab.display_name}
      </h1>
      <p className="mt-3 text-sm text-[#737373]">
        本版块暂无可阅读的文档。
        <br />
        <span className="text-xs text-[#A3A3A3]">No documents yet.</span>
      </p>
    </div>
  )
}
