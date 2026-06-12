'use client'

import { useState, useEffect, useRef, useCallback, useMemo, type MouseEvent } from 'react'
import dynamic from 'next/dynamic'
import { cn } from '@/utils/classnames'
import {
  createMarkdownLinkRehypeRewrite,
  stripMarkdownHeadingAnchorsRehypeRewrite,
} from '@/utils/strip-markdown-heading-anchors'
import { getSamePageNavigationLinkProps } from '@/utils/same-page-navigation-allowlist'
import {
  isWeixinMiniProgramUrl,
  openWeixinMiniProgramLink,
} from '@/utils/wx-mini-program'
import {
  IconChevronDown,
  IconChevronRight,
  IconSearch,
  IconTool,
  IconLoader2,
} from '@tabler/icons-react'
import type { ThinkingBlock, ContentBlock, ToolBlock } from '@/models/conversation'
import type { PluggableList } from 'unified'

const MarkdownPreview = dynamic(() => import('@uiw/react-markdown-preview/nohighlight'), {
  ssr: false,
})

const SAFE_MARKDOWN_TAGS = new Set([
  'a',
  'blockquote',
  'br',
  'code',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'img',
  'li',
  'ol',
  'p',
  'pre',
  'strong',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'ul',
  'source',
  'video',
])

function safeMarkdownUrlTransform(url: string) {
  const trimmed = url.trim()
  if (!trimmed) return ''
  if (isWeixinMiniProgramUrl(trimmed)) return trimmed
  if (
    trimmed.startsWith('#') ||
    trimmed.startsWith('/') ||
    trimmed.startsWith('./') ||
    trimmed.startsWith('../')
  ) {
    return trimmed
  }

  try {
    const parsed = new URL(trimmed)
    return ['http:', 'https:', 'mailto:', 'tel:'].includes(parsed.protocol)
      ? trimmed
      : ''
  } catch {
    return ''
  }
}

function safeMarkdownAllowElement(element: { tagName?: string }) {
  const tagName = element.tagName?.toLowerCase()
  return Boolean(tagName && SAFE_MARKDOWN_TAGS.has(tagName))
}

function getWeixinMiniProgramUrlFromClick(target: EventTarget | null) {
  if (!(target instanceof Element)) return null
  const link = target.closest('a[href]')
  const href = link?.getAttribute('href')?.trim()
  return href && isWeixinMiniProgramUrl(href) ? href : null
}

function useWeixinMiniProgramClickHandler() {
  return useCallback((event: MouseEvent<HTMLDivElement>) => {
    const url = getWeixinMiniProgramUrlFromClick(event.target)
    if (!url) return

    event.preventDefault()
    void openWeixinMiniProgramLink(url, () => {
      window.alert('请在微信小程序中打开此功能')
    })
  }, [])
}

function safeMarkdownPluginsFilter(
  type: 'remark' | 'rehype',
  plugins: PluggableList,
): PluggableList {
  if (type !== 'rehype') return plugins
  return plugins.filter((plugin) => {
    const pluginFn = Array.isArray(plugin) ? plugin[0] : plugin
    const name = typeof pluginFn === 'function' ? pluginFn.name : ''
    return name !== 'rehypeAttrs' && name !== 'rehypeRaw'
  }) as PluggableList
}

// ── Typewriter hook ──────────────────────────────────────
// Buffers incoming text and reveals it progressively at ~30fps (33ms aligns
// with every 2 rAF on 60Hz displays).
// Adaptive speed: more pending chars → faster typing to catch up;
// fewer pending → slower, natural pace. Flushes instantly on stream end.

const TYPEWRITER_FRAME_MS = 33
const TYPEWRITER_CATCH_UP_RATIO = 0.06
const TYPEWRITER_MIN_CHARS_PER_TICK = 1
const TYPEWRITER_MAX_CHARS_PER_TICK = 4

function useTypewriter(text: string, isActive: boolean): string {
  const [displayedLen, setDisplayedLen] = useState(() => text.length)
  const textRef = useRef(text)
  const rafRef = useRef<number | null>(null)
  const lastTickRef = useRef(0)

  textRef.current = text

  useEffect(() => {
    if (!isActive) {
      setDisplayedLen(text.length)
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    const tick = (time: number) => {
      if (time - lastTickRef.current < TYPEWRITER_FRAME_MS) {
        rafRef.current = requestAnimationFrame(tick)
        return
      }
      lastTickRef.current = time

      setDisplayedLen(prev => {
        const target = textRef.current.length
        if (prev >= target) return prev
        const pending = target - prev
        const speed = Math.min(
          TYPEWRITER_MAX_CHARS_PER_TICK,
          Math.max(
            TYPEWRITER_MIN_CHARS_PER_TICK,
            Math.ceil(pending * TYPEWRITER_CATCH_UP_RATIO),
          ),
        )
        return Math.min(prev + speed, target)
      })

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [isActive])

  // When not streaming, always return the full text immediately — avoids any
  // timing edge case where displayedLen hasn't caught up after isActive flipped.
  if (!isActive) return text
  return text.slice(0, Math.min(displayedLen, text.length))
}

/** Shown while assistant stream has not produced visible reply text yet */
export function StreamingThinkingPlaceholder({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-flex items-center gap-1.5', className)}
      role="status"
      aria-live="polite"
    >
      <span>正在思考中</span>
      <span className="inline-flex items-end gap-0.5 pb-0.5" aria-hidden>
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-current opacity-70 will-change-transform [animation:thinking-dot-pop_0.36s_ease-in-out_infinite]"
            style={{ animationDelay: `${i * 0.1}s` }}
          />
        ))}
      </span>
    </span>
  )
}

export function ThinkingBlockUI({
  block,
  onInspect,
}: {
  block: ThinkingBlock
  onInspect?: (stepId: number) => void
}) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(() => (
    block.isStreaming ? true : null
  ))
  const expanded = manualToggle !== null ? manualToggle : block.isStreaming
  const displayText = useTypewriter(block.content, block.isStreaming)

  return (
    <div className="mb-1 rounded-lg border border-[#E4E4E7] bg-white px-3 py-2">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setManualToggle(expanded ? false : true)}
          className="flex items-center gap-1 text-xs text-[#71717A] hover:text-[#1A1A1A]"
        >
          {expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
          <span>思考</span>
          {block.isStreaming && <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-[#A1A1AA]" />}
        </button>
        <div className="flex items-center gap-1">
          {block.llmStepId && onInspect && (
            <button
              onClick={() => onInspect(block.llmStepId!)}
              className="flex items-center justify-center text-[#A1A1AA] transition-colors hover:text-[#71717A]"
              title="检视"
            >
              <IconSearch size={12} />
            </button>
          )}
          <button
            onClick={() => setManualToggle(expanded ? false : true)}
            className="flex items-center justify-center text-[#A1A1AA] transition-colors hover:text-[#71717A]"
          >
            <IconChevronRight size={12} />
          </button>
        </div>
      </div>
      {expanded && (
        <div className="mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap break-words border-t border-[#F0F0F0] pt-2 font-mono text-xs leading-relaxed text-[#71717A]">
          {displayText}
          {block.isStreaming && (
            <span
              className="ml-0.5 inline-block h-[6px] w-[6px] translate-y-[-1px] rounded-full bg-[#9CA3AF] [animation:streaming-dot_1.2s_ease-in-out_infinite]"
              aria-hidden
            />
          )}
        </div>
      )}
    </div>
  )
}

export function ToolBlockUI({
  block,
  onInspect,
}: {
  block: ToolBlock
  onInspect?: (stepId: number) => void
}) {
  return (
    <div
      className={cn(
        'mb-1 flex items-center gap-2 rounded-lg border bg-white px-3 py-2',
        block.isExecuting
          ? 'border-dashed border-[#3B82F6]/40'
          : 'border-[#E4E4E7]'
      )}
    >
      <IconTool size={14} className="shrink-0 text-[#71717A]" />
      <span className="min-w-0 flex-1 truncate text-xs text-[#404040]">{block.brief}</span>
      {block.isExecuting && (
        <IconLoader2 size={12} className="shrink-0 animate-spin text-[#3B82F6]" />
      )}
      {block.llmStepId && onInspect && (
        <button
          onClick={() => onInspect(block.llmStepId!)}
          className="shrink-0 text-[#A1A1AA] transition-colors hover:text-[#71717A]"
          title="检视"
        >
          <IconSearch size={12} />
        </button>
      )}
    </div>
  )
}

/**
 * Wraps the interleaved thinking/tool/intermediate-content timeline. The
 * collapsed/expanded default is derived deterministically from `isStreaming`
 * rather than from observing a streaming→done transition: expanded while the
 * turn streams, collapsed into a one-line summary once finished. This keeps
 * the state stable across refreshes, history loads, and remounts (e.g. when
 * scrolling re-mounts the message subtree), where a transition would never be
 * observed. User toggles win for the current mount.
 */
export function IntermediateSteps({
  thinkingBlocks,
  toolBlocks,
  inlineContentBlocks,
  isStreaming,
  onInspect,
  samePageNavigationUrlAllowlist,
}: {
  thinkingBlocks: ThinkingBlock[]
  toolBlocks: ToolBlock[]
  inlineContentBlocks: ContentBlock[]
  isStreaming: boolean
  onInspect?: (stepId: number) => void
  samePageNavigationUrlAllowlist?: readonly string[]
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null)

  const entries = [
    ...thinkingBlocks.map(b => ({ type: 'thinking' as const, block: b, idx: b.timelineIndex ?? 0 })),
    ...toolBlocks.map(b => ({ type: 'tool' as const, block: b, idx: b.timelineIndex ?? 0 })),
    ...inlineContentBlocks.map(b => ({ type: 'content' as const, block: b, idx: b.timelineIndex ?? 0 })),
  ].sort((a, b) => a.idx - b.idx)

  if (entries.length === 0) return null

  const open = manualOpen !== null ? manualOpen : isStreaming

  const summaryParts: string[] = []
  if (thinkingBlocks.length > 0) summaryParts.push('已思考')
  if (toolBlocks.length > 0) summaryParts.push(`调用了 ${toolBlocks.length} 个工具`)
  const summary = summaryParts.join(' · ') || '查看过程'

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setManualOpen(true)}
        className="mb-1 flex items-center gap-1.5 self-start rounded-lg border border-[#E4E4E7] bg-white px-3 py-1.5 text-xs text-[#71717A] transition-colors hover:text-[#1A1A1A]"
      >
        <IconChevronRight size={14} />
        <span>{summary}</span>
      </button>
    )
  }

  return (
    <>
      {!isStreaming && (
        <button
          type="button"
          onClick={() => setManualOpen(false)}
          className="mb-1 flex items-center gap-1.5 self-start text-xs text-[#A1A1AA] transition-colors hover:text-[#71717A]"
        >
          <IconChevronDown size={14} />
          <span>{summary}</span>
        </button>
      )}
      {entries.map(entry => {
        switch (entry.type) {
          case 'thinking':
            return <ThinkingBlockUI key={entry.block.id} block={entry.block} onInspect={onInspect} />
          case 'tool':
            return <ToolBlockUI key={entry.block.id} block={entry.block} onInspect={onInspect} />
          case 'content':
            return (
              <InlineContentUI
                key={entry.block.id}
                block={entry.block}
                samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
              />
            )
        }
      })}
    </>
  )
}

