import { useQuery } from '@tanstack/react-query'

import {
  getAgentList,
  getBatchEmotions,
  getBatchRelationships,
  getBatchSessionCounts,
  getBatchLatestSubAgentRecords,
  type AgentConfigInfo,
  type BatchEmotionItem,
  type BatchRelationshipItem,
  type BatchLatestSubAgentItem,
} from '@/lib/agent-api'

export interface BatchAgentData {
  agents: AgentConfigInfo[]
  emotions: Record<string, BatchEmotionItem>
  relationships: Record<string, BatchRelationshipItem[]>
  sessionCounts: Record<string, number>
  latestSubAgentRecords: Record<string, BatchLatestSubAgentItem | null>
  isLoading: boolean
  error: Error | null
  refetch: () => void
}

export function useBatchAgentData(): BatchAgentData {
  const agentsQuery = useQuery({
    queryKey: ['agents', 'batch', 'overview'],
    queryFn: async () => {
      const [agents, emotions, relationships, sessionCounts, latestSubAgentRecords] = await Promise.all([
        getAgentList(),
        getBatchEmotions().catch(() => ({} as Record<string, BatchEmotionItem>)),
        getBatchRelationships().catch(() => ({} as Record<string, BatchRelationshipItem[]>)),
        getBatchSessionCounts().catch(() => ({} as Record<string, number>)),
        getBatchLatestSubAgentRecords().catch(() => ({} as Record<string, BatchLatestSubAgentItem | null>)),
      ])
      return { agents, emotions, relationships, sessionCounts, latestSubAgentRecords }
    },
  })

  const data = agentsQuery.data

  return {
    agents: data?.agents ?? [],
    emotions: data?.emotions ?? {},
    relationships: data?.relationships ?? {},
    sessionCounts: data?.sessionCounts ?? {},
    latestSubAgentRecords: data?.latestSubAgentRecords ?? {},
    isLoading: agentsQuery.isLoading,
    error: agentsQuery.error,
    refetch: () => agentsQuery.refetch(),
  }
}