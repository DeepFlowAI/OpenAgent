import { describe, expect, it } from 'vitest'
import {
  ATTACHMENT_HANDOFF_COPY,
  getEnabledHandoffTools,
  isConfiguredToolUnavailable,
} from './attachment-handoff-setting-utils'

const tools = [
  {
    id: 1,
    tool_type: 'human_handoff',
    name: 'human_handoff',
    is_enabled: true,
  },
  {
    id: 2,
    tool_type: 'human_handoff',
    name: 'disabled_handoff',
    is_enabled: false,
  },
]

describe('attachment handoff setting helpers', () => {
  it('lists only enabled human handoff tools', () => {
    expect(getEnabledHandoffTools(tools).map((tool) => tool.id)).toEqual([1])
  })

  it('detects missing or disabled configured tools without clearing the id', () => {
    expect(isConfiguredToolUnavailable(1, tools)).toBe(false)
    expect(isConfiguredToolUnavailable(2, tools)).toBe(true)
    expect(isConfiguredToolUnavailable(999, tools)).toBe(true)
    expect(isConfiguredToolUnavailable(null, tools)).toBe(false)
  })

  it('provides required Chinese and English feedback copy', () => {
    expect(ATTACHMENT_HANDOFF_COPY.zh.updated).toBe('图片/文件处理设置已更新')
    expect(ATTACHMENT_HANDOFF_COPY.en.saveFailed).toContain('Failed to save')
  })
})
