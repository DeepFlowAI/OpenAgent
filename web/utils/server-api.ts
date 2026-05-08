/**
 * Server-side API helpers used by the visitor-facing Help Center routes
 * under `/hc/*`. These call the backend directly from the Next.js server
 * runtime (NOT from the browser), so we can render SEO-critical content
 * into the first HTML response.
 *
 * NOTE: This file is the ONLY server-side API client in the project. All
 * other code (admin / agent UI) uses React Query + ky on the client.
 */

const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:5001'

type FetchOpts = {
  searchParams?: Record<string, string | number | undefined>
}

export class ServerApiError extends Error {
  constructor(
    public status: number,
    public path: string,
    public body?: string,
  ) {
    super(`Server API ${status} on ${path}`)
  }
}

function buildUrl(path: string, opts?: FetchOpts): string {
  const url = new URL(path.replace(/^\/+/, ''), BACKEND.replace(/\/$/, '') + '/')
  if (opts?.searchParams) {
    for (const [k, v] of Object.entries(opts.searchParams)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

export async function serverGet<T>(
  path: string,
  opts?: FetchOpts,
): Promise<T> {
  const url = buildUrl(path, opts)
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ServerApiError(res.status, path, text)
  }
  return (await res.json()) as T
}

export async function serverGetText(
  path: string,
  opts?: FetchOpts,
): Promise<string> {
  const url = buildUrl(path, opts)
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    throw new ServerApiError(res.status, path)
  }
  return await res.text()
}
