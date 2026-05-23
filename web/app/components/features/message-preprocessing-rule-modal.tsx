'use client'

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/app/components/base/button'
import { ConfirmModal, Modal } from '@/app/components/base/modal'
import { Input } from '@/app/components/base/input'
import { Textarea } from '@/app/components/base/textarea'
import type {
  AgentMessagePreprocessingAction,
  AgentMessagePreprocessingRule,
  CreateAgentMessagePreprocessingRulePayload,
} from '@/models/agent-message-preprocessing-rule'

type RuleFormValues = CreateAgentMessagePreprocessingRulePayload

type RuleFormErrors = Partial<Record<keyof RuleFormValues, string>>

type MessagePreprocessingRuleModalProps = {
  open: boolean
  rule: AgentMessagePreprocessingRule | null
  loading?: boolean
  onClose: () => void
  onSubmit: (values: RuleFormValues) => Promise<void>
}

const DEFAULT_VALUES: RuleFormValues = {
  condition: '',
  action: 'prefix',
  value: '',
}

export function MessagePreprocessingRuleModal({
  open,
  rule,
  loading,
  onClose,
  onSubmit,
}: MessagePreprocessingRuleModalProps) {
  const [values, setValues] = useState<RuleFormValues>(DEFAULT_VALUES)
  const [errors, setErrors] = useState<RuleFormErrors>({})
  const [discardOpen, setDiscardOpen] = useState(false)

  const initialValues = useMemo<RuleFormValues>(() => {
    if (!rule) return DEFAULT_VALUES
    return {
      condition: rule.condition,
      action: rule.action,
      value: rule.value,
    }
  }, [rule])

  useEffect(() => {
    if (!open) return
    setValues(initialValues)
    setErrors({})
    setDiscardOpen(false)
  }, [open, initialValues])

  const isDirty = useMemo(
    () => JSON.stringify(values) !== JSON.stringify(initialValues),
    [values, initialValues],
  )

  const validate = () => {
    const nextErrors: RuleFormErrors = {}
    if (!values.condition) {
      nextErrors.condition = '请输入正则表达式'
    } else if (values.condition.length > 1000) {
      nextErrors.condition = '条件最多 1000 个字符'
    }
    if ((values.value ?? '').length > 500) {
      nextErrors.value = '值最多 500 个字符'
    }
    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    await onSubmit({
      condition: values.condition,
      action: values.action,
      value: values.value ?? '',
    })
  }

  const handleClose = () => {
    if (loading) return
    if (!isDirty) {
      onClose()
      return
    }
    setDiscardOpen(true)
  }

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title={rule ? '编辑规则' : '新建规则'}
        className="w-[520px]"
        footer={
          <>
            <Button variant="outline" onClick={handleClose} disabled={loading}>
              取消
            </Button>
            <Button onClick={handleSubmit} loading={loading}>
              确定
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Textarea
              label="条件"
              required
              value={values.condition}
              onChange={(e) =>
                setValues((prev) => ({ ...prev, condition: e.target.value }))
              }
              onBlur={validate}
              placeholder="请输入 Python regex module 正则表达式"
              error={errors.condition}
              hint="按 Python regex module 语法填写；正则合法性以后端校验结果为准。"
              className="min-h-[120px] resize-y"
            />
            <div className="mt-1 text-right text-xs text-[#71717A]">
              {values.condition.length} / 1000
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="message-preprocessing-action"
              className="text-sm font-medium text-[#1a1a1a]"
            >
              动作
            </label>
            <select
              id="message-preprocessing-action"
              value={values.action}
              onChange={(e) =>
                setValues((prev) => ({
                  ...prev,
                  action: e.target.value as AgentMessagePreprocessingAction,
                }))
              }
              className="h-11 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] outline-none transition-colors focus:border-[#1a1a1a] focus:ring-2 focus:ring-[#1a1a1a]/10"
            >
              <option value="prefix">前缀</option>
              <option value="suffix">后缀</option>
            </select>
          </div>

          <Input
            label="值"
            value={values.value ?? ''}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, value: e.target.value }))
            }
            onBlur={validate}
            placeholder="请输入要添加的内容"
            error={errors.value}
            maxLength={500}
          />
        </div>
      </Modal>

      <ConfirmModal
        open={discardOpen}
        onClose={() => setDiscardOpen(false)}
        onConfirm={() => {
          setDiscardOpen(false)
          onClose()
        }}
        title="关闭弹框"
        description="已修改内容尚未提交，确定关闭？"
        confirmText="确定关闭"
        cancelText="取消"
      />
    </>
  )
}
