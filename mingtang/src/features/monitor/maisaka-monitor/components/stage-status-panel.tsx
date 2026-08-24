/**
 * StageStatusPanel 阶段状态面板
 *
 * 展示阶段名/轮次/智能体状态/详情/更新时间。
 * 操作按钮：清空时间线 + 回到底部 + 持续获取开关。
 * 统计 tooltip（消息数/循环数/工具调用数）。
 */
import { Activity, ChevronDown, Eraser, Radio } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { StageStatusInfo, MonitorStats } from '../hooks/persist-monitor'
import { cn } from '@/lib/utils'

import { MonitorStats as MonitorStatsTooltip } from './monitor-stats'
import { formatRelativeTime } from './timeline-entry-item'

export interface StageStatusPanelProps {
  status?: StageStatusInfo
  stats: MonitorStats
  autoScroll: boolean
  backgroundCollection: boolean
  onClearTimeline: () => void
  onToggleBackgroundCollection: () => void
  onScrollToBottom: () => void
}

export function StageStatusPanel({
  status,
  stats,
  autoScroll,
  backgroundCollection,
  onClearTimeline,
  onToggleBackgroundCollection,
  onScrollToBottom,
}: StageStatusPanelProps) {
  const { t } = useTranslation()

  const actions = (
    <>
      <MonitorStatsTooltip stats={stats} />
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <Button
          variant={backgroundCollection ? 'secondary' : 'ghost'}
          size="sm"
          className="h-6 shrink-0 px-2 text-[11px]"
          onClick={onToggleBackgroundCollection}
          title={backgroundCollection ? t('monitor.maisaka.disableBackground') : t('monitor.maisaka.enableBackground')}
        >
          <Radio className={cn('h-3 w-3 mr-1', backgroundCollection && 'text-primary')} />
          {t('monitor.maisaka.backgroundCollection')}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 shrink-0 px-2 text-[11px]"
          onClick={onScrollToBottom}
          title={t('monitor.maisaka.scrollToBottom')}
        >
          <ChevronDown className={cn('h-3 w-3 mr-1', autoScroll && 'text-primary')} />
          {t('monitor.maisaka.scrollToBottom')}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={onClearTimeline}
          title={t('monitor.maisaka.clear')}
          aria-label={t('monitor.maisaka.clear')}
        >
          <Eraser className="h-3 w-3" />
        </Button>
      </div>
    </>
  )

  if (!status) {
    return (
      <div className="mb-1.5 flex min-w-0 items-center gap-2 overflow-x-auto rounded-md border bg-muted/30 px-2 py-1">
        {actions}
        <div className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
          {t('monitor.maisaka.noStageStatus')}
        </div>
      </div>
    )
  }

  const rel = formatRelativeTime(status.updatedAt)

  return (
    <div className="mb-1.5 flex min-w-0 items-center gap-2 overflow-x-auto rounded-md border bg-background px-2 py-1">
      {actions}
      <div className="flex shrink-0 items-center gap-1.5">
        <Badge variant="default" className="gap-1 px-1.5 text-[10px]">
          <Activity className="h-2.5 w-2.5" />
          {status.stage || t('monitor.maisaka.unknownStage')}
        </Badge>
        {status.roundText && (
          <Badge variant="secondary" className="px-1.5 text-[10px]">
            {status.roundText}
          </Badge>
        )}
        {status.agentState && (
          <Badge variant={status.agentState === 'running' ? 'default' : 'outline'} className="px-1.5 text-[10px]">
            {status.agentState}
          </Badge>
        )}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {t('monitor.maisaka.updatedAt', { time: t(rel.key, rel.options) })}
        </span>
      </div>
      {status.detail && (
        <p className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{status.detail}</p>
      )}
    </div>
  )
}