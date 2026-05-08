// Legacy single-key types (backward compat)
export type ApiKeyInfo = {
  masked_key: string
  created_at: string
  updated_at: string
}

export type ApiKeyFull = {
  key_value: string
}

// Multi-key management types
export type ApiKeyItem = {
  id: number
  name: string
  description: string | null
  masked_key: string
  scopes: string[]
  status: string
  created_at: string
  updated_at: string
}

export type ApiKeyCreatePayload = {
  name: string
  scopes: string[]
  description?: string
}

export type ApiKeyCreateResponse = ApiKeyItem & {
  key_value: string
}

export type ApiKeyListResponse = {
  items: ApiKeyItem[]
  total: number
  page: number
  per_page: number
  pages: number
}
