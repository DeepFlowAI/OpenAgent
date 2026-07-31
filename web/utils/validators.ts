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

const accountPasswordSchema = z
  .string()
  .min(8, '密码为 8–32 位，需包含大小写字母和数字')
  .max(32, '密码为 8–32 位，需包含大小写字母和数字')
  .regex(
    /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/,
    '密码为 8–32 位，需包含大小写字母和数字'
  )

const accountBaseSchema = z.object({
  username: z
    .string()
    .trim()
    .min(1, '请输入用户名')
    .regex(
      /^[A-Za-z0-9._-]{4,32}$/,
      '用户名为 4–32 位，仅支持字母、数字、点、下划线和短横线'
    ),
  email: z
    .string()
    .trim()
    .min(1, '请输入邮箱')
    .email('请输入有效的邮箱地址')
    .max(128, '请输入有效的邮箱地址'),
  role: z.enum(['admin', 'quality_inspector']),
  agent_ids: z.array(z.number().int().positive()),
  knowledge_base_ids: z.array(z.number().int().positive()),
})

export const createAccountSchema = accountBaseSchema.extend({
  password: accountPasswordSchema,
})

export const updateAccountSchema = accountBaseSchema.extend({
  password: z
    .union([accountPasswordSchema, z.literal('')])
    .optional(),
})
