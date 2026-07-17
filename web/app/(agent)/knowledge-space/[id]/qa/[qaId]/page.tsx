'use client'

import { use } from 'react'
import { KnowledgeBaseQaForm } from '@/app/components/features/knowledge-base-qa-form'
import { useKnowledgeBaseQa } from '@/service/use-knowledge-base-qa'

export default function KnowledgeBaseQaDetailPage({ params }: { params: Promise<{ id: string; qaId: string }> }) {
  const { id, qaId } = use(params)
  const kbId = Number(id)
  const { data, isLoading, isError } = useKnowledgeBaseQa(kbId, Number(qaId))
  if (isLoading) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
  if (isError || !data) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">QA 不存在或无权查看</div>
  return <KnowledgeBaseQaForm kbId={kbId} qa={data} />
}
