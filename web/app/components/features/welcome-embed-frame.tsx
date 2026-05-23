'use client'

import { useCallback, useMemo, useRef, type CSSProperties } from 'react'
import { buildWelcomeEmbedSrcDoc } from '@/utils/welcome-message'

const WELCOME_EMBED_RENDERER_PATH = '/welcome-embed'
const WELCOME_EMBED_MESSAGE_TYPE = 'openagent:welcome-embed'

function hashString(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0
  }
  return `${value.length}-${hash >>> 0}`
}

type WelcomeEmbedFrameProps = {
  title: string
  embedCode: string
  className?: string
  style?: CSSProperties
}

export function WelcomeEmbedFrame({
  title,
  embedCode,
  className,
  style,
}: WelcomeEmbedFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const embedHtml = useMemo(() => buildWelcomeEmbedSrcDoc(embedCode), [embedCode])
  const frameKey = useMemo(() => hashString(embedHtml), [embedHtml])

  const postEmbedHtml = useCallback(() => {
    const targetWindow = iframeRef.current?.contentWindow
    if (!targetWindow) return

    targetWindow.postMessage(
      {
        type: WELCOME_EMBED_MESSAGE_TYPE,
        html: embedHtml,
      },
      window.location.origin,
    )
  }, [embedHtml])

  const handleLoad = useCallback(() => {
    postEmbedHtml()
    window.setTimeout(postEmbedHtml, 50)
    window.setTimeout(postEmbedHtml, 150)
  }, [postEmbedHtml])

  return (
    <iframe
      key={frameKey}
      ref={iframeRef}
      title={title}
      src={WELCOME_EMBED_RENDERER_PATH}
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-presentation"
      allow="autoplay; fullscreen; picture-in-picture"
      className={className}
      style={style}
      onLoad={handleLoad}
    />
  )
}
