import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { EmotionStateInfo, AgentConfigInfo, EmotionBehaviorRule } from '@/lib/agent-api'
import { EMOTION_COLORS, EMOTION_ICONS } from '../../utils/emotion-constants'
import { EmotionBaselineShift } from './emotion-baseline-shift'
import { EmotionBehaviorMap } from './emotion-behavior-map'
import { DeepMonitorLink } from './deep-monitor-link'

// 情绪柱状图（原 dashboard 共享组件——agent 域仅 EmotionLandscape 单消费者，内联保留——`#9b59b6` 为 EMOTION_COLORS 缺失兜底色，属数据可视化色板豁免）
interface EmotionBarChartProps {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  showValues?: boolean
}

function EmotionBarChart({
  emotions,
  emotionLabels,
  showValues = true,
}: EmotionBarChartProps) {
  return (
    <div className="space-y-1.5">
      {Object.entries(emotions).map(([key, val]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-14 text-xs text-muted-foreground shrink-0 truncate">
            {EMOTION_ICONS[key]} {emotionLabels[key] || key}
          </span>
          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(val, 100)}%`,
                backgroundColor: EMOTION_COLORS[key] || '#9b59b6',
              }}
            />
          </div>
          {showValues && (
            <span className="text-xs text-muted-foreground w-7 text-right">{Math.round(val)}</span>
          )}
        </div>
      ))}
    </div>
  )
}

// 情绪雷达图（原 dashboard 共享组件——agent 域仅 EmotionLandscape 单消费者，内联保留）
interface EmotionRadarChartProps {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  size?: number
  color?: string
}

function EmotionRadarChart({
  emotions,
  emotionLabels,
  size = 180,
  color = 'currentColor',
}: EmotionRadarChartProps) {
  const maxVal = Math.max(...Object.values(emotions), 1)
  const center = size / 2
  const radius = size / 2 - 24
  const entries = Object.entries(emotions)
  const n = entries.length

  return (
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
          strokeOpacity={0.12}
          strokeWidth={1}
        />
      ))}
      {entries.map(([,], i) => {
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
            strokeOpacity={0.08}
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
        fill={color}
        fillOpacity={0.15}
        stroke={color}
        strokeWidth={2}
      />
      {entries.map(([key], i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        const lx = center + (radius + 18) * Math.cos(angle)
        const ly = center + (radius + 18) * Math.sin(angle)
        return (
          <text
            key={key}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-muted-foreground"
            fontSize={9}
          >
            {EMOTION_ICONS[key]} {emotionLabels[key] || key}
          </text>
        )
      })}
    </svg>
  )
}

interface EmotionLandscapeProps {
  agentId: string
  emotion: EmotionStateInfo | null
  agent: AgentConfigInfo | null
  behaviorRules: EmotionBehaviorRule[]
}

export function EmotionLandscape({ agentId, emotion, agent, behaviorRules }: EmotionLandscapeProps) {
  const { t } = useTranslation()

  if (!emotion) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        {t('agent.emotionLandscape.unavailable')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.radarTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionRadarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.barTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionBarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
      </div>

      {agent && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('agent.emotionLandscape.baselineShift')}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmotionBaselineShift
              emotions={emotion.emotions}
              baseline={agent.emotion_baseline}
              emotionLabels={emotion.emotion_labels}
            />
          </CardContent>
        </Card>
      )}

      <EmotionBehaviorMap rules={behaviorRules} />

      <DeepMonitorLink agentId={agentId} target="emotion" />
    </div>
  )
}