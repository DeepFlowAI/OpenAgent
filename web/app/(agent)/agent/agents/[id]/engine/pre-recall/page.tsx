'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { useAgent, useUpdateEngineConfig } from '@/service/use-agent'
import { useAgentTools } from '@/service/use-agent-tool'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import { Switch } from '@/app/components/base/switch'
import { IconChevronDown, IconInfoCircle } from '@tabler/icons-react'
import { cn } from '@/utils/classnames'
import type { EngineConfig, PreRecallConfig } from '@/models/agent'
import { DEFAULT_ENGINE_CONFIG } from '@/models/agent'

export default function PreRecallPage() {
  const params = useParams()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const { data: agent, isLoading } = useAgent(agentId)
  const { data: toolsData } = useAgentTools(agentId)
  const updateMutation = useUpdateEngineConfig()

  const [config, setConfig] = useState<PreRecallConfig>(DEFAULT_ENGINE_CONFIG.pre_recall)
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (agent && !initialized) {
      const saved = (agent.engine_config?.pre_recall ?? {}) as Record<string, unknown>
      setConfig({
        ...DEFAULT_ENGINE_CONFIG.pre_recall,
        ...saved,
      } as PreRecallConfig)
      setInitialized(true)
    }
  }, [agent, initialized])

  const searchTools = useMemo(
    () =>
      (toolsData?.items ?? []).filter(
        (t) => t.tool_type === 'search' && t.is_enabled,
      ),
    [toolsData],
  )

  const isDirty = useMemo(() => {
    if (!agent || !initialized) return false
    const saved = {
      ...DEFAULT_ENGINE_CONFIG.pre_recall,
      ...((agent.engine_config?.pre_recall ?? {}) as Record<string, unknown>),
    } as PreRecallConfig
    return JSON.stringify(config) !== JSON.stringify(saved)
  }, [agent, config, initialized])

  const canSave = useMemo(() => {
    if (!isDirty) return false
    if (config.enabled && !config.tool_id) return false
    return true
  }, [isDirty, config])

  const handleSave = useCallback(async () => {
    if (config.enabled && !config.tool_id) {
      toast('请先选择文档切片搜索工具', 'error')
      return
    }
    try {
      await updateMutation.mutateAsync({
        id: agentId,
        data: { pre_recall: config },
      })
      toast('保存成功', 'success')
    } catch (err) {
      toast(await getErrorMessage(err), 'error')
    }
  }, [agentId, config, updateMutation, toast])

  if (isLoading) {
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
        <h2 className="text-base font-semibold text-[#18181B]">预召回</h2>
        <button
          disabled={!canSave || updateMutation.isPending}
          onClick={handleSave}
          className="rounded-lg bg-[#18181B] px-5 py-2 text-sm font-medium text-white transition-opacity disabled:opacity-50"
        >
          {updateMutation.isPending ? '保存中...' : '保存'}
        </button>
      </div>

      {/* Config area */}
      <div className="flex-1 space-y-6 overflow-auto p-8">
        {/* Block A: Toggle */}
        <section className="space-y-3">
          <div className="flex items-center gap-3">
            <Switch
              checked={config.enabled}
              onChange={(v) => setConfig((prev) => ({ ...prev, enabled: v }))}
            />
            <div>
              <span className="text-sm font-medium text-[#18181B]">启用预召回</span>
              <p className="mt-0.5 text-[13px] text-[#71717A]">
                在会话首轮用户消息时，自动执行一次文档切片搜索，将结果注入系统提示词
              </p>
            </div>
          </div>
        </section>

        {/* Block B: Tool selection (only when enabled) */}
        {config.enabled && (
          <section className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-[#18181B]">
                预召回使用的文档切片搜索工具
              </h3>
              <p className="mt-1 text-[13px] text-[#71717A]">
                仅展示已启用且类型为搜索的工具实例
              </p>
            </div>

            {searchTools.length === 0 ? (
              <div className="rounded-lg border border-dashed border-[#E4E4E7] px-4 py-6 text-center">
                <p className="text-sm text-[#A1A1AA]">
                  暂无可用的搜索工具，请先在
                  <a
                    href={`/agent/agents/${agentId}/tools`}
                    className="mx-1 text-[#18181B] underline underline-offset-2 hover:text-[#3F3F46]"
                  >
                    工具管理
                  </a>
                  中添加并启用搜索工具
                </p>
              </div>
            ) : (
              <ToolSelect
                tools={searchTools}
                selectedId={config.tool_id}
                onChange={(id) => setConfig((prev) => ({ ...prev, tool_id: id }))}
              />
            )}

            {config.enabled && !config.tool_id && searchTools.length > 0 && (
              <p className="text-xs text-red-500">请选择一个搜索工具</p>
            )}
          </section>
        )}

        {/* Block C: Variable docs */}
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-[#18181B]">提示词变量说明</h3>
          <div className="rounded-lg border border-[#E4E4E7] bg-[#FAFBFC] p-5">
            <div className="flex items-start gap-2.5">
              <IconInfoCircle size={16} className="mt-0.5 shrink-0 text-[#71717A]" />
              <div className="space-y-3 text-[13px] text-[#3F3F46]">
                <p>
                  首轮预召回执行后，可在「基础设定」的系统提示词中使用以下变量引用检索结果：
                </p>
                <div className="space-y-2">
                  <div>
                    <code className="rounded bg-[#F4F4F5] px-1.5 py-0.5 font-mono text-xs text-[#18181B]">
                      {'{{first_search}}'}
                    </code>
                    <span className="ml-2 text-[#71717A]">
                      替换为预召回检索结果，无内容时为空字符串
                    </span>
                  </div>
                  <div>
                    <code className="rounded bg-[#F4F4F5] px-1.5 py-0.5 font-mono text-xs text-[#18181B]">
                      {'{{#first_search}}...{{/first_search}}'}
                    </code>
                    <span className="ml-2 text-[#71717A]">
                      条件块，无内容时整段（含标题）不注入
                    </span>
                  </div>
                </div>
                <div className="mt-2 rounded-md bg-[#18181B] p-3 font-mono text-xs leading-relaxed text-[#E4E4E7]">
                  <div className="text-[#71717A]">{'// 推荐写法（写入系统提示词）'}</div>
                  <div className="mt-1">{'{{#first_search}}'}</div>
                  <div>{'## 搜索结果'}</div>
                  <div>&nbsp;</div>
                  <div>{'{{.}}'}</div>
                  <div>{'{{/first_search}}'}</div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function ToolSelect({
  tools,
  selectedId,
  onChange,
}: {
  tools: { id: number; name: string; config: Record<string, unknown> }[]
  selectedId: number | null
  onChange: (id: number | null) => void
}) {
  const [open, setOpen] = useState(false)
  const selected = tools.find((t) => t.id === selectedId)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left transition-colors',
          open ? 'border-[#18181B]' : 'border-[#E4E4E7] hover:border-[#A1A1AA]',
        )}
      >
        <span className={cn('text-sm', selected ? 'text-[#18181B]' : 'text-[#A1A1AA]')}>
          {selected ? selected.name : '选择工具...'}
        </span>
        <IconChevronDown
          size={16}
          className={cn(
            'shrink-0 text-[#A1A1AA] transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-20 mt-1 max-h-[240px] overflow-auto rounded-lg border border-[#E4E4E7] bg-white py-1 shadow-lg">
          {tools.map((tool) => {
            const isSelected = tool.id === selectedId
            const kbName = (tool.config?.knowledge_base_name as string) || ''
            return (
              <button
                key={tool.id}
                type="button"
                onClick={() => {
                  onChange(tool.id)
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-[#F4F4F5]',
                  isSelected && 'bg-[#F4F4F5]',
                )}
              >
                <span className="flex-1 text-sm text-[#18181B]">{tool.name}</span>
                {kbName && (
                  <span className="text-[11px] text-[#A1A1AA]">{kbName}</span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
