/**
 * useDashboardData —— 仪表盘统计数据领域 hook（页面逻辑下沉）。
 *
 * useQuery 化（5min staleTime + refetchOnWindowFocus）——替代原版手写 Map 模块级缓存
 * + getCachedDashboardData/getStaleDashboardData。统一走 useApiQuery 包装。
 *
 * P2 清理：伪加载进度条（loadingProgress 8 级 setTimeout effect）已删除——
 * 无任何 UI 消费（home-page 只解构 dashboardData），与 useQuery loading 态解耦的
 * 视觉进度无意义；loading 直接暴露 useQuery 的 loading。
 *
 * force 契约简化说明（P2）：design §2.2.2.2 承诺 fetchDashboardData(force?: boolean)——
 * invalidateQueries 对 active 查询总是重新拉取（即 force=true 语义），且当前无消费者传 force，
 * 故保持无参形式（fetchDashboardData = refresh），对外返回值结构不变。
 */
import { useState } from 'react'

import { backendApi } from '@/lib/http'

import { useApiQuery } from './use-api-query'
import { DEFAULT_TIME_RANGE, type DashboardData } from '../types'

export function useDashboardData() {
  const [timeRange, setTimeRange] = useState(DEFAULT_TIME_RANGE)

  const { data, loading, refresh } = useApiQuery<DashboardData>(
    ['api', 'statistics', 'dashboard', { hours: timeRange }],
    () =>
      backendApi.get<DashboardData>('/api/webui/statistics/dashboard', {
        query: { hours: timeRange },
      }),
    {
      staleTime: 5 * 60_000,
      refetchOnWindowFocus: true,
    },
  )

  return {
    dashboardData: data ?? null,
    loading,
    timeRange,
    setTimeRange,
    fetchDashboardData: refresh,
  }
}
