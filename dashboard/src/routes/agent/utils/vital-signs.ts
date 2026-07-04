export type ActivityStatus = 'active' | 'quiet' | 'dormant'

export type WarmthLevel = 'warm' | 'moderate' | 'cold' | 'unavailable'

export type InnerActivityStatus = 'introspecting' | 'quiet' | 'unavailable'

export interface EmotionPulseData {
  dominantEmotion: string
  dominantEmotionLabel: string
  intensity: number
  color: string
}

export interface ActivityRhythmData {
  status: ActivityStatus
  sessionCount: number
}

export interface RelationshipWarmthData {
  warmth: WarmthLevel
  relationshipCount: number
  highestLevel: number
}

export interface InnerActivityData {
  status: InnerActivityStatus
  latestType: string | null
  latestSummary: string | null
}

export interface VitalSignsData {
  agentId: string
  displayName: string
  color: string
  isDefault: boolean
  emotionPulse: EmotionPulseData | null
  activityRhythm: ActivityRhythmData
  relationshipWarmth: RelationshipWarmthData
  innerActivity: InnerActivityData
}

import type { AgentConfigInfo, BatchEmotionItem, BatchRelationshipItem, BatchLatestSubAgentItem } from '@/lib/agent-api'
import { EMOTION_COLORS } from './emotion-constants'

export function deriveEmotionPulseData(
  emotion: BatchEmotionItem | undefined | null,
): EmotionPulseData | null {
  if (!emotion) return null
  const intensity = Math.max(...Object.values(emotion.emotions), 0)
  return {
    dominantEmotion: emotion.dominant_emotion,
    dominantEmotionLabel: emotion.dominant_emotion_label,
    intensity,
    color: EMOTION_COLORS[emotion.dominant_emotion] || '#9b59b6',
  }
}

export function deriveActivityRhythmData(
  agent: AgentConfigInfo,
  sessionCount: number,
): ActivityRhythmData {
  if (sessionCount > 0 && agent.talk_value_modifier > 1.0) {
    return { status: 'active', sessionCount }
  }
  if (sessionCount > 0 && agent.talk_value_modifier >= 0.5) {
    return { status: 'quiet', sessionCount }
  }
  return { status: 'dormant', sessionCount }
}

export function deriveRelationshipWarmthData(
  relationships: BatchRelationshipItem[] | undefined | null,
): RelationshipWarmthData {
  if (!relationships || relationships.length === 0) {
    return { warmth: 'unavailable', relationshipCount: 0, highestLevel: 0 }
  }
  const highestLevel = Math.max(...relationships.map((r) => r.level))
  let warmth: WarmthLevel
  if (highestLevel >= 3) {
    warmth = 'warm'
  } else if (highestLevel >= 2) {
    warmth = 'moderate'
  } else if (highestLevel >= 1) {
    warmth = 'cold'
  } else {
    warmth = 'unavailable'
  }
  return { warmth, relationshipCount: relationships.length, highestLevel }
}

export function deriveInnerActivityData(
  latestRecord: BatchLatestSubAgentItem | null | undefined,
): InnerActivityData {
  if (!latestRecord) {
    return { status: 'unavailable', latestType: null, latestSummary: null }
  }
  if (latestRecord.completed_at) {
    const completedTime = new Date(latestRecord.completed_at).getTime()
    const oneHourAgo = Date.now() - 60 * 60 * 1000
    if (completedTime > oneHourAgo) {
      return {
        status: 'introspecting',
        latestType: latestRecord.subagent_type,
        latestSummary: latestRecord.result_summary,
      }
    }
  }
  return {
    status: 'quiet',
    latestType: latestRecord.subagent_type,
    latestSummary: latestRecord.result_summary,
  }
}

export function deriveVitalSignsData(
  agent: AgentConfigInfo,
  emotion: BatchEmotionItem | undefined | null,
  relationships: BatchRelationshipItem[] | undefined | null,
  sessionCount: number,
  latestRecord: BatchLatestSubAgentItem | null | undefined,
): VitalSignsData {
  return {
    agentId: agent.agent_id,
    displayName: agent.display_name,
    color: agent.color,
    isDefault: agent.is_default,
    emotionPulse: deriveEmotionPulseData(emotion),
    activityRhythm: deriveActivityRhythmData(agent, sessionCount),
    relationshipWarmth: deriveRelationshipWarmthData(relationships),
    innerActivity: deriveInnerActivityData(latestRecord),
  }
}