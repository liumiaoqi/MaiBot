import { useTranslation } from 'react-i18next'

import type { RelationshipWarmthData } from '../utils/vital-signs'

interface RelationshipWarmthIndicatorProps {
  data: RelationshipWarmthData
}

// 关系热度语义状态色板（warm/moderate/cold/no_data/unavailable——语义状态色板豁免）
const WARMTH_COLORS: Record<string, string> = {
  warm: '#ef4444',
  moderate: '#f97316',
  cold: '#3b82f6',
  no_data: '#9ca3af',
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
      {data.dataSource === 'internal_relationship' && (
        <span className="text-muted-foreground">
          · {t('agent.vitalSigns.warmth.basedOnInternal')}
        </span>
      )}
      {data.relationshipCount > 0 && (
        <span className="text-muted-foreground">
          · {t('agent.vitalSigns.relationshipCount', { count: data.relationshipCount })}
        </span>
      )}
    </div>
  )
}