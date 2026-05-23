import {
  DEFAULT_CONVERSATION_SETTINGS,
  type AIDisclaimerConfig,
  type ConversationSettingsConfig,
  type ToolCallLimitReplyConfig,
  type WelcomeMessageBlock,
} from '@/models/agent'

function createDefaultConversationSettings(): ConversationSettingsConfig {
  return {
    welcome_message: {
      enabled: DEFAULT_CONVERSATION_SETTINGS.welcome_message.enabled,
      blocks: [],
    },
    ai_disclaimer: {
      enabled: DEFAULT_CONVERSATION_SETTINGS.ai_disclaimer.enabled,
      content: DEFAULT_CONVERSATION_SETTINGS.ai_disclaimer.content,
    },
    tool_call_limit_reply: {
      enabled: DEFAULT_CONVERSATION_SETTINGS.tool_call_limit_reply.enabled,
      content: DEFAULT_CONVERSATION_SETTINGS.tool_call_limit_reply.content,
    },
  }
}

export function normalizeWelcomeMessageBlock(
  block: unknown,
): WelcomeMessageBlock | null {
  if (!block || typeof block !== 'object') return null
  const record = block as Record<string, unknown>

  if (record.type === 'markdown') {
    return {
      type: 'markdown',
      content: typeof record.content === 'string' ? record.content : '',
    }
  }

  if (record.type === 'embed') {
    const rawHeight = Number(record.height)
    return {
      type: 'embed',
      embed_code: typeof record.embed_code === 'string' ? record.embed_code : '',
      height: Number.isInteger(rawHeight) && rawHeight > 0 ? rawHeight : 360,
    }
  }

  return null
}

export function normalizeConversationSettings(
  input: unknown,
): ConversationSettingsConfig {
  const defaults = createDefaultConversationSettings()
  if (!input || typeof input !== 'object') return defaults
  const record = input as Record<string, unknown>
  const welcome = record.welcome_message
  const aiDisclaimer = record.ai_disclaimer
  const toolCallLimitReply = record.tool_call_limit_reply

  const welcomeRecord =
    welcome && typeof welcome === 'object'
      ? (welcome as Record<string, unknown>)
      : null
  const rawBlocks = welcomeRecord?.blocks
  const blocks = Array.isArray(rawBlocks)
    ? rawBlocks
        .map(normalizeWelcomeMessageBlock)
        .filter((block): block is WelcomeMessageBlock => Boolean(block))
    : []
  const disclaimerRecord =
    aiDisclaimer && typeof aiDisclaimer === 'object'
      ? (aiDisclaimer as Record<string, unknown>)
      : null
  const disclaimer: AIDisclaimerConfig = {
    enabled: Boolean(disclaimerRecord?.enabled),
    content:
      typeof disclaimerRecord?.content === 'string'
        ? disclaimerRecord.content
        : defaults.ai_disclaimer.content,
  }
  const toolLimitRecord =
    toolCallLimitReply && typeof toolCallLimitReply === 'object'
      ? (toolCallLimitReply as Record<string, unknown>)
      : null
  const toolLimitReply: ToolCallLimitReplyConfig = {
    enabled:
      typeof toolLimitRecord?.enabled === 'boolean'
        ? toolLimitRecord.enabled
        : defaults.tool_call_limit_reply.enabled,
    content:
      typeof toolLimitRecord?.content === 'string'
        ? toolLimitRecord.content
        : defaults.tool_call_limit_reply.content,
  }

  return {
    welcome_message: {
      enabled: Boolean(welcomeRecord?.enabled),
      blocks,
    },
    ai_disclaimer: disclaimer,
    tool_call_limit_reply: toolLimitReply,
  }
}

export function markdownHasVisibleContent(content: string) {
  const imageMatch = /!\[[^\]]*]\((https?:\/\/|\/)[^)]+?\)/i.test(content)
  const text = content
    .replace(/!\[[^\]]*]\([^)]+\)/g, '')
    .replace(/\[[^\]]+]\([^)]+\)/g, '$1')
    .replace(/[`*_>#\-\+\=\[\]\(\).!|~]/g, '')
    .trim()
  return imageMatch || text.length > 0
}

export function isValidWelcomeBlock(block: WelcomeMessageBlock) {
  if (block.type === 'markdown') {
    return markdownHasVisibleContent(block.content)
  }
  return block.embed_code.trim().length > 0 && block.height > 0
}

const WELCOME_EMBED_BASE_STYLE = `<style>
  html, body {
    margin: 0;
    width: 100%;
    height: 100%;
    min-height: 100%;
    background: transparent;
    overflow: hidden;
  }
  *, *::before, *::after { box-sizing: border-box; }
  iframe, video, img, object, embed { max-width: 100%; }
  #J_prismPlayer,
  .prism-player {
    width: 100% !important;
    height: 100% !important;
  }
  .prism-player video,
  .prism-player .prism-cover {
    width: 100% !important;
    height: 100% !important;
  }
</style>`

function isCompleteHtmlDocument(embedCode: string) {
  return /(?:<!doctype\s+html|<html[\s>])/i.test(embedCode)
}

function injectWelcomeEmbedBaseStyle(html: string) {
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `${WELCOME_EMBED_BASE_STYLE}</head>`)
  }

  if (/<html[\s>]/i.test(html)) {
    return html.replace(/<html([^>]*)>/i, `<html$1><head>${WELCOME_EMBED_BASE_STYLE}</head>`)
  }

  return `${WELCOME_EMBED_BASE_STYLE}${html}`
}

export function buildWelcomeEmbedSrcDoc(embedCode: string) {
  if (isCompleteHtmlDocument(embedCode)) {
    return injectWelcomeEmbedBaseStyle(embedCode)
  }

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta http-equiv="x-ua-compatible" content="IE=edge" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  ${WELCOME_EMBED_BASE_STYLE}
</head>
<body>${embedCode}</body>
</html>`
}
