'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTenants, useUpdateTenantStatus } from '@/service/use-tenant'
import { Button } from '@/app/components/base/button'
import { Badge } from '@/app/components/base/badge'
import { ConfirmModal } from '@/app/components/base/modal'
import { useToast } from '@/app/components/base/toast'
import { IconPlus, IconPencil, IconBan, IconCircleCheck } from '@tabler/icons-react'
import type { Tenant } from '@/models/tenant'

export default function TenantsPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useTenants({ page, per_page: 20 })
  const statusMutation = useUpdateTenantStatus()
  const { toast } = useToast()

  const [statusModal, setStatusModal] = useState<{
    open: boolean
    tenant: Tenant | null
    targetStatus: 'enabled' | 'disabled'
  }>({ open: false, tenant: null, targetStatus: 'enabled' })

  const handleToggleStatus = (tenant: Tenant) => {
    const target = tenant.status === 'enabled' ? 'disabled' : 'enabled'
    setStatusModal({ open: true, tenant, targetStatus: target })
  }

  const confirmToggleStatus = async () => {
    if (!statusModal.tenant) return
    try {
      await statusMutation.mutateAsync({
        id: statusModal.tenant.id,
        data: { status: statusModal.targetStatus },
      })
      toast(
        statusModal.targetStatus === 'enabled'
          ? `租户「${statusModal.tenant.name}」已启用`
          : `租户「${statusModal.tenant.name}」已停用`
      )
      setStatusModal({ open: false, tenant: null, targetStatus: 'enabled' })
    } catch {
      toast('操作失败，请重试', 'error')
    }
  }

  const isDisabling = statusModal.targetStatus === 'disabled'

  return (
    <div className="flex h-full flex-col gap-6 p-8 px-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight text-[#1a1a1a]">
          租户管理
        </h1>
        <Link href="/admin/tenants/new">
          <Button>
            <IconPlus size={16} className="mr-2" />
            新建租户
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="flex flex-1 items-center justify-center text-[#737373]">
          加载中...
        </div>
      ) : !data?.items.length ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-[#737373]">
          <p>暂无租户，创建第一个租户开始使用</p>
          <Link href="/admin/tenants/new">
            <Button>
              <IconPlus size={16} className="mr-2" />
              新建租户
            </Button>
          </Link>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-[#E5E5E5]">
            <table className="w-full">
              <thead>
                <tr className="h-14 bg-[#F8F8F8]">
                  <th className="px-6 text-left text-sm font-semibold text-[#404040]">
                    租户名称
                  </th>
                  <th className="w-[110px] px-6 text-left text-sm font-semibold text-[#404040]">
                    租户 ID
                  </th>
                  <th className="w-[140px] px-6 text-left text-sm font-semibold text-[#404040]">
                    租户别名
                  </th>
                  <th className="px-6 text-left text-sm font-semibold text-[#404040]">
                    备注
                  </th>
                  <th className="w-[100px] px-6 text-left text-sm font-semibold text-[#404040]">
                    状态
                  </th>
                  <th className="w-[140px] px-6 text-left text-sm font-semibold text-[#404040]">
                    创建时间
                  </th>
                  <th className="w-[90px] px-6 text-left text-sm font-semibold text-[#404040]">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((tenant) => (
                  <tr
                    key={tenant.id}
                    className="h-14 border-b border-[#E5E5E5] last:border-b-0"
                  >
                    <td className="px-6 text-sm text-[#1a1a1a]">
                      {tenant.name}
                    </td>
                    <td className="px-6 font-mono text-[13px] text-[#737373]">
                      {tenant.id}
                    </td>
                    <td className="max-w-[160px] truncate px-6 font-mono text-[13px] text-[#737373]">
                      {tenant.slug || '—'}
                    </td>
                    <td className="max-w-[200px] truncate px-6 text-sm text-[#737373]">
                      {tenant.remark || '—'}
                    </td>
                    <td className="px-6">
                      <Badge
                        variant={
                          tenant.status === 'enabled' ? 'success' : 'danger'
                        }
                      >
                        {tenant.status === 'enabled' ? '启用' : '停用'}
                      </Badge>
                    </td>
                    <td className="px-6 text-[13px] text-[#737373]">
                      {tenant.created_at
                        ? new Date(tenant.created_at).toLocaleDateString('zh-CN')
                        : '—'}
                    </td>
                    <td className="px-6">
                      <div className="flex items-center gap-3">
                        <Link
                          href={`/admin/tenants/${tenant.id}`}
                          className="text-[#404040] transition-colors hover:text-[#1a1a1a]"
                        >
                          <IconPencil size={18} />
                        </Link>
                        <button
                          onClick={() => handleToggleStatus(tenant)}
                          className="text-[#404040] transition-colors hover:text-[#1a1a1a]"
                        >
                          {tenant.status === 'enabled' ? (
                            <IconBan size={18} />
                          ) : (
                            <IconCircleCheck size={18} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span className="text-sm text-[#737373]">
                {page} / {data.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </>
      )}

      <ConfirmModal
        open={statusModal.open}
        onClose={() =>
          setStatusModal({ open: false, tenant: null, targetStatus: 'enabled' })
        }
        onConfirm={confirmToggleStatus}
        title={isDisabling ? '停用租户' : '启用租户'}
        description={
          isDisabling
            ? `停用后，该租户下所有账号将无法登录。确定停用租户「${statusModal.tenant?.name}」？`
            : `确定启用租户「${statusModal.tenant?.name}」？启用后该租户下账号可正常登录。`
        }
        confirmText={isDisabling ? '确定停用' : '确定启用'}
        variant={isDisabling ? 'destructive' : 'default'}
        loading={statusMutation.isPending}
      />
    </div>
  )
}
