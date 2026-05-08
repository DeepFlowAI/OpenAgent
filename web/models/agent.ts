export type Agent = {
  id: number
  tenant_id: string
  name: string
  description: string | null
  status: 'active' | 'inactive'
  engine_config: EngineConfig
  created_at: string
  updated_at: string
}

export type ModelConfig = {
  model_name: string
  first_round_thinking: boolean
  subsequent_rounds_thinking: boolean
  temperature: number
  top_p: number
  max_tokens: number
}

export type ContextConfig = {
  max_rounds: number
  history_tool_rounds: number
  recent_full_tool_responses: number
}

export type PreRecallConfig = {
  enabled: boolean
  tool_id: number | null
}

export type EngineConfig = {
  system_prompt: string
  model: ModelConfig
  selected_tool_ids: number[]
  context: ContextConfig
  pre_recall: PreRecallConfig
}

export const DEFAULT_ENGINE_CONFIG: EngineConfig = {
  system_prompt: '',
  model: {
    model_name: '',
    first_round_thinking: false,
    subsequent_rounds_thinking: false,
    temperature: 0.01,
    top_p: 0.85,
    max_tokens: 4096,
  },
  selected_tool_ids: [],
  context: {
    max_rounds: 0,
    history_tool_rounds: 0,
    recent_full_tool_responses: 1,
  },
  pre_recall: {
    enabled: false,
    tool_id: null,
  },
}

export type CreateAgentPayload = {
  tenant_id: string
  name: string
  description?: string
}

export type UpdateAgentPayload = {
  name?: string
  description?: string
}

export type UpdateAgentStatusPayload = {
  status: 'active' | 'inactive'
}
