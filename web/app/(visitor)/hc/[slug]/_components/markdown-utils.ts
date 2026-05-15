/**
 * Visitor-side markdown helpers shared between the server-rendered article
 * body and the right-hand "本页大纲" outline. Everything here must be
 * deterministic so the slug used by an outline anchor matches the `id`
 * generated when the heading is rendered.
 */

export type TocEntry = {
  level: 2 | 3
  text: string
  slug: string
}

/**
 * Strip ingestion-time scaffolding from raw markdown_content so the visitor
 * sees a clean, reading-mode rendering. Mirrors the cleanup applied by the
 * admin-side "阅读 Markdown" tab in `knowledge-space/[id]/documents/[docId]`:
 *   - leading YAML frontmatter (`--- ... ---`)
 *   - `<slice-meta>...</slice-meta>` blocks the sync pipeline injects
 *   - `+++` separator lines used as page/slice breaks
 */
export function cleanReadingMarkdown(source: string | null | undefined): string {
  if (!source) return ''
  return source
    .replace(/^---\s*\n[\s\S]*?\n---\s*\n/, '')
    .replace(/<slice-meta>[\s\S]*?<\/slice-meta>/g, '')
    .replace(/^\+\+\+\s*$/gm, '')
}

function normalizeComparableHeading(text: string): string {
  const stripped = text.replace(/[*_`]/g, '').trim().replace(/\s+/g, ' ')
  return stripped
}

/**
 * Remove the first ATX heading (# … ######) when it duplicates the article
 * title already shown in the page header — authors often repeat the title as
 * the opening markdown line.
 *
 * Uses the same fenced-code awareness as `extractToc` so `# foo` inside code
 * fences is not treated as a heading.
 */
export function stripLeadingDuplicateTitleHeading(
  markdown: string,
  docTitle: string,
): string {
  const target = normalizeComparableHeading(docTitle)
  if (!target || !markdown) return markdown

  const lines = markdown.split('\n')
  let start = 0
  while (start < lines.length && lines[start].trim() === '') start++

  let inFence = false
  for (let j = start; j < lines.length; j++) {
    const line = lines[j]
    const trimmedEnd = line.trimEnd()
    if (trimmedEnd.startsWith('```') || trimmedEnd.startsWith('~~~')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    const m = trimmedEnd.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/)
    if (!m) break

    const candidate = normalizeComparableHeading(m[2])
    if (candidate === target) {
      let end = j + 1
      while (end < lines.length && lines[end].trim() === '') end++
      return [...lines.slice(0, start), ...lines.slice(end)].join('\n').trimStart()
    }
    break
  }

  return markdown
}

const NON_SLUG_CHARS = /[^\p{Letter}\p{Number}\u4e00-\u9fff]+/gu

/**
 * GitHub-style heading slug, but tolerant of CJK characters: keeps letters
 * (any script), numbers, CJK ideographs, and replaces every other run of
 * characters with a single dash. Lowercases ASCII letters; CJK is left
 * untouched so anchors can still be readable for Chinese docs.
 */
export function slugifyHeading(text: string): string {
  return text
    .trim()
    .replace(NON_SLUG_CHARS, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
}

/**
 * Pull `## ` and `### ` headings out of a markdown source. We deliberately
 * stay regex-based — running a full markdown AST here would add bundle
 * weight without the right-rail outline needing a perfect parse.
 *
 * Skips fenced code blocks so a `# foo` line inside ``` blocks isn't picked
 * up as a heading.
 */
export function extractToc(source: string | null | undefined): TocEntry[] {
  if (!source) return []
  const out: TocEntry[] = []
  const lines = source.split('\n')
  let inFence = false

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (line.startsWith('```') || line.startsWith('~~~')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    const m = line.match(/^(#{2,3})\s+(.+?)\s*#*\s*$/)
    if (!m) continue
    const level = m[1].length === 2 ? 2 : 3
    const text = m[2].trim()
    if (!text) continue
    out.push({ level, text, slug: slugifyHeading(text) })
  }
  return out
}
