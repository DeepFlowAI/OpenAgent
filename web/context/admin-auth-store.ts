import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type AdminUser = {
  id: number
  username: string
  role: string
}

type AdminAuthState = {
  user: AdminUser | null
  token: string | null
  setAuth: (user: AdminUser, token: string) => void
  clearAuth: () => void
}

export const useAdminAuthStore = create<AdminAuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token) => {
        set({ user, token })
        localStorage.setItem('admin_auth_token', token)
      },
      clearAuth: () => {
        set({ user: null, token: null })
        localStorage.removeItem('admin_auth_token')
      },
    }),
    { name: 'admin-auth' }
  )
)
