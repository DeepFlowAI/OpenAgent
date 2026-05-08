'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function ChannelsRedirectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/system/channels/web-sdk')
  }, [router])

  return null
}
