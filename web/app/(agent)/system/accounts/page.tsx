import { Suspense } from 'react'

import { AccountList } from '@/app/components/features/account-list'

export default function AccountsPage() {
  return (
    <Suspense>
      <AccountList />
    </Suspense>
  )
}
