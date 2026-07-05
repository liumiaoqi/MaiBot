import { useTranslation } from 'react-i18next'

import type { VitalSignsData } from '../../utils/vital-signs'

interface ActivityHeatmapProps {
  vitalSignsList: VitalSignsData[]
}

const STATUS_COLORS: Record<string, string> = {
  active: '#ef4444',
  quiet: '#fbbf24',
  dormant: '#3b82f6',
}

export function ActivityHeatmap({ vitalSignsList }: ActivityHeatmapProps) {
  const { t } = useTranslation()

  return (
    <div>
      <h3 className="text-sm font-medium mb-2">{t('agent.globalSituation.activityHeatmap')}</h3>
      <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-7 gap-2">
        {vitalSignsList.map((vs) => (
          <div
            key={vs.agentId}
            className="aspect-square rounded-lg flex items-center justify-center text-white font-bold text-sm"
            style={{ backgroundColor: STATUS_COLORS[vs.activityRhythm.status] }}
            title={`${vs.displayName}: ${vs.activityRhythm.status}`}
          >
            {vs.displayName.charAt(0)}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-2">
        {(['active', 'quiet', 'dormant'] as const).map((status) => (
          <div key={status} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: STATUS_COLORS[status] }} />
            <span>{t(`agent.globalSituation.heatmapLegend.${status}`)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}