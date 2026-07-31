'use client'

import { useAuthStore } from '@/context/auth-store'
import { KnowledgeBaseForm } from '@/app/components/features/knowledge-base-form'
import { ForbiddenState } from '@/app/components/base/forbidden-state'

export default function NewKnowledgeBasePage() {
  const tenantId = useAuthStore((s) => s.user?.tenant_id) || ''
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')

  return isAdmin ? (
    <KnowledgeBaseForm tenantId={tenantId} />
  ) : (
    <ForbiddenState
      returnHref="/knowledge-space"
      returnLabel="返回知识空间"
      returnLabelEn="Back to knowledge space"
    />
  )
}