function StreamingCursor({ active }: { active: boolean }) {
  if (!active) return null
  return (
    <span
      className="ml-0.5 inline-block h-[6px] w-[6px] translate-y-[-1px] rounded-full bg-current [animation:streaming-dot_1.2s_ease-in-out_infinite]"
      aria-hidden
    />
  )
}

export function InlineContentUI({
  block,
  samePageNavigationUrlAllowlist,
}: {
  block: ContentBlock
  samePageNavigationUrlAllowlist?: readonly string[]
}) {
  const displayText = useTypewriter(block.content, block.isStreaming)
  const hasText = Boolean(block.content.trim())
  const handleClick = useWeixinMiniProgramClickHandler()

  if (!hasText && !block.isStreaming) return null

  return (
    <div className="mb-1 rounded-[14px] bg-white px-[14px] py-[10px] shadow-sm">
      {hasText ? (
        <div
          className="text-sm leading-relaxed text-[#1A1A1A]"
          data-color-mode="light"
          onClick={handleClick}
        >
          <MarkdownPreview
            source={displayText}
            style={{ background: 'transparent', fontSize: 14 }}
            skipHtml
            allowElement={safeMarkdownAllowElement}
            pluginsFilter={safeMarkdownPluginsFilter}
            urlTransform={safeMarkdownUrlTransform}
            rehypeRewrite={
              samePageNavigationUrlAllowlist?.length
                ? createMarkdownLinkRehypeRewrite((href) =>
                    getSamePageNavigationLinkProps(href, samePageNavigationUrlAllowlist)
                  )
                : stripMarkdownHeadingAnchorsRehypeRewrite
            }
          />
          <StreamingCursor active={block.isStreaming} />
        </div>
      ) : (
        <StreamingThinkingPlaceholder className="text-sm text-[#1A1A1A]" />
      )}
    </div>
  )
}

export function MarkdownContent({
  source,
  style,
  samePageNavigationUrlAllowlist,
}: {
  source: string
  style?: React.CSSProperties
  samePageNavigationUrlAllowlist?: readonly string[]
}) {
  const handleClick = useWeixinMiniProgramClickHandler()
  const rehypeRewrite = useMemo(() => {
    if (!samePageNavigationUrlAllowlist?.length) {
      return stripMarkdownHeadingAnchorsRehypeRewrite
    }
    return createMarkdownLinkRehypeRewrite((href) =>
      getSamePageNavigationLinkProps(href, samePageNavigationUrlAllowlist)
    )
  }, [samePageNavigationUrlAllowlist])

  return (
    // leading-[26px] matches chat user bubble; avoid leading-relaxed stacking with @uiw .wmde-markdown { line-height: 1.5 }
    <div className="chat-markdown text-sm leading-[26px]" data-color-mode="light" onClick={handleClick}>
      <MarkdownPreview
        source={source}
        style={{ background: 'transparent', fontSize: 14, ...style }}
        skipHtml
        allowElement={safeMarkdownAllowElement}
        pluginsFilter={safeMarkdownPluginsFilter}
        urlTransform={safeMarkdownUrlTransform}
        rehypeRewrite={rehypeRewrite}
      />
    </div>
  )
}

/** MarkdownContent with typewriter animation for streaming replies */
export function StreamingMarkdownContent({
  source,
  isStreaming,
  style,
  samePageNavigationUrlAllowlist,
}: {
  source: string
  isStreaming: boolean
  style?: React.CSSProperties
  samePageNavigationUrlAllowlist?: readonly string[]
}) {
  const displayText = useTypewriter(source, isStreaming)
  return (
    <div>
      <MarkdownContent
        source={displayText}
        style={style}
        samePageNavigationUrlAllowlist={samePageNavigationUrlAllowlist}
      />
      <StreamingCursor active={isStreaming} />
    </div>
  )
}
