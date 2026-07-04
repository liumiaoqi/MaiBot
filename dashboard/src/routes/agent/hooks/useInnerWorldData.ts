import { useQuery } from '@tanstack/react-query'

import {
  getAgentDetail,
  getAgentEmotion,
  getAgentRelationships,
  getEmotionBehaviorRules,
  getSessionsByAgent,
  getSubAgentRecords,
  type AgentConfigInfo,
  type EmotionStateInfo,
  type RelationshipInfo,
  type SessionAgentInfo,
  type SubAgentRecord,
  type EmotionBehaviorRule,
} from '@/lib/agent-api'

export interface InnerWorldData {
  agent: AgentConfigInfo | null
  emotion: EmotionStateInfo | null
  relationships: RelationshipInfo[]
  sessions: SessionAgentInfo[]
  subAgentRecords: SubAgentRecord[]
  emotionBehaviorRules: EmotionBehaviorRule[]
  isLoading: boolean
  error: Error | null
}

export function useInnerWorldData(agentId: string | null) {
  const enabled = !!agentId

  const agentQuery = useQuery({
    queryKey: ['agents', 'detail', agentId],
    queryFn: () => getAgentDetail(agentId!),
    enabled,
  })

  const emotionQuery = useQuery({
    queryKey: ['agents', 'emotion', agentId],
    queryFn: () => getAgentEmotion(agentId!),
    enabled,
  })

  const relationshipQuery = useQuery({
    queryKey: ['agents', 'relationships', agentId],
    queryFn: () => getAgentRelationships(agentId!),
    enabled,
  })

  const sessionsQuery = useQuery({
    queryKey: ['agents', 'sessions', agentId],
    queryFn: () => getSessionsByAgent(agentId!),
    enabled,
  })

  const subAgentQuery = useQuery({
    queryKey: ['agents', 'subagent', agentId],
    queryFn: () => getSubAgentRecords({ agent_id: agentId!, limit: 10 }),
    enabled,
  })

  const behaviorRulesQuery = useQuery({
    queryKey: ['agents', 'emotion-behavior-rules', agentId],
    queryFn: () => getEmotionBehaviorRules(agentId!),
    enabled,
  })

  const isLoading = agentQuery.isLoading || emotionQuery.isLoading

  return {
    agent: agentQuery.data ?? null,
    emotion: emotionQuery.data ?? null,
    relationships: relationshipQuery.data ?? [],
    sessions: sessionsQuery.data ?? [],
    subAgentRecords: subAgentQuery.data ?? [],
    emotionBehaviorRules: behaviorRulesQuery.data ?? [],
    isLoading,
    error: agentQuery.error ?? emotionQuery.error,
  }
}