import type { KnowledgeBaseQaDirectory } from '@/models/knowledge-base-qa-directory'

export function flattenKnowledgeBaseQaDirectoryTree(
  directories: KnowledgeBaseQaDirectory[],
): KnowledgeBaseQaDirectory[] {
  const children = new Map<number | null, KnowledgeBaseQaDirectory[]>()
  for (const directory of directories) {
    const siblings = children.get(directory.parent_id) ?? []
    siblings.push(directory)
    children.set(directory.parent_id, siblings)
  }
  for (const siblings of children.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
  }

  const result: KnowledgeBaseQaDirectory[] = []
  const visit = (parentId: number | null) => {
    for (const directory of children.get(parentId) ?? []) {
      result.push(directory)
      visit(directory.id)
    }
  }
  visit(null)
  return result
}
