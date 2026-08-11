import { useTranslation } from 'react-i18next'

import type { EmotionPulseData } from '../utils/vital-signs'
import { EMOTION_ICONS } from '../utils/emotion-constants'

interface EmotionPulseProps {
  data: EmotionPulseData | null
}

export function EmotionPulse({ data }: EmotionPulseProps) {
  const { t } = useTranslation()

  if (!data) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="w-4 h-4 rounded-full bg-muted" />
        <span>{t('agent.vitalSigns.emotionPulse.unavailable')}</span>
      </div>
    )
  }

  const intensity = data.intensity ?? 0
  const scale = Math.min(1.0 + intensity / 200, 1.2)
  const duration = Math.max(800, 2000 - (intensity / 100) * 1000)

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className="w-4 h-4 rounded-full flex items-center justify-center text-[10px]"
        style={{
          backgroundColor: data.color,
          animation: `agent-emotion-pulse ${duration}ms ease-in-out infinite`,
          ['--agent-pulse-scale' as string]: scale,
        }}
      >
        {EMOTION_ICONS[data.dominantEmotion] || ''}
      </span>
      <span className="text-muted-foreground">{data.dominantEmotionLabel}</span>
    </div>
  )
}