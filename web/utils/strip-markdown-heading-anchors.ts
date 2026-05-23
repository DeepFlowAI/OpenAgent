type HastLikeElement = {
  type: string
  tagName?: string
  properties?: Record<string, unknown>
  children?: Array<{
    type?: string
    tagName?: string
    properties?: Record<string, unknown>
  }>
}

export type MarkdownLinkPropsResolver = (href: string) => {
  target?: string
  rel?: string
}

/**
 * Strips heading permalink anchors injected by @uiw/react-markdown-preview
 * (rehype-slug + rehype-autolink-headings). Pass as `rehypeRewrite` on MarkdownPreview.
 * Also makes user-facing markdown links open outside the embedded chat iframe.
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
