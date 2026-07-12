import { useRouterState } from '@tanstack/react-router'
import { Heart, RefreshCw, Timer, TimerOff } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'

import type { AgentConfigInfo, EmotionStateInfo } from '@/lib/agent-api'

import { useEmotionMonitor } from '@/hooks/useEmotionMonitor'

import { cn } from '@/lib/utils'

const EMOTION_COLORS: Record<string, string> = {
  happy: '#fbbf24',
  sad: '#60a5fa',
  anxious: '#a78bfa',
  angry: '#ef4444',
  calm: '#34d399',
  excited: '#f97316',
  lonely: '#94a3b8',
}

const EMOTION_ICONS: Record<string, string> = {
  happy: '😊',
  sad: '😢',
  anxious: '😰',
  angry: '😠',
  calm: '😌',
  excited: '🤩',
  lonely: '😔',
}

function EmotionRadarChart({
  emotions,
  emotionLabels,
  size = 180,
  color = 'currentColor',
}: {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  size?: number
  color?: string
}) {
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

function EmotionBarChart({
  emotions,
  emotionLabels,
  showValues = true,
}: {
  emotions: Record<string, number>
  emotionLabels: Record<string, string>
  showValues?: boolean
}) {
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

function AgentEmotionCard({
  agent,
  emotion,
}: {
  agent: AgentConfigInfo
  emotion: EmotionStateInfo
}) {
  const dominantColor = EMOTION_COLORS[emotion.dominant_emotion] || '#9b59b6'

  return (
    <Card className="overflow-hidden">
      <div className="h-1" style={{ backgroundColor: dominantColor }} />
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0"
            style={{ backgroundColor: agent.color }}
          >
            {agent.display_name.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm truncate">{agent.display_name}</CardTitle>
          </div>
          <Badge
            style={{ backgroundColor: dominantColor, color: 'white' }}
            className="shrink-0"
          >
            {EMOTION_ICONS[emotion.dominant_emotion]} {emotion.dominant_emotion_label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-start gap-4">
          <div className="shrink-0">
            <EmotionRadarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
              size={150}
              color={dominantColor}
            />
          </div>
          <div className="flex-1 min-w-0">
            <EmotionBarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function BaselineComparisonCard({
  agent,
  emotion,
}: {
  agent: AgentConfigInfo
  emotion: EmotionStateInfo
}) {
  const { t } = useTranslation()
  const baseline = Object.fromEntries(
    Object.entries(agent.emotion_baseline).map(([k, v]) => [k, v as number])
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-xs shrink-0"
            style={{ backgroundColor: agent.color }}
          >
            {agent.display_name.charAt(0)}
          </div>
          <CardTitle className="text-sm">{agent.display_name}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground mb-2">{t('emotion.currentState')}</p>
            <EmotionBarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
              showValues={false}
            />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">{t('emotion.baseline')}</p>
            <EmotionBarChart
              emotions={baseline}
              emotionLabels={emotion.emotion_labels}
              showValues={false}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function EmotionMonitorPage() {
  const { t } = useTranslation()
  const search = useRouterState().location.search as Record<string, unknown>
  const agentParam = typeof search.agent === 'string' ? search.agent : undefined

  const {
    agents,
    allEmotions,

    selectedAgent,
    selectedEmotion,
    viewMode,
    autoRefresh,
    isInitialLoading,
    isRefreshing,
    setSelectedAgentId,
    setViewMode,
    setAutoRefresh,
    refresh,
  } = useEmotionMonitor(agentParam)


  const dominantEmotionStats = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const emotion of Object.values(allEmotions)) {
      const d = emotion.dominant_emotion
      counts[d] = (counts[d] || 0) + 1
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .map(([emotion, count]) => ({
        emotion,
        label: allEmotions[Object.keys(allEmotions)[0]]?.emotion_labels[emotion] || emotion,
        count,
        color: EMOTION_COLORS[emotion],
      }))
  }, [allEmotions])

  return (
    <div className="h-full flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <Heart className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">{t('emotion.pageTitle')}</h1>
          <Badge variant="outline">{t('emotion.agentCount', { count: agents.length })}</Badge>
        </div>
        <div className="flex items-center gap-2">
          {viewMode === 'detail' && selectedAgent && (
            <Button variant="outline" size="sm" onClick={() => setViewMode('grid')}>
              {t('emotion.backToOverview')}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setAutoRefresh(!autoRefresh)}
            title={autoRefresh ? t('emotion.autoRefreshOff') : t('emotion.autoRefreshOn')}
          >
            {autoRefresh ? (
              <Timer className="h-4 w-4 text-emerald-500" />
            ) : (
              <TimerOff className="h-4 w-4 text-muted-foreground" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={refresh}
          >
            <RefreshCw
              className={cn(
                'h-4 w-4',
                isRefreshing && 'animate-spin'
              )}
            />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {viewMode === 'grid' ? (
          <ScrollArea className="h-full">
            <div className="p-4 space-y-6">
              {/* 主导情绪统计 */}
              {dominantEmotionStats.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{t('emotion.dominantDistribution')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-3">
                      {dominantEmotionStats.map(({ emotion, label, count, color }) => (
                        <div
                          key={emotion}
                          className="flex items-center gap-2 px-3 py-1.5 rounded-full border"
                        >
                          <span>{EMOTION_ICONS[emotion]}</span>
                          <span className="text-sm">{label}</span>
                          <Badge
                            style={{ backgroundColor: color, color: 'white' }}
                            className="text-xs"
                          >
                            {count}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 智能体情绪卡片网格 */}
              {isInitialLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-56 rounded-lg" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {agents.map((agent) => {
                    const emotion = allEmotions[agent.agent_id]
                    if (!emotion) return null
                    return (
                      <div
                        key={agent.agent_id}
                        className="cursor-pointer"
                        onClick={() => {
                          setSelectedAgentId(agent.agent_id)
                          setViewMode('detail')
                        }}
                      >
                        <AgentEmotionCard agent={agent} emotion={emotion} />
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </ScrollArea>
        ) : selectedAgent && selectedEmotion ? (
          <ScrollArea className="h-full">
            <div className="p-4 space-y-6 max-w-4xl">
              {/* 详情头部 */}
              <div className="flex items-center gap-4">
                <div
                  className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-xl shrink-0"
                  style={{ backgroundColor: selectedAgent.color }}
                >
                  {selectedAgent.display_name.charAt(0)}
                </div>
                <div>
                  <h2 className="text-xl font-bold">{selectedAgent.display_name}</h2>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge
                      style={{
                        backgroundColor:
                          EMOTION_COLORS[selectedEmotion.dominant_emotion],
                        color: 'white',
                      }}
                    >
                      {EMOTION_ICONS[selectedEmotion.dominant_emotion]}{' '}
                      {selectedEmotion.dominant_emotion_label}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {t('emotion.dominantIntensity', { value: Math.round(
                         selectedEmotion.emotions[
                           selectedEmotion.dominant_emotion
                         ] ?? 0
                       ) })}
                    </span>
                  </div>
                </div>
              </div>

              {/* 雷达图 + 柱状图 */}
              <div className="grid grid-cols-2 gap-6">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{t('emotion.radarTitle')}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex justify-center">
                    <EmotionRadarChart
                      emotions={selectedEmotion.emotions}
                      emotionLabels={selectedEmotion.emotion_labels}
                      size={220}
                      color={EMOTION_COLORS[selectedEmotion.dominant_emotion] || '#9b59b6'}
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{t('emotion.intensityTitle')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <EmotionBarChart
                      emotions={selectedEmotion.emotions}
                      emotionLabels={selectedEmotion.emotion_labels}
                    />
                  </CardContent>
                </Card>
              </div>

              {/* 基线对比 */}
              <BaselineComparisonCard
                agent={selectedAgent}
                emotion={selectedEmotion}
              />

              {/* 行为参数 */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{t('emotion.behaviorParams')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">{t('emotion.decayRate')}</p>
                      <p className="text-lg font-semibold">{selectedAgent.emotion_decay_rate}/h</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">{t('emotion.activityModifier')}</p>
                      <p className="text-lg font-semibold">×{selectedAgent.talk_value_modifier.toFixed(1)}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </ScrollArea>
        ) : (
          <div className="flex items-center justify-center h-full">
            <Skeleton className="h-48 w-48 rounded-lg" />
          </div>
        )}
      </div>
    </div>
  )
}