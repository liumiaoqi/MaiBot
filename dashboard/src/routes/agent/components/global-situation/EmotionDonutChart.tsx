import { useMemo } from 'react'

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { useTranslation } from 'react-i18next'

import { EMOTION_COLORS } from '../../utils/emotion-constants'
import type { BatchEmotionItem } from '@/lib/agent-api'

interface EmotionDonutChartProps {
  emotions: Record<string, BatchEmotionItem>
}

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
      label: Object.values(emotions).find(e => e.emotion_labels?.[emotion])?.emotion_labels[emotion] || emotion,
      value: count,
      color: EMOTION_COLORS[emotion] || '#9b59b6',
    }))
  }, [emotions])

  if (distribution.length === 0) return null

  return (
    <div className="h-72">
      <h3 className="text-sm font-medium mb-2">{t('agent.globalSituation.emotionDistribution')}</h3>
      <ResponsiveContainer width="100%" height="80%">
        <PieChart>
          <Pie
            data={distribution}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            dataKey="value"
            nameKey="label"
          >
            {distribution.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
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