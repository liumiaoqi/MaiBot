import { useTranslation } from 'react-i18next'

import type { RelationshipWarmthData } from '../utils/vital-signs'

interface RelationshipWarmthIndicatorProps {
  data: RelationshipWarmthData
}

const WARMTH_COLORS: Record<string, string> = {
  warm: '#ef4444',
  moderate: '#f97316',
  cold: '#3b82f6',
  unavailable: '#6b7280',
}

export function RelationshipWarmthIndicator({ data }: RelationshipWarmthIndicatorProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className="w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: WARMTH_COLORS[data.warmth] }}
      />
      <span className="text-muted-foreground">
        {t(`agent.vitalSigns.warmth.${data.warmth}`)}
      </span>
      {data.relationshipCount > 0 && (
        <span className="text-muted-foreground">
          · {t('agent.vitalSigns.relationshipCount', { count: data.relationshipCount })}
        </span>
      )}
    </div>
  )
}