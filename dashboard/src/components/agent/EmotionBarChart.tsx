import { EMOTION_COLORS, EMOTION_ICONS } from '@/routes/agent/utils/emotion-constants'

interface EmotionBarChartProps {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  showValues?: boolean
}

export function EmotionBarChart({
  emotions,
  emotionLabels,
  showValues = true,
}: EmotionBarChartProps) {
  return (
    <div className="space-y-2">
      {Object.entries(emotions).map(([key, val]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-16 text-xs text-muted-foreground shrink-0">
            {EMOTION_ICONS[key]} {emotionLabels[key] || key}
          </span>
          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(val, 100)}%`,
                backgroundColor: EMOTION_COLORS[key] || '#9b59b6',
              }}
            />
          </div>
          {showValues && (
            <span className="text-xs text-muted-foreground w-8 text-right">{Math.round(val)}</span>
          )}
        </div>
      ))}
    </div>
  )
}