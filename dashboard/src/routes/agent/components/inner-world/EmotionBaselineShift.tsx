import { useTranslation } from 'react-i18next'

import { EMOTION_ICONS } from '../../utils/emotion-constants'

interface EmotionBaselineShiftProps {
  emotions: Record<string, number>
  baseline: Record<string, number>
  emotionLabels: Record<string, string>
}

export function EmotionBaselineShift({ emotions, baseline, emotionLabels }: EmotionBaselineShiftProps) {
  const { t } = useTranslation()

  const shifts = Object.entries(emotions).map(([key, current]) => {
    const base = baseline[key] ?? 0
    const delta = current - base
    return { key, current, base, delta, label: emotionLabels[key] || key }
  })

  return (
    <div className="space-y-2">
      {shifts.map(({ key, delta, label }) => {
        const isUp = delta > 5
        const isDown = delta < -5

        const barColor = isUp ? 'bg-green-500' : isDown ? 'bg-red-500' : 'bg-muted-foreground/30'
        const arrow = isUp ? '↑' : isDown ? '↓' : '→'
        const shiftLabel = isUp
          ? t('agent.emotionLandscape.shiftUp')
          : isDown
            ? t('agent.emotionLandscape.shiftDown')
            : t('agent.emotionLandscape.shiftStable')

        return (
          <div key={key} className="flex items-center gap-2 text-sm">
            <span className="w-5 text-center">{EMOTION_ICONS[key]}</span>
            <span className="w-14 text-muted-foreground text-xs truncate">{label}</span>
            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${barColor}`}
                style={{ width: `${Math.abs(delta) >= 5 ? Math.max(Math.min(Math.abs(delta), 100), 10) : Math.min(Math.abs(delta), 100)}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground w-4">{arrow}</span>
            <span className="text-xs text-muted-foreground">{shiftLabel}</span>
          </div>
        )
      })}
    </div>
  )
}