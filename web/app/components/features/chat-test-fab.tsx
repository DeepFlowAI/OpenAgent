'use client'

import { IconMessage } from '@tabler/icons-react'

type ChatTestFabProps = {
  onClick: () => void
}

export function ChatTestFab({ onClick }: ChatTestFabProps) {
  return (
    <button
      onClick={onClick}
      className="fixed bottom-8 right-8 z-30 flex h-[50px] w-[50px] items-center justify-center rounded-full bg-[#1A1A1A] text-white shadow-[0_4px_16px_rgba(0,0,0,0.2)] transition-transform hover:scale-105 active:scale-95"
      aria-label="对话测试"
    >
      <IconMessage size={20} />
    </button>
  )
}
