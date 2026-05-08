import { z } from 'zod'

const tenantSlugSchema = z
  .string()
  .trim()
  .toLowerCase()
  .refine(
    (value) =>
      value === '' ||
      (
        value.length >= 2 &&
        value.length <= 64 &&
        /^[a-z0-9/-]+$/.test(value) &&
        !value.startsWith('/') &&
        !value.endsWith('/') &&
        !value.includes('//') &&
        !value.includes('--')
      ),
    '租户别名格式不正确'
  )

export const createTenantSchema = z.object({
  name: z.string().min(1, '请输入租户名称').max(64, '租户名称不能超过 64 个字符'),
  slug: tenantSlugSchema.optional(),
  remark: z.string().max(256, '备注不能超过 256 个字符').optional().or(z.literal('')),
  admin_username: z
    .string()
    .min(3, '用户名至少 3 个字符')
    .max(64, '用户名不能超过 64 个字符')
    .regex(/^[a-zA-Z0-9_]+$/, '用户名只能包含字母、数字和下划线'),
  admin_password: z
    .string()
    .min(8, '密码至少 8 个字符')
    .max(64, '密码不能超过 64 个字符'),
})

export const updateTenantSchema = z.object({
  name: z.string().min(1, '请输入租户名称').max(64, '租户名称不能超过 64 个字符'),
  slug: tenantSlugSchema.optional(),
  remark: z.string().max(256, '备注不能超过 256 个字符').optional().or(z.literal('')),
  admin_username: z
    .string()
    .min(3, '用户名至少 3 个字符')
    .max(64, '用户名不能超过 64 个字符')
    .regex(/^[a-zA-Z0-9_]+$/, '用户名只能包含字母、数字和下划线'),
  admin_password: z
    .string()
    .max(64, '密码不能超过 64 个字符')
    .optional()
    .or(z.literal('')),
})

export type CreateTenantFormData = z.infer<typeof createTenantSchema>
export type UpdateTenantFormData = z.infer<typeof updateTenantSchema>
