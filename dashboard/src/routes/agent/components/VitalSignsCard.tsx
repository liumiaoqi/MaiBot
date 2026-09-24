import { cn } from '@/lib/utils'

import type { VitalSignsData } from '../utils/vital-signs'
import { ActivityRhythmIndicator } from './ActivityRhythmIndicator'
import { CoreBadge } from './CoreBadge'
import { EmotionPulse } from './EmotionPulse'
import { InnerActivityIndicator } from './InnerActivityIndicator'
import { RelationshipWarmthIndicator } from './RelationshipWarmthIndicator'

interface VitalSignsCardProps {
  data: VitalSignsData
  isSelected: boolean
  onClick: () => void
}

export function VitalSignsCard({ data, isSelected, onClick }: VitalSignsCardProps) {
  return (
    <div
      className={cn(
        'cursor-pointer rounded-lg border bg-card p-4 transition-all hover:shadow-md',
        isSelected && 'ring-2 ring-primary'
      )}
      onClick={onClick}
    >
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0"
          style={{ backgroundColor: data.color }}
        >
          {data.displayName.charAt(0)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">{data.displayName}</span>
            {data.isDefault && <CoreBadge />}
          </div>
          <span className="text-xs text-muted-foreground truncate block">{data.agentId}</span>
        </div>
      </div>
      <div className="space-y-1.5">
        <EmotionPulse data={data.emotionPulse} />
        <ActivityRhythmIndicator data={data.activityRhythm} />
        <RelationshipWarmthIndicator data={data.relationshipWarmth} />
        <InnerActivityIndicator data={data.innerActivity} />
      </div>
    </div>
  )
}