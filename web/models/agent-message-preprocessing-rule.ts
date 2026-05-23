export type AgentMessagePreprocessingAction = 'prefix' | 'suffix'

export type AgentMessagePreprocessingRule = {
  id: number
  agent_id: number
  tenant_id: string
  condition: string
  action: AgentMessagePreprocessingAction
  value: string
  created_at: string
  updated_at: string
}

export type AgentMessagePreprocessingRuleListResponse = {
  items: AgentMessagePreprocessingRule[]
  total: number
}

export type CreateAgentMessagePreprocessingRulePayload = {
  condition: string
  action: AgentMessagePreprocessingAction
  value?: string
}

export type UpdateAgentMessagePreprocessingRulePayload =
  Partial<CreateAgentMessagePreprocessingRulePayload>

export const AGENT_MESSAGE_PREPROCESSING_ACTION_LABELS: Record<
  AgentMessagePreprocessingAction,
  { zh: string; en: string }
> = {
  prefix: { zh: '前缀', en: 'Prefix' },
  suffix: { zh: '后缀', en: 'Suffix' },
}
