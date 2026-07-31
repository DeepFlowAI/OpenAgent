export type AccountRole = 'admin' | 'quality_inspector'

export type Account = {
  id: number
  username: string
  email: string
  role: AccountRole
  agent_ids: number[]
  agent_names: string[]
  knowledge_base_ids: number[]
  knowledge_base_names: string[]
  is_current: boolean
  is_last_admin: boolean
  created_at: string | null
  updated_at: string | null
}

export type AccountPayload = {
  username: string
  email: string
  role: AccountRole
  password?: string
  agent_ids: number[]
  knowledge_base_ids: number[]
}

export type CreateAccountPayload = AccountPayload & {
  password: string
}

export type AccountResourceOption = {
  id: number
  name: string
  status: string | null
}

export type AccountResourceOptions = {
  agents: AccountResourceOption[]
  knowledge_bases: AccountResourceOption[]
}

export type AccountListParams = {
  q?: string
  role?: AccountRole
  page: number
  per_page: 20 | 50 | 100
}
