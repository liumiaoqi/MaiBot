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

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const agents = agentsQuery.data ?? []

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

  useEffect(() => {
    if (!initialAgentId) return
    const found = agents.find((a) => a.agent_id === initialAgentId)
    if (found) {
      setSelectedAgentId(initialAgentId)
      setViewMode('detail')
    }
  }, [initialAgentId, agents])

  const doRefresh = useCallback(() => {
    allEmotionsQuery.refetch()
    agentsQuery.refetch()
    if (viewMode === 'detail' && selectedAgentId) {
      singleEmotionQuery.refetch()
    }
  }, [allEmotionsQuery, agentsQuery, singleEmotionQuery, viewMode, selectedAgentId])

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