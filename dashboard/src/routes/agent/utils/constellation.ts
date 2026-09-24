import type { AgentConfigInfo, BatchEmotionItem } from '@/lib/agent-api'
import type { ActivityStatus } from './vital-signs'

export type MentionLabel = 'close' | 'moderate' | 'distant'

export interface ConstellationNode {
  id: string
  displayName: string
  color: string
  isDefault: boolean
  activityStatus: ActivityStatus
  dominantEmotion: string
  dominantEmotionLabel: string
  emotionColor: string
}

export interface ConstellationEdge {
  id: string
  source: string
  target: string
  relationshipType: string
  attitude: string
  interactionStyle: string
  mentionTendency: number
  mentionLabel: MentionLabel
  color: string
  width: number
}

export interface ConstellationData {
  nodes: ConstellationNode[]
  edges: ConstellationEdge[]
}

import { EMOTION_COLORS } from './emotion-constants'
import { deriveActivityRhythmData } from './vital-signs'

const REL_TYPE_COLORS: Record<string, string> = {
  romantic: '#ef4444',
  family: '#f97316',
  mentor: '#3b82f6',
  friend: '#22c55e',
  rival: '#94a3b8',
}

function deriveMentionLabel(tendency: number): MentionLabel {
  if (tendency >= 0.7) return 'close'
  if (tendency >= 0.4) return 'moderate'
  return 'distant'
}

export function deriveConstellationData(
  agents: AgentConfigInfo[],
  emotions: Record<string, BatchEmotionItem>,
  sessionCounts: Record<string, number>,
): ConstellationData {
  const nodes: ConstellationNode[] = agents.map((agent) => {
    const emotion = emotions[agent.agent_id]
    const sessionCount = sessionCounts[agent.agent_id] ?? 0
    const activity = deriveActivityRhythmData(agent, sessionCount)
    return {
      id: agent.agent_id,
      displayName: agent.display_name,
      color: agent.color,
      isDefault: agent.is_default,
      activityStatus: activity.status,
      dominantEmotion: emotion?.dominant_emotion ?? 'calm',
      dominantEmotionLabel: emotion?.dominant_emotion_label ?? '平静',
      emotionColor: EMOTION_COLORS[emotion?.dominant_emotion ?? 'calm'] || '#9b59b6',
    }
  })

  const edges: ConstellationEdge[] = []
  const seen = new Set<string>()

  for (const agent of agents) {
    for (const rel of agent.internal_relationships) {
      const edgeKey = [agent.agent_id, rel.target_agent_id].sort().join('-')
      if (seen.has(edgeKey)) continue
      seen.add(edgeKey)

      const targetExists = agents.some((a) => a.agent_id === rel.target_agent_id)
      if (!targetExists) continue

      const mentionLabel = deriveMentionLabel(rel.mention_tendency)
      edges.push({
        id: edgeKey,
        source: agent.agent_id,
        target: rel.target_agent_id,
        relationshipType: rel.relationship_type,
        attitude: rel.attitude,
        interactionStyle: rel.interaction_style,
        mentionTendency: rel.mention_tendency,
        mentionLabel,
        color: REL_TYPE_COLORS[rel.relationship_type] || '#94a3b8',
        width: Math.round(rel.mention_tendency * 4 + 1),
      })
    }
  }

  return { nodes, edges }
}