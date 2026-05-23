'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { Button } from '@/app/components/base/button'
import { ServiceHoursForm } from '@/app/components/features/service-hours-form'
import { useServiceHours } from '@/service/use-service-hours'

export default function EditServiceHoursPage() {
  const params = useParams<{ id: string }>()
  const id = Number(params?.id)
  const validId = Number.isFinite(id) ? id : null
  const { data, isLoading, isError } = useServiceHours(validId)

  if (isError || (!isLoading && !data)) {
    return (
      <div className="px-12 py-10">
        <p className="text-sm text-[#737373]">加载失败或不存在。</p>
        <Link href="/system/service-hours">
          <Button variant="outline" size="sm" className="mt-4">
            返回列表
          </Button>
        </Link>
      </div>
    )
  }

  return <ServiceHoursForm mode="edit" serviceHours={data} loading={isLoading} />
}
