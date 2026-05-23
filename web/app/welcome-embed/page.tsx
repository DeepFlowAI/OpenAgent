'use client'

import { useEffect } from 'react'

const WELCOME_EMBED_MESSAGE_TYPE = 'openagent:welcome-embed'

export default function WelcomeEmbedPage() {
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return
      const data = event.data as { type?: unknown; html?: unknown }
      if (
        !data ||
        data.type !== WELCOME_EMBED_MESSAGE_TYPE ||
        typeof data.html !== 'string'
      ) {
        return
      }

      document.open()
      document.write(data.html)
      document.close()
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  return null
}
