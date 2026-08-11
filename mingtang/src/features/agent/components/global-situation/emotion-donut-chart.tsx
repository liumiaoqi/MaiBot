import { useMemo } from 'react'

import { useTranslation } from 'react-i18next'

import type { BatchEmotionItem } from '@/lib/agent-api'

import { EMOTION_COLORS } from '../../utils/emotion-constants'

interface EmotionDonutChartProps {
  emotions: Record<string, BatchEmotionItem>
}

// 图表：自绘 SVG 环图（源文件同构——行为等价，非 recharts——mingtang 无 recharts 依赖）
export function EmotionDonutChart({ emotions }: EmotionDonutChartProps) {
  const { t } = useTranslation()

  const distribution = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const emotion of Object.values(emotions)) {
      const dominant = emotion.dominant_emotion
      counts[dominant] = (counts[dominant] || 0) + 1
    }
    return Object.entries(counts).map(([emotion, count]) => ({
      name: emotion,
      label: Object.values(emotions).find((e) => e.emotion_labels?.[emotion])?.emotion_labels[emotion] || emotion,
      value: count,
      // `#9b59b6` 为 EMOTION_COLORS 缺失兜底色（数据可视化色板豁免）
      color: EMOTION_COLORS[emotion] || '#9b59b6',
    }))
  }, [emotions])

  if (distribution.length === 0) return null

  const total = distribution.reduce((sum, d) => sum + d.value, 0)
  const radius = 80
  const strokeWidth = 30
  const circumference = 2 * Math.PI * radius

  let offset = 0

  return (
    <div className="h-72">
      <h3 className="text-sm font-medium mb-2">{t('agent.globalSituation.emotionDistribution')}</h3>
      <div className="flex items-center justify-center h-[80%]">
        <svg viewBox="0 0 200 200" className="w-48 h-48">
          <circle
            cx="100"
            cy="100"
            r={radius}
            fill="none"
            stroke="var(--color-muted)"
            strokeWidth={strokeWidth}
          />
          {distribution.map((entry) => {
            const dash = (entry.value / total) * circumference
            const segment = (
              <circle
                key={entry.name}
                cx="100"
                cy="100"
                r={radius}
                fill="none"
                stroke={entry.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 100 100)"
              />
            )
            offset += dash
            return segment
          })}
        </svg>
      </div>
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mt-1">
        {distribution.map((entry) => (
          <div key={entry.name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: entry.color }} />
            <span>{entry.label}</span>
            <span className="font-medium">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}