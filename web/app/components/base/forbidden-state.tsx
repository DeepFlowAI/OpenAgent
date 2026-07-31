'use client'

import Link from 'next/link'
import { IconLock } from '@tabler/icons-react'

import { Button } from '@/app/components/base/button'
import { useAppLanguage } from '@/utils/use-app-language'

type ForbiddenStateProps = {
  returnHref: string
  returnLabel: string
  returnLabelEn?: string
}

export function ForbiddenState({
  returnHref,
  returnLabel,
  returnLabelEn,
}: ForbiddenStateProps) {
  const language = useAppLanguage()
  const title =
    language === 'en'
      ? 'You do not have permission to access this content'
      : '你没有权限访问此内容'
  const description =
    language === 'en'
      ? 'Return to content you can access, or contact an administrator.'
      : '请返回可访问的内容，或联系管理员调整权限。'

  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center px-8 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <IconLock size={22} aria-hidden />
      </div>
      <h1 className="text-lg font-semibold text-foreground">
        {title}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {description}
      </p>
      <Link href={returnHref} className="mt-5">
        <Button variant="outline">
          {language === 'en' ? returnLabelEn ?? returnLabel : returnLabel}
        </Button>
      </Link>
    </div>
  )
}
