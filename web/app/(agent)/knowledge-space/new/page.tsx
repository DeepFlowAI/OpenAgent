'use client'

import { useAuthStore } from '@/context/auth-store'
import { KnowledgeBaseForm } from '@/app/components/features/knowledge-base-form'

export default function NewKnowledgeBasePage() {
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''

  return <KnowledgeBaseForm tenantId={tenantId} />
}
