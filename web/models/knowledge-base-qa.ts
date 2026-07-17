export type QaProcessStatus = 'processing' | 'ready' | 'failed'

export type KnowledgeBaseQa = {
  id: number
  tenant_id: string
  knowledge_base_id: number
  directory_id: number
  directory_path: string[]
  question: string
  answer_markdown: string
  enabled: boolean
  access_keywords: string[]
  process_status: QaProcessStatus
  process_error: string | null
  document_id: number | null
  created_at: string
  updated_at: string
}

export type KnowledgeBaseQaPayload = {
  directory_id: number
  question: string
  answer_markdown: string
  access_keywords: string[]
  enabled: boolean
}

export type KnowledgeBaseQaListParams = {
  search?: string
  enabled?: boolean
  process_status?: QaProcessStatus
  directory_id?: number
  page?: number
  per_page?: number
}
