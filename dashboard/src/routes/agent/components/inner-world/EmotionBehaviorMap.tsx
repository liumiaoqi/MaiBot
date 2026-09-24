import { useTranslation } from 'react-i18next'

import type { EmotionBehaviorRule } from '@/lib/agent-api'

interface EmotionBehaviorMapProps {
  rules: EmotionBehaviorRule[]
}

export function EmotionBehaviorMap({ rules }: EmotionBehaviorMapProps) {
  const { t } = useTranslation()

  if (rules.length === 0) return null

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground">
        {t('agent.emotionLandscape.behaviorTendency')}
      </h4>
      {rules.map((rule, i) => (
        <div key={i} className="text-sm text-muted-foreground">
          {rule.behavior_tendency || `${rule.emotion_type}: ${rule.reply_style_modifier}`}
        </div>
      ))}
    </div>
  )
}