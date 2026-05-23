'use client'

import {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'
import { useParams } from 'next/navigation'
import { useAgent, useUpdateEngineConfig } from '@/service/use-agent'
import { useSystemInfo } from '@/service/use-system'
import { useAgentTools } from '@/service/use-agent-tool'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Switch } from '@/app/components/base/switch'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { IconBraces, IconChevronDown, IconCopy, IconX, IconCheck } from '@tabler/icons-react'
import { cn } from '@/utils/classnames'
import type { EngineConfig } from '@/models/agent'
import { DEFAULT_ENGINE_CONFIG } from '@/models/agent'

const FALLBACK_LLM_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
] as const

type BasicEngineConfig = Pick<
  EngineConfig,
  'system_prompt' | 'model' | 'selected_tool_ids' | 'context'
>

const DEFAULT_BASIC_CONFIG: BasicEngineConfig = {
  system_prompt: DEFAULT_ENGINE_CONFIG.system_prompt,
  model: DEFAULT_ENGINE_CONFIG.model,
  selected_tool_ids: DEFAULT_ENGINE_CONFIG.selected_tool_ids,
  context: DEFAULT_ENGINE_CONFIG.context,
}

type PromptVariable = {
  code: string
  description: string
  condition?: string
  example?: string
}

const DATE_TIME_VARIABLES: PromptVariable[] = [
  {
    code: '{{current_date}}',
    description: '当前日期，格式 YYYY-MM-DD',
    example: '2026-05-17',
  },
  {
    code: '{{current_weekday}}',
    description: '当前星期，中文星期一至星期日',
    example: '星期日',
  },
  {
    code: '{{current_time}}',
    description: '当前时间，格式 HH:MM',
    example: '14:30',
  },
  {
    code: '{{current_datetime}}',
    description: '当前日期时间，格式 YYYY-MM-DD HH:MM',
    example: '2026-05-17 14:30',
  },
]

const PRE_RECALL_VARIABLES: PromptVariable[] = [
  {
    code: '{{first_search}}',
    description: '首轮预召回的格式化检索结果',
    condition: '当前轮为会话首轮，预召回开启，已选择搜索工具，且检索有结果',
  },
]

const NOTEBOOK_VARIABLES: PromptVariable[] = [
  {
    code: '{{tool_notebook_output}}',
    description: '当前会话笔记工具汇总，格式为 <notebook>...</notebook> 结构化文本',
    condition: '当前 Agent 已选择且启用内置笔记工具，工具 name = notebook、tool_type = notebook',
  },
]

const RUNTIME_VARIABLES: PromptVariable[] = [
  {
    code: '{{context_max_rounds}}',
    description: '基础设定中的「对话轮次」M；0 表示历史轮次不按轮数限制',
    example: '2',
  },
  {
    code: '{{context_history_tool_rounds}}',
    description: '基础设定中的「历史轮次保留工具信息」N；0 表示已结束历史轮默认不附带工具链',
    example: '0',
  },
  {
    code: '{{context_recent_full_tool_responses}}',
    description: '基础设定中的「最近完整工具响应条数」k',
    example: '4',
  },
  {
    code: '{{conversation_round_number}}',
    description: '当前用户消息所在会话轮次，1 起算',
    example: '3',
  },
  {
    code: '{{history_loaded_round_count}}',
    description: '本次请求实际装入的已结束历史轮数',
    example: '2',
  },
  {
    code: '{{history_tool_trace_round_count}}',
    description: '本次请求实际保留工具轨迹的历史轮数',
    example: '0',
  },
  {
    code: '{{llm_call_index_in_round}}',
    description: '当前轮内第几次 LLM 调用，1 起算',
    example: '2',
  },
  {
    code: '{{completed_tool_call_count_in_round}}',
    description: '当前轮内，在本次 LLM 调用前已经完成的工具调用次数',
    example: '1',
  },
  {
    code: '{{next_tool_call_index_in_round}}',
    description: '如果本次 LLM 决定调用工具，第一条工具调用将是当前轮第几次工具调用',
    example: '2',
  },
  {
    code: '{{max_tool_loop_rounds}}',
    description: '当前引擎允许的单轮 LLM-工具循环上限',
    example: '20',
  },
  {
    code: '{{remaining_tool_loop_rounds}}',
    description: '当前轮内包含本次在内还剩多少次 LLM-工具循环机会',
    example: '19',
  },
]

