'use client'

import { use } from 'react'
import { ForbiddenState } from '@/app/components/base/forbidden-state'
import { KnowledgeBaseQaForm } from '@/app/components/features/knowledge-base-qa-form'
import { useAuthStore } from '@/context/auth-store'
import { useKnowledgeBaseQa } from '@/service/use-knowledge-base-qa'

export default function KnowledgeBaseQaDetailPage({ params }: { params: Promise<{ id: string; qaId: string }> }) {
  const { id, qaId } = use(params)
  const isAdmin = useAuthStore((state) => state.user?.role === 'admin')
  if (!isAdmin) {
    return (
      <ForbiddenState
        returnHref={`/knowledge-space/${id}`}
        returnLabel="返回知识库"
        returnLabelEn="Back to knowledge base"
      />
    )
  }
  return <AdminQaDetail kbId={Number(id)} qaId={Number(qaId)} />
}

function AdminQaDetail({ kbId, qaId }: { kbId: number; qaId: number }) {
  const { data, isLoading, isError } = useKnowledgeBaseQa(kbId, qaId)
  if (isLoading) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
  if (isError || !data) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">QA 不存在或无权查看</div>
  return <KnowledgeBaseQaForm kbId={kbId} qa={data} />
}
