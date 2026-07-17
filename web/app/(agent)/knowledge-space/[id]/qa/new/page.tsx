'use client'

import { use } from 'react'
import { KnowledgeBaseQaForm } from '@/app/components/features/knowledge-base-qa-form'

export default function NewKnowledgeBaseQaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <KnowledgeBaseQaForm kbId={Number(id)} />
}