const FIRST_SEARCH_SNIPPET = `{{#first_search}}
## 搜索结果

{{.}}
{{/first_search}}`

const EMPTY_NOTEBOOK_SNIPPET = `<notebook>
</notebook>`

function mergeBasicConfig(
  defaults: BasicEngineConfig,
  saved: Record<string, unknown>,
): BasicEngineConfig {
  const savedModel = { ...((saved.model ?? {}) as Record<string, unknown>) }

  // Backward compat: map legacy thinking_mode to new split fields
  if ('thinking_mode' in savedModel) {
    const legacy = Boolean(savedModel.thinking_mode)
    if (!('first_round_thinking' in savedModel)) {
      savedModel.first_round_thinking = legacy
    }
    if (!('subsequent_rounds_thinking' in savedModel)) {
      savedModel.subsequent_rounds_thinking = legacy
    }
    delete savedModel.thinking_mode
  }

  return {
    system_prompt: (saved.system_prompt as string) ?? defaults.system_prompt,
    model: { ...defaults.model, ...savedModel } as EngineConfig['model'],
    selected_tool_ids: (saved.selected_tool_ids as number[]) ?? defaults.selected_tool_ids,
    context: { ...defaults.context, ...(saved.context as Record<string, unknown> ?? {}) },
  }
}

