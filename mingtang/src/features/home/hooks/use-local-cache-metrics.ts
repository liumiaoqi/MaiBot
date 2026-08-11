/**
 * useLocalCacheMetrics —— 本地存储占用领域 hook（页面逻辑下沉）。
 *
 * useQuery 化（15min staleTime）——替代原版手写 let 模块级缓存 + getCachedLocalCacheStats。
 * fetchLocalCacheStats 内部改 invalidateQueries，对外返回值结构不变。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { getLocalCacheStats, type LocalCacheStats } from '@/lib/system-api'

const QUERY_KEY = ['api', 'system', 'local-cache-stats'] as const

export function useLocalCacheMetrics() {
  const queryClient = useQueryClient()
  const { data: localCacheStats, isLoading: isLocalCacheStatsLoading } = useQuery<LocalCacheStats>({
    queryKey: QUERY_KEY,
    queryFn: () => getLocalCacheStats(),
    staleTime: 15 * 60_000,
  })

  const fetchLocalCacheStats = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: QUERY_KEY })
  }, [queryClient])

  return {
    localCacheStats: localCacheStats ?? null,
    isLocalCacheStatsLoading,
    fetchLocalCacheStats,
  }
}