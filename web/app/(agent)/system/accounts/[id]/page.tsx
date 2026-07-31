'use client'

import { use } from 'react'

import { AccountForm } from '@/app/components/features/account-form'

export default function EditAccountPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  return <AccountForm accountId={Number(id)} />
}
