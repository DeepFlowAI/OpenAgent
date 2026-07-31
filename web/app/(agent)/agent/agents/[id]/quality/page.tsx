'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import { IconChevronLeft, IconChevronRight, IconSearch } from '@tabler/icons-react'
import { useConversation } from '@/service/use-conversation'
import { useConversationTimeline } from '@/service/use-conversation-step'
import { useQualityQueue, useSaveInspection, type InspectionTag } from '@/service/use-conversation-inspection'
import { MarkdownContent } from '@/app/components/features/chat-message-blocks'
import { SOURCE_OPTIONS } from '@/models/conversation'

const labels: Record<InspectionTag, string> = { good: 'Good', pass: '合格', bad: 'Bad' }

const tagButtonClasses: Record<InspectionTag, { idle: string; selected: string }> = {
  good: {
    idle: 'border-[#E5E5E5] bg-white text-[#737373] hover:border-[#059669] hover:bg-[#ECFDF5] hover:text-[#047857]',
    selected: 'border-[#059669] bg-[#059669] text-white hover:bg-[#047857] hover:text-[#D1FAE5]',
  },
  pass: {
    idle: 'border-[#E5E5E5] bg-white text-[#737373] hover:border-[#2563EB] hover:bg-[#EFF6FF] hover:text-[#1D4ED8]',
    selected: 'border-[#2563EB] bg-[#2563EB] text-white hover:bg-[#1D4ED8] hover:text-[#DBEAFE]',
  },
  bad: {
    idle: 'border-[#E5E5E5] bg-white text-[#737373] hover:border-[#DC2626] hover:bg-[#FEF2F2] hover:text-[#B91C1C]',
    selected: 'border-[#DC2626] bg-[#DC2626] text-white hover:bg-[#B91C1C] hover:text-[#FEE2E2]',
  },
}

