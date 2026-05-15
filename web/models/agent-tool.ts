export type AgentTool = {
  id: number
  agent_id: number
  tenant_id: string
  tool_type: 'search' | 'doc_query' | 'doc_grep' | 'notebook' | 'tool_response_fetch' | 'python_code'
  name: string
  description: string | null
  is_system: boolean
  is_enabled: boolean
  parameters_schema: Record<string, unknown> | null
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type CreateAgentToolPayload = {
  name: string
  description?: string
  tool_type: AgentTool['tool_type']
  config?: Record<string, unknown>
}

export type UpdateAgentToolPayload = {
  name?: string
  description?: string
  config?: Record<string, unknown>
}

export type ToggleAgentToolPayload = {
  is_enabled: boolean
}

export const TOOL_TYPE_LABELS: Record<AgentTool['tool_type'], { zh: string; en: string }> = {
  search: { zh: '搜索工具', en: 'Search Tool' },
  doc_query: { zh: '文档查询', en: 'Doc Query' },
  doc_grep: { zh: '单文档检索', en: 'Doc Grep' },
  notebook: { zh: '笔记', en: 'Notebook' },
  tool_response_fetch: { zh: '按ID取回', en: 'ID Fetch' },
  python_code: { zh: 'Python 代码', en: 'Python Code' },
}
