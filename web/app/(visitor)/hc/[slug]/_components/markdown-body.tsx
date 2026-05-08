import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { slugifyHeading } from './markdown-utils'

/**
 * Server-rendered Markdown body. We deliberately avoid the heavier
 * @uiw/react-markdown-preview client component here so the visitor site
 * ships minimal JS for SEO/GEO compliance.
 *
 * H1/H2/H3 are augmented with deterministic slug `id`s so the right-hand
 * outline (see PageToc) can deep-link via `#anchor`.
 */
export function MarkdownBody({ source }: { source: string | null }) {
  if (!source || source.trim().length === 0) {
    return (
      <p className="text-sm text-[#A1A1AA]">本文暂无正文 / No content yet.</p>
    )
  }

  return (
    <article className="prose-doc">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // `node` is the mdast node react-markdown passes to custom
          // renderers — exclude it so it doesn't leak onto the DOM as
          // `node="[object Object]"`.
          h1: ({ node: _n, children, ...props }) => (
            <h1 id={headingId(children)} {...props}>
              {children}
            </h1>
          ),
          h2: ({ node: _n, children, ...props }) => (
            <h2 id={headingId(children)} {...props}>
              {children}
            </h2>
          ),
          h3: ({ node: _n, children, ...props }) => (
            <h3 id={headingId(children)} {...props}>
              {children}
            </h3>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </article>
  )
}

function headingId(children: React.ReactNode): string | undefined {
  const text = flattenText(children)
  if (!text) return undefined
  return slugifyHeading(text) || undefined
}

function flattenText(node: React.ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(flattenText).join('')
  if (typeof node === 'object' && 'props' in node) {
    // React element — recurse through children.
    return flattenText(
      (node as { props: { children?: React.ReactNode } }).props?.children,
    )
  }
  return ''
}
