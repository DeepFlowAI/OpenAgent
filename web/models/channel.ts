export type Channel = {
  id: number
  tenant_id: string
  token: string
  name: string
  description: string | null
  channel_type: string
  agent_id: number | null
  access_mode: string
  secret_key: string | null
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

// Browser-facing public channel info (returned by GET /v1/public/channels/{token}).
// Intentionally omits `tenant_id` and `secret_key` — they are stripped server-side
// to avoid leaking embed-token signing material to the client.
export type PublicChannel = {
  id: number
  token: string
  name: string
  description: string | null
  channel_type: string
  agent_id: number | null
  access_mode: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type CreateChannelPayload = {
  tenant_id: string
  name: string
  description?: string
  channel_type?: string
  agent_id?: number | null
  access_mode?: string
  config?: Record<string, unknown>
}

export type UpdateChannelPayload = {
  name?: string
  description?: string | null
  agent_id?: number | null
  access_mode?: string
  config?: Record<string, unknown>
}
