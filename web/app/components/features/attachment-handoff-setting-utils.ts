export type HandoffToolOption = {
  id: number
  name: string
  tool_type: string
  is_enabled: boolean
}

export const ATTACHMENT_HANDOFF_COPY = {
  zh: {
    title: '图片/文件消息处理',
    description: '为开放 API 收到的图片或文件选择转人工工具；不选择时按普通 URL 消息处理。',
    label: '转人工工具',
    placeholder: '不设置（按普通 URL 处理）',
    noTools: '暂无已启用的转人工工具',
    goToTools: '前往工具管理',
    unavailable: '所选转人工工具当前不可用，请重新选择。',
    loading: '设置加载中...',
    loadFailed: '图片/文件处理设置加载失败',
    retry: '重试',
    updated: '图片/文件处理设置已更新',
    saveFailed: '设置保存失败，请重试',
    unavailableOption: '当前所选工具不可用',
  },
  en: {
    title: 'Image and file message handling',
    description: 'Choose a human handoff tool for images or files received through the Open API. If none is selected, the URL is handled as regular text.',
    label: 'Human handoff tool',
    placeholder: 'Not configured (treat as a regular URL)',
    noTools: 'No enabled human handoff tools',
    goToTools: 'Go to tool management',
    unavailable: 'The selected human handoff tool is unavailable. Choose another tool.',
    loading: 'Loading setting...',
    loadFailed: 'Failed to load image and file handling setting',
    retry: 'Retry',
    updated: 'Image and file handling setting updated',
    saveFailed: 'Failed to save the setting. Try again.',
    unavailableOption: 'Selected tool is unavailable',
  },
} as const

export function getEnabledHandoffTools(
  tools: HandoffToolOption[]
): HandoffToolOption[] {
  return tools.filter(
    (tool) => tool.tool_type === 'human_handoff' && tool.is_enabled
  )
}

export function isConfiguredToolUnavailable(
  configuredId: number | null,
  tools: HandoffToolOption[]
): boolean {
  return configuredId !== null && !getEnabledHandoffTools(tools).some(
    (tool) => tool.id === configuredId
  )
}
