export type Document = {
  id: number
  knowledge_base_id: number
  tenant_id: string
  title: string | null
  description: string | null
  file_path: string
  source_url: string | null
  markdown_content: string | null
  doc_meta: Record<string, unknown> | null
  toc: Array<{ level: number; text: string }> | null
  slice_count: number
  created_at: string
  updated_at: string
}

export type Slice = {
  id: number
  document_id: number
  knowledge_base_id: number
  content: string
  content_for_search: string | null
  toc_path: string[] | null
  slice_meta: Record<string, unknown> | null
  doc_meta: Record<string, unknown> | null
  source_url: string | null
  markdown_url: string | null
  slice_order: number
  created_at: string
  updated_at: string
}

export type SyncProgress = {
  phase?: 'git_pull' | 'discovered' | 'import' | 'embedding' | 'delete'
  file_index?: number
  file_total?: number
  current_file?: string
  slice_count?: number
  embedding_batch?: number
  embedding_batch_total?: number
  success_count?: number
  error_count?: number
  message?: string
  updated_at?: string
  percent?: number
}

export type SyncLogFileEntry = {
  file: string
  status: string
  error?: string
  slice_count?: number
}

export type SyncLogDetailsObject = {
  sync_mode?: string
  schema_changed?: boolean
  progress?: SyncProgress
  files?: SyncLogFileEntry[]
  error?: string
}

export type SyncLog = {
  id: number
  knowledge_base_id: number
  tenant_id: string
  status: 'running' | 'success' | 'partial_success' | 'failed' | 'cancelled'
  started_at: string
  finished_at: string | null
  total_files: number | null
  success_count: number | null
  error_count: number | null
  details:
    | SyncLogFileEntry[]
    | SyncLogDetailsObject
    | null
}
