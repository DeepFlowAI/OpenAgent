export const SAME_PAGE_NAVIGATION_ALLOWLIST_KEY = 'samePageNavigationUrlAllowlist'

export const SAME_PAGE_NAVIGATION_ALLOWLIST_LIMIT = 50
export const SAME_PAGE_NAVIGATION_ALLOWLIST_PATTERN_LIMIT = 512

const MATCH_ALL_PATTERNS = new Set(['*', 'http://*', 'https://*'])

export type SamePageNavigationLinkProps = {
  target?: '_self' | '_blank'
  rel?: string
}

export type SamePageNavigationAllowlistResult = {
  patterns: string[]
  error: string | null
}

function normalizePattern(pattern: string): string {
  const parts = pattern.split('://')
  if (parts.length !== 2) return pattern

  const [scheme, rest] = parts
  let boundary = rest.length
  for (const marker of ['/', '?', '#']) {
    const index = rest.indexOf(marker)
    if (index !== -1) boundary = Math.min(boundary, index)
  }

  const host = rest.slice(0, boundary)
  const suffix = rest.slice(boundary)
  return `${scheme.toLowerCase()}://${host.toLowerCase()}${suffix}`
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function patternToRegExp(pattern: string): RegExp {
  const source = pattern.split('*').map(escapeRegExp).join('.*')
  return new RegExp(`^${source}$`)
}

export function normalizeSamePageNavigationAllowlist(
  input: string | readonly string[] | null | undefined,
): SamePageNavigationAllowlistResult {
  const values = typeof input === 'string' ? input.split(/\r?\n/) : [...(input ?? [])]
  const patterns: string[] = []
  const seen = new Set<string>()

  for (const raw of values) {
    const pattern = raw.trim()
    if (!pattern) continue

    if (pattern.length > SAME_PAGE_NAVIGATION_ALLOWLIST_PATTERN_LIMIT) {
      return { patterns, error: '单条规则不能超过 512 个字符' }
    }

    const lowered = pattern.toLowerCase()
    if (!lowered.startsWith('http://') && !lowered.startsWith('https://')) {
      return { patterns, error: '请输入以 http:// 或 https:// 开头的 URL 规则' }
    }

    const normalized = normalizePattern(pattern)
    if (MATCH_ALL_PATTERNS.has(normalized.toLowerCase())) {
      return { patterns, error: '白名单规则不能匹配所有 URL' }
    }

    if (!seen.has(normalized)) {
      patterns.push(normalized)
      seen.add(normalized)
    }
  }

  if (patterns.length > SAME_PAGE_NAVIGATION_ALLOWLIST_LIMIT) {
    return { patterns, error: '最多添加 50 条规则' }
  }

  return { patterns, error: null }
}

export function isSamePageNavigationAllowed(
  href: string,
  patterns: readonly string[] | null | undefined,
): boolean {
  if (!patterns?.length) return false

  const rawHref = href.trim()
  if (!rawHref) return false

  let targetUrl: URL
  try {
    targetUrl = new URL(rawHref)
  } catch {
    return false
  }

  if (targetUrl.protocol !== 'http:' && targetUrl.protocol !== 'https:') {
    return false
  }

  const normalizedHref = targetUrl.href
  return patterns.some((pattern) => patternToRegExp(pattern).test(normalizedHref))
}

export function getSamePageNavigationLinkProps(
  href: string,
  patterns: readonly string[] | null | undefined,
): SamePageNavigationLinkProps {
  if (isSamePageNavigationAllowed(href, patterns)) {
    return { target: '_self' }
  }
  return { target: '_blank', rel: 'noopener noreferrer' }
}
