/**
 * useBotStatus —— 机器人运行状态领域 hook（页面逻辑下沉）。
 *
 * useQuery 化（30s staleTime + refetchInterval + refetchOnWindowFocus）
 * ——替代原版手写 let 模块级缓存 + setInterval 轮询 + addEventListener visibilitychange/focus。
 * TanStack Query 内置轮询 + 可见性刷新，fetchBotStatus 内部改 invalidateQueries。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { backendApi } from '@/lib/http'

import type { BotStatus } from '../types'

const QUERY_KEY = ['api', 'system', 'status'] as const

export function useBotStatus() {
  const queryClient = useQueryClient()
  const { data: botStatus, isLoading: isBotStatusLoading } = useQuery<BotStatus>({
    queryKey: QUERY_KEY,
    queryFn: () => backendApi.get<BotStatus>('/api/webui/system/status'),
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })

  const fetchBotStatus = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: QUERY_KEY })
  }, [queryClient])

  return {
    botStatus: botStatus ?? null,
    isBotStatusLoading,
    fetchBotStatus,
  }
}