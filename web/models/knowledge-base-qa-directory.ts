export type KnowledgeBaseQaDirectory = {
  id: number
  tenant_id: string
  knowledge_base_id: number
  parent_id: number | null
  name: string
  sort_order: number
  depth: number
  path: string[]
  qa_count: number
  created_at: string
  updated_at: string
}

export type KnowledgeBaseQaDirectoryList = {
  items: KnowledgeBaseQaDirectory[]
  total_qa_count: number
}

export type CreateKnowledgeBaseQaDirectoryPayload = {
  name: string
  parent_id: number | null
}

export type UpdateKnowledgeBaseQaDirectoryPayload = {
  name?: string
  parent_id?: number | null
  sort_order?: number
}
