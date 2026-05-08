export type LoginPayload = {
  tenant: string
  username: string
  password: string
}

export type LoginUser = {
  id: number
  tenant_id: string
  username: string
  role: string
}

export type LoginResponse = {
  token: string
  user: LoginUser
}

export type SendCodePayload = {
  tenant: string
  username: string
  locale?: string
}

export type ResetPasswordPayload = {
  tenant: string
  username: string
  verify_code: string
  new_password: string
}

export type MessageResponse = {
  message: string
}
