import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

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

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const agents = agentsQuery.data ?? []

  useEffect(() => {
    if (!initialAgentId) return
    const found = agents.find((a) => a.agent_id === initialAgentId)
    if (found) {
      setSelectedAgentId(initialAgentId)
    }
  }, [initialAgentId, agents])

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

  const allRelationships = allRelationshipsQuery.data ?? {}
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
    isRefreshing: agentsQuery.isFetching || agentsQuery.isFetching,
    setSelectedAgentId,
    refresh,
  }
}