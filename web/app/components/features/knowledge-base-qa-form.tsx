'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { IconArrowLeft, IconX } from '@tabler/icons-react'
import { Badge } from '@/app/components/base/badge'
import { Button } from '@/app/components/base/button'
import { Switch } from '@/app/components/base/switch'
import { Textarea } from '@/app/components/base/textarea'
import { useToast } from '@/app/components/base/toast'
import { useQaDirectoryCopy } from '@/app/components/features/knowledge-base-qa-copy'
import { useAuthStore } from '@/context/auth-store'
import { getErrorMessage } from '@/service/base'
import {
  useCreateKnowledgeBaseQa,
  useRetryKnowledgeBaseQa,
  useUpdateKnowledgeBaseQa,
} from '@/service/use-knowledge-base-qa'
import { useKnowledgeBaseQaDirectories } from '@/service/use-knowledge-base-qa-directory'
import type { KnowledgeBaseQa, KnowledgeBaseQaPayload } from '@/models/knowledge-base-qa'
import { flattenKnowledgeBaseQaDirectoryTree } from '@/utils/knowledge-base-qa-directory'

type FieldErrors = Partial<Record<'directory' | 'question' | 'answer' | 'keywords', string>>

export function KnowledgeBaseQaForm({
  kbId,
  qa,
}: {
  kbId: number
  qa?: KnowledgeBaseQa
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const t = useQaDirectoryCopy()
  const canManage = useAuthStore((state) => state.user?.role === 'admin')
  const requestedValue = searchParams.get('directory')
  const requestedDirectoryId = requestedValue && /^\d+$/.test(requestedValue) ? Number(requestedValue) : null
  const { data: directoryData } = useKnowledgeBaseQaDirectories(kbId)
  const createMutation = useCreateKnowledgeBaseQa()
  const updateMutation = useUpdateKnowledgeBaseQa()
  const retryMutation = useRetryKnowledgeBaseQa()
  const [question, setQuestion] = useState(qa?.question ?? '')
  const [answer, setAnswer] = useState(qa?.answer_markdown ?? '')
  const [enabled, setEnabled] = useState(qa?.enabled ?? true)
  const [keywords, setKeywords] = useState<string[]>(qa?.access_keywords ?? [])
  const [keywordInput, setKeywordInput] = useState('')
  const [preview, setPreview] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [directoryId, setDirectoryId] = useState<number | null>(qa?.directory_id ?? requestedDirectoryId)
  const [baselineDirectoryId, setBaselineDirectoryId] = useState<number | null>(qa?.directory_id ?? requestedDirectoryId)
  const initial = useMemo(() => JSON.stringify({ directoryId: qa?.directory_id ?? baselineDirectoryId, question: qa?.question ?? '', answer: qa?.answer_markdown ?? '', enabled: qa?.enabled ?? true, keywords: qa?.access_keywords ?? [] }), [baselineDirectoryId, qa])
  const current = JSON.stringify({ directoryId, question, answer, enabled, keywords })
  const dirty = current !== initial
  const processing = qa?.process_status === 'processing'
  const saving = createMutation.isPending || updateMutation.isPending
  const directoryOptions = useMemo(
    () => flattenKnowledgeBaseQaDirectoryTree(directoryData?.items ?? []),
    [directoryData?.items],
  )

  useEffect(() => {
    if (!qa) return
    setQuestion(qa.question)
    setAnswer(qa.answer_markdown)
    setEnabled(qa.enabled)
    setKeywords(qa.access_keywords)
    setDirectoryId(qa.directory_id)
    setBaselineDirectoryId(qa.directory_id)
  }, [qa])

  useEffect(() => {
    if (qa || !directoryData) return
    const valid = requestedDirectoryId !== null && directoryData.items.some((item) => item.id === requestedDirectoryId)
    const value = valid ? requestedDirectoryId : null
    setDirectoryId(value)
    setBaselineDirectoryId(value)
    if (requestedValue && !valid) router.replace(`/knowledge-space/${kbId}/qa/new`)
  }, [directoryData, kbId, qa, requestedDirectoryId, requestedValue, router])

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  useEffect(() => {
    if (!dirty) return
    const onPopState = () => {
      if (!window.confirm('存在未保存的更改，确定离开吗？')) {
        window.history.forward()
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [dirty])

  const leave = () => {
    if (dirty && !window.confirm('存在未保存的更改，确定离开吗？')) return
    router.push(`/knowledge-space/${kbId}?tab=qa${requestedDirectoryId ? `&directory=${requestedDirectoryId}` : ''}`)
  }

  const addKeyword = () => {
    const value = keywordInput.trim().toLowerCase()
    if (!value) return
    if (!/^[a-z0-9_]+$/.test(value)) {
      setErrors((old) => ({ ...old, keywords: '权限标签仅支持字母、数字和下划线' }))
      return
    }
    if (keywords.length >= 50) {
      setErrors((old) => ({ ...old, keywords: '权限标签最多添加 50 个' }))
      return
    }
    setKeywords((old) => old.includes(value) ? old : [...old, value])
    setKeywordInput('')
    setErrors((old) => ({ ...old, keywords: undefined }))
  }

  const validate = () => {
    const next: FieldErrors = {}
    const q = question.trim()
    const a = answer.trim()
    if (directoryId === null) next.directory = t.directoryRequired
    if (!q) next.question = '请输入问题'
    else if (q.length > 500) next.question = '问题最多输入 500 个字符'
    if (!a) next.answer = '请输入答案'
    else if (a.length > 7000) next.answer = '答案最多输入 7000 个字符'
    setErrors(next)
    const first = next.directory ? 'qa-directory' : next.question ? 'qa-question' : next.answer ? 'qa-answer' : null
    if (first) document.getElementById(first)?.focus()
    return Object.keys(next).length === 0
  }

  const save = async () => {
    if (!validate() || directoryId === null) return
    const pendingKeyword = keywordInput.trim().toLowerCase()
    if (pendingKeyword && !/^[a-z0-9_]+$/.test(pendingKeyword)) {
      setErrors((old) => ({ ...old, keywords: '权限标签仅支持字母、数字和下划线' }))
      return
    }
    const finalKeywords = pendingKeyword && !keywords.includes(pendingKeyword)
      ? [...keywords, pendingKeyword]
      : keywords
    if (finalKeywords.length > 50) {
      setErrors((old) => ({ ...old, keywords: '权限标签最多添加 50 个' }))
      return
    }
    const payload: KnowledgeBaseQaPayload = {
      directory_id: directoryId,
      question: question.trim(),
      answer_markdown: answer.trim(),
      access_keywords: finalKeywords,
      enabled,
    }
    try {
      if (qa) {
        await updateMutation.mutateAsync({ kbId, qaId: qa.id, data: payload })
        const contentChanged = question.trim() !== qa.question || answer.trim() !== qa.answer_markdown || JSON.stringify(finalKeywords) !== JSON.stringify(qa.access_keywords)
        const directoryOnlyChanged = directoryId !== qa.directory_id && !contentChanged && enabled === qa.enabled
        toast(directoryOnlyChanged ? t.directoryOnlyUpdated : contentChanged ? 'QA 已保存，系统正在重新处理' : 'QA 已保存', 'success')
      } else {
        const created = await createMutation.mutateAsync({ kbId, data: payload })
        toast('QA 已新建，系统正在处理', 'success')
        router.replace(`/knowledge-space/${kbId}/qa/${created.id}?directory=${directoryId}`)
      }
    } catch (error) {
      const message = await getErrorMessage(error)
      if (message.toLowerCase().includes('question')) {
        setErrors((old) => ({ ...old, question: '当前知识库已存在相同问题' }))
      }
      toast(message, 'error')
    }
  }

  const retry = async () => {
    if (!qa) return
    try {
      await retryMutation.mutateAsync({ kbId, qaId: qa.id })
      toast('已重新处理 QA', 'success')
    } catch (error) {
      toast(await getErrorMessage(error), 'error')
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-6 py-3 backdrop-blur-sm">
        <button type="button" onClick={leave} className="flex items-center gap-2 text-base font-semibold text-foreground"><IconArrowLeft size={20} className="text-muted-foreground" />{qa ? 'QA 详情' : '新建 QA'}</button>
        <div className="flex gap-2"><Button variant="outline" onClick={leave}>取消</Button>{canManage && <Button disabled={processing || (!dirty && !!qa) || !directoryData?.items.length} loading={saving} onClick={save}>保存</Button>}</div>
      </div>
      <div className="mx-auto w-full max-w-[900px] space-y-6 px-8 py-6">
        <section className="space-y-6 rounded-lg border border-border bg-white p-6">
          <h2 className="text-base font-semibold">基本信息</h2>
          <div className="space-y-1.5"><label htmlFor="qa-directory" className="text-sm font-medium">{t.directorySelect}<span className="ml-0.5 text-[#DC2626]">*</span></label><select id="qa-directory" value={directoryId ?? ''} disabled={processing || !canManage} className={`h-11 w-full rounded-lg border bg-white px-3 text-sm outline-none focus:border-[#1a1a1a] ${errors.directory ? 'border-[#DC2626]' : 'border-[#E5E5E5]'}`} onChange={(event) => { setDirectoryId(event.target.value ? Number(event.target.value) : null); setErrors((old) => ({ ...old, directory: undefined })) }}><option value="">{t.directoryPlaceholder}</option>{directoryOptions.map((item) => <option key={item.id} value={item.id}>{`${'　'.repeat(item.depth - 1)}${item.name}`}</option>)}</select>{errors.directory && <p className="text-xs text-[#DC2626]">{errors.directory}</p>}{directoryData && directoryData.items.length === 0 && <p className="text-xs text-[#A3A3A3]">{t.noDirectoryHint}</p>}</div>
          <Textarea id="qa-question" label="问题" required value={question} disabled={processing || !canManage} maxLength={500} placeholder="请输入问题" error={errors.question} className="min-h-[96px]" onChange={(event) => setQuestion(event.target.value)} />
          <div className="space-y-2">
            <div className="flex items-center justify-between"><label htmlFor="qa-answer" className="text-sm font-medium">答案<span className="ml-0.5 text-[#DC2626]">*</span></label><div className="flex rounded-lg bg-[#F5F5F5] p-1 text-xs"><button type="button" onClick={() => setPreview(false)} className={`rounded-md px-3 py-1.5 ${!preview ? 'bg-white shadow-sm' : 'text-muted-foreground'}`}>编辑</button><button type="button" onClick={() => setPreview(true)} className={`rounded-md px-3 py-1.5 ${preview ? 'bg-white shadow-sm' : 'text-muted-foreground'}`}>预览</button></div></div>
            {preview ? <div className="prose prose-sm min-h-[240px] max-w-none rounded-lg border border-border p-4"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answer || '暂无预览内容'}</ReactMarkdown></div> : <Textarea id="qa-answer" value={answer} disabled={processing || !canManage} maxLength={7000} placeholder="请输入答案" error={errors.answer} className="min-h-[240px] font-mono" onChange={(event) => setAnswer(event.target.value)} />}
          </div>
            <div className="space-y-1.5"><label htmlFor="qa-keyword" className="text-sm font-medium">权限标签 access_keywords</label><div className={`flex min-h-11 flex-wrap items-center gap-1.5 rounded-lg border bg-white px-2 py-1.5 ${errors.keywords ? 'border-[#DC2626]' : 'border-[#E5E5E5]'}`}>{keywords.map((keyword) => <span key={keyword} className="flex items-center gap-1 rounded-full bg-[#F5F5F5] px-2.5 py-1 text-xs">{keyword}<button type="button" disabled={processing || !canManage} aria-label={`删除 ${keyword}`} onClick={() => setKeywords((old) => old.filter((item) => item !== keyword))}><IconX size={12} /></button></span>)}<input id="qa-keyword" value={keywordInput} disabled={processing || !canManage} placeholder={keywords.length ? '' : '输入后按 Enter 添加'} className="h-8 min-w-[180px] flex-1 bg-transparent px-1 text-sm outline-none" onChange={(event) => setKeywordInput(event.target.value)} onBlur={addKeyword} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); addKeyword() } }} /></div>{errors.keywords ? <p className="text-xs text-[#DC2626]">{errors.keywords}</p> : <p className="text-xs text-[#A3A3A3]">留空表示共享内容；如需按权限规则限制，请填写与权限引擎一致的标签。</p>}</div>
          <div className="flex items-center justify-between"><div><p className="text-sm font-medium">启用 QA</p><p className="mt-1 text-xs text-muted-foreground">关闭时仍保存与处理内容，但不参与检索。</p></div><Switch checked={enabled} disabled={processing || !canManage} onChange={setEnabled} /></div>
        </section>
        {qa && <section className="space-y-4 rounded-lg border border-border bg-white p-6"><div className="flex items-center justify-between"><h2 className="text-base font-semibold">处理信息</h2>{canManage && qa.process_status === 'failed' && <Button variant="outline" loading={retryMutation.isPending} onClick={retry}>重试处理</Button>}</div><div className="grid grid-cols-2 gap-4 text-sm"><Info label="处理状态"><Badge variant={qa.process_status === 'ready' ? 'success' : qa.process_status === 'failed' ? 'danger' : 'warning'}>{qa.process_status === 'ready' ? '可检索' : qa.process_status === 'failed' ? '处理失败' : '处理中'}</Badge></Info><Info label="启用状态">{qa.enabled ? '已启用' : '已停用'}</Info><Info label="创建时间">{new Date(qa.created_at).toLocaleString('zh-CN')}</Info><Info label="更新时间">{new Date(qa.updated_at).toLocaleString('zh-CN')}</Info></div>{qa.process_error && <div className="rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#DC2626]">{qa.process_error}</div>}</section>}
        <p className="text-center text-xs text-muted-foreground">问题与答案将作为一个切片参与检索</p>
      </div>
    </div>
  )
}

function Info({ label, children }: { label: string; children: React.ReactNode }) { return <div><p className="text-xs text-muted-foreground">{label}</p><div className="mt-1 text-foreground">{children}</div></div> }
