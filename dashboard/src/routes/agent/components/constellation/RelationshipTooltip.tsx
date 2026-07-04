import { useTranslation } from 'react-i18next'

import type { ConstellationEdge as ConstellationEdgeData } from '../../utils/constellation'

interface RelationshipTooltipProps {
  data: ConstellationEdgeData
}

export function RelationshipTooltip({ data }: RelationshipTooltipProps) {
  const { t } = useTranslation()

  return (
    <div className="bg-popover text-popover-foreground rounded-lg border shadow-md p-3 text-sm space-y-1">
      <div className="font-medium">{data.relationshipType}</div>
      <div className="text-muted-foreground">{data.attitude}</div>
      {data.interactionStyle && (
        <div className="text-muted-foreground text-xs">{data.interactionStyle}</div>
      )}
      <div className="text-xs text-muted-foreground">
        {t(`agent.constellation.mention.${data.mentionLabel}`)}
      </div>
    </div>
  )
}