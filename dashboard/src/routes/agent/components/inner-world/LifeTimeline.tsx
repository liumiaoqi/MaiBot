import { useTranslation } from 'react-i18next'

import type { RelationshipInfo, SubAgentRecord } from '@/lib/agent-api'
import type { EmotionStateInfo } from '@/lib/agent-api'

interface LifeTimelineProps {
  emotion: EmotionStateInfo | null
  relationships: RelationshipInfo[]
  subAgentRecords: SubAgentRecord[]
}

interface TimelineEvent {
  type: 'emotion_shift' | 'relationship_breakthrough' | 'memory_milestone'
  timestamp: string
  description: string
  icon: string
}

export function LifeTimeline({ emotion, relationships, subAgentRecords }: LifeTimelineProps) {
  const { t } = useTranslation()

  const events: TimelineEvent[] = []

  if (emotion) {
    events.push({
      type: 'emotion_shift',
      timestamp: 'current',
      description: t('agent.lifeTimeline.emotionShift', { emotion: emotion.dominant_emotion_label }),
      icon: '💫',
    })
  }

  const nearBreakthrough = relationships.filter((r) => {
    if (r.level === 0 && r.score >= 300) return true
    if (r.level === 1 && r.score >= 600) return true
    if (r.level === 2 && r.score >= 850) return true
    return false
  })
  nearBreakthrough.forEach((rel) => {
    events.push({
      type: 'relationship_breakthrough',
      timestamp: 'current',
      description: t('agent.lifeTimeline.relationshipWarmUp', { user: rel.user_id }),
      icon: '🔥',
    })
  })

  subAgentRecords
    .filter((r) => r.status === 'completed' && r.completed_at)
    .slice(0, 5)
    .forEach((record) => {
      events.push({
        type: 'memory_milestone',
        timestamp: record.completed_at!,
        description: t('agent.lifeTimeline.memoryMilestone', { type: record.subagent_type }),
        icon: '🧠',
      })
    })

  events.sort((a, b) => {
    const ta = a.timestamp === 'current' ? Date.now() : new Date(a.timestamp).getTime()
    const tb = b.timestamp === 'current' ? Date.now() : new Date(b.timestamp).getTime()
    return tb - ta
  })

  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        {t('agent.lifeTimeline.noEvents')}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {events.slice(0, 20).map((event, i) => (
        <div key={i} className="flex items-start gap-3 text-sm">
          <span className="text-base">{event.icon}</span>
          <div className="flex-1">
            <span className="text-muted-foreground">{event.description}</span>
          </div>
          <span className="text-xs text-muted-foreground shrink-0">
            {event.timestamp === 'current'
              ? t('agent.lifeTimeline.currentStatus')
              : new Date(event.timestamp).toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  )
}