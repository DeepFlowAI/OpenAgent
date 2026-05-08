export type KnowledgeBase = {
  id: number
  tenant_id: string
  name: string
  description: string | null
  git_url: string
  git_branch: string
  auth_type: 'none' | 'token'
  auth_token: string | null
  last_synced_at: string | null
  document_count: number
  status: string
  created_at: string
  updated_at: string
}

export type CreateKnowledgeBasePayload = {
  tenant_id: string
  name: string
  description?: string
  git_url: string
  git_branch?: string
  auth_type?: 'none' | 'token'
  auth_token?: string
}

export type UpdateKnowledgeBasePayload = {
  name?: string
  description?: string
  git_url?: string
  git_branch?: string
  auth_type?: 'none' | 'token'
  auth_token?: string
}
