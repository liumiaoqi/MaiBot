import { EmotionPulse } from '../emotion-pulse'
import { ActivityRhythmIndicator } from '../activity-rhythm-indicator'
import type { ConstellationNode as ConstellationNodeData } from '../../utils/constellation'
import { deriveEmotionPulseData, deriveActivityRhythmData } from '../../utils/vital-signs'
import type { BatchEmotionItem } from '@/lib/agent-api'

interface NodeDetailPopoverProps {
  data: ConstellationNodeData
  emotion: BatchEmotionItem | undefined
  sessionCount: number
  talkValueModifier: number
}

export function NodeDetailPopover({ data, emotion, sessionCount, talkValueModifier }: NodeDetailPopoverProps) {
  const emotionPulse = deriveEmotionPulseData(emotion ?? null)
  const activityRhythm = deriveActivityRhythmData(
    { talk_value_modifier: talkValueModifier },
    sessionCount,
  )

  return (
    <div className="bg-popover text-popover-foreground rounded-lg border shadow-md p-3 text-sm space-y-2 min-w-[160px]">
      <div className="font-medium">{data.displayName}</div>
      <EmotionPulse data={emotionPulse} />
      <ActivityRhythmIndicator data={activityRhythm} />
    </div>
  )
}