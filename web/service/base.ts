import ky from 'ky'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'

/** 401 on these routes is expected (wrong password etc.); do not clear session or redirect. */
function isCredentialAuthRequest(request: Request): boolean {
  const path = new URL(request.url).pathname
  return (
    path.endsWith('/v1/auth/login') ||
    path.endsWith('/v1/auth/admin-login')
  )
}

function isPublicRoute(): boolean {
  if (typeof window === 'undefined') return false
  return window.location.pathname.startsWith('/chat/')
}

const client = ky.create({
  prefixUrl: API_BASE,
  timeout: 30000,
  hooks: {
    beforeRequest: [
      (request) => {
        if (isPublicRoute()) return
        const isAdminPath = window.location.pathname.startsWith('/admin')
        const tokenKey = isAdminPath ? 'admin_auth_token' : 'auth_token'
        const token = localStorage.getItem(tokenKey)
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (isPublicRoute()) return
        if (response.status === 401 && !isCredentialAuthRequest(request)) {
          const isAdminPath = window.location.pathname.startsWith('/admin')
          if (isAdminPath) {
            localStorage.removeItem('admin_auth_token')
            window.location.href = '/admin/login'
          } else {
            localStorage.removeItem('auth_token')
            window.location.href = '/login'
          }
        }
      },
    ],
  },
})

export const get = <T>(url: string, options?: Parameters<typeof client.get>[1]) =>
  client.get(url, options).json<T>()

export const post = <T>(url: string, options?: Parameters<typeof client.post>[1]) =>
  client.post(url, options).json<T>()

export const put = <T>(url: string, options?: Parameters<typeof client.put>[1]) =>
  client.put(url, options).json<T>()

export const patch = <T>(url: string, options?: Parameters<typeof client.patch>[1]) =>
  client.patch(url, options).json<T>()

export const del = <T = void>(url: string, options?: Parameters<typeof client.delete>[1]) =>
  client.delete(url, options).json<T>()

export async function uploadImage(file: File): Promise<{ url: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post('v1/upload/image', { body: formData, timeout: 60000 }).json<{ url: string }>()
}

function messageFromFastApiDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return undefined
  const msgs: string[] = []
  for (const item of detail) {
    if (item !== null && typeof item === 'object' && 'msg' in item) {
      const m = (item as { msg: unknown }).msg
      if (typeof m === 'string' && m) msgs.push(m)
    }
  }
  return msgs.length ? msgs.join('；') : undefined
}

export async function getErrorMessage(error: unknown): Promise<string> {
  try {
    const { HTTPError } = await import('ky')
    if (error instanceof HTTPError) {
      const text = await error.response.clone().text()
      if (text) {
        try {
          const body = JSON.parse(text) as {
            message?: string
            detail?: unknown
          }
          if (body?.message) return body.message
          const fromDetail = messageFromFastApiDetail(body?.detail)
          if (fromDetail) return fromDetail
        } catch {
          /* non-JSON body */
        }
      }
      const status = error.response.status
      const statusText = error.response.statusText
      if (statusText) return `${statusText} (${status})`
      return `请求失败 (${status})`
    }
  } catch {
    /* ignore */
  }
  return '操作失败，请重试'
}
