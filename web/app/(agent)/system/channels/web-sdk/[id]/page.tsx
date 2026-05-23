'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useChannel, useUpdateChannel } from '@/service/use-channel'
import { useAgents } from '@/service/use-agent'
import { useToast } from '@/app/components/base/toast'
import { getErrorMessage, uploadImage } from '@/service/base'
import { Button } from '@/app/components/base/button'
import { Modal } from '@/app/components/base/modal'
import { Switch } from '@/app/components/base/switch'
import { normalizeSamePageNavigationAllowlist } from '@/utils/same-page-navigation-allowlist'
import {
  IconArrowLeft,
  IconCopy,
  IconCheck,
  IconChevronDown,
  IconImageInPicture,
  IconX,
  IconLoader2,
} from '@tabler/icons-react'

type AppearanceConfig = {
  favicon: string
  pageTitle: string
  logo: string
  pcMemberLogo: string
  mobileLogo: string
  mobileMemberLogo: string
  headerCustomButtonImage: string
  headerCustomButtonUrl: string
  headerMemberCustomButtonImage: string
  headerMemberCustomButtonUrl: string
  title: string
  pcTitleColor: string
  headerBgColor: string
  headerTitleColor: string
  historySidebarBgColor: string
  historySidebarTextColor: string
  historyItemActiveBgColor: string
  historyItemHoverBgColor: string
  messageAreaBgColor: string
  pcEmptyStateImage: string
  mobileEmptyStateImage: string
  pcMemberEmptyStateImage: string
  mobileMemberEmptyStateImage: string
  sendMessageButtonBgColor: string
  sendMessageButtonIconColor: string
  stopMessageButtonBgColor: string
  agentBubbleBgColor: string
  agentBubbleTextColor: string
  agentBubbleBorderColor: string
  agentBubbleRadius: string
  agentAvatar: string
  userAvatar: string
  userBubbleBgColor: string
  userBubbleTextColor: string
  userBubbleBorderColor: string
  userBubbleRadius: string
  embedButtonBgColor: string
  embedButtonIconColor: string
  // Sidebar footer (company intro & links)
  sidebarFooterLogos: string[]
  sidebarFooterIntro: string
  sidebarFooterSubtext: string
  sidebarFooterLinkLabel: string
  sidebarFooterLinkUrl: string
}

type BehaviorConfig = {
  inputPlaceholder: string
  feedbackEnabled: boolean
}

type ChannelConfig = {
  appearance: AppearanceConfig
  behavior: BehaviorConfig
  samePageNavigationUrlAllowlist: string[]
}

const DEFAULT_APPEARANCE: AppearanceConfig = {
  favicon: '',
  pageTitle: '',
  logo: '',
  pcMemberLogo: '',
  mobileLogo: '',
  mobileMemberLogo: '',
  headerCustomButtonImage: '',
  headerCustomButtonUrl: '',
  headerMemberCustomButtonImage: '',
  headerMemberCustomButtonUrl: '',
  title: '',
  pcTitleColor: '#1A1A1A',
  headerBgColor: '#1A1A1A',
  headerTitleColor: '#FFFFFF',
  historySidebarBgColor: '#F4F4F5',
  historySidebarTextColor: '#18181B',
  historyItemActiveBgColor: '#F4F4F5',
  historyItemHoverBgColor: '#F0F0F0',
  messageAreaBgColor: '#FFFFFF',
  pcEmptyStateImage: '',
  mobileEmptyStateImage: '',
  pcMemberEmptyStateImage: '',
  mobileMemberEmptyStateImage: '',
  sendMessageButtonBgColor: '#1A1A1A',
  sendMessageButtonIconColor: '#FFFFFF',
  stopMessageButtonBgColor: '#DC2626',
  agentBubbleBgColor: '#F4F4F5',
  agentBubbleTextColor: '#18181B',
  agentBubbleBorderColor: '#E4E4E7',
  agentBubbleRadius: '20 20 20 20',
  agentAvatar: '',
  userAvatar: '',
  userBubbleBgColor: '#1A1A1A',
  userBubbleTextColor: '#FAFAFA',
  userBubbleBorderColor: '',
  userBubbleRadius: '20 20 20 20',
  embedButtonBgColor: '#1A1A1A',
  embedButtonIconColor: '#FFFFFF',
  sidebarFooterLogos: [],
  sidebarFooterIntro: '',
  sidebarFooterSubtext: '',
  sidebarFooterLinkLabel: '',
  sidebarFooterLinkUrl: '',
}

const SIDEBAR_FOOTER_LOGO_MAX = 4

const DEFAULT_BEHAVIOR: BehaviorConfig = {
  inputPlaceholder: '输入消息...',
  feedbackEnabled: false,
}

