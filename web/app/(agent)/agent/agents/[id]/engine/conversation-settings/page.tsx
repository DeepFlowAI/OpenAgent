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
import { ConfirmModal } from '@/app/components/base/modal'
import { Input } from '@/app/components/base/input'
import { Switch } from '@/app/components/base/switch'
import { Textarea } from '@/app/components/base/textarea'
import { useToast } from '@/app/components/base/toast'
import { MarkdownContent } from '@/app/components/features/chat-message-blocks'
import { WelcomeEmbedFrame } from '@/app/components/features/welcome-embed-frame'
import {
  DEFAULT_CONVERSATION_SETTINGS,
  DEFAULT_ENGINE_CONFIG,
  type ConversationSettingsConfig,
  type FAQCategoryConfig,
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
const FAQ_TITLE_MAX_LENGTH = 20
const FAQ_CATEGORY_MAX_LENGTH = 20
const FAQ_QUESTION_MAX_LENGTH = 100
const TOOL_CALL_LIMIT_REPLY_MAX_LENGTH = 300

function createMarkdownBlock(): WelcomeMessageBlock {
  return { type: 'markdown', content: '' }
}

function createEmbedBlock(): WelcomeMessageBlock {
  return { type: 'embed', embed_code: '', height: 360 }
}

function createFAQCategory(): FAQCategoryConfig {
  return { name: '', questions: [] }
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
  const [activeFAQCategoryIndex, setActiveFAQCategoryIndex] = useState(0)
  const [deletingFAQCategoryIndex, setDeletingFAQCategoryIndex] = useState<
    number | null
  >(null)

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

  useEffect(() => {
    setActiveFAQCategoryIndex((index) => {
      if (config.faq.categories.length === 0) return 0
      return Math.min(index, config.faq.categories.length - 1)
    })
  }, [config.faq.categories.length])

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
  const faq = config.faq
  const faqTitleError = useMemo(() => {
    if (faq.title.length > FAQ_TITLE_MAX_LENGTH) {
      return `最多输入 ${FAQ_TITLE_MAX_LENGTH} 个字符`
    }
    if (faq.enabled && faq.title.trim().length === 0) {
      return '请输入组件名称'
    }
    return ''
  }, [faq.enabled, faq.title])
  const faqContentError = useMemo(() => {
    for (const category of faq.categories) {
      if (category.name.length > FAQ_CATEGORY_MAX_LENGTH) {
        return `类型名称最多输入 ${FAQ_CATEGORY_MAX_LENGTH} 个字符`
      }
      for (const question of category.questions) {
        if (question.text.length > FAQ_QUESTION_MAX_LENGTH) {
          return `问题最多输入 ${FAQ_QUESTION_MAX_LENGTH} 个字符`
        }
      }
    }
    return ''
  }, [faq.categories])
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
    isDirty &&
    !heightError &&
    !faqTitleError &&
    !faqContentError &&
    !aiDisclaimerError &&
    !toolCallLimitReplyError

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

  const setFAQEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        enabled,
      },
    }))
  }, [])

  const setFAQTitle = useCallback((title: string) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        title,
      },
    }))
  }, [])

  const addFAQCategory = useCallback(() => {
    setConfig((prev) => {
      const categories = [...prev.faq.categories, createFAQCategory()]
      setActiveFAQCategoryIndex(categories.length - 1)
      return {
        ...prev,
        faq: {
          ...prev.faq,
          categories,
        },
      }
    })
  }, [])

  const updateFAQCategoryName = useCallback((index: number, name: string) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.map((category, itemIndex) =>
          itemIndex === index ? { ...category, name } : category,
        ),
      },
    }))
  }, [])

  const moveFAQCategory = useCallback((index: number, direction: -1 | 1) => {
    setConfig((prev) => {
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= prev.faq.categories.length) return prev
      const categories = [...prev.faq.categories]
      const current = categories[index]
      categories[index] = categories[nextIndex]
      categories[nextIndex] = current
      setActiveFAQCategoryIndex(nextIndex)
      return {
        ...prev,
        faq: {
          ...prev.faq,
          categories,
        },
      }
    })
  }, [])

  const removeFAQCategory = useCallback((index: number) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.filter((_, itemIndex) => itemIndex !== index),
      },
    }))
  }, [])

  const addFAQQuestion = useCallback((categoryIndex: number) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.map((category, itemIndex) =>
          itemIndex === categoryIndex
            ? { ...category, questions: [...category.questions, { text: '' }] }
            : category,
        ),
      },
    }))
  }, [])

  const updateFAQQuestion = useCallback((
    categoryIndex: number,
    questionIndex: number,
    text: string,
  ) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.map((category, itemIndex) =>
          itemIndex === categoryIndex
            ? {
                ...category,
                questions: category.questions.map((question, qIndex) =>
                  qIndex === questionIndex ? { text } : question,
                ),
              }
            : category,
        ),
      },
    }))
  }, [])

  const moveFAQQuestion = useCallback((
    categoryIndex: number,
    questionIndex: number,
    direction: -1 | 1,
  ) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.map((category, itemIndex) => {
          if (itemIndex !== categoryIndex) return category
          const nextIndex = questionIndex + direction
          if (nextIndex < 0 || nextIndex >= category.questions.length) return category
          const questions = [...category.questions]
          const current = questions[questionIndex]
          questions[questionIndex] = questions[nextIndex]
          questions[nextIndex] = current
          return { ...category, questions }
        }),
      },
    }))
  }, [])

  const removeFAQQuestion = useCallback((categoryIndex: number, questionIndex: number) => {
    setConfig((prev) => ({
      ...prev,
      faq: {
        ...prev.faq,
        categories: prev.faq.categories.map((category, itemIndex) =>
          itemIndex === categoryIndex
            ? {
                ...category,
                questions: category.questions.filter(
                  (_, qIndex) => qIndex !== questionIndex,
                ),
              }
            : category,
        ),
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
    if (faqTitleError) {
      toast(faqTitleError, 'error')
      return
    }
    if (faqContentError) {
      toast(faqContentError, 'error')
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
    faqContentError,
    faqTitleError,
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
  const faqEnabled = config.faq.enabled
  const faqCategories = config.faq.categories
  const activeFAQCategory = faqCategories[activeFAQCategoryIndex]
  const deletingFAQCategory =
    deletingFAQCategoryIndex === null
      ? null
      : faqCategories[deletingFAQCategoryIndex] ?? null
  const aiDisclaimerEnabled = config.ai_disclaimer.enabled
  const toolCallLimitReplyEnabled = config.tool_call_limit_reply.enabled
  const configuredMaxToolLoopRounds = Number(
    agent?.engine_config?.context?.max_tool_loop_rounds,
  )
  const maxToolLoopRounds =
    Number.isFinite(configuredMaxToolLoopRounds) && configuredMaxToolLoopRounds > 0
      ? Math.trunc(configuredMaxToolLoopRounds)
      : DEFAULT_ENGINE_CONFIG.context.max_tool_loop_rounds

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
              checked={faqEnabled}
              onChange={setFAQEnabled}
              className="mt-0.5 shrink-0"
              aria-label="启用常见问题"
            />
            <div className="min-w-0 flex-1 space-y-1">
              <h3 className="text-sm font-semibold text-[#18181B]">常见问题</h3>
              <p className="text-[13px] leading-relaxed text-[#71717A]">
                开启后，在当前会话欢迎语下方展示问题引导；配置内容不进入历史。
              </p>
            </div>
          </div>

          {faqEnabled && (
            <div className="mt-6 space-y-5">
              <div className="max-w-[360px]">
                <Input
                  label="组件名称"
                  placeholder="常见问题"
                  value={config.faq.title}
                  onChange={(event) => setFAQTitle(event.currentTarget.value)}
                  error={faqTitleError || undefined}
                />
                <div className="mt-1 text-right text-xs text-[#A3A3A3]">
                  {config.faq.title.length}/{FAQ_TITLE_MAX_LENGTH}
                </div>
              </div>

              <div className="grid gap-5 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)]">
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-[#18181B]">问题类型</h4>
                      <p className="mt-1 text-[12px] text-[#71717A]">
                        访客侧按此顺序从左到右展示。
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={addFAQCategory}
                    >
                      <IconPlus size={15} />
                      添加类型
                    </Button>
                  </div>

                  {faqCategories.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-[#D4D4D8] px-4 py-8 text-center">
                      <p className="text-sm font-medium text-[#18181B]">暂无问题类型</p>
                      <p className="mt-1 text-[13px] text-[#71717A]">
                        添加类型后，可继续维护该类型下的问题。
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {faqCategories.map((category, index) => (
                        <div
                          key={`faq-category-${index}`}
                          className={cn(
                            'rounded-lg border bg-white p-3 transition-colors',
                            activeFAQCategoryIndex === index
                              ? 'border-[#18181B]'
                              : 'border-[#E4E4E7]',
                          )}
                        >
                          <button
                            type="button"
                            className="mb-3 w-full text-left"
                            onClick={() => setActiveFAQCategoryIndex(index)}
                          >
                            <span className="block text-sm font-medium text-[#18181B]">
                              {category.name.trim() || '未命名类型'}
                            </span>
                            <span className="mt-0.5 block text-[12px] text-[#A1A1AA]">
                              {category.questions.length} 个问题
                            </span>
                          </button>
                          <Input
                            placeholder="输入类型名称"
                            value={category.name}
                            onChange={(event) =>
                              updateFAQCategoryName(index, event.currentTarget.value)
                            }
                            error={
                              category.name.length > FAQ_CATEGORY_MAX_LENGTH
                                ? `最多输入 ${FAQ_CATEGORY_MAX_LENGTH} 个字符`
                                : undefined
                            }
                          />
                          <div className="mt-3 flex items-center justify-between">
                            <span className="text-xs text-[#A3A3A3]">
                              {category.name.length}/{FAQ_CATEGORY_MAX_LENGTH}
                            </span>
                            <div className="flex items-center gap-1">
                              <IconButton
                                label="上移类型"
                                disabled={index === 0}
                                onClick={() => moveFAQCategory(index, -1)}
                              >
                                <IconArrowUp size={16} />
                              </IconButton>
                              <IconButton
                                label="下移类型"
                                disabled={index === faqCategories.length - 1}
                                onClick={() => moveFAQCategory(index, 1)}
                              >
                                <IconArrowDown size={16} />
                              </IconButton>
                              <IconButton
                                label="删除类型"
                                destructive
                                onClick={() => setDeletingFAQCategoryIndex(index)}
                              >
                                <IconTrash size={16} />
                              </IconButton>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-[#18181B]">
                        当前类型的问题
                      </h4>
                      <p className="mt-1 text-[12px] text-[#71717A]">
                        空问题可保存，但不会在访客侧展示。
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      disabled={!activeFAQCategory}
                      onClick={() => addFAQQuestion(activeFAQCategoryIndex)}
                    >
                      <IconPlus size={15} />
                      添加问题
                    </Button>
                  </div>

                  {!activeFAQCategory ? (
                    <div className="rounded-lg border border-dashed border-[#D4D4D8] px-4 py-8 text-center">
                      <p className="text-sm font-medium text-[#18181B]">暂无问题</p>
                      <p className="mt-1 text-[13px] text-[#71717A]">
                        先添加或选择一个问题类型。
                      </p>
                    </div>
                  ) : activeFAQCategory.questions.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-[#D4D4D8] px-4 py-8 text-center">
                      <p className="text-sm font-medium text-[#18181B]">暂无问题</p>
                      <p className="mt-1 text-[13px] text-[#71717A]">
                        添加问题后，访客可点击发送。
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {activeFAQCategory.questions.map((question, index) => (
                        <div
                          key={`faq-question-${activeFAQCategoryIndex}-${index}`}
                          className="rounded-lg border border-[#E4E4E7] bg-white p-3"
                        >
                          <Input
                            placeholder="输入问题"
                            value={question.text}
                            onChange={(event) =>
                              updateFAQQuestion(
                                activeFAQCategoryIndex,
                                index,
                                event.currentTarget.value,
                              )
                            }
                            error={
                              question.text.length > FAQ_QUESTION_MAX_LENGTH
                                ? `最多输入 ${FAQ_QUESTION_MAX_LENGTH} 个字符`
                                : undefined
                            }
                          />
                          <div className="mt-3 flex items-center justify-between">
                            <span className="text-xs text-[#A3A3A3]">
                              {question.text.length}/{FAQ_QUESTION_MAX_LENGTH}
                            </span>
                            <div className="flex items-center gap-1">
                              <IconButton
                                label="上移问题"
                                disabled={index === 0}
                                onClick={() =>
                                  moveFAQQuestion(activeFAQCategoryIndex, index, -1)
                                }
                              >
                                <IconArrowUp size={16} />
                              </IconButton>
                              <IconButton
                                label="下移问题"
                                disabled={index === activeFAQCategory.questions.length - 1}
                                onClick={() =>
                                  moveFAQQuestion(activeFAQCategoryIndex, index, 1)
                                }
                              >
                                <IconArrowDown size={16} />
                              </IconButton>
                              <IconButton
                                label="删除问题"
                                destructive
                                onClick={() =>
                                  removeFAQQuestion(activeFAQCategoryIndex, index)
                                }
                              >
                                <IconTrash size={16} />
                              </IconButton>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {faqContentError && (
                <p className="text-xs text-[#DC2626]">{faqContentError}</p>
              )}
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
                当前系统会在一轮回复达到 {maxToolLoopRounds} 次 LLM-工具循环后停止继续调用工具。
              </div>
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
                    支持 Markdown 基础语法；HTML、脚本、iframe 和链接卡片不会被渲染。
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
          )}
        </section>
      </div>

      <ConfirmModal
        open={deletingFAQCategoryIndex !== null}
        onClose={() => setDeletingFAQCategoryIndex(null)}
        onConfirm={() => {
          if (deletingFAQCategoryIndex !== null) {
            removeFAQCategory(deletingFAQCategoryIndex)
          }
          setDeletingFAQCategoryIndex(null)
        }}
        title="删除问题类型"
        description={`确定删除以下问题类型及其下所有问题？\n${
          deletingFAQCategory?.name.trim() || '未命名类型'
        }\n${deletingFAQCategory?.questions.length ?? 0} 个问题`}
        confirmText="确定删除"
        cancelText="取消"
        variant="destructive"
      />
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
