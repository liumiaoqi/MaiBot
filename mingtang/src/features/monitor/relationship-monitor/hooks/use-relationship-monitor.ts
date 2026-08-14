/**
 * useRelationshipMonitor 关系监控 hook（T1-4-4 搬移——React 19 适配）
 *
 * React 19 适配（design.md §2.1.3 D）：
 * - initialAgentId seed：渲染期 setState（React 官方模式——替代 effect 内 setState）
 * - agents 用 useMemo 缓存（完整对象依赖——R4-2 教训 #6）
 * - useMemo 派生 selectedAgent / totalRelationships
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import {
  getAgentList,
  getAgentRelationships,
  type AgentConfigInfo,
  type RelationshipInfo,
} from '@/lib/agent-api'

export interface UseRelationshipMonitorReturn {
  agents: AgentConfigInfo[]
  allRelationships: Record<string, RelationshipInfo[]>
  selectedAgentId: string | null
  selectedAgent: AgentConfigInfo | undefined
  selectedRelationships: RelationshipInfo[]
  totalRelationships: number
  isInitialLoading: boolean
  isRefreshing: boolean
  setSelectedAgentId: (id: string | null) => void
  refresh: () => void
}

export function useRelationshipMonitor(
  initialAgentId?: string
): UseRelationshipMonitorReturn {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [seedState, setSeedState] = useState<{ id: string; done: boolean }>({ id: '', done: false })

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const agents = useMemo(() => agentsQuery.data ?? [], [agentsQuery.data])

  // 渲染期 seed（React 19 官方模式——替代 effect 内 setState）：initialAgentId 匹配时
  // 选中对应智能体——仅首次 seed（seedState.done），用户后续手动切换不受影响
  if (initialAgentId && seedState.id !== initialAgentId && !seedState.done) {
    const found = agents.find((a) => a.agent_id === initialAgentId)
    if (found) {
      setSeedState({ id: initialAgentId, done: true })
      setSelectedAgentId(initialAgentId)
    }
  }

  const allRelationshipsQuery = useQuery({
    queryKey: ['agents', 'relationships', 'all'],
    queryFn: async () => {
      const agentList = await getAgentList()
      const results: Record<string, RelationshipInfo[]> = {}
      await Promise.all(
        agentList.map(async (agent) => {
          try {
            results[agent.agent_id] = await getAgentRelationships(agent.agent_id)
          } catch {
            results[agent.agent_id] = []
          }
        })
      )
      return results
    },
    enabled: !!agentsQuery.data,
  })

  const selectedRelationshipQuery = useQuery({
    queryKey: ['agents', 'relationships', selectedAgentId],
    queryFn: () => getAgentRelationships(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const allRelationships = useMemo(
    () => allRelationshipsQuery.data ?? {},
    [allRelationshipsQuery.data]
  )
  const selectedAgent = useMemo(
    () => agents.find((a) => a.agent_id === selectedAgentId),
    [agents, selectedAgentId]
  )
  const selectedRelationships = selectedRelationshipQuery.data ?? []
  const totalRelationships = useMemo(
    () => Object.values(allRelationships).reduce((sum, rels) => sum + rels.length, 0),
    [allRelationships]
  )

  const refresh = () => {
    allRelationshipsQuery.refetch()
    agentsQuery.refetch()
  }

  return {
    agents,
    allRelationships,
    selectedAgentId,
    selectedAgent,
    selectedRelationships,
    totalRelationships,
    isInitialLoading: agentsQuery.isLoading || allRelationshipsQuery.isLoading,
    isRefreshing: agentsQuery.isFetching || allRelationshipsQuery.isFetching,
    setSelectedAgentId,
    refresh,
  }
}