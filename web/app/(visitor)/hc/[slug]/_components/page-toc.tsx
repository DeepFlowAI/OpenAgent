import { IconAlignLeft } from '@tabler/icons-react'
import { extractToc } from './markdown-utils'

/**
 * Right-rail outline of the currently rendered article. Built from the
 * same markdown source that `MarkdownBody` consumes; both rely on
 * `slugifyHeading` so the `#anchor` here matches the `id` injected on
 * each heading element.
 *
 * Returns `null` when the doc has no `##` / `###` headings — we hide
 * the column entirely rather than show an empty pane.
 */
export function PageToc({ source }: { source: string | null }) {
  const entries = extractToc(source)
  if (entries.length === 0) return null

  return (
    <nav aria-label="本页大纲" className="flex flex-col gap-3 text-sm">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#737373]">
        <IconAlignLeft size={14} stroke={1.8} />
        本页大纲
      </p>
      <ul className="flex flex-col gap-2">
        {entries.map((e, i) => (
          <li key={`${e.slug}-${i}`}>
            <a
              href={`#${e.slug}`}
              className={
                e.level === 2
                  ? 'block text-[13px] font-medium text-[#1a1a1a] hover:text-[#000]'
                  : 'block pl-3 text-[13px] text-[#737373] hover:text-[#1a1a1a]'
              }
            >
              {e.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
