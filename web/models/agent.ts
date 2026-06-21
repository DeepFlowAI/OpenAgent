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
  max_tool_loop_rounds: number
}

export type PreRecallConfig = {
  enabled: boolean
  tool_id: number | null
}

export type WelcomeMessageBlock =
  | {
      type: 'markdown'
      content: string
    }
  | {
      type: 'embed'
      embed_code: string
      height: number
    }

export type WelcomeMessageConfig = {
  enabled: boolean
  blocks: WelcomeMessageBlock[]
}

export type AIDisclaimerConfig = {
  enabled: boolean
  content: string
}

export type FAQQuestionConfig = {
  text: string
}

export type FAQCategoryConfig = {
  name: string
  questions: FAQQuestionConfig[]
}

export type FAQConfig = {
  enabled: boolean
  title: string
  categories: FAQCategoryConfig[]
}

export type ToolCallLimitReplyConfig = {
  enabled: boolean
  /** Markdown source rendered when a turn reaches the tool-call limit. */
  content: string
}

export type ConversationSettingsConfig = {
  welcome_message: WelcomeMessageConfig
  faq: FAQConfig
  ai_disclaimer: AIDisclaimerConfig
  tool_call_limit_reply: ToolCallLimitReplyConfig
}

export type EngineConfig = {
  system_prompt: string
  model: ModelConfig
  selected_tool_ids: number[]
  context: ContextConfig
  pre_recall: PreRecallConfig
  conversation_settings: ConversationSettingsConfig
}

export const DEFAULT_AI_DISCLAIMER_CONTENT = '本内容由AI生成，仅供参考'
export const DEFAULT_TOOL_CALL_LIMIT_REPLY_CONTENT =
  '抱歉，本轮回复已达到工具调用上限，暂时无法继续处理。请简化问题、缩小查询范围或稍后重试。'

export const DEFAULT_CONVERSATION_SETTINGS: ConversationSettingsConfig = {
  welcome_message: {
    enabled: false,
    blocks: [],
  },
  faq: {
    enabled: false,
    title: '常见问题',
    categories: [],
  },
  ai_disclaimer: {
    enabled: false,
    content: DEFAULT_AI_DISCLAIMER_CONTENT,
  },
  tool_call_limit_reply: {
    enabled: true,
    content: DEFAULT_TOOL_CALL_LIMIT_REPLY_CONTENT,
  },
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
    max_tool_loop_rounds: 20,
  },
  pre_recall: {
    enabled: false,
    tool_id: null,
  },
  conversation_settings: DEFAULT_CONVERSATION_SETTINGS,
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
