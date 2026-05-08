'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Input } from '@/app/components/base/input'
import { Textarea } from '@/app/components/base/textarea'
import { Button } from '@/app/components/base/button'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import {
  useCreateKnowledgeBase,
  useUpdateKnowledgeBase,
} from '@/service/use-knowledge-base'
import type { KnowledgeBase } from '@/models/knowledge-base'

type KnowledgeBaseFormProps = {
  knowledgeBase?: KnowledgeBase
  tenantId: string
}

export function KnowledgeBaseForm({
  knowledgeBase,
  tenantId,
}: KnowledgeBaseFormProps) {
  const router = useRouter()
  const { toast } = useToast()
  const isEdit = !!knowledgeBase
  const createMutation = useCreateKnowledgeBase()
  const updateMutation = useUpdateKnowledgeBase()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [gitUrl, setGitUrl] = useState('')
  const [gitBranch, setGitBranch] = useState('main')
  const [authType, setAuthType] = useState<'none' | 'token'>('none')
  const [authToken, setAuthToken] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (knowledgeBase) {
      setName(knowledgeBase.name)
      setDescription(knowledgeBase.description || '')
      setGitUrl(knowledgeBase.git_url)
      setGitBranch(knowledgeBase.git_branch)
      setAuthType(knowledgeBase.auth_type)
      setAuthToken(knowledgeBase.auth_token || '')
    }
  }, [knowledgeBase])

  const validate = () => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = '请输入知识库名称'
    else if (name.length > 64) errs.name = '名称最多 64 个字符'
    if (!gitUrl.trim()) errs.gitUrl = '请输入仓库地址'
    if (authType === 'token' && !authToken.trim())
      errs.authToken = '请输入 Token'
    if (description.length > 256) errs.description = '描述最多 256 个字符'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return

    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: knowledgeBase.id,
          data: {
            name: name.trim(),
            description: description.trim() || undefined,
            git_url: gitUrl.trim(),
            git_branch: gitBranch.trim() || 'main',
            auth_type: authType,
            auth_token: authType === 'token' ? authToken.trim() : undefined,
          },
        })
        toast('保存成功', 'success')
      } else {
        await createMutation.mutateAsync({
          tenant_id: tenantId,
          name: name.trim(),
          description: description.trim() || undefined,
          git_url: gitUrl.trim(),
          git_branch: gitBranch.trim() || 'main',
          auth_type: authType,
          auth_token: authType === 'token' ? authToken.trim() : undefined,
        })
        toast('创建成功', 'success')
      }
      router.push('/knowledge-space')
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const isLoading = createMutation.isPending || updateMutation.isPending

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background px-8 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/knowledge-space')}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            ←
          </button>
          <h1 className="text-lg font-semibold text-foreground">
            {isEdit ? `编辑：${knowledgeBase.name}` : '新建知识库'}
          </h1>
        </div>
        <Button onClick={handleSubmit} loading={isLoading}>
          保存
        </Button>
      </div>

      <div className="flex-1 overflow-auto px-8 py-8">
        <div className="max-w-[640px] space-y-8">
          <section className="space-y-4">
            <h2 className="text-sm font-semibold text-foreground">基本信息</h2>
            <Input
              label="知识库名称"
              required
              placeholder="请输入知识库名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={errors.name}
              maxLength={64}
            />
            <Textarea
              label="描述"
              placeholder="描述该知识库的用途（可选）"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              error={errors.description}
              maxLength={256}
              className="min-h-[80px]"
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-sm font-semibold text-foreground">Git 绑定</h2>
            <Input
              label="仓库地址"
              required
              placeholder="Git 仓库地址（HTTPS）"
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              error={errors.gitUrl}
            />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="分支"
                placeholder="main"
                value={gitBranch}
                onChange={(e) => setGitBranch(e.target.value)}
              />
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-[#1a1a1a]">
                  认证方式
                </label>
                <select
                  value={authType}
                  onChange={(e) =>
                    setAuthType(e.target.value as 'none' | 'token')
                  }
                  className="h-11 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm text-[#1a1a1a] transition-colors focus:border-[#1a1a1a] focus:outline-none focus:ring-2 focus:ring-[#1a1a1a]/10"
                >
                  <option value="none">无</option>
                  <option value="token">Token</option>
                </select>
              </div>
            </div>
            {authType === 'token' && (
              <Input
                label="Token"
                required
                placeholder="请输入访问 Token"
                value={authToken}
                onChange={(e) => setAuthToken(e.target.value)}
                error={errors.authToken}
                type="password"
              />
            )}
            <p className="text-xs text-muted-foreground">
              仓库需符合《可编程文档规范》，根目录含 schema/，其他目录含 .md 文档
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
