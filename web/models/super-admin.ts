export type AdminLoginPayload = {
  username: string
  password: string
}

export type AdminUser = {
  id: number
  username: string
  role: string
}

export type AdminLoginResponse = {
  token: string
  user: AdminUser
}
