'use client'

import { use } from 'react'
import { ForbiddenState } from '@/app/components/base/forbidden-state'
import { KnowledgeBaseQaForm } from '@/app/components/features/knowledge-base-qa-form'
import { useAuthStore } from '@/context/auth-store'

export default function NewKnowledgeBaseQaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
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
  return <KnowledgeBaseQaForm kbId={Number(id)} />
}
