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
  type InternalRelationshipSummaryItem,
} from '@/lib/agent-api'

export interface BatchAgentData {
  agents: AgentConfigInfo[]
  emotions: Record<string, BatchEmotionItem>
  relationships: Record<string, BatchRelationshipItem[]>
  internalRelationshipsSummary: Record<string, InternalRelationshipSummaryItem[]>
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
      const [agents, emotions, relResult, sessionCounts, latestSubAgentRecords] = await Promise.all([
        getAgentList(),
        getBatchEmotions().catch(() => ({} as Record<string, BatchEmotionItem>)),
        getBatchRelationships().catch(() => ({ data: {}, internal_relationships_summary: {} } as { data: Record<string, BatchRelationshipItem[]>; internal_relationships_summary: Record<string, InternalRelationshipSummaryItem[]> })),
        getBatchSessionCounts().catch(() => ({} as Record<string, number>)),
        getBatchLatestSubAgentRecords().catch(() => ({} as Record<string, BatchLatestSubAgentItem | null>)),
      ])
      const relationships = relResult.data ?? {}
      const internalRelationshipsSummary = relResult.internal_relationships_summary ?? {}
      return { agents, emotions, relationships, internalRelationshipsSummary, sessionCounts, latestSubAgentRecords }
    },
  })

  const data = agentsQuery.data

  return {
    agents: data?.agents ?? [],
    emotions: data?.emotions ?? {},
    relationships: data?.relationships ?? {},
    internalRelationshipsSummary: data?.internalRelationshipsSummary ?? {},
    sessionCounts: data?.sessionCounts ?? {},
    latestSubAgentRecords: data?.latestSubAgentRecords ?? {},
    isLoading: agentsQuery.isLoading,
    error: agentsQuery.error,
    refetch: () => agentsQuery.refetch(),
  }
}