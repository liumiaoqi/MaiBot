/**
 * MonitorStats 统计信息 tooltip
 *
 * 纯展示——用 Tooltip + Badge 展示消息数/循环数/工具调用数。
 */
import { Activity } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export interface MonitorStatsProps {
  stats: {
    messages: number
    cycles: number
    toolCalls: number
  }
}

export function MonitorStats({ stats }: MonitorStatsProps) {
  const { t } = useTranslation()

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex h-6 shrink-0 items-center gap-1 rounded-md border bg-background/60 px-1.5 text-muted-foreground">
          <Activity className="h-3 w-3" />
          <span className="text-[10px] font-medium">{t('monitor.maisaka.stats')}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="start" className="space-y-1">
        <div>{t('monitor.maisaka.statsMessages', { count: stats.messages })}</div>
        <div>{t('monitor.maisaka.statsCycles', { count: stats.cycles })}</div>
        <div>{t('monitor.maisaka.statsToolCalls', { count: stats.toolCalls })}</div>
      </TooltipContent>
    </Tooltip>
  )
}