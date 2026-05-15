'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import {
  buildDocTree,
  defaultExpandedKeys,
  type TreeNode,
} from './doc-tree-utils'
import type { NavEntry, PublicDocSummary } from '@/models/help-center'
import { cn } from '@/utils/classnames'

type Props = {
  slug: string
  tabSlug: string
  docs: PublicDocSummary[]
  nav: NavEntry[] | null
}

const PATH_PREFIX_RE = (slug: string, tabSlug: string) =>
  `/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(tabSlug)}/`

/**
 * Left-rail document tree shown on every visitor page within a tab. Tree
 * structure mirrors the docs' `file_path` layout. First- and second-level
 * folders open by default; deeper folders along the active doc path stay
 * expanded so the current article remains visible in the rail.
 */
export function DocTree({ slug, tabSlug, docs, nav }: Props) {
  const pathname = usePathname()
  const linkPrefix = PATH_PREFIX_RE(slug, tabSlug)

  // Decode the "/.../docs/{path}" portion to recover the original file_path.
  const activeFilePath = useMemo(() => {
    if (!pathname || !pathname.startsWith(linkPrefix)) return null
    const tail = pathname.slice(linkPrefix.length)
    if (!tail) return null
    return tail
      .split('/')
      .map((seg) => {
        try {
          return decodeURIComponent(seg)
        } catch {
          return seg
        }
      })
      .join('/')
  }, [pathname, linkPrefix])

  const tree = useMemo(() => buildDocTree(docs, nav), [docs, nav])

  const [expanded, setExpanded] = useState<Set<string>>(
    () => defaultExpandedKeys(tree, activeFilePath),
  )

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (docs.length === 0) {
    return (
      <p className="px-2 py-3 text-xs text-[#A1A1AA]">
        本版块暂无文档
      </p>
    )
  }

  return (
    <nav aria-label="文档目录" className="flex flex-col gap-1 text-sm">
      <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[#737373]">
        目录
      </p>
      <TreeList
        nodes={tree}
        depth={0}
        slug={slug}
        tabSlug={tabSlug}
        activeFilePath={activeFilePath}
        expanded={expanded}
        onToggle={toggle}
      />
    </nav>
  )
}

function TreeList({
  nodes,
  depth,
  slug,
  tabSlug,
  activeFilePath,
  expanded,
  onToggle,
}: {
  nodes: TreeNode[]
  depth: number
  slug: string
  tabSlug: string
  activeFilePath: string | null
  expanded: Set<string>
  onToggle: (key: string) => void
}) {
  return (
    <ul className="flex flex-col gap-0.5">
      {nodes.map((node) => {
        if (node.kind === 'folder') {
          const key = node.path.join('/')
          const isOpen = expanded.has(key)
          return (
            <li key={`folder:${key}`}>
              <button
                type="button"
                onClick={() => onToggle(key)}
                className={cn(
                  'flex w-full items-center gap-1 rounded px-2 py-1.5 text-left',
                  'text-[13px] font-medium text-[#1a1a1a] hover:bg-[#F0F0F0]',
                )}
                style={{ paddingLeft: 8 + depth * 12 }}
                aria-expanded={isOpen}
              >
                {isOpen ? (
                  <IconChevronDown size={14} className="text-[#737373]" />
                ) : (
                  <IconChevronRight size={14} className="text-[#737373]" />
                )}
                <span className="truncate">{node.name}</span>
              </button>
              {isOpen && (
                <TreeList
                  nodes={node.children}
                  depth={depth + 1}
                  slug={slug}
                  tabSlug={tabSlug}
                  activeFilePath={activeFilePath}
                  expanded={expanded}
                  onToggle={onToggle}
                />
              )}
            </li>
          )
        }

        const isActive = activeFilePath === node.file_path
        const href = buildDocHref(slug, tabSlug, node.file_path)
        return (
          <li key={`file:${node.file_path}`}>
            <Link
              href={href}
              prefetch={false}
              className={cn(
                'block truncate rounded px-2 py-1.5 text-[13px]',
                isActive
                  ? 'bg-[#F0F0F0] font-semibold text-[#1a1a1a]'
                  : 'text-[#525252] hover:bg-[#F0F0F0] hover:text-[#1a1a1a]',
              )}
              style={{ paddingLeft: 8 + depth * 12 + 14 }}
              aria-current={isActive ? 'page' : undefined}
              title={node.title || node.name}
            >
              {node.title || stripMdSuffix(node.name)}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

function buildDocHref(slug: string, tabSlug: string, filePath: string): string {
  const encodedPath = filePath.split('/').map(encodeURIComponent).join('/')
  return `/hc/${encodeURIComponent(slug)}/t/${encodeURIComponent(tabSlug)}/${encodedPath}`
}

function stripMdSuffix(name: string): string {
  return name.endsWith('.md') ? name.slice(0, -3) : name
}
