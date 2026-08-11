/**
 * useDashboardData —— 仪表盘统计数据领域 hook（页面逻辑下沉）。
 *
 * useQuery 化（5min staleTime）——替代原版手写 Map 模块级缓存 + getCachedDashboardData/getStaleDashboardData。
 * 保留伪加载进度条 effect（独立 effect 与 useQuery loading 态解耦）。
 * fetchDashboardData 内部改 invalidateQueries，对外返回值结构不变。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'

import { backendApi } from '@/lib/http'

import { DEFAULT_TIME_RANGE, type DashboardData } from '../types'

export function useDashboardData() {
  const queryClient = useQueryClient()
  const [timeRange, setTimeRange] = useState(DEFAULT_TIME_RANGE)
  const [loadingProgress, setLoadingProgress] = useState(0)

  const { data: dashboardData, isLoading: loading } = useQuery<DashboardData>({
    queryKey: ['api', 'statistics', 'dashboard', { hours: timeRange }],
    queryFn: () => backendApi.get<DashboardData>('/api/webui/statistics/dashboard', {
      query: { hours: timeRange },
    }),
    staleTime: 5 * 60_000,
  })

  const fetchDashboardData = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['api', 'statistics', 'dashboard'] })
  }, [queryClient])

  // 伪加载进度条效果（与 useQuery loading 态解耦——独立 effect 驱动视觉进度）
  useEffect(() => {
    if (!loading) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 伪加载进度条：loading=false 时置 100%，spec §4.1 mode 7 明确要求
      setLoadingProgress(100)
      return
    }

    // 先归零，再逐级递增（用 0ms 定时器避免在 effect 同步体内 setState）
    const timer0 = setTimeout(() => setLoadingProgress(0), 0)
    const timer1 = setTimeout(() => setLoadingProgress(15), 200)
    const timer2 = setTimeout(() => setLoadingProgress(30), 800)
    const timer3 = setTimeout(() => setLoadingProgress(45), 2000)
    const timer4 = setTimeout(() => setLoadingProgress(60), 4000)
    const timer5 = setTimeout(() => setLoadingProgress(75), 6500)
    const timer6 = setTimeout(() => setLoadingProgress(85), 9000)
    const timer7 = setTimeout(() => setLoadingProgress(92), 11000)

    return () => {
      clearTimeout(timer0)
      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
      clearTimeout(timer4)
      clearTimeout(timer5)
      clearTimeout(timer6)
      clearTimeout(timer7)
    }
  }, [loading])

  return {
    dashboardData: dashboardData ?? null,
    loading,
    loadingProgress,
    timeRange,
    setTimeRange,
    fetchDashboardData,
  }
}