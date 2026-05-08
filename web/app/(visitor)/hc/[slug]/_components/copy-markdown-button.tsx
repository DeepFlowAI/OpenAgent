'use client'

import { useState } from 'react'
import { IconCopy, IconLoader2 } from '@tabler/icons-react'
import { useToast } from '@/app/components/base/toast'

export function CopyMarkdownButton({ markdown }: { markdown: string }) {
  const { toast } = useToast()
  const [copying, setCopying] = useState(false)

  const handleCopy = async () => {
    setCopying(true)
    try {
      await navigator.clipboard.writeText(markdown)
      toast('已复制当前页 Markdown', 'success')
    } catch {
      toast('复制失败，请重试', 'error')
    } finally {
      setCopying(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      disabled={copying}
      className="inline-flex h-10 shrink-0 items-center gap-2 rounded-full border border-[#D4D4D8] bg-white px-4 text-sm font-medium text-[#3F3F46] transition-colors hover:bg-[#FAFAFA] disabled:pointer-events-none disabled:opacity-60"
    >
      {copying ? (
        <IconLoader2 size={18} className="animate-spin" />
      ) : (
        <IconCopy size={18} />
      )}
      Copy
    </button>
  )
}