export default function QualityPage() {
  const agentId = Number(useParams().id)
  const [filters, setFilters] = useState<Record<string, string>>({
    inspection_status: 'unfinished',
    start_time: '',
    end_time: '',
    source: '',
    channel_id: '',
    channel_source: '',
    message_content: '',
    conversation_id: '',
    external_user_id: '',
  })
  const queue = useQualityQueue(agentId, filters)
  const [index, setIndex] = useState(0)
  const current = queue.data?.items[index]
  const detail = useConversation(agentId, current?.id ?? 0)
  const timeline = useConversationTimeline(agentId, current?.id ?? 0)
  const save = useSaveInspection(agentId, current?.id ?? 0)
  const [selectedTags, setSelectedTags] = useState<Record<number, InspectionTag>>({})

  const selectTag = (stepId: number, tag: InspectionTag) => {
    const previousTag = selectedTags[stepId]
    setSelectedTags((tags) => ({ ...tags, [stepId]: tag }))
    save.mutate(
      { stepId, tag },
      {
        onError: () => setSelectedTags((tags) => {
          const nextTags = { ...tags }
          if (previousTag) nextTags[stepId] = previousTag
          else delete nextTags[stepId]
          return nextTags
        }),
      },
    )
  }

  return <main className="flex h-full flex-col bg-white">
    <header className="sticky top-0 z-10 flex items-center border-b border-[#ECECEC] bg-white/80 px-8 py-3 backdrop-blur-sm"><h1 className="text-base font-semibold text-[#18181B]">质检工作台</h1></header>
    <form className="flex flex-col gap-3 border-b border-[#E5E5E5] px-8 py-4" onSubmit={(event) => { event.preventDefault(); setIndex(0); queue.refetch() }}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">开始时间<input type="datetime-local" className="ml-2 h-10 rounded-lg border border-[#E5E5E5] px-3" value={filters.start_time} onChange={(e) => setFilters({ ...filters, start_time: e.target.value })} /></label>
        <label className="text-sm">结束时间<input type="datetime-local" className="ml-2 h-10 rounded-lg border border-[#E5E5E5] px-3" value={filters.end_time} onChange={(e) => setFilters({ ...filters, end_time: e.target.value })} /></label>
        <label className="text-sm">来源<select className="ml-2 h-10 rounded-lg border border-[#E5E5E5] px-3" value={filters.source} onChange={(e) => setFilters({ ...filters, source: e.target.value })}><option value="">全部</option>{SOURCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label className="text-sm">渠道 ID<input className="ml-2 h-10 w-32 rounded-lg border border-[#E5E5E5] px-3" value={filters.channel_id} onChange={(e) => setFilters({ ...filters, channel_id: e.target.value })} /></label>
        <label className="text-sm">质检状态<select className="ml-2 h-10 rounded-lg border border-[#E5E5E5] px-3" value={filters.inspection_status} onChange={(e) => setFilters({ ...filters, inspection_status: e.target.value })}><option value="unfinished">未完成</option><option value="pending">待质检</option><option value="in_progress">质检中</option><option value="completed">已质检</option></select></label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">渠道标识<input className="ml-2 h-10 w-40 rounded-lg border border-[#E5E5E5] px-3" value={filters.channel_source} onChange={(e) => setFilters({ ...filters, channel_source: e.target.value })} /></label>
        <label className="text-sm">会话 ID<input className="ml-2 h-10 w-44 rounded-lg border border-[#E5E5E5] px-3" value={filters.conversation_id} onChange={(e) => setFilters({ ...filters, conversation_id: e.target.value })} /></label>
        <label className="text-sm">用户 ID<input className="ml-2 h-10 w-40 rounded-lg border border-[#E5E5E5] px-3" value={filters.external_user_id} onChange={(e) => setFilters({ ...filters, external_user_id: e.target.value })} /></label>
        <label className="text-sm">聊天内容<input className="ml-2 h-10 w-56 rounded-lg border border-[#E5E5E5] px-3" value={filters.message_content} onChange={(e) => setFilters({ ...filters, message_content: e.target.value })} /></label>
        <button className="flex h-10 items-center gap-1 rounded-lg bg-[#1a1a1a] px-5 text-sm text-white"><IconSearch size={16}/>查询</button>
      </div>
    </form>
    {!current ? <div className="p-8 text-[#737373]">未找到符合条件的会话</div> : <>
      <nav className="flex items-center justify-between border-b border-[#E5E5E5] px-8 py-3"><span>共 {queue.data?.total} 个会话 · 第 {index + 1} / {queue.data?.total} 个 · <code>{current.external_id}</code></span><span className="flex gap-2"><button disabled={index === 0} onClick={() => setIndex(index - 1)} className="rounded-lg border px-3 py-2 disabled:opacity-40"><IconChevronLeft size={16}/></button><button disabled={index >= (queue.data?.items.length ?? 1) - 1} onClick={() => setIndex(index + 1)} className="rounded-lg bg-[#1a1a1a] px-3 py-2 text-white disabled:opacity-40"><IconChevronRight size={16}/></button></span></nav>
      <section className="grid grid-cols-4 gap-4 border-b border-[#E5E5E5] px-8 py-4 text-sm"><span>用户 ID：{detail.data?.external_user_id || '—'}</span><span>来源：{detail.data?.source || '—'}</span><span>轮次：{detail.data?.round_count ?? 0} 轮</span><span>质检进度：已标注 {current.inspected_count} / {current.assistant_reply_count} 条</span></section>
      <section className="flex-1 overflow-auto px-8 py-6"><div className="mx-auto flex max-w-4xl flex-col gap-5">{timeline.data?.steps.filter((step) => step.step_type === 'user_message' || step.step_type === 'assistant_message').map((step) => <article key={step.id} className={step.step_type === 'assistant_message' ? 'ml-16' : 'mr-16'}><div className={step.step_type === 'assistant_message' ? 'rounded-lg bg-[#F5F5F5] p-4' : 'rounded-lg bg-[#FAFAFA] p-4'}><MarkdownContent source={step.content || ''}/></div>{step.step_type === 'assistant_message' && <div className="mt-2 flex gap-2">{(['good', 'pass', 'bad'] as InspectionTag[]).map((tag) => <button key={tag} type="button" disabled={save.isPending} aria-pressed={selectedTags[step.id] === tag} onClick={() => selectTag(step.id, tag)} className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${tagButtonClasses[tag][selectedTags[step.id] === tag ? 'selected' : 'idle']}`}>{labels[tag]}</button>)}</div>}</article>)}</div></section>
    </>}
  </main>
}
