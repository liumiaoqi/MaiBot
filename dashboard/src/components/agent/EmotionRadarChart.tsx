import { EMOTION_ICONS } from '@/routes/agent/utils/emotion-constants'

interface EmotionRadarChartProps {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  size?: number
  color?: string
}

export function EmotionRadarChart({
  emotions,
  emotionLabels,
  size = 160,
  color,
}: EmotionRadarChartProps) {
  const maxVal = Math.max(...Object.values(emotions), 1)
  const center = size / 2
  const radius = size / 2 - 20
  const entries = Object.entries(emotions)
  const n = entries.length

  return (
    <div className="flex items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {[0.25, 0.5, 0.75, 1].map((ring) => (
          <polygon
            key={ring}
            points={entries
              .map((_, i) => {
                const angle = (2 * Math.PI * i) / n - Math.PI / 2
                const x = center + radius * ring * Math.cos(angle)
                const y = center + radius * ring * Math.sin(angle)
                return `${x},${y}`
              })
              .join(' ')}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.15}
            strokeWidth={1}
          />
        ))}
        {entries.map(([, _val], i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const x = center + radius * Math.cos(angle)
          const y = center + radius * Math.sin(angle)
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={x}
              y2={y}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          )
        })}
        <polygon
          points={entries
            .map(([, val], i) => {
              const ratio = val / maxVal
              const angle = (2 * Math.PI * i) / n - Math.PI / 2
              const x = center + radius * ratio * Math.cos(angle)
              const y = center + radius * ratio * Math.sin(angle)
              return `${x},${y}`
            })
            .join(' ')}
          fill={color || 'currentColor'}
          fillOpacity={0.15}
          stroke={color || 'currentColor'}
          strokeWidth={2}
        />
        {entries.map(([key, _val], i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const lx = center + (radius + 14) * Math.cos(angle)
          const ly = center + (radius + 14) * Math.sin(angle)
          return (
            <text
              key={key}
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-muted-foreground"
              fontSize={10}
            >
              {EMOTION_ICONS[key] || ''} {emotionLabels[key] || key}
            </text>
          )
        })}
      </svg>
    </div>
  )
}