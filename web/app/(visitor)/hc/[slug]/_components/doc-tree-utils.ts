import type { NavEntry, PublicDocSummary } from '@/models/help-center'

/**
 * Doc-tree node shape consumed by the visitor sidebar. Folders carry a
 * `path` segment list (cumulative, used as a stable key + for default
 * expansion logic) and any number of children of either kind. Files map
 * 1:1 to a `PublicDocSummary` and store the full `file_path` so links
 * can be built without re-walking the tree.
 */
export type TreeNode = TreeFolder | TreeFile

export type TreeFolder = {
  kind: 'folder'
  name: string
  /** Cumulative path segments, e.g. ["api", "v1"]. */
  path: string[]
  children: TreeNode[]
}

export type TreeFile = {
  kind: 'file'
  name: string
  /** Original `file_path` from backend — used for the route link. */
  file_path: string
  doc_id: number
  title: string
}

// ---------------------------------------------------------------------------
// Nav ordering helpers
// ---------------------------------------------------------------------------

type NavOrderMap = Map<string, number>

/**
 * Flatten the recursive `nav` array from schema/nav.yaml into two lookup maps:
 * - fileOrder: full file_path → position index
 * - folderOrder: full folder path (e.g. "管理后台/工单配置") → position index
 *
 * Position indices are scoped per parent: each children array produces
 * independent 0-based indices so siblings sort correctly among themselves.
 */
function buildNavOrderMaps(nav: NavEntry[] | null): {
  fileOrder: NavOrderMap
  folderOrder: NavOrderMap
} {
  const fileOrder: NavOrderMap = new Map()
  const folderOrder: NavOrderMap = new Map()

  if (!nav) return { fileOrder, folderOrder }

  const walk = (entries: NavEntry[], pathPrefix: string) => {
    let position = 0
    for (const entry of entries) {
      if (typeof entry === 'string') {
        const fullPath = pathPrefix ? `${pathPrefix}/${entry}` : entry
        fileOrder.set(fullPath, position++)
        continue
      }
      if ('file' in entry) {
        const fullPath = pathPrefix ? `${pathPrefix}/${entry.file}` : entry.file
        fileOrder.set(fullPath, position++)
        continue
      }
      if ('folder' in entry) {
        const folderPath = pathPrefix ? `${pathPrefix}/${entry.folder}` : entry.folder
        folderOrder.set(folderPath, position++)
        if (entry.children) {
          walk(entry.children, folderPath)
        }
      }
    }
  }

  walk(nav, '')
  return { fileOrder, folderOrder }
}

// ---------------------------------------------------------------------------
// Tree building
// ---------------------------------------------------------------------------

/**
 * Build a hierarchical tree from a flat list of `PublicDocSummary` rows,
 * optionally sorted by nav.yaml ordering. Items present in `nav` sort first
 * (by declared position); items absent from `nav` sort after, falling back to
 * locale-aware alphabetical order.
 */
export function buildDocTree(
  docs: PublicDocSummary[],
  nav?: NavEntry[] | null,
): TreeNode[] {
  const root: TreeFolder = { kind: 'folder', name: '', path: [], children: [] }

  for (const doc of docs) {
    const segments = doc.file_path.split('/').filter(Boolean)
    if (segments.length === 0) continue
    const fileName = segments[segments.length - 1]
    const folderSegs = segments.slice(0, -1)

    let cursor: TreeFolder = root
    for (let i = 0; i < folderSegs.length; i++) {
      const seg = folderSegs[i]
      const cumulative = folderSegs.slice(0, i + 1)
      let next = cursor.children.find(
        (c): c is TreeFolder => c.kind === 'folder' && c.name === seg,
      )
      if (!next) {
        next = { kind: 'folder', name: seg, path: cumulative, children: [] }
        cursor.children.push(next)
      }
      cursor = next
    }

    cursor.children.push({
      kind: 'file',
      name: fileName,
      file_path: doc.file_path,
      doc_id: doc.id,
      title: doc.title,
    })
  }

  const { fileOrder, folderOrder } = buildNavOrderMaps(nav ?? null)
  sortTree(root, fileOrder, folderOrder)
  return root.children
}

/**
 * Sort children of every folder node. When nav ordering is available, items
 * explicitly listed in nav come first (preserving declared order); unlisted
 * items follow in locale-aware alphabetical order.
 */
function sortTree(
  node: TreeFolder,
  fileOrder: NavOrderMap,
  folderOrder: NavOrderMap,
): void {
  node.children.sort((a, b) => {
    const aKey = nodeKey(a)
    const bKey = nodeKey(b)
    const aOrder = lookupOrder(a, aKey, fileOrder, folderOrder)
    const bOrder = lookupOrder(b, bKey, fileOrder, folderOrder)

    const aHasNav = aOrder !== undefined
    const bHasNav = bOrder !== undefined

    if (aHasNav && bHasNav) return aOrder - bOrder
    if (aHasNav && !bHasNav) return -1
    if (!aHasNav && bHasNav) return 1

    // Fallback: folders first, then alphabetical
    if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1
    const an = a.kind === 'file' ? a.title || a.name : a.name
    const bn = b.kind === 'file' ? b.title || b.name : b.name
    return an.localeCompare(bn, 'zh-Hans-CN')
  })

  for (const child of node.children) {
    if (child.kind === 'folder') sortTree(child, fileOrder, folderOrder)
  }
}

function nodeKey(node: TreeNode): string {
  if (node.kind === 'file') return node.file_path
  return node.path.join('/')
}

function lookupOrder(
  node: TreeNode,
  key: string,
  fileOrder: NavOrderMap,
  folderOrder: NavOrderMap,
): number | undefined {
  if (node.kind === 'file') return fileOrder.get(key)
  return folderOrder.get(key)
}

/**
 * Collect folder keys for the first two path segments (top-level folder +
 * one nested folder) so the sidebar opens those tiers by default.
 */
function collectExpandedThroughSecondLevel(nodes: TreeNode[]): Set<string> {
  const out = new Set<string>()
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (n.kind !== 'folder') continue
      const key = n.path.join('/')
      if (n.path.length <= 2) out.add(key)
      walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/**
 * Compute the set of folder-path keys (joined by `/`) that should be
 * expanded by default:
 * - First- and second-level folders (path depth 1–2) are open so nested
 *   sections are visible without clicking.
 * - Additionally, every ancestor folder of the active document stays open
 *   so deeper paths remain navigable when a doc is selected.
 */
export function defaultExpandedKeys(
  tree: TreeNode[],
  activeFilePath: string | null,
): Set<string> {
  const out = collectExpandedThroughSecondLevel(tree)

  if (activeFilePath) {
    const targetSegs = activeFilePath.split('/').filter(Boolean)
    // For "api/v1/list.md" the folders to expand are "api" and "api/v1".
    for (let i = 1; i < targetSegs.length; i++) {
      out.add(targetSegs.slice(0, i).join('/'))
    }
  }

  // Sanity check: only keep folders that exist in the tree.
  return filterExisting(tree, out)
}

function filterExisting(tree: TreeNode[], wanted: Set<string>): Set<string> {
  const seen = new Set<string>()
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) {
      if (n.kind === 'folder') {
        const key = n.path.join('/')
        if (wanted.has(key)) seen.add(key)
        walk(n.children)
      }
    }
  }
  walk(tree)
  return seen
}
