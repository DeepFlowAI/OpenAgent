import { useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type { SystemInfo } from '@/models/system'

/** Fetch deployment-time info (edition, single-tenant mode, defaults).
 *  Cached for the life of the page — doesn't change during a session. */
export const useSystemInfo = () =>
  useQuery({
    queryKey: ['system', 'info'],
    queryFn: () => get<SystemInfo>('v1/system/info'),
    staleTime: Infinity,
    retry: 1,
  })
