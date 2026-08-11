/**
 * useEmotionMonitor 情绪监控 hook（T1-3-4 搬移——React 19 适配）
 *
 * React 19 适配（design.md §2.1.3 D）：
 * - initialAgentId seed：渲染期 setState（React 官方模式——替代 effect 内 setState）
 * - useMemo 派生 selectedAgent（依赖数组用完整对象——R4-2 教训 #6）
 * - autoRefresh interval 保留在 useEffect（纯副作用——模式 4）
 */
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  getAgentEmotion,
  getAgentList,
  type AgentConfigInfo,
  type EmotionStateInfo,
} from '@/lib/agent-api'

export interface UseEmotionMonitorReturn {
  agents: AgentConfigInfo[]
  allEmotions: Record<string, EmotionStateInfo>
  selectedAgentId: string | null
  selectedAgent: AgentConfigInfo | undefined
  selectedEmotion: EmotionStateInfo | undefined
  viewMode: 'grid' | 'detail'
  autoRefresh: boolean
  isInitialLoading: boolean
  isRefreshing: boolean
  setSelectedAgentId: (id: string | null) => void
  setViewMode: (mode: 'grid' | 'detail') => void
  setAutoRefresh: (value: boolean) => void
  refresh: () => void
}

export function useEmotionMonitor(
  initialAgentId?: string
): UseEmotionMonitorReturn {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'grid' | 'detail'>('grid')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [seedState, setSeedState] = useState<{ id: string; done: boolean }>({ id: '', done: false })

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const agents = useMemo(() => agentsQuery.data ?? [], [agentsQuery.data])

  // 渲染期 seed（React 19 官方模式——替代 effect 内 setState）：initialAgentId 匹配时
  // 进入 detail 视图——仅首次 seed（seedState.done），用户后续手动切换不受影响
  if (initialAgentId && seedState.id !== initialAgentId && !seedState.done) {
    const found = agents.find((a) => a.agent_id === initialAgentId)
    if (found) {
      setSeedState({ id: initialAgentId, done: true })
      setSelectedAgentId(initialAgentId)
      setViewMode('detail')
    }
  }

  const allEmotionsQuery = useQuery({
    queryKey: ['agents', 'emotions', 'all'],
    queryFn: async () => {
      const agentList = await getAgentList()
      const results: Record<string, EmotionStateInfo> = {}
      await Promise.all(
        agentList.map(async (agent) => {
          try {
            results[agent.agent_id] = await getAgentEmotion(agent.agent_id)
          } catch {
            // skip failed
          }
        })
      )
      return results
    },
    enabled: !!agentsQuery.data,
  })

  const singleEmotionQuery = useQuery({
    queryKey: ['agents', 'emotion', selectedAgentId],
    queryFn: () => getAgentEmotion(selectedAgentId!),
    enabled: !!selectedAgentId && viewMode === 'detail',
  })

  const doRefresh = useCallback(() => {
    allEmotionsQuery.refetch()
    agentsQuery.refetch()
    if (viewMode === 'detail' && selectedAgentId) {
      singleEmotionQuery.refetch()
    }
  }, [allEmotionsQuery, agentsQuery, singleEmotionQuery, viewMode, selectedAgentId])

  // autoRefresh：30s 轮询 + 页面可见时刷新（纯副作用）
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(doRefresh, 30000)
    const onVisible = () => {
      if (document.visibilityState === 'visible') doRefresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [autoRefresh, doRefresh])

  const allEmotions = allEmotionsQuery.data ?? {}
  const selectedAgent = useMemo(
    () => agents.find((a) => a.agent_id === selectedAgentId),
    [agents, selectedAgentId]
  )

  return {
    agents,
    allEmotions,
    selectedAgentId,
    selectedAgent,
    selectedEmotion: singleEmotionQuery.data,
    viewMode,
    autoRefresh,
    isInitialLoading: agentsQuery.isLoading || allEmotionsQuery.isLoading,
    isRefreshing: agentsQuery.isFetching || allEmotionsQuery.isFetching,
    setSelectedAgentId,
    setViewMode,
    setAutoRefresh,
    refresh: doRefresh,
  }
}