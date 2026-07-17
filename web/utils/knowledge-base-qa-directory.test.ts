import { describe, expect, it } from 'vitest'
import type { KnowledgeBaseQaDirectory } from '@/models/knowledge-base-qa-directory'
import { flattenKnowledgeBaseQaDirectoryTree } from './knowledge-base-qa-directory'

function directory(
  id: number,
  name: string,
  parentId: number | null,
  sortOrder: number,
  depth: number,
): KnowledgeBaseQaDirectory {
  return {
    id,
    tenant_id: 'T_TEST',
    knowledge_base_id: 7,
    parent_id: parentId,
    name,
    sort_order: sortOrder,
    depth,
    path: [name],
    qa_count: 0,
    created_at: '2026-07-13T00:00:00',
    updated_at: '2026-07-13T00:00:00',
  }
}

describe('flattenKnowledgeBaseQaDirectoryTree', () => {
  it('places each directory immediately after its parent in sibling order', () => {
    const directories = [
      directory(1, '产品', null, 0, 1),
      directory(4, '服务', null, 1, 1),
      directory(2, '售后', 1, 0, 2),
      directory(5, '咨询', 4, 0, 2),
      directory(3, '退款', 2, 0, 3),
    ]

    const result = flattenKnowledgeBaseQaDirectoryTree(directories)

    expect(result.map((item) => item.id)).toEqual([1, 2, 3, 4, 5])
  })
})
