import type { PublicDocSummary } from '@/models/help-center'

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

/**
 * Build a hierarchical tree from a flat list of `PublicDocSummary` rows.
 *
 *   [{file_path: "guide/intro.md"}, {file_path: "api/v1/list.md"}]
 *   ↓
 *   ├── api/
 *   │   └── v1/
 *   │       └── list.md
 *   └── guide/
 *       └── intro.md
 *
 * Children are ordered: folders first (alphabetical), then files
 * (alphabetical by display name). Sorting is stable across renders so
 * the active-doc highlight doesn't flicker.
 */
export function buildDocTree(docs: PublicDocSummary[]): TreeNode[] {
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

  sortTree(root)
  return root.children
}

function sortTree(node: TreeFolder): void {
  node.children.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1
    const an = a.kind === 'file' ? a.title || a.name : a.name
    const bn = b.kind === 'file' ? b.title || b.name : b.name
    return an.localeCompare(bn, 'zh-Hans-CN')
  })
  for (const child of node.children) {
    if (child.kind === 'folder') sortTree(child)
  }
}

/**
 * Compute the set of folder-path keys (joined by `/`) that should be
 * expanded by default — those that contain the currently-active document.
 * Returns an empty set when no doc is active.
 */
export function defaultExpandedKeys(
  tree: TreeNode[],
  activeFilePath: string | null,
): Set<string> {
  const out = new Set<string>()
  if (!activeFilePath) return out

  const targetSegs = activeFilePath.split('/').filter(Boolean)
  // For "api/v1/list.md" the folders to expand are "api" and "api/v1".
  for (let i = 1; i < targetSegs.length; i++) {
    out.add(targetSegs.slice(0, i).join('/'))
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