export default function BasicSettingsPage() {
  const params = useParams()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const { data: agent, isLoading: agentLoading } = useAgent(agentId)
  const { data: toolsData } = useAgentTools(agentId)
  const { data: systemInfo } = useSystemInfo()
  const updateMutation = useUpdateEngineConfig()

  const availableModels =
    systemInfo?.llm_models?.length ? systemInfo.llm_models : [...FALLBACK_LLM_MODELS]

  const [config, setConfig] = useState<BasicEngineConfig>(DEFAULT_BASIC_CONFIG)
  const [initialized, setInitialized] = useState(false)
  const [variablesOpen, setVariablesOpen] = useState(false)

  useEffect(() => {
    if (agent && !initialized) {
      const merged = mergeBasicConfig(
        DEFAULT_BASIC_CONFIG,
        (agent.engine_config ?? {}) as Record<string, unknown>,
      )
      setConfig(merged)
      setInitialized(true)
    }
  }, [agent, initialized])

  const enabledTools = useMemo(
    () => (toolsData?.items ?? []).filter((t) => t.is_enabled),
    [toolsData],
  )

  const isDirty = useMemo(() => {
    if (!agent || !initialized) return false
    const saved = mergeBasicConfig(
      DEFAULT_BASIC_CONFIG,
      (agent.engine_config ?? {}) as Record<string, unknown>,
    )
    return JSON.stringify(config) !== JSON.stringify(saved)
  }, [agent, config, initialized])

  const handleSave = useCallback(async () => {
    try {
      await updateMutation.mutateAsync({
        id: agentId,
        data: {
          system_prompt: config.system_prompt,
          model: config.model,
          selected_tool_ids: config.selected_tool_ids,
          context: config.context,
        },
      })
      toast('保存成功', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }, [agentId, config, updateMutation, toast])

  const handleCopy = useCallback(
    async (text: string) => {
      try {
        if (typeof navigator === 'undefined' || !navigator.clipboard) {
          throw new Error('Clipboard is unavailable')
        }
        await navigator.clipboard.writeText(text)
        toast('已复制', 'success')
      } catch {
        toast('复制失败，请手动复制', 'error')
      }
    },
    [toast],
  )

  const updateModel = useCallback(
    (key: string, value: unknown) => {
      setConfig((prev) => ({
        ...prev,
        model: { ...prev.model, [key]: value },
      }))
    },
    [],
  )

  const updateContext = useCallback(
    (key: string, value: unknown) => {
      setConfig((prev) => ({
        ...prev,
        context: { ...prev.context, [key]: value },
      }))
    },
    [],
  )

  if (agentLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-[#71717A]">加载中...</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Sticky top bar */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#ECECEC] bg-white/80 px-6 py-4 backdrop-blur-sm">
        <h2 className="text-base font-semibold text-[#18181B]">基础设定</h2>
        <button
          disabled={!isDirty || updateMutation.isPending}
          onClick={handleSave}
          className="rounded-lg bg-[#18181B] px-5 py-2 text-sm font-medium text-white transition-opacity disabled:opacity-50"
        >
          {updateMutation.isPending ? '保存中...' : '保存'}
        </button>
      </div>

      {/* Form area */}
      <div className="flex-1 space-y-8 overflow-auto p-8">
        {/* System Prompt */}
        <section className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-[#18181B]">提示词 / System Prompt</h3>
              <p className="mt-1 text-[13px] text-[#71717A]">
                定义 Agent 的角色、行为规范和能力边界
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setVariablesOpen(true)}
              disabled={agentLoading}
              className="shrink-0 gap-1.5"
            >
              <IconBraces size={16} />
              变量
            </Button>
          </div>
          <textarea
            value={config.system_prompt}
            onChange={(e) => setConfig((prev) => ({ ...prev, system_prompt: e.target.value }))}
            placeholder="你是一个AI助手，请帮助用户..."
            maxLength={10000}
            rows={12}
            className="w-full resize-y rounded-lg border border-[#E4E4E7] p-4 font-mono text-sm text-[#18181B] outline-none placeholder:text-[#A1A1AA] focus:border-[#18181B]"
          />
        </section>

        {/* Model Configuration */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-[#18181B]">模型配置</h3>
          <div className="grid grid-cols-2 gap-5">
            {/* Model select */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                模型选择
              </label>
              <select
                value={config.model.model_name}
                onChange={(e) => updateModel('model_name', e.target.value)}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              >
                <option value="">选择模型</option>
                {availableModels.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>

            {/* First round thinking */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                首轮思考
              </label>
              <div className="flex items-center gap-3 pt-1">
                <Switch
                  checked={config.model.first_round_thinking}
                  onChange={(v) => updateModel('first_round_thinking', v)}
                />
                <span className="text-sm text-[#71717A]">
                  {config.model.first_round_thinking ? '已开启' : '关闭'}
                </span>
              </div>
            </div>

            {/* Subsequent rounds thinking */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                后续轮思考
              </label>
              <div className="flex items-center gap-3 pt-1">
                <Switch
                  checked={config.model.subsequent_rounds_thinking}
                  onChange={(v) => updateModel('subsequent_rounds_thinking', v)}
                />
                <span className="text-sm text-[#71717A]">
                  {config.model.subsequent_rounds_thinking ? '已开启' : '关闭'}
                </span>
              </div>
            </div>

            {/* Temperature */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                温度 / Temperature
              </label>
              <input
                type="number"
                value={config.model.temperature}
                onChange={(e) => updateModel('temperature', parseFloat(e.target.value) || 0)}
                min={0}
                max={2}
                step={0.01}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              />
            </div>

            {/* Top P */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                多样性 / Top P
              </label>
              <input
                type="number"
                value={config.model.top_p}
                onChange={(e) => updateModel('top_p', parseFloat(e.target.value) || 0)}
                min={0}
                max={1}
                step={0.01}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              />
            </div>

            {/* Max tokens */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                最大生成 Token / Max Tokens
              </label>
              <input
                type="number"
                value={config.model.max_tokens}
                onChange={(e) => updateModel('max_tokens', parseInt(e.target.value) || 4096)}
                min={1}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              />
            </div>
          </div>
        </section>

        {/* Tools Selection */}
        <section className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-[#18181B]">使用工具 / Tools</h3>
            <p className="mt-1 text-[13px] text-[#71717A]">
              选择该 Agent 在对话中可调用的工具
            </p>
          </div>
          <ToolMultiSelect
            tools={enabledTools}
            selectedIds={config.selected_tool_ids}
            onChange={(ids) => setConfig((prev) => ({ ...prev, selected_tool_ids: ids }))}
          />
        </section>

        {/* Context & Tool Trace */}
        <section className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-[#18181B]">
              上下文与工具轨迹 / Context & Tool Trace
            </h3>
          </div>
          <div className="grid grid-cols-3 gap-5">
            {/* Max rounds M */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                对话轮次
              </label>
              <input
                type="number"
                value={config.context.max_rounds}
                onChange={(e) => updateContext('max_rounds', parseInt(e.target.value) || 0)}
                min={0}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              />
              <p className="mt-1 text-xs text-[#A1A1AA]">0 = 不限制</p>
            </div>

            {/* History tool rounds N */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                历史轮次保留工具信息
              </label>
              <select
                value={config.context.history_tool_rounds}
                onChange={(e) => updateContext('history_tool_rounds', parseInt(e.target.value))}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              >
                {[0, 1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n} 轮
                  </option>
                ))}
              </select>
            </div>

            {/* Recent full tool responses k */}
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#18181B]">
                最近完整工具响应条数
              </label>
              <input
                type="number"
                value={config.context.recent_full_tool_responses}
                onChange={(e) =>
                  updateContext('recent_full_tool_responses', parseInt(e.target.value) || 1)
                }
                min={1}
                max={5}
                className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#18181B]"
              />
            </div>
          </div>
        </section>
      </div>

      <PromptVariablesModal
        open={variablesOpen}
        onClose={() => setVariablesOpen(false)}
        onCopy={handleCopy}
      />
    </div>
  )
}

function PromptVariablesModal({
  open,
  onClose,
  onCopy,
}: {
  open: boolean
  onClose: () => void
  onCopy: (text: string) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="提示词变量"
      className="w-[720px] max-w-[calc(100vw-32px)]"
      footer={
        <Button type="button" variant="outline" onClick={onClose}>
          关闭
        </Button>
      }
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onClose}
        title="关闭"
        aria-label="关闭变量弹窗"
        className="absolute right-4 top-4 h-8 w-8 text-[#737373]"
      >
        <IconX size={18} />
      </Button>

      <div className="max-h-[68vh] space-y-5 overflow-auto pr-1">
        <p className="rounded-lg bg-[#F5F5F5] px-3 py-2 text-[13px] leading-relaxed text-[#52525B]">
          变量会在每次 LLM 调用前替换。未满足条件或未注入的变量会替换为空字符串。
        </p>

        <VariableSection title="日期时间变量" variables={DATE_TIME_VARIABLES} onCopy={onCopy} />

        <VariableSection title="预召回变量" variables={PRE_RECALL_VARIABLES} onCopy={onCopy}>
          <SnippetBlock
            title="推荐条件块"
            description="块内 {{.}} 表示 first_search 的检索结果；无内容时整块不注入。"
            content={FIRST_SEARCH_SNIPPET}
            onCopy={onCopy}
          />
        </VariableSection>

        <VariableSection
          title="运行态变量"
          description="这些变量在每次 LLM 调用前更新，适合放在 System Prompt 中帮助模型判断是否继续调用工具或收敛回答。"
          variables={RUNTIME_VARIABLES}
          onCopy={onCopy}
        />

        <VariableSection title="笔记工具变量" variables={NOTEBOOK_VARIABLES} onCopy={onCopy}>
          <SnippetBlock
            title="空 notebook 示例"
            description="笔记工具可用但暂无笔记条目时，变量内容为空 notebook 结构。"
            content={EMPTY_NOTEBOOK_SNIPPET}
            onCopy={onCopy}
          />
        </VariableSection>
      </div>
    </Modal>
  )
}

function VariableSection({
  title,
  description,
  variables,
  children,
  onCopy,
}: {
  title: string
  description?: string
  variables: PromptVariable[]
  children?: ReactNode
  onCopy: (text: string) => void
}) {
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold text-[#18181B]">{title}</h3>
      {description && (
        <p className="text-[13px] leading-relaxed text-[#71717A]">{description}</p>
      )}
      <div className="space-y-2">
        {variables.map((variable) => (
          <VariableRow key={variable.code} variable={variable} onCopy={onCopy} />
        ))}
      </div>
      {children}
    </section>
  )
}

function VariableRow({
  variable,
  onCopy,
}: {
  variable: PromptVariable
  onCopy: (text: string) => void
}) {
  return (
    <div className="rounded-lg border border-[#E5E5E5] bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <code className="inline-flex rounded-md bg-[#F4F4F5] px-2 py-1 font-mono text-xs text-[#18181B]">
            {variable.code}
          </code>
          <p className="text-[13px] leading-relaxed text-[#52525B]">{variable.description}</p>
        </div>
        <CopyButton label="复制变量" onClick={() => onCopy(variable.code)} />
      </div>
      {(variable.example || variable.condition) && (
        <div className="mt-2 space-y-1 border-t border-[#F4F4F5] pt-2 text-xs text-[#71717A]">
          {variable.example && <p>示例：{variable.example}</p>}
          {variable.condition && <p>可用条件：{variable.condition}</p>}
        </div>
      )}
    </div>
  )
}

function SnippetBlock({
  title,
  description,
  content,
  onCopy,
}: {
  title: string
  description: string
  content: string
  onCopy: (text: string) => void
}) {
  return (
    <div className="rounded-lg border border-[#E5E5E5] bg-white p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-[#18181B]">{title}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-[#71717A]">{description}</p>
        </div>
        <CopyButton label="复制片段" onClick={() => onCopy(content)} />
      </div>
      <pre className="overflow-auto rounded-md bg-[#18181B] p-3 font-mono text-xs leading-relaxed text-[#E4E4E7]">{content}</pre>
    </div>
  )
}

function CopyButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="h-8 w-8 shrink-0 text-[#404040]"
    >
      <IconCopy size={16} />
    </Button>
  )
}

function ToolMultiSelect({
  tools,
  selectedIds,
  onChange,
}: {
  tools: { id: number; name: string; tool_type: string }[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggle = (id: number) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    )
  }

  const remove = (id: number, e: ReactMouseEvent) => {
    e.stopPropagation()
    onChange(selectedIds.filter((x) => x !== id))
  }

  const selectedTools = tools.filter((t) => selectedIds.includes(t.id))

  if (tools.length === 0) {
    return <p className="text-sm text-[#A1A1AA]">暂无可用工具，请先在工具管理中添加工具</p>
  }

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors',
          open ? 'border-[#18181B]' : 'border-[#E4E4E7] hover:border-[#A1A1AA]',
        )}
      >
        <div className="flex min-h-[24px] flex-1 flex-wrap gap-1.5">
          {selectedTools.length === 0 ? (
            <span className="text-sm text-[#A1A1AA]">选择工具...</span>
          ) : (
            selectedTools.map((t) => (
              <span
                key={t.id}
                className="inline-flex items-center gap-1 rounded-md bg-[#F4F4F5] px-2 py-0.5 text-xs font-medium text-[#18181B]"
              >
                {t.name}
                <IconX
                  size={12}
                  className="cursor-pointer text-[#A1A1AA] hover:text-[#18181B]"
                  onClick={(e) => remove(t.id, e)}
                />
              </span>
            ))
          )}
        </div>
        <IconChevronDown
          size={16}
          className={cn(
            'shrink-0 text-[#A1A1AA] transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 right-0 z-20 mt-1 max-h-[240px] overflow-auto rounded-lg border border-[#E4E4E7] bg-white py-1 shadow-lg">
          {tools.map((tool) => {
            const isSelected = selectedIds.includes(tool.id)
            return (
              <button
                key={tool.id}
                type="button"
                onClick={() => toggle(tool.id)}
                className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-[#F4F4F5]"
              >
                <div
                  className={cn(
                    'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                    isSelected
                      ? 'border-[#18181B] bg-[#18181B]'
                      : 'border-[#D4D4D8]',
                  )}
                >
                  {isSelected && <IconCheck size={12} className="text-white" />}
                </div>
                <span className="flex-1 text-sm text-[#18181B]">{tool.name}</span>
                <span className="text-[11px] text-[#A1A1AA]">{tool.tool_type}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