function parseConfig(raw: Record<string, unknown>): ChannelConfig {
  const a = (raw?.appearance ?? {}) as Partial<AppearanceConfig>
  const b = (raw?.behavior ?? {}) as Partial<BehaviorConfig>
  const allowlist = normalizeSamePageNavigationAllowlist(
    Array.isArray(raw?.samePageNavigationUrlAllowlist)
      ? raw.samePageNavigationUrlAllowlist.filter((item): item is string => typeof item === 'string')
      : null
  )
  return {
    appearance: { ...DEFAULT_APPEARANCE, ...a },
    behavior: { ...DEFAULT_BEHAVIOR, ...b },
    samePageNavigationUrlAllowlist: allowlist.patterns,
  }
}

export default function EditWebSdkChannelPage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  const channelId = Number(params.id)

  const user = useAuthStore((s) => s.user)
  const tenantId = user?.tenant_id ?? ''

  const { data: channel, isLoading } = useChannel(channelId)
  const { data: agentsData } = useAgents(tenantId, 'active', { page: 1, per_page: 100 })
  const updateMutation = useUpdateChannel()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [agentId, setAgentId] = useState<number | null>(null)
  const [accessMode, setAccessMode] = useState<'url' | 'embed'>('url')
  const [appearance, setAppearance] = useState<AppearanceConfig>(DEFAULT_APPEARANCE)
  const [behavior, setBehavior] = useState<BehaviorConfig>(DEFAULT_BEHAVIOR)
  const [samePageNavigationUrlAllowlistText, setSamePageNavigationUrlAllowlistText] = useState('')
  const [dirty, setDirty] = useState(false)
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const [pendingLeave, setPendingLeave] = useState(false)

  useEffect(() => {
    if (!channel) return
    setName(channel.name)
    setDescription(channel.description ?? '')
    setAgentId(channel.agent_id)
    setAccessMode(channel.access_mode as 'url' | 'embed')
    const cfg = parseConfig(channel.config)
    setAppearance(cfg.appearance)
    setBehavior(cfg.behavior)
    setSamePageNavigationUrlAllowlistText(cfg.samePageNavigationUrlAllowlist.join('\n'))
    setErrors({})
    setDirty(false)
  }, [channel])

  const markDirty = useCallback(() => setDirty(true), [])

  const updateAppearance = useCallback((patch: Partial<AppearanceConfig>) => {
    setAppearance(p => ({ ...p, ...patch }))
    setDirty(true)
  }, [])

  const updateBehavior = useCallback((patch: Partial<BehaviorConfig>) => {
    setBehavior(p => ({ ...p, ...patch }))
    setDirty(true)
  }, [])

  const validateForm = (): { valid: boolean; samePageNavigationUrlAllowlist: string[] } => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = '请输入渠道名称'
    else if (name.length > 64) errs.name = '名称不能超过 64 个字符'
    if (description.length > 500) errs.description = '描述不能超过 500 个字符'

    const allowlist = normalizeSamePageNavigationAllowlist(samePageNavigationUrlAllowlistText)
    if (allowlist.error) {
      errs.samePageNavigationUrlAllowlist = allowlist.error
    }

    setErrors(errs)
    return {
      valid: Object.keys(errs).length === 0,
      samePageNavigationUrlAllowlist: allowlist.patterns,
    }
  }

  const handleSave = async () => {
    const validation = validateForm()
    if (!validation.valid) return

    // Sanitize sidebar-footer fields: trim text and drop empty logos
    const cleanedAppearance: AppearanceConfig = {
      ...appearance,
      sidebarFooterLogos: (appearance.sidebarFooterLogos || [])
        .map(s => (s || '').trim())
        .filter(Boolean),
      sidebarFooterIntro: (appearance.sidebarFooterIntro || '').trim(),
      sidebarFooterSubtext: (appearance.sidebarFooterSubtext || '').trim(),
      sidebarFooterLinkLabel: (appearance.sidebarFooterLinkLabel || '').trim(),
      sidebarFooterLinkUrl: (appearance.sidebarFooterLinkUrl || '').trim(),
      headerCustomButtonImage: (appearance.headerCustomButtonImage || '').trim(),
      headerCustomButtonUrl: (appearance.headerCustomButtonUrl || '').trim(),
      headerMemberCustomButtonImage: (appearance.headerMemberCustomButtonImage || '').trim(),
      headerMemberCustomButtonUrl: (appearance.headerMemberCustomButtonUrl || '').trim(),
      pcEmptyStateImage: (appearance.pcEmptyStateImage || '').trim(),
      mobileEmptyStateImage: (appearance.mobileEmptyStateImage || '').trim(),
      pcMemberEmptyStateImage: (appearance.pcMemberEmptyStateImage || '').trim(),
      mobileMemberEmptyStateImage: (appearance.mobileMemberEmptyStateImage || '').trim(),
    }

    // Soft-validate the privacy/policy URL — non-blocking warning
    const urlsToCheck = [
      cleanedAppearance.sidebarFooterLinkUrl,
      cleanedAppearance.headerCustomButtonUrl,
      cleanedAppearance.headerMemberCustomButtonUrl,
    ]
    if (urlsToCheck.some(u => u && !/^https?:\/\//i.test(u))) {
      toast('链接 URL 建议以 http(s):// 开头', 'error')
    }

    try {
      await updateMutation.mutateAsync({
        id: channelId,
        data: {
          name: name.trim(),
          description: description.trim() || null,
          agent_id: agentId,
          access_mode: accessMode,
          config: {
            appearance: cleanedAppearance,
            behavior,
            samePageNavigationUrlAllowlist: validation.samePageNavigationUrlAllowlist,
          },
        },
      })
      setAppearance(cleanedAppearance)
      setSamePageNavigationUrlAllowlistText(
        validation.samePageNavigationUrlAllowlist.join('\n')
      )
      setName(name.trim())
      setDescription(description.trim())
      toast('已保存', 'success')
      setDirty(false)
    } catch (err) {
      const msg = await getErrorMessage(err)
      toast(msg, 'error')
    }
  }

  const handleBack = () => {
    if (dirty) {
      setShowLeaveModal(true)
      setPendingLeave(true)
    } else {
      router.push('/system/channels/web-sdk')
    }
  }

  const handleLeaveConfirm = () => {
    setShowLeaveModal(false)
    if (pendingLeave) router.push('/system/channels/web-sdk')
  }

  const channelToken = channel?.token ?? ''

  const chatPageUrl = useMemo(() => {
    if (typeof window === 'undefined' || !channelToken) return ''
    return `${window.location.origin}/chat/${channelToken}`
  }, [channelToken])

  const testChatPageUrl = useMemo(() => {
    if (!chatPageUrl) return ''
    const url = new URL(chatPageUrl)
    url.searchParams.set('test', 'true')
    return url.toString()
  }, [chatPageUrl])

  const embedSnippet = useMemo(() => {
    if (typeof window === 'undefined' || !channelToken) return ''
    const origin = window.location.origin
    return `<script src="${origin}/sdk/openagent-sdk.js"></script>\n<script>\n  OpenAgentSDK.init({ channelId: '${channelToken}' });\n</script>`
  }, [channelToken])

  const agents = agentsData?.items ?? []

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#E4E4E7] border-t-[#1A1A1A]" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 border-b border-[#E4E4E7] bg-white px-10 py-3 backdrop-blur-sm supports-[backdrop-filter]:bg-white/80">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              className="flex items-center gap-2 text-sm text-[#737373] transition-colors hover:text-[#18181B]"
              onClick={handleBack}
            >
              <IconArrowLeft size={20} />
              <span>返回列表</span>
            </button>
            <h1 className="text-base font-semibold text-[#18181B]">
              编辑：{name}
            </h1>
          </div>
          <button
            className="flex h-9 items-center justify-center rounded-lg bg-[#1A1A1A] px-4 text-sm font-medium text-white transition-colors hover:bg-[#333] disabled:opacity-50"
            onClick={handleSave}
            disabled={updateMutation.isPending}
          >
            {updateMutation.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-auto px-10 py-8">
        <div className="flex flex-col gap-4">

          {/* ── Section: 基础信息 ── */}
          <SectionCard>
            <SectionTitle>基础信息</SectionTitle>
            <div className="flex max-w-[560px] flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-[#404040]">
                  名称 <span className="text-[#DC2626]">*</span>
                </label>
                <input
                  className={`h-10 rounded-lg border bg-white px-3 text-sm text-[#18181B] outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A] ${
                    errors.name ? 'border-[#DC2626]' : 'border-[#E4E4E7]'
                  }`}
                  placeholder="请输入渠道名称"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value)
                    markDirty()
                    if (errors.name) setErrors((prev) => ({ ...prev, name: '' }))
                  }}
                  maxLength={64}
                />
                {errors.name && <span className="text-xs text-[#DC2626]">{errors.name}</span>}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-[#404040]">描述</label>
                <textarea
                  className={`min-h-[80px] resize-none rounded-lg border bg-white px-3 py-2 text-sm text-[#18181B] outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A] ${
                    errors.description ? 'border-[#DC2626]' : 'border-[#E4E4E7]'
                  }`}
                  placeholder="选填，用于内部识别"
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value)
                    markDirty()
                    if (errors.description) setErrors((prev) => ({ ...prev, description: '' }))
                  }}
                  maxLength={500}
                />
                {errors.description && <span className="text-xs text-[#DC2626]">{errors.description}</span>}
              </div>
            </div>
          </SectionCard>

          {/* ── Section: 接入模式 ── */}
          <SectionCard>
            <SectionTitle>接入模式</SectionTitle>
            <p className="-mt-1 text-xs leading-snug text-[#71717A]">选择渠道接入方式</p>

            <div className="flex flex-wrap items-center gap-2">
              <SegmentPill active={accessMode === 'url'} onClick={() => { setAccessMode('url'); markDirty() }}>
                URL 模式
              </SegmentPill>
              <SegmentPill active={accessMode === 'embed'} onClick={() => { setAccessMode('embed'); markDirty() }}>
                嵌入 SDK 模式
              </SegmentPill>
            </div>

            {/* URL mode card */}
            {accessMode === 'url' && (
              <div className="flex flex-col gap-4 rounded-lg bg-[#FAFAFA] p-3">
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-medium text-[#404040]">测试链接</span>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="flex h-9 min-w-0 flex-1 items-center rounded-lg border border-[#E4E4E7] bg-white px-3">
                      <span className="truncate text-[13px] text-[#71717A]">{testChatPageUrl}</span>
                    </div>
                    <CopyButton text={testChatPageUrl} label="复制链接" />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-medium text-[#404040]">会话页链接</span>
                    <span className="shrink-0 text-xs text-[#A1A1AA]">URL 模式</span>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="flex h-9 min-w-0 flex-1 items-center rounded-lg border border-[#E4E4E7] bg-white px-3">
                      <span className="truncate text-[13px] text-[#71717A]">{chatPageUrl}</span>
                    </div>
                    <CopyButton text={chatPageUrl} label="复制链接" />
                  </div>
                </div>
              </div>
            )}

            {/* Embed card */}
            {accessMode === 'embed' && (
              <div className="rounded-lg bg-[#FAFAFA] p-3">
                <span className="text-[13px] font-medium text-[#404040]">小窗浮层</span>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-[#404040]">嵌入代码</span>
                  <span className="shrink-0 text-xs text-[#A1A1AA]">嵌入 SDK 模式</span>
                </div>
                <div className="mt-3 flex gap-2">
                  <div className="min-h-[5rem] flex-1 rounded-lg border border-[#27272A] bg-[#18181B] p-2.5">
                    <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-[#A1A1AA]">{embedSnippet}</pre>
                  </div>
                  <CopyButton text={embedSnippet} label="复制代码" />
                </div>
              </div>
            )}
          </SectionCard>

          {/* ── Section: Agent 选择 ── */}
          <SectionCard>
            <SectionTitle>Agent 选择</SectionTitle>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium text-[#404040]">Agent</span>
              <div className="relative">
                <select
                  className="h-9 w-[min(100%,320px)] min-w-[200px] appearance-none rounded-lg border border-[#E4E4E7] bg-white px-3 pr-8 text-sm text-[#18181B] outline-none transition-colors focus:border-[#1A1A1A]"
                  value={agentId ?? ''}
                  onChange={(e) => { setAgentId(e.target.value ? Number(e.target.value) : null); markDirty() }}
                >
                  <option value="">请选择 Agent</option>
                  {agents.map((ag) => (
                    <option key={ag.id} value={ag.id}>{ag.name}</option>
                  ))}
                </select>
                <IconChevronDown size={18} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#737373]" />
              </div>
            </div>
          </SectionCard>

          {/* ── Section: 窗口外观 ── */}
          <SectionCard>
            <SectionTitle>窗口外观</SectionTitle>

            {/* 网页信息 — URL mode only */}
            {accessMode === 'url' && (
              <>
                <FieldRow label="网页 icon">
                  <UploadArea value={appearance.favicon}
                    onChange={(v) => updateAppearance({ favicon: v })}
                    onError={(msg) => toast(msg, 'error')} />
                </FieldRow>
                <FieldRow label="网页标题">
                  <TextInput width={280} value={appearance.pageTitle} placeholder="浏览器标签页标题"
                    onChange={(v) => updateAppearance({ pageTitle: v })} />
                </FieldRow>

                <Sep />
              </>
            )}

            {/* 头部 */}
            <SubTitle>头部</SubTitle>
            <FieldRow label="标题">
              <TextInput width={280} value={appearance.title} placeholder="头部标题"
                onChange={(v) => updateAppearance({ title: v })} />
            </FieldRow>

            <SubTitle>PC</SubTitle>
            <FieldRow label="PC 标题颜色">
              <ColorSwatch value={appearance.pcTitleColor}
                onChange={(v) => updateAppearance({ pcTitleColor: v })} />
            </FieldRow>
            <FieldRow label="PC Logo">
              <UploadArea value={appearance.logo}
                onChange={(v) => updateAppearance({ logo: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="PC 会员 Logo">
              <UploadArea value={appearance.pcMemberLogo}
                onChange={(v) => updateAppearance({ pcMemberLogo: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>

            <SubTitle>移动端 / 小窗</SubTitle>
            <FieldRow label="头部背景色">
              <ColorSwatch value={appearance.headerBgColor}
                onChange={(v) => updateAppearance({ headerBgColor: v })} />
            </FieldRow>
            <FieldRow label="移动端 Logo">
              <UploadArea value={appearance.mobileLogo}
                onChange={(v) => updateAppearance({ mobileLogo: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="移动端会员 Logo">
              <UploadArea value={appearance.mobileMemberLogo}
                onChange={(v) => updateAppearance({ mobileMemberLogo: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="标题颜色（移动端）">
              <ColorSwatch value={appearance.headerTitleColor}
                onChange={(v) => updateAppearance({ headerTitleColor: v })} />
            </FieldRow>

            <SubTitle>头部自定义按钮</SubTitle>
            <FieldRow label="自定义按钮图片">
              <UploadArea value={appearance.headerCustomButtonImage}
                onChange={(v) => updateAppearance({ headerCustomButtonImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="自定义按钮链接">
              <TextInput width={360} value={appearance.headerCustomButtonUrl} placeholder="https://"
                onChange={(v) => updateAppearance({ headerCustomButtonUrl: v })} />
            </FieldRow>
            <FieldRow label="会员自定义按钮图片">
              <UploadArea value={appearance.headerMemberCustomButtonImage}
                onChange={(v) => updateAppearance({ headerMemberCustomButtonImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="会员自定义按钮链接">
              <TextInput width={360} value={appearance.headerMemberCustomButtonUrl} placeholder="https://"
                onChange={(v) => updateAppearance({ headerMemberCustomButtonUrl: v })} />
            </FieldRow>

            <Sep />

            {/* 历史消息区 — URL mode only */}
            {accessMode === 'url' && (
              <>
                <SubTitle>历史消息区</SubTitle>
                <ColorGrid items={[
                  { label: '背景色', value: appearance.historySidebarBgColor, onChange: (v) => updateAppearance({ historySidebarBgColor: v }) },
                  { label: '文字色', value: appearance.historySidebarTextColor, onChange: (v) => updateAppearance({ historySidebarTextColor: v }) },
                  { label: '选中背景色', value: appearance.historyItemActiveBgColor, onChange: (v) => updateAppearance({ historyItemActiveBgColor: v }) },
                  { label: '悬停背景色', value: appearance.historyItemHoverBgColor, onChange: (v) => updateAppearance({ historyItemHoverBgColor: v }) },
                ]} />
              </>
            )}

            {/* 消息区 */}
            <SubTitle>消息区</SubTitle>
            <FieldRow label="消息区背景色">
              <ColorSwatch value={appearance.messageAreaBgColor}
                onChange={(v) => updateAppearance({ messageAreaBgColor: v })} />
            </FieldRow>
            <FieldRow label="PC 无消息时图片">
              <UploadArea value={appearance.pcEmptyStateImage}
                onChange={(v) => updateAppearance({ pcEmptyStateImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="移动端无消息时图片">
              <UploadArea value={appearance.mobileEmptyStateImage}
                onChange={(v) => updateAppearance({ mobileEmptyStateImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="PC 会员无消息时图片">
              <UploadArea value={appearance.pcMemberEmptyStateImage}
                onChange={(v) => updateAppearance({ pcMemberEmptyStateImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>
            <FieldRow label="移动端会员无消息时图片">
              <UploadArea value={appearance.mobileMemberEmptyStateImage}
                onChange={(v) => updateAppearance({ mobileMemberEmptyStateImage: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>

            <Sep />

            {/* Input area and action buttons */}
            <SubTitle>输入区与发送/暂停按钮</SubTitle>
            <FieldRow label="输入框占位文案">
              <TextInput width={280} value={behavior.inputPlaceholder} placeholder="输入消息..."
                onChange={(v) => updateBehavior({ inputPlaceholder: v })} />
            </FieldRow>
            <FieldRow label="评价功能">
              <Switch
                checked={behavior.feedbackEnabled}
                onChange={(checked) => updateBehavior({ feedbackEnabled: checked })}
              />
              <span className="text-[13px] text-[#71717A]">
                开启后，访客可对 Agent 回复提交赞 / 踩和文字评价
              </span>
            </FieldRow>
            <ColorGrid items={[
              { label: '按钮背景色', value: appearance.sendMessageButtonBgColor, onChange: (v) => updateAppearance({ sendMessageButtonBgColor: v }) },
              { label: '按钮图标色', value: appearance.sendMessageButtonIconColor, onChange: (v) => updateAppearance({ sendMessageButtonIconColor: v }) },
              { label: '暂停按钮色', value: appearance.stopMessageButtonBgColor, onChange: (v) => updateAppearance({ stopMessageButtonBgColor: v }) },
            ]} />

            <Sep />

            {/* Agent message bubble */}
            <SubTitle>Agent 消息气泡</SubTitle>
            <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
              <ColorGridItem label="背景色" value={appearance.agentBubbleBgColor}
                onChange={(v) => updateAppearance({ agentBubbleBgColor: v })} />
              <ColorGridItem label="文字颜色" value={appearance.agentBubbleTextColor}
                onChange={(v) => updateAppearance({ agentBubbleTextColor: v })} />
              <ColorGridItem label="边框颜色" value={appearance.agentBubbleBorderColor}
                onChange={(v) => updateAppearance({ agentBubbleBorderColor: v })} />
              <RadiusInput value={appearance.agentBubbleRadius}
                onChange={(v) => updateAppearance({ agentBubbleRadius: v })} />
            </div>
            <FieldRow label="Agent 头像">
              <UploadArea value={appearance.agentAvatar}
                onChange={(v) => updateAppearance({ agentAvatar: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>

            <Sep />

            {/* 用户消息气泡 */}
            <SubTitle>用户消息气泡</SubTitle>
            <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
              <ColorGridItem label="背景色" value={appearance.userBubbleBgColor}
                onChange={(v) => updateAppearance({ userBubbleBgColor: v })} />
              <ColorGridItem label="文字颜色" value={appearance.userBubbleTextColor}
                onChange={(v) => updateAppearance({ userBubbleTextColor: v })} />
              <ColorGridItem label="边框颜色" value={appearance.userBubbleBorderColor}
                onChange={(v) => updateAppearance({ userBubbleBorderColor: v })} />
              <RadiusInput value={appearance.userBubbleRadius}
                onChange={(v) => updateAppearance({ userBubbleRadius: v })} />
            </div>
            <FieldRow label="用户头像">
              <UploadArea value={appearance.userAvatar}
                onChange={(v) => updateAppearance({ userAvatar: v })}
                onError={(msg) => toast(msg, 'error')} />
            </FieldRow>

            <Sep />

            {/* 嵌入按钮 — Embed mode only */}
            {accessMode === 'embed' && (
              <>
                <SubTitle>嵌入按钮</SubTitle>
                <ColorGrid items={[
                  { label: '按钮背景色', value: appearance.embedButtonBgColor, onChange: (v) => updateAppearance({ embedButtonBgColor: v }) },
                  { label: '按钮图标色', value: appearance.embedButtonIconColor, onChange: (v) => updateAppearance({ embedButtonIconColor: v }) },
                ]} />
              </>
            )}

            <Sep />

            {/* 侧栏底部（公司介绍与链接） */}
            <SubTitle>侧栏底部（公司介绍与链接）</SubTitle>
            <FieldRow label="侧栏底部 Logo">
              <MultiUploadArea
                values={appearance.sidebarFooterLogos}
                max={SIDEBAR_FOOTER_LOGO_MAX}
                onChange={(arr) => updateAppearance({ sidebarFooterLogos: arr })}
                onError={(msg) => toast(msg, 'error')}
              />
            </FieldRow>
            <FieldRow label="主说明">
              <TextInput width={360} value={appearance.sidebarFooterIntro}
                placeholder="例如：服务说明 / 公司一句话介绍"
                onChange={(v) => updateAppearance({ sidebarFooterIntro: v })} />
            </FieldRow>
            <FieldRow label="辅助说明">
              <TextInput width={360} value={appearance.sidebarFooterSubtext}
                placeholder="例如：官方微信可协助您解决使用疑问"
                onChange={(v) => updateAppearance({ sidebarFooterSubtext: v })} />
            </FieldRow>
            <FieldRow label="底部链接文字">
              <TextInput width={280} value={appearance.sidebarFooterLinkLabel}
                placeholder="例如：隐私政策"
                onChange={(v) => updateAppearance({ sidebarFooterLinkLabel: v })} />
            </FieldRow>
            <FieldRow label="底部链接 URL">
              <TextInput width={360} value={appearance.sidebarFooterLinkUrl}
                placeholder="https://..."
                onChange={(v) => updateAppearance({ sidebarFooterLinkUrl: v })} />
            </FieldRow>
          </SectionCard>

          {/* ── Section: 当前页面跳转 URL 白名单 ── */}
          <SectionCard>
            <SectionTitle>当前页面跳转 URL 白名单</SectionTitle>
            <p className="-mt-1 text-xs leading-relaxed text-[#71717A]">
              每行一条 URL 规则，支持 * 通配符。命中的链接将在当前页面打开；其它链接仍在新标签页打开。
            </p>
            <div className="flex max-w-[720px] flex-col gap-2">
              <label
                className="text-sm font-medium text-[#404040]"
                htmlFor="same-page-navigation-url-allowlist"
              >
                URL 规则
              </label>
              <textarea
                id="same-page-navigation-url-allowlist"
                className={`min-h-[112px] resize-y rounded-lg border bg-white px-3 py-2 font-mono text-sm text-[#18181B] outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A] ${
                  errors.samePageNavigationUrlAllowlist ? 'border-[#DC2626]' : 'border-[#E4E4E7]'
                }`}
                placeholder={[
                  'https://login.example.com/*',
                  'https://*.example.com/oauth/*',
                  'https://example.com/account/bind?redirect=*',
                ].join('\n')}
                value={samePageNavigationUrlAllowlistText}
                onChange={(e) => {
                  setSamePageNavigationUrlAllowlistText(e.target.value)
                  markDirty()
                  if (errors.samePageNavigationUrlAllowlist) {
                    setErrors((prev) => ({ ...prev, samePageNavigationUrlAllowlist: '' }))
                  }
                }}
                aria-invalid={Boolean(errors.samePageNavigationUrlAllowlist)}
                aria-describedby={
                  errors.samePageNavigationUrlAllowlist
                    ? 'same-page-navigation-url-allowlist-error'
                    : undefined
                }
              />
              {errors.samePageNavigationUrlAllowlist && (
                <span
                  id="same-page-navigation-url-allowlist-error"
                  className="text-xs text-[#DC2626]"
                >
                  {errors.samePageNavigationUrlAllowlist}
                </span>
              )}
            </div>
          </SectionCard>
        </div>
      </div>

      {/* Leave confirmation */}
      <Modal
        open={showLeaveModal}
        onClose={() => { setShowLeaveModal(false); setPendingLeave(false) }}
        title="离开此页？"
        footer={
          <>
            <Button variant="outline" onClick={() => { setShowLeaveModal(false); setPendingLeave(false) }}>
              留在页面
            </Button>
            <Button onClick={handleLeaveConfirm}>离开</Button>
          </>
        }
      >
        <p className="text-sm text-[#737373]">有未保存的修改，确定离开吗？</p>
      </Modal>
    </div>
  )
}

/* ────────── Helper components ────────── */

function SectionCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col gap-4 rounded-lg border border-[#E4E4E7] bg-white p-5 ${className}`}>
      {children}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-base font-semibold text-[#18181B]">{children}</h2>
}

function SubTitle({ children }: { children: React.ReactNode }) {
  return <span className="text-[13px] font-semibold text-[#71717A]">{children}</span>
}

function Sep() {
  return <div className="h-px w-full bg-[#F0F0F0]" />
}

function SegmentPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      className={`rounded-lg px-3 py-2 text-sm transition-colors ${
        active
          ? 'bg-[#1A1A1A] font-medium text-white'
          : 'border border-[#E4E4E7] bg-white text-[#525252] hover:bg-[#FAFAFA]'
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="text-sm font-medium text-[#404040]">{label}</span>
      {children}
    </div>
  )
}

function TextInput({ width, value, placeholder, onChange }: {
  width: number; value: string; placeholder?: string; onChange: (v: string) => void
}) {
  return (
    <input
      className="h-9 rounded-lg border border-[#E4E4E7] bg-white px-3 text-sm text-[#18181B] outline-none transition-colors placeholder:text-[#A1A1AA] focus:border-[#1A1A1A]"
      style={{ width }}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
  )
}

function UploadArea({ value, onChange, onError }: {
  value: string
  onChange: (url: string) => void
  onError?: (msg: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setUploading(true)
    try {
      const { url } = await uploadImage(file)
      onChange(url)
    } catch (err) {
      const msg = await getErrorMessage(err)
      onError?.(msg)
    } finally {
      setUploading(false)
    }
  }

  if (value) {
    return (
      <div className="group relative h-[72px] w-[72px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={value} alt="" className="h-[72px] w-[72px] rounded-lg border border-[#E4E4E7] object-cover" />
        <button
          className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#1A1A1A] text-white opacity-0 transition-opacity group-hover:opacity-100"
          onClick={() => onChange('')}
        >
          <IconX size={12} />
        </button>
      </div>
    )
  }

  return (
    <>
      <button
        className="flex h-[72px] w-[72px] items-center justify-center rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] transition-colors hover:border-[#A1A1AA]"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
      >
        {uploading
          ? <IconLoader2 size={24} className="animate-spin text-[#A1A1AA]" />
          : <IconImageInPicture size={24} className="text-[#A1A1AA]" />
        }
      </button>
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
    </>
  )
}

function MultiUploadArea({ values, max, onChange, onError }: {
  values: string[]
  max: number
  onChange: (arr: string[]) => void
  onError?: (msg: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const list = values || []
  const canAddMore = list.length < max

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setUploading(true)
    try {
      const { url } = await uploadImage(file)
      onChange([...list, url])
    } catch (err) {
      const msg = await getErrorMessage(err)
      onError?.(msg)
    } finally {
      setUploading(false)
    }
  }

  const removeAt = (idx: number) => {
    const next = list.slice()
    next.splice(idx, 1)
    onChange(next)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {list.map((url, idx) => (
        <div key={`${url}-${idx}`} className="group relative h-[72px] w-[72px]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt="" className="h-[72px] w-[72px] rounded-lg border border-[#E4E4E7] object-cover" />
          <button
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#1A1A1A] text-white opacity-0 transition-opacity group-hover:opacity-100"
            onClick={() => removeAt(idx)}
          >
            <IconX size={12} />
          </button>
        </div>
      ))}
      {canAddMore && (
        <>
          <button
            className="flex h-[72px] w-[72px] items-center justify-center rounded-lg border border-dashed border-[#E4E4E7] bg-[#FAFAFA] transition-colors hover:border-[#A1A1AA]"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
          >
            {uploading
              ? <IconLoader2 size={24} className="animate-spin text-[#A1A1AA]" />
              : <IconImageInPicture size={24} className="text-[#A1A1AA]" />
            }
          </button>
          <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
        </>
      )}
    </div>
  )
}

function ColorSwatch({ value, onChange, size = 40 }: {
  value: string; onChange: (v: string) => void; size?: number
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="relative">
      <button
        type="button"
        className="rounded-lg border border-[#E4E4E7]"
        style={{ width: size, height: size, backgroundColor: value || '#FFFFFF' }}
        onClick={() => inputRef.current?.click()}
      />
      <input
        ref={inputRef}
        type="color"
        className="invisible absolute left-0 top-0 h-0 w-0"
        value={value || '#000000'}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function ColorGridItem({ label, value, onChange }: {
  label: string; value: string; onChange: (v: string) => void
}) {
  return (
    <div className="flex w-[132px] flex-col gap-1">
      <span className="text-[13px] text-[#525252]">{label}</span>
      <ColorSwatch value={value} onChange={onChange} size={48} />
    </div>
  )
}

function ColorGrid({ items }: {
  items: { label: string; value: string; onChange: (v: string) => void }[]
}) {
  return (
    <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
      {items.map((item) => (
        <div key={item.label} className="flex w-[100px] flex-col gap-1">
          <span className="text-[13px] text-[#525252]">{item.label}</span>
          <ColorSwatch value={item.value} onChange={item.onChange} size={48} />
        </div>
      ))}
    </div>
  )
}

function RadiusInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const parts = (value || '20 20 20 20').split(' ')
  const [tl, tr, br, bl] = [
    parts[0] || '20', parts[1] || '20', parts[2] || '20', parts[3] || '20',
  ]

  const update = (idx: number, v: string) => {
    const p = [tl, tr, br, bl]
    p[idx] = v.replace(/\D/g, '')
    onChange(p.join(' '))
  }

  const cellCls = 'flex h-9 w-full items-center rounded-lg bg-[#F4F4F5] px-2.5 text-sm text-[#18181B] outline-none focus:ring-1 focus:ring-[#1A1A1A]'

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[13px] text-[#525252]">圆角</span>
      <div className="flex flex-col gap-0.5" style={{ width: 160 }}>
        <div className="flex gap-0.5">
          <input className={cellCls} value={tl} onChange={(e) => update(0, e.target.value)} />
          <input className={cellCls} value={tr} onChange={(e) => update(1, e.target.value)} />
        </div>
        <div className="flex gap-0.5">
          <input className={cellCls} value={bl} onChange={(e) => update(3, e.target.value)} />
          <input className={cellCls} value={br} onChange={(e) => update(2, e.target.value)} />
        </div>
      </div>
    </div>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      className="flex h-9 shrink-0 items-center justify-center rounded-lg border border-[#E4E4E7] bg-white px-3 text-[13px] font-medium text-[#18181B] transition-colors hover:bg-[#FAFAFA]"
      onClick={handleCopy}
    >
      {copied ? '已复制' : label}
    </button>
  )
}
