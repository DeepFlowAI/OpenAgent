'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams } from 'next/navigation'
import {
  IconArrowDown,
  IconArrowUp,
  IconCode,
  IconFileText,
  IconInfoCircle,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { Button } from '@/app/components/base/button'
import { Switch } from '@/app/components/base/switch'
import { Textarea } from '@/app/components/base/textarea'
import { useToast } from '@/app/components/base/toast'
import { MarkdownContent } from '@/app/components/features/chat-message-blocks'
import { WelcomeEmbedFrame } from '@/app/components/features/welcome-embed-frame'
import {
  DEFAULT_CONVERSATION_SETTINGS,
  type ConversationSettingsConfig,
  type WelcomeMessageBlock,
} from '@/models/agent'
import { getErrorMessage } from '@/service/base'
import { useAgent, useUpdateEngineConfig } from '@/service/use-agent'
import { cn } from '@/utils/classnames'
import { useUnsavedChangesGuard } from '@/utils/use-unsaved-changes'
import {
  isValidWelcomeBlock,
  normalizeConversationSettings,
} from '@/utils/welcome-message'

const AI_DISCLAIMER_MAX_LENGTH = 200
const TOOL_CALL_LIMIT_REPLY_MAX_LENGTH = 300

function createMarkdownBlock(): WelcomeMessageBlock {
  return { type: 'markdown', content: '' }
}

function createEmbedBlock(): WelcomeMessageBlock {
  return { type: 'embed', embed_code: '', height: 360 }
}

export default function ConversationSettingsPage() {
  const params = useParams()
  const agentId = Number(params.id)
  const { toast } = useToast()
  const { data: agent, isLoading } = useAgent(agentId)
  const updateMutation = useUpdateEngineConfig()

  const [config, setConfig] = useState<ConversationSettingsConfig>(
    DEFAULT_CONVERSATION_SETTINGS,
  )
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (agent && !initialized) {
      setConfig(normalizeConversationSettings(agent.engine_config?.conversation_settings))
      setInitialized(true)
    }
  }, [agent, initialized])

  const savedConfig = useMemo(
    () => normalizeConversationSettings(agent?.engine_config?.conversation_settings),
    [agent],
  )

  const isDirty = useMemo(() => {
    if (!agent || !initialized) return false
    return JSON.stringify(config) !== JSON.stringify(savedConfig)
  }, [agent, config, initialized, savedConfig])
  useUnsavedChangesGuard(isDirty)

  const heightError = useMemo(
    () =>
      config.welcome_message.blocks.some(
        (block) =>
          block.type === 'embed' &&
          (!Number.isInteger(block.height) || block.height <= 0),
      ),
    [config],
  )
  const aiDisclaimerContent = config.ai_disclaimer.content
  const aiDisclaimerError = useMemo(() => {
    if (aiDisclaimerContent.length > AI_DISCLAIMER_MAX_LENGTH) {
      return `最多输入 ${AI_DISCLAIMER_MAX_LENGTH} 字`
    }
    if (config.ai_disclaimer.enabled && aiDisclaimerContent.trim().length === 0) {
      return '请输入免责声明内容'
    }
    return ''
  }, [aiDisclaimerContent, config.ai_disclaimer.enabled])
  const toolCallLimitReplyContent = config.tool_call_limit_reply.content
  const toolCallLimitReplyError = useMemo(() => {
    if (toolCallLimitReplyContent.length > TOOL_CALL_LIMIT_REPLY_MAX_LENGTH) {
      return `最多输入 ${TOOL_CALL_LIMIT_REPLY_MAX_LENGTH} 字`
    }
    if (
      config.tool_call_limit_reply.enabled &&
      toolCallLimitReplyContent.trim().length === 0
    ) {
      return '请输入工具调用上限回复'
    }
    return ''
  }, [config.tool_call_limit_reply.enabled, toolCallLimitReplyContent])

  const canSave =
    isDirty && !heightError && !aiDisclaimerError && !toolCallLimitReplyError

  const setWelcomeEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({
      ...prev,
      welcome_message: {
        ...prev.welcome_message,
        enabled,
      },
    }))
  }, [])

  const setAIDisclaimerEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({
      ...prev,
      ai_disclaimer: {
        ...prev.ai_disclaimer,
        enabled,
      },
    }))
  }, [])

  const setAIDisclaimerContent = useCallback((content: string) => {
    setConfig((prev) => ({
      ...prev,
      ai_disclaimer: {
        ...prev.ai_disclaimer,
        content,
      },
    }))
  }, [])

  const setToolCallLimitReplyContent = useCallback((content: string) => {
    setConfig((prev) => ({
      ...prev,
      tool_call_limit_reply: {
        ...prev.tool_call_limit_reply,
        content,
      },
    }))
  }, [])

  const addBlock = useCallback((block: WelcomeMessageBlock) => {
    setConfig((prev) => ({
      ...prev,
      welcome_message: {
        ...prev.welcome_message,
        blocks: [...prev.welcome_message.blocks, block],
      },
    }))
  }, [])

  const updateBlock = useCallback((index: number, block: WelcomeMessageBlock) => {
    setConfig((prev) => ({
      ...prev,
      welcome_message: {
        ...prev.welcome_message,
        blocks: prev.welcome_message.blocks.map((item, itemIndex) =>
          itemIndex === index ? block : item,
        ),
      },
    }))
  }, [])

  const removeBlock = useCallback((index: number) => {
    setConfig((prev) => ({
      ...prev,
      welcome_message: {
        ...prev.welcome_message,
        blocks: prev.welcome_message.blocks.filter((_, itemIndex) => itemIndex !== index),
      },
    }))
  }, [])

  const moveBlock = useCallback((index: number, direction: -1 | 1) => {
    setConfig((prev) => {
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= prev.welcome_message.blocks.length) return prev
      const blocks = [...prev.welcome_message.blocks]
      const current = blocks[index]
      blocks[index] = blocks[nextIndex]
      blocks[nextIndex] = current
      return {
        ...prev,
        welcome_message: {
          ...prev.welcome_message,
          blocks,
        },
      }
    })
  }, [])

  const handleSave = useCallback(async () => {
    if (heightError) {
      toast('嵌入组件高度必须为正整数', 'error')
      return
    }
    if (aiDisclaimerError) {
      toast(aiDisclaimerError, 'error')
      return
    }
    if (toolCallLimitReplyError) {
      toast(toolCallLimitReplyError, 'error')
      return
    }
    try {
      await updateMutation.mutateAsync({
        id: agentId,
        data: { conversation_settings: config },
      })
      toast('已保存', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }, [
    agentId,
    aiDisclaimerError,
    config,
    heightError,
    toast,
    toolCallLimitReplyError,
    updateMutation,
  ])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-[#71717A]">加载中...</p>
      </div>
    )
  }

  const blocks = config.welcome_message.blocks
  const enabled = config.welcome_message.enabled
  const validBlocks = blocks.filter(isValidWelcomeBlock)
  const aiDisclaimerEnabled = config.ai_disclaimer.enabled
  const toolCallLimitReplyEnabled = config.tool_call_limit_reply.enabled

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#ECECEC] bg-white/80 px-6 py-4 backdrop-blur-sm">
        <h2 className="text-base font-semibold text-[#18181B]">对话设置</h2>
        <Button
          disabled={!canSave}
          loading={updateMutation.isPending}
          onClick={handleSave}
        >
          保存
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-8">
        <section className="rounded-[10px] border border-[#E4E4E7] bg-white p-6">
          <div className="flex items-start gap-3">
            <Switch
              checked={enabled}
              onChange={setWelcomeEnabled}
              className="mt-0.5 shrink-0"
              aria-label="启用欢迎语"
            />
            <div className="min-w-0 flex-1 space-y-1">
              <h3 className="text-sm font-semibold text-[#18181B]">欢迎语</h3>
              <p className="text-[13px] leading-relaxed text-[#71717A]">
                开启后，访客打开 Web SDK 时优先展示欢迎语；访客发送第一条消息前不会创建会话。
              </p>
            </div>
          </div>

          {enabled && (
            <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-semibold text-[#18181B]">内容块</h4>
                    <p className="mt-1 text-[12px] text-[#71717A]">
                      按顺序渲染 Markdown 正文和第三方嵌入组件。
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={() => addBlock(createMarkdownBlock())}
                    >
                      <IconPlus size={15} />
                      Markdown
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={() => addBlock(createEmbedBlock())}
                    >
                      <IconPlus size={15} />
                      嵌入组件
                    </Button>
                  </div>
                </div>

                {blocks.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-[#D4D4D8] px-4 py-10 text-center">
                    <p className="text-sm font-medium text-[#18181B]">暂无内容块</p>
                    <p className="mt-1 text-[13px] text-[#71717A]">
                      添加 Markdown 或嵌入组件后，Web SDK 才会展示欢迎语。
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {blocks.map((block, index) => (
                      <WelcomeBlockEditor
                        key={`${block.type}-${index}`}
                        block={block}
                        index={index}
                        total={blocks.length}
                        onChange={(next) => updateBlock(index, next)}
                        onRemove={() => removeBlock(index)}
                        onMove={(direction) => moveBlock(index, direction)}
                      />
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-3">
                <div>
                  <h4 className="text-sm font-semibold text-[#18181B]">预览</h4>
                  <p className="mt-1 text-[12px] text-[#71717A]">
                    仅展示有效块；空块可保存但不会出现在 Web SDK。
                  </p>
                </div>
                <WelcomePreview blocks={validBlocks} />
              </div>
            </div>
          )}
        </section>

        <section className="mt-6 rounded-[10px] border border-[#E4E4E7] bg-white p-6">
          <div className="flex items-start gap-3">
            <Switch
              checked={aiDisclaimerEnabled}
              onChange={setAIDisclaimerEnabled}
              className="mt-0.5 shrink-0"
              aria-label="启用 AI 免责声明"
            />
            <div className="min-w-0 flex-1 space-y-1">
              <h3 className="text-sm font-semibold text-[#18181B]">AI 免责声明</h3>
              <p className="text-[13px] leading-relaxed text-[#71717A]">
                开启后，在 Web SDK 的 Agent 回复消息下方展示免责声明。
              </p>
            </div>
          </div>

          {aiDisclaimerEnabled && (
            <div className="mt-6 space-y-3">
              <Textarea
                label="免责声明内容"
                placeholder="请输入 AI 免责声明内容"
                value={aiDisclaimerContent}
                onChange={(event) =>
                  setAIDisclaimerContent(event.currentTarget.value)
                }
                error={aiDisclaimerError || undefined}
                className="min-h-[112px]"
              />
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-start gap-1.5 text-[12px] leading-relaxed text-[#71717A]">
                  <IconInfoCircle size={14} className="mt-0.5 shrink-0" />
                  <span className="min-w-0">
                    仅按纯文本展示，不解析 Markdown、HTML 或脚本。
                  </span>
                </div>
                <span
                  className={cn(
                    'shrink-0 text-xs',
                    aiDisclaimerContent.length > AI_DISCLAIMER_MAX_LENGTH
                      ? 'text-[#DC2626]'
                      : 'text-[#A3A3A3]',
                  )}
                >
                  {aiDisclaimerContent.length}/{AI_DISCLAIMER_MAX_LENGTH}
                </span>
              </div>
            </div>
          )}
        </section>

        <section className="mt-6 rounded-[10px] border border-[#E4E4E7] bg-white p-6">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#F4F4F5] text-[#52525B]">
              <IconInfoCircle size={15} />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <h3 className="text-sm font-semibold text-[#18181B]">工具调用上限回复</h3>
              <p className="text-[13px] leading-relaxed text-[#71717A]">
                当一轮回复达到工具调用上限时，在用户侧展示以下提示，避免用户误认为对话卡住。
              </p>
            </div>
          </div>

          {toolCallLimitReplyEnabled && (
            <div className="mt-6 space-y-3">
              <div className="rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-[12px] leading-relaxed text-[#92400E]">
                当前系统会在一轮回复达到 20 次工具调用后停止继续调用工具。
              </div>
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
                <div className="space-y-3">
                  <Textarea
                    label="回复内容"
                    placeholder={'请输入达到工具调用上限时展示给用户的回复，支持 **加粗**、列表和 [链接](https://example.com)'}
                    value={toolCallLimitReplyContent}
                    onChange={(event) =>
                      setToolCallLimitReplyContent(event.currentTarget.value)
                    }
                    error={toolCallLimitReplyError || undefined}
                    className="min-h-[140px] font-mono"
                  />
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-1.5 text-[12px] leading-relaxed text-[#71717A]">
                      <IconInfoCircle size={14} className="mt-0.5 shrink-0" />
                      <span className="min-w-0">
                        支持 Markdown 基础语法；HTML、脚本、iframe 和链接预览不会被渲染。
                      </span>
                    </div>
                    <span
                      className={cn(
                        'shrink-0 text-xs',
                        toolCallLimitReplyContent.length > TOOL_CALL_LIMIT_REPLY_MAX_LENGTH
                          ? 'text-[#DC2626]'
                          : 'text-[#A3A3A3]',
                      )}
                    >
                      {toolCallLimitReplyContent.length}/{TOOL_CALL_LIMIT_REPLY_MAX_LENGTH}
                    </span>
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-semibold text-[#18181B]">预览</h4>
                    <p className="mt-1 text-[12px] text-[#71717A]">
                      超限后将按该效果展示给用户。
                    </p>
                  </div>
                  <div className="min-h-[140px] rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] p-4">
                    {toolCallLimitReplyContent.trim() ? (
                      <div className="rounded-[14px] border border-[#E5E5E5] bg-white px-3 py-3">
                        <MarkdownContent
                          source={toolCallLimitReplyContent}
                          style={{ color: '#1A1A1A' }}
                        />
                      </div>
                    ) : (
                      <div className="flex min-h-[100px] items-center justify-center text-[13px] text-[#A1A1AA]">
                        暂无预览
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function WelcomeBlockEditor({
  block,
  index,
  total,
  onChange,
  onRemove,
  onMove,
}: {
  block: WelcomeMessageBlock
  index: number
  total: number
  onChange: (block: WelcomeMessageBlock) => void
  onRemove: () => void
  onMove: (direction: -1 | 1) => void
}) {
  const isEmbedHeightInvalid =
    block.type === 'embed' && (!Number.isInteger(block.height) || block.height <= 0)

  return (
    <div className="rounded-lg border border-[#E4E4E7] bg-white">
      <div className="flex items-center justify-between border-b border-[#ECECEC] px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4F4F5] text-[#52525B]">
            {block.type === 'markdown' ? <IconFileText size={16} /> : <IconCode size={16} />}
          </div>
          <div>
            <p className="text-sm font-medium text-[#18181B]">
              {block.type === 'markdown' ? 'Markdown 块' : '嵌入组件块'}
            </p>
            <p className="text-[12px] text-[#A1A1AA]">#{index + 1}</p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <IconButton
            label="上移"
            disabled={index === 0}
            onClick={() => onMove(-1)}
          >
            <IconArrowUp size={16} />
          </IconButton>
          <IconButton
            label="下移"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
          >
            <IconArrowDown size={16} />
          </IconButton>
          <IconButton label="删除" destructive onClick={onRemove}>
            <IconTrash size={16} />
          </IconButton>
        </div>
      </div>

      <div className="space-y-4 p-4">
        {block.type === 'markdown' ? (
          <Textarea
            label="Markdown 内容"
            placeholder="输入欢迎语正文，支持链接、列表、图片等 Markdown 语法。"
            value={block.content}
            onChange={(event) =>
              onChange({ ...block, content: event.currentTarget.value })
            }
            className="min-h-[180px] font-mono"
          />
        ) : (
          <>
            <Textarea
              label="嵌入代码"
              placeholder="粘贴第三方平台提供的 iframe / script / HTML 片段"
              value={block.embed_code}
              onChange={(event) =>
                onChange({ ...block, embed_code: event.currentTarget.value })
              }
              className="min-h-[180px] font-mono"
            />
            <div className="max-w-[220px]">
              <label className="mb-1.5 block text-sm font-medium text-[#1a1a1a]">
                高度（px）
              </label>
              <input
                type="number"
                min={1}
                value={block.height}
                onChange={(event) =>
                  onChange({
                    ...block,
                    height: Number.parseInt(event.currentTarget.value, 10) || 0,
                  })
                }
                className={cn(
                  'h-10 w-full rounded-lg border border-[#E5E5E5] px-3 text-sm text-[#18181B] outline-none focus:border-[#18181B]',
                  isEmbedHeightInvalid && 'border-[#DC2626] focus:border-[#DC2626]',
                )}
              />
              {isEmbedHeightInvalid && (
                <p className="mt-1 text-xs text-[#DC2626]">
                  嵌入组件高度必须为正整数
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function IconButton({
  children,
  label,
  destructive,
  disabled,
  onClick,
}: {
  children: ReactNode
  label: string
  destructive?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-md text-[#52525B] transition-colors hover:bg-[#F4F4F5] hover:text-[#18181B] disabled:cursor-not-allowed disabled:opacity-40',
        destructive && 'hover:bg-[#FEF2F2] hover:text-[#DC2626]',
      )}
    >
      {children}
    </button>
  )
}

function WelcomePreview({ blocks }: { blocks: WelcomeMessageBlock[] }) {
  if (blocks.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[#D4D4D8] bg-[#FAFAFA] px-4 py-10 text-center">
        <p className="text-sm font-medium text-[#18181B]">暂无有效欢迎语</p>
        <p className="mt-1 text-[13px] leading-relaxed text-[#71717A]">
          Web SDK 将继续展示原无消息图片 / 空状态。
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-[#E4E4E7] bg-[#FAFAFA] p-4">
      <div className="rounded-[14px] border border-[#E5E5E5] bg-white px-3 py-3">
        <div className="space-y-3">
          {blocks.map((block, index) =>
            block.type === 'markdown' ? (
              <MarkdownContent
                key={`preview-md-${index}`}
                source={block.content}
                style={{ color: '#1A1A1A' }}
              />
            ) : (
              <WelcomeEmbedFrame
                key={`preview-embed-${index}`}
                title={`欢迎语嵌入组件预览 ${index + 1}`}
                embedCode={block.embed_code}
                className="w-full rounded-lg border border-[#E4E4E7] bg-white"
                style={{ height: block.height }}
              />
            ),
          )}
        </div>
      </div>
    </div>
  )
}
