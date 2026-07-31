'use client'

import { useEffect, useState } from 'react'

export type AppLanguage = 'zh' | 'en'

export function useAppLanguage(): AppLanguage {
  const [language, setLanguage] = useState<AppLanguage>('zh')

  useEffect(() => {
    const locale = document.documentElement.lang || navigator.language
    setLanguage(locale.toLowerCase().startsWith('en') ? 'en' : 'zh')
  }, [])

  return language
}
