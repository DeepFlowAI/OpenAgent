'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { IconExternalLink } from '@tabler/icons-react'
import { Button } from '@/app/components/base/button'
import { useToast } from '@/app/components/base/toast'
import {
  ATTACHMENT_HANDOFF_COPY,
  getEnabledHandoffTools,
  isConfiguredToolUnavailable,
} from '@/app/components/features/attachment-handoff-setting-utils'
import { useAgent, useUpdateEngineConfig } from '@/service/use-agent'
import { useAgentTools } from '@/service/use-agent-tool'

export function AttachmentHandoffSetting({ agentId }: { agentId: number }) {
  const { toast } = useToast()
  const [language, setLanguage] = useState<'zh' | 'en'>('zh')
  const [selectedToolId, setSelectedToolId] = useState<number | null>(null)
  const agentQuery = useAgent(agentId)
  const toolsQuery = useAgentTools(agentId)
  const updateMutation = useUpdateEngineConfig()
  const copy = ATTACHMENT_HANDOFF_COPY[language]
  const tools = useMemo(() => toolsQuery.data?.items ?? [], [toolsQuery.data])
  const enabledTools = useMemo(() => getEnabledHandoffTools(tools), [tools])
  const savedToolId = agentQuery.data?.engine_config.attachment_handoff_tool_id ?? null
  const configuredUnavailable = isConfiguredToolUnavailable(savedToolId, tools)

  useEffect(() => {
    const locale = document.documentElement.lang || navigator.language
    setLanguage(locale.toLowerCase().startsWith('en') ? 'en' : 'zh')
  }, [])

  useEffect(() => {
    if (!updateMutation.isPending) setSelectedToolId(savedToolId)
  }, [savedToolId, updateMutation.isPending])

  const handleChange = async (value: string) => {
    const previous = selectedToolId
    const next = value ? Number(value) : null
    setSelectedToolId(next)
    try {
      await updateMutation.mutateAsync({
        id: agentId,
        data: { attachment_handoff_tool_id: next },
      })
      toast(copy.updated, 'success')
    } catch {
      setSelectedToolId(previous)
      toast(copy.saveFailed, 'error')
    }
  }

  const loading = agentQuery.isLoading || toolsQuery.isLoading
  const loadFailed = agentQuery.isError || toolsQuery.isError
  const selectDisabled = updateMutation.isPending
    || (enabledTools.length === 0 && selectedToolId === null)

  return (
    <section className="rounded-[10px] border border-[#ECECEC] bg-white p-5">
      <div className="space-y-1">
        <h2 className="text-base font-semibold text-[#18181B]">{copy.title}</h2>
        <p className="text-[13px] leading-relaxed text-[#71717A]">
          {copy.description}
        </p>
      </div>

      {loading && <p className="mt-5 text-sm text-[#71717A]">{copy.loading}</p>}

      {!loading && loadFailed && (
        <div className="mt-5 flex items-center gap-3">
          <p className="text-sm text-[#71717A]">{copy.loadFailed}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              agentQuery.refetch()
              toolsQuery.refetch()
            }}
          >
            {copy.retry}
          </Button>
        </div>
      )}

      {!loading && !loadFailed && (
        <div className="mt-5 max-w-[600px] space-y-3">
          <label htmlFor="attachment-handoff-tool" className="block text-sm font-medium text-[#18181B]">
            {copy.label}
          </label>
          <select
            id="attachment-handoff-tool"
            value={selectedToolId ?? ''}
            disabled={selectDisabled}
            onChange={(event) => handleChange(event.target.value)}
            className="h-11 w-full rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#18181B] outline-none transition-colors focus:border-[#1a1a1a] focus:ring-2 focus:ring-[#1a1a1a]/10 disabled:bg-[#F5F5F5] disabled:text-[#737373]"
          >
            <option value="">{copy.placeholder}</option>
            {configuredUnavailable && savedToolId !== null && (
              <option value={savedToolId} disabled>{copy.unavailableOption}</option>
            )}
            {enabledTools.map((tool) => (
              <option key={tool.id} value={tool.id}>{tool.name}</option>
            ))}
          </select>

          {configuredUnavailable && (
            <p className="rounded-lg bg-[#FFFBEB] px-3 py-2 text-[13px] text-[#D97706]">
              {copy.unavailable}
            </p>
          )}

          {enabledTools.length === 0 && (
            <div className="flex items-center gap-3 text-[13px] text-[#71717A]">
              <span>{copy.noTools}</span>
              <Link
                href={`/agent/agents/${agentId}/tools`}
                className="inline-flex items-center gap-1 font-medium text-[#18181B] underline-offset-4 hover:underline"
              >
                {copy.goToTools}
                <IconExternalLink size={14} />
              </Link>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
