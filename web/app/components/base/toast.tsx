'use client'

import { useState, useEffect, useCallback, createContext, useContext, type ReactNode } from 'react'
import { cn } from '@/utils/classnames'

type ToastType = 'success' | 'error' | 'info'

type ToastItem = {
  id: number
  message: string
  type: ToastType
}

type ToastContextType = {
  toast: (message: string, type?: ToastType) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

let toastId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const toast = useCallback((message: string, type: ToastType = 'success') => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, type }])
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed right-4 top-4 z-[100] flex flex-col gap-2">
        {toasts.map((t) => (
          <ToastMessage key={t.id} item={t} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastMessage({ item, onRemove }: { item: ToastItem; onRemove: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onRemove(item.id), 3000)
    return () => clearTimeout(timer)
  }, [item.id, onRemove])

  return (
    <div
      className={cn(
        'animate-in slide-in-from-right-full rounded-lg px-4 py-3 text-sm font-medium text-white shadow-lg',
        item.type === 'success' && 'bg-emerald-600',
        item.type === 'error' && 'bg-red-600',
        item.type === 'info' && 'bg-primary'
      )}
    >
      {item.message}
    </div>
  )
}
