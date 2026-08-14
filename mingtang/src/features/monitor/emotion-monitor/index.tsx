/**
 * EmotionMonitorPage 情绪监控页（T1-3-5 搬移——cockpit 只读模式）
 *
 * 定位：情绪雷达图/柱状图/基线对比（REST only——零写操作）
 * 数据流：useEmotionMonitor（getAgentList + getAgentEmotion 聚合）
 * 只读约束：零写操作（spec.md §4.3 #2）
 * i18n：页面标题/雷达/基线用 monitor.emotion.*（design.md §2.5），其余沿用预埋 emotion.*
 * 图表：自绘 SVG（源文件同构——行为等价，非 recharts）
 */
import { useRouterState } from '@tanstack/react-router'
import { RefreshCw, Timer, TimerOff } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { EmotionBarChart, EmotionRadarChart } from '@/components/biz/charts/emotion-charts'
import { PageShell } from '@/components/biz/page-shell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { EMOTION_COLORS, EMOTION_ICONS } from '@/features/agent/utils/emotion-constants'
import { cn } from '@/lib/utils'
import type { AgentConfigInfo, EmotionStateInfo } from '@/lib/agent-api'

import { useEmotionMonitor } from './hooks/use-emotion-monitor'

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
              icons={EMOTION_ICONS}
              size={150}
              color={dominantColor}
            />
          </div>
          <div className="flex-1 min-w-0">
            <EmotionBarChart
              emotions={emotion.emotions}
              emotionLabels={emotion.emotion_labels}
              colors={EMOTION_COLORS}
              icons={EMOTION_ICONS}
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
              colors={EMOTION_COLORS}
              icons={EMOTION_ICONS}
              showValues={false}
            />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">{t('monitor.emotion.baseline')}</p>
            <EmotionBarChart
              emotions={baseline}
              emotionLabels={emotion.emotion_labels}
              colors={EMOTION_COLORS}
              icons={EMOTION_ICONS}
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
  const search = useRouterState({ select: (s) => s.location.search }) as Record<string, unknown>
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
    <PageShell
      title={t('monitor.emotion.title')}
      actions={
        <>
          <Badge variant="outline">{t('emotion.agentCount', { count: agents.length })}</Badge>
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
          <Button variant="ghost" size="icon" onClick={refresh}>
            <RefreshCw
              className={cn(
                'h-4 w-4',
                isRefreshing && 'animate-spin'
              )}
            />
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {viewMode === 'grid' ? (
          <>
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
          </>
        ) : selectedAgent && selectedEmotion ? (
          <ScrollArea className="h-[calc(100vh-220px)] max-w-4xl">
            <div className="space-y-6 pr-4">
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
                    <CardTitle className="text-sm">{t('monitor.emotion.radar')}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex justify-center">
                    <EmotionRadarChart
                      emotions={selectedEmotion.emotions}
                      emotionLabels={selectedEmotion.emotion_labels}
                      icons={EMOTION_ICONS}
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
                      colors={EMOTION_COLORS}
                      icons={EMOTION_ICONS}
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
          <div className="flex items-center justify-center h-64">
            <Skeleton className="h-48 w-48 rounded-lg" />
          </div>
        )}
      </div>
    </PageShell>
  )
}