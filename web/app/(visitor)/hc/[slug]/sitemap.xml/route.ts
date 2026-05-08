import { NextResponse } from 'next/server'
import { serverGetText, ServerApiError } from '@/utils/server-api'

/**
 * Visitor-side sitemap.xml endpoint. Pure passthrough — the backend already
 * renders the XML using the platform's PUBLIC_DOCS_HOST, so the Next.js
 * server just streams it through to the browser/crawler with the right
 * Content-Type. Cache-Control mirrors HTTP defaults; tune via CDN later.
 */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ slug: string }> },
) {
  const { slug } = await ctx.params
  try {
    const xml = await serverGetText(
      `/api/v1/public/help-centers/${encodeURIComponent(slug)}/sitemap.xml`,
    )
    return new NextResponse(xml, {
      status: 200,
      headers: { 'Content-Type': 'application/xml; charset=utf-8' },
    })
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) {
      return new NextResponse('Not Found', { status: 404 })
    }
    return new NextResponse('Internal Server Error', { status: 500 })
  }
}
