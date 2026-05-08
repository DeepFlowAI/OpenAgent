/**
 * Login / forgot-password "enterprise ID" field: must match backend
 * LoginRequest.tenant (2–64) and slug character set (a-z, 0-9, /, -).
 * Comments use English only for mixed-audience codebases.
 */

export const TENANT_LOGIN_FIELD_PATTERN = /^[a-zA-Z0-9/-]{2,64}$/

/** Returns a field error string, or null if the trimmed value is valid. */
export function tenantLoginFieldError(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed) return '请输入企业 ID'
  if (!TENANT_LOGIN_FIELD_PATTERN.test(trimmed)) {
    return '企业 ID 为 2–64 位，支持字母、数字、短横线或 /'
  }
  return null
}
