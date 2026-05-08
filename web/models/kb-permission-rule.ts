export type UserConditionOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'in'
  | 'not_in'
  | 'is_empty'
  | 'is_not_empty'

export type ScopeOperator =
  | 'equals'
  | 'not_equals'
  | 'contains_any'
  | 'not_contains_any'

export type UserCondition = {
  field: string
  operator: UserConditionOperator
  value: string | string[] | null
}

export type KbPermissionRule = {
  id: number
  tenant_id: string
  knowledge_base_id: number
  name: string
  enabled: boolean
  user_conditions: UserCondition[]
  scope_operator: ScopeOperator
  scope_labels: string[] | null
  created_at: string
  updated_at: string
}

export type CreateKbPermissionRulePayload = {
  name: string
  enabled?: boolean
  user_conditions: UserCondition[]
  scope_operator: ScopeOperator
  scope_labels?: string[] | null
}

export type UpdateKbPermissionRulePayload = Partial<CreateKbPermissionRulePayload>
