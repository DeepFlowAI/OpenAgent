import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type User = {
  id: number
  tenant_id: string
  username: string
  role: string
}

type AuthState = {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token) => {
        set({ user, token })
        localStorage.setItem('auth_token', token)
      },
      clearAuth: () => {
        set({ user: null, token: null })
        localStorage.removeItem('auth_token')
      },
    }),
    { name: 'app-auth' }
  )
)
