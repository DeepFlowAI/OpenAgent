export type Tenant = {
  id: string
  name: string
  slug: string | null
  remark: string | null
  status: 'enabled' | 'disabled'
  admin_username: string | null
  created_at: string | null
  updated_at: string | null
}

export type CreateTenantPayload = {
  name: string
  slug?: string
  remark?: string
  admin_username: string
  admin_password: string
}

export type UpdateTenantPayload = {
  name?: string
  slug?: string | null
  remark?: string
  admin_username?: string
  admin_password?: string
}

export type UpdateTenantStatusPayload = {
  status: 'enabled' | 'disabled'
}
