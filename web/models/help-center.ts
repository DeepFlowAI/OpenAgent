export type HelpCenter = {
  id: number
  tenant_id: string
  name: string
  description: string | null
  public_slug: string | null
  site_name: string | null
  publisher_logo_url: string | null
  public_root_url: string | null
  created_at: string
  updated_at: string
}

export type HelpCenterCreatePayload = {
  name: string
  description?: string | null
}

export type HelpCenterUpdatePayload = Partial<{
  name: string
  description: string | null
  public_slug: string | null
  site_name: string | null
  publisher_logo_url: string | null
}>

export type HelpCenterListResponse = {
  items: HelpCenter[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type SlugAvailability = { available: boolean }

export const SLUG_REGEX = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/

// ── Help Center Tab ──

export const FILTER_OPS = ['eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in'] as const
export type FilterOp = (typeof FILTER_OPS)[number]

export type TabFilterCondition = {
  field: string
  op: FilterOp
  value: unknown
}

export type HelpCenterTab = {
  id: number
  help_center_id: number
  display_name: string
  tab_slug: string | null
  knowledge_base_id: number
  knowledge_base_name: string | null
  fixed_filters: TabFilterCondition[]
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export type TabCreatePayload = {
  display_name: string
  tab_slug?: string | null
  knowledge_base_id: number
  fixed_filters?: TabFilterCondition[]
}

export type TabUpdatePayload = Partial<{
  display_name: string
  tab_slug: string | null
  knowledge_base_id: number
  fixed_filters: TabFilterCondition[]
}>

export type TabListResponse = { items: HelpCenterTab[] }

// ── Public (visitor-facing) shapes ──

export type PublicTab = {
  id: number
  display_name: string
  tab_slug: string
  sort_order: number
}

export type PublicHelpCenterBundle = {
  slug: string
  site_name: string
  publisher_logo_url: string | null
  tabs: PublicTab[]
}

export type PublicDocSummary = {
  id: number
  title: string
  description: string | null
  file_path: string
  updated_at: string | null
}

export type PublicDocListResponse = {
  items: PublicDocSummary[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type PublicDocDetail = {
  id: number
  title: string
  description: string | null
  file_path: string
  markdown_content: string | null
  doc_meta: Record<string, unknown> | null
  updated_at: string | null
}
