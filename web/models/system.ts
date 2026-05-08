export type SystemEdition = 'community' | 'enterprise'

export type SystemInfo = {
  app_name: string
  app_version: string
  edition: SystemEdition
  /** UX hint: hide the tenant field on the login form when true. Defaults
   *  to true on OSS deployments (tenants extension absent). */
  single_tenant_mode: boolean
  /** Tenant slug to auto-fill when single_tenant_mode is true. */
  default_tenant_id: string
}
