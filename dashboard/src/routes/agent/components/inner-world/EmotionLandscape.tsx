import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmotionBarChart } from '@/components/agent/EmotionBarChart'
import { EmotionRadarChart } from '@/components/agent/EmotionRadarChart'

import type { EmotionStateInfo, AgentConfigInfo, EmotionBehaviorRule } from '@/lib/agent-api'
import { EmotionBaselineShift } from './EmotionBaselineShift'
import { EmotionBehaviorMap } from './EmotionBehaviorMap'
import { DeepMonitorLink } from './DeepMonitorLink'

interface EmotionLandscapeProps {
  agentId: string
  emotion: EmotionStateInfo | null
  agent: AgentConfigInfo | null
  behaviorRules: EmotionBehaviorRule[]
}

export function EmotionLandscape({ agentId, emotion, agent, behaviorRules }: EmotionLandscapeProps) {
  const { t } = useTranslation()

  if (!emotion) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        {t('agent.emotionLandscape.unavailable')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.radarTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionRadarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.barTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionBarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
      </div>

      {agent && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.baselineShift')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionBaselineShift
              emotions={emotion.emotions}
              baseline={agent.emotion_baseline}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
      )}

      <EmotionBehaviorMap rules={behaviorRules} />

      <DeepMonitorLink agentId={agentId} target="emotion" />
    </div>
  )
}