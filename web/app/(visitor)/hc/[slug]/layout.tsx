import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { serverGet, ServerApiError } from '@/utils/server-api'
import type { PublicHelpCenterBundle } from '@/models/help-center'
import { TopNav } from './_components/top-nav'

type Props = {
  children: React.ReactNode
  params: Promise<{ slug: string }>
}

async function fetchBundle(slug: string): Promise<PublicHelpCenterBundle> {
  try {
    return await serverGet<PublicHelpCenterBundle>(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}`,
    )
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) {
      notFound()
    }
    throw err
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  try {
    const bundle = await fetchBundle(slug)
    return {
      title: bundle.site_name,
      description: bundle.site_name,
      icons: bundle.publisher_logo_url ? [bundle.publisher_logo_url] : undefined,
    }
  } catch {
    return { title: 'Help Center' }
  }
}

export default async function HelpCenterLayout({ children, params }: Props) {
  const { slug } = await params
  const bundle = await fetchBundle(slug)

  return (
    <div className="flex min-h-screen flex-col bg-white text-[#1a1a1a]">
      <header className="sticky top-0 z-30 border-b border-[#E4E4E7] bg-white/95 backdrop-blur">
        <div className="relative flex h-16 w-full items-center px-6">
          <Link
            href={`/hc/${encodeURIComponent(slug)}`}
            className="relative z-10 flex items-center gap-2 font-semibold text-[#1a1a1a]"
          >
            {bundle.publisher_logo_url && (
              // Plain <img> avoids the next/image domain config requirement
              // for arbitrary publisher logos.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={bundle.publisher_logo_url}
                alt=""
                className="h-7 w-auto max-w-none object-contain"
              />
            )}
            <span>{bundle.site_name}</span>
          </Link>
          <TopNav slug={slug} tabs={bundle.tabs} />
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-[#E4E4E7] py-6 text-center text-xs text-[#737373]">
        © {new Date().getFullYear()} {bundle.site_name}
      </footer>
    </div>
  )
}
