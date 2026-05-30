type HastLikeElement = {
  type: string
  tagName?: string
  properties?: Record<string, unknown>
  children?: HastLikeNode[]
}

type HastLikeNode = {
  type?: string
  tagName?: string
  value?: string
  properties?: Record<string, unknown>
  children?: HastLikeNode[]
}

export type MarkdownLinkPropsResolver = (href: string) => {
  target?: string
  rel?: string
}

function isMp4VideoUrl(href: string) {
  const trimmed = href.trim()
  if (!trimmed || trimmed.startsWith('#')) return false

  const isRelativeUrl =
    trimmed.startsWith('/') ||
    trimmed.startsWith('./') ||
    trimmed.startsWith('../')

  try {
    const parsed = isRelativeUrl
      ? new URL(trimmed, 'https://markdown.local')
      : new URL(trimmed)
    if (!isRelativeUrl && !['http:', 'https:'].includes(parsed.protocol)) {
      return false
    }
    return parsed.pathname.toLowerCase().endsWith('.mp4')
  } catch {
    return false
  }
}

function getPlainText(nodes: HastLikeNode[] | undefined): string {
  if (!nodes) return ''
  return nodes
    .map((child) => {
      if (child.type === 'text') return child.value ?? ''
      return getPlainText(child.children)
    })
    .join('')
}

function rewriteVideoLink(el: HastLikeElement, href: string) {
  const label = getPlainText(el.children).trim()
  el.tagName = 'video'
  el.properties = {
    className: ['markdown-video-player'],
    controls: true,
    preload: 'metadata',
    playsInline: true,
    ...(label ? { ariaLabel: label } : {}),
  }
  el.children = [
    {
      type: 'element',
      tagName: 'source',
      properties: {
        src: href,
        type: 'video/mp4',
      },
      children: [],
    },
    {
      type: 'text',
      value: label || '您的浏览器不支持视频播放。',
    },
  ]
}

/**
 * Strips heading permalink anchors injected by @uiw/react-markdown-preview
 * (rehype-slug + rehype-autolink-headings). Pass as `rehypeRewrite` on MarkdownPreview.
 * Also makes user-facing markdown links open outside the embedded chat iframe.
 * MP4 markdown links are upgraded to inline playable videos.
 */
function rewriteMarkdownLinksAndHeadings(
  node: HastLikeElement | { type: string },
  resolveLinkProps: MarkdownLinkPropsResolver,
  _index?: number,
  _parent?: unknown,
): void {
  const el = node as HastLikeElement
  if (el.type !== 'element' || !el.tagName) return

  if (el.tagName === 'a') {
    const href = typeof el.properties?.href === 'string' ? el.properties.href : ''
    if (href && isMp4VideoUrl(href)) {
      rewriteVideoLink(el, href.trim())
      return
    }
    if (href && !href.startsWith('#')) {
      el.properties = {
        ...el.properties,
        ...resolveLinkProps(href),
      }
    }
    return
  }

  if (!/^h[1-6]$/.test(el.tagName)) return
  const child = el.children?.[0]
  if (child?.type === 'element' && child.tagName === 'a' && child.properties?.ariaHidden === 'true') {
    el.children = el.children!.slice(1)
  }
}

export function createMarkdownLinkRehypeRewrite(
  resolveLinkProps: MarkdownLinkPropsResolver,
) {
  return (
    node: HastLikeElement | { type: string },
    index?: number,
    parent?: unknown,
  ): void => rewriteMarkdownLinksAndHeadings(node, resolveLinkProps, index, parent)
}

export function stripMarkdownHeadingAnchorsRehypeRewrite(
  node: HastLikeElement | { type: string },
  index?: number,
  parent?: unknown,
): void {
  rewriteMarkdownLinksAndHeadings(
    node,
    () => ({ target: '_blank', rel: 'noopener noreferrer' }),
    index,
    parent,
  )
}
