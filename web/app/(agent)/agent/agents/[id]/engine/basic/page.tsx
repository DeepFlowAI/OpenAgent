'use client'

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useParams } from 'next/navigation'
import { useAgent, useUpdateEngineConfig } from '@/service/use-agent'
import { useAgentTools } from '@/service/use-agent-tool'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Switch } from '@/app/components/base/switch'
import { IconChevronDown, IconX, IconCheck } from '@tabler/icons-react'
import { cn } from '@/utils/classnames'
import type { EngineConfig } from '@/models/agent'
import { DEFAULT_ENGINE_CONFIG } from '@/models/agent'

const AVAILABLE_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'kimi-k2.5', label: 'Kimi K2.5' },
  { value: 'kimi-k2.6', label: 'Kimi K2.6' },
  { value: 'glm-5', label: 'GLM-5' },
  { value: 'glm-5.1', label: 'GLM-5.1' },
  { value: 'ling-2.6-flash', label: 'Ling 2.6 Flash' },
  { value: 'mimo-v2.5-pro', label: 'MiMo V2.5 Pro' },
  { value: 'minimax-m2.5', label: 'MiniMax M2.5' },
  { value: 'minimax-m2.7', label: 'MiniMax M2.7' },
  { value: 'step-3.5-flash', label: 'Step 3.5 Flash' },
  { value: 'grok-4.20', label: 'Grok 4.20' },
  { value: 'grok-4.20-multi-agent', label: 'Grok 4.20 (Multi-Agent)' },
]

function deepMerge(defaults: EngineConfig, saved: Record<string, unknown>): EngineConfig {
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
    pre_recall: { ...defaults.pre_recall, ...(saved.pre_recall as Record<string, unknown> ?? {}) },
  }
}

export default function BasicSettingsPage() {
  const params = useParams()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const { data: agent, isLoading: agentLoading } = useAgent(agentId)
  const { data: toolsData } = useAgentTools(agentId)
  const updateMutation = useUpdateEngineConfig()

  const [config, setConfig] = useState<EngineConfig>(DEFAULT_ENGINE_CONFIG)
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (agent && !initialized) {
      const merged = deepMerge(
        DEFAULT_ENGINE_CONFIG,
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
    const saved = deepMerge(
      DEFAULT_ENGINE_CONFIG,
      (agent.engine_config ?? {}) as Record<string, unknown>,
    )
    return JSON.stringify(config) !== JSON.stringify(saved)
  }, [agent, config, initialized])

  const handleSave = useCallback(async () => {
    try {
      await updateMutation.mutateAsync({ id: agentId, data: config })
      toast('保存成功', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }, [agentId, config, updateMutation, toast])

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
          <div>
            <h3 className="text-sm font-semibold text-[#18181B]">提示词 / System Prompt</h3>
            <p className="mt-1 text-[13px] text-[#71717A]">
              定义 Agent 的角色、行为规范和能力边界
            </p>
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
                {AVAILABLE_MODELS.map((m) => (
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
    </div>
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

  const remove = (id: number, e: React.MouseEvent) => {
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
