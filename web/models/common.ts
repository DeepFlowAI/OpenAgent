export type PaginatedResponse<T> = {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type ApiError = {
  code: string
  message: string
  status: number
}
