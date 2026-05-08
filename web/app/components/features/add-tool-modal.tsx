'use client'

import { useState } from 'react'
import { Modal } from '@/app/components/base/modal'
import { Button } from '@/app/components/base/button'
import type { AgentTool, CreateAgentToolPayload } from '@/models/agent-tool'
import { TOOL_TYPE_LABELS } from '@/models/agent-tool'

type AddToolModalProps = {
  open: boolean
  onClose: () => void
  onSubmit: (payload: CreateAgentToolPayload) => void
  loading?: boolean
  existingNames: string[]
}

const ADDABLE_TOOL_TYPES: AgentTool['tool_type'][] = [
  'search',
  'doc_query',
  'python_code',
]

export function AddToolModal({
  open,
  onClose,
  onSubmit,
  loading,
  existingNames,
}: AddToolModalProps) {
  const [selectedType, setSelectedType] = useState<AgentTool['tool_type'] | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const handleClose = () => {
    setSelectedType(null)
    setName('')
    setDescription('')
    setError('')
    onClose()
  }

  const handleSubmit = () => {
    if (!selectedType) {
      setError('请选择工具类型')
      return
    }
    const trimmedName = name.trim()
    if (!trimmedName) {
      setError('工具名称不能为空')
      return
    }
    if (existingNames.includes(trimmedName)) {
      setError('工具名称已存在')
      return
    }
    setError('')
    onSubmit({
      tool_type: selectedType,
      name: trimmedName,
      description: description.trim() || undefined,
    })
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="添加工具"
      footer={
        <>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            取消
          </Button>
          <Button onClick={handleSubmit} loading={loading}>
            添加
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Tool type selection */}
        <div>
          <label className="mb-2 block text-sm font-medium text-[#18181B]">
            工具类型
          </label>
          <div className="grid grid-cols-3 gap-2">
            {ADDABLE_TOOL_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => {
                  setSelectedType(type)
                  if (!name) {
                    setName(type === 'search' ? 'knowledge_search' : type === 'doc_query' ? 'doc_query' : 'python_code')
                  }
                }}
                className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                  selectedType === type
                    ? 'border-[#18181B] bg-[#18181B] text-white'
                    : 'border-[#E4E4E7] text-[#71717A] hover:border-[#A1A1AA]'
                }`}
              >
                {TOOL_TYPE_LABELS[type].zh}
              </button>
            ))}
          </div>
        </div>

        {/* Tool name */}
        <div>
          <label className="mb-2 block text-sm font-medium text-[#18181B]">
            工具名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="tool_name (LLM function call name)"
            className="w-full rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none placeholder:text-[#A1A1AA] focus:border-[#18181B]"
            maxLength={128}
          />
        </div>

        {/* Tool description */}
        <div>
          <label className="mb-2 block text-sm font-medium text-[#18181B]">
            工具描述
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe this tool for LLM to understand when to use it"
            rows={3}
            className="w-full resize-y rounded-lg border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none placeholder:text-[#A1A1AA] focus:border-[#18181B]"
          />
        </div>

        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}
      </div>
    </Modal>
  )
}
