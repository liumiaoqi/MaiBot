import { useSpring, animated } from '@react-spring/web'

import { useTranslation } from 'react-i18next'

import type { ActivityRhythmData } from '../utils/vital-signs'

interface ActivityRhythmIndicatorProps {
  data: ActivityRhythmData
}

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  quiet: '#fbbf24',
  dormant: '#94a3b8',
}

export function ActivityRhythmIndicator({ data }: ActivityRhythmIndicatorProps) {
  const { t } = useTranslation()

  const isActive = data.status === 'active'
  const isQuiet = data.status === 'quiet'

  const spring = useSpring({
    from: { opacity: isActive ? 0.4 : isQuiet ? 0.2 : 0.6 },
    to: { opacity: isActive ? 1.0 : isQuiet ? 0.5 : 0.6 },
    loop: isActive || isQuiet,
    config: { duration: isActive ? 1500 : 2500 },
    reverse: isActive || isQuiet,
    immediate: data.status === 'dormant',
  })

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <animated.span
        className="w-2.5 h-2.5 rounded-full"
        style={{
          backgroundColor: STATUS_COLORS[data.status],
          opacity: spring.opacity,
        }}
      />
      <span className="text-muted-foreground">
        {t(`agent.vitalSigns.activity.${data.status}`)}
      </span>
      {data.sessionCount > 0 && (
        <span className="text-muted-foreground">
          · {t('agent.vitalSigns.sessionCount', { count: data.sessionCount })}
        </span>
      )}
    </div>
  )
}