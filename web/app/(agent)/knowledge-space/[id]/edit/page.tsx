'use client'

import { use } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useKnowledgeBase } from '@/service/use-knowledge-base'
import { KnowledgeBaseForm } from '@/app/components/features/knowledge-base-form'

export default function EditKnowledgeBasePage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''
  const { data: knowledgeBase, isLoading } = useKnowledgeBase(Number(id))

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (!knowledgeBase) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">知识库不存在</p>
      </div>
    )
  }

  return <KnowledgeBaseForm knowledgeBase={knowledgeBase} tenantId={tenantId} />
}
