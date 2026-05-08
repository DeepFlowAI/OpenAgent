'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'

export default function EngineRedirect() {
  const params = useParams()
  const router = useRouter()

  useEffect(() => {
    router.replace(`/agent/agents/${params.id}/engine/basic`)
  }, [params.id, router])

  return null
}
