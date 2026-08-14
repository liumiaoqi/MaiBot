import { useTranslation } from 'react-i18next'

import { STATUS_COLORS, type ActivityRhythmData } from '../utils/vital-signs'

interface ActivityRhythmIndicatorProps {
  data: ActivityRhythmData
}

export function ActivityRhythmIndicator({ data }: ActivityRhythmIndicatorProps) {
  const { t } = useTranslation()

  const isActive = data.status === 'active'
  const isDormant = data.status === 'dormant'

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className="w-2.5 h-2.5 rounded-full"
        style={{
          backgroundColor: STATUS_COLORS[data.status],
          ...(isDormant
            ? { opacity: 1 }
            : {
                animation: `agent-rhythm ${isActive ? 1500 : 2500}ms ease-in-out infinite alternate`,
                ['--agent-rhythm-from' as string]: isActive ? 0.4 : 0.2,
                ['--agent-rhythm-to' as string]: isActive ? 1 : 0.5,
              }),
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