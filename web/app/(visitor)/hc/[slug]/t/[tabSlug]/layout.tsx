import { notFound } from 'next/navigation'
import { serverGet, ServerApiError } from '@/utils/server-api'
import type {
  PublicDocListResponse,
  PublicHelpCenterBundle,
} from '@/models/help-center'
import { ResizableDocSidebar } from '../../_components/resizable-doc-sidebar'

type Props = {
  children: React.ReactNode
  params: Promise<{ slug: string; tabSlug: string }>
}

/**
 * Maximum number of docs we ship into the visitor sidebar in one round
 * trip. Capped at the public docs API's hard limit (`per_page <= 100`,
 * see `routers/v1/public_help_center.py`). The visitor outline is meant
 * to be navigable by humans, not a search interface — for tabs that
 * exceed this, the search / paginated tree UX is a separate iteration
 * (see 03_访客站与SEO §3.1).
 */
const TREE_PAGE_SIZE = 100

async function fetchAllDocs(
  slug: string,
  tabSlug: string,
): Promise<PublicDocListResponse> {
  try {
    return await serverGet<PublicDocListResponse>(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}/tabs/${encodeURIComponent(tabSlug)}/docs`,
      { searchParams: { per_page: TREE_PAGE_SIZE } },
    )
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) notFound()
    throw err
  }
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

export default async function TabLayout({ children, params }: Props) {
  const { slug, tabSlug } = await params

  const [bundle, docList] = await Promise.all([
    fetchBundle(slug),
    fetchAllDocs(slug, tabSlug),
  ])

  // Tab membership check — fast 404 if the tab slug isn't one this Help
  // Center exposes (the docs query returns 404 too, but bundle is needed
  // anyway so we use it here).
  if (!bundle.tabs.some((t) => t.tab_slug === tabSlug)) {
    notFound()
  }

  return (
    <div className="flex w-full">
      <ResizableDocSidebar slug={slug} tabSlug={tabSlug} docs={docList.items} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
