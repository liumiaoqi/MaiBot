import { useQuery } from '@tanstack/react-query'
import { Activity, Brain, Filter, Megaphone, MessageSquare, RefreshCw, Zap } from 'lucide-react'
import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { getAutonomyLogs, type AutonomyLogItem } from '@/lib/agent-api'
import { cn } from '@/lib/utils'

const EVENT_TYPE_OPTIONS = [
  { value: '', labelKey: 'agent.autonomyLogs.allTypes' },
  { value: 'thinking', labelKey: 'agent.autonomyLogs.thinking' },
  { value: 'expression', labelKey: 'agent.autonomyLogs.expression' },
  { value: 'inner_need', labelKey: 'agent.autonomyLogs.innerNeed' },
  { value: 'behavior_intent', labelKey: 'agent.autonomyLogs.behaviorIntent' },
  { value: 'interjection', labelKey: 'agent.autonomyLogs.interjection' },
  { value: 'orchestration', labelKey: 'agent.autonomyLogs.orchestration' },
] as const

const EVENT_TYPE_COLORS: Record<string, string> = {
  thinking: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/25',
  expression: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/25',
  inner_need: 'bg-purple-500/15 text-purple-700 dark:text-purple-400 border-purple-500/25',
  behavior_intent: 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-400 border-cyan-500/25',
  interjection: 'bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/25',
  orchestration: 'bg-pink-500/15 text-pink-700 dark:text-pink-400 border-pink-500/25',
}

const EVENT_TYPE_ICONS: Record<string, typeof Brain> = {
  thinking: Brain,
  expression: Megaphone,
  inner_need: Activity,
  behavior_intent: Zap,
  interjection: MessageSquare,
  orchestration: Filter,
}

function formatTimestamp(ts: string): string {
  if (!ts) return ''
  try {
    const date = new Date(ts)
    if (isNaN(date.getTime())) return ts
    return date.toLocaleString()
  } catch {
    return ts
  }
}

export function AutonomyLogPanel({ agentId }: { agentId?: string }) {
  const { t } = useTranslation()
  const [eventTypeFilter, setEventTypeFilter] = useState('')
  const [page, setPage] = useState(1)

  const { data, isPending, isFetching, refetch } = useQuery({
    queryKey: ['autonomy-logs', agentId, eventTypeFilter, page],
    queryFn: () =>
      getAutonomyLogs({
        agent_id: agentId || undefined,
        event_type: eventTypeFilter || undefined,
        page,
        page_size: 50,
      }),
    refetchInterval: 10000,
  })

  const handleEventTypeChange = useCallback((value: string) => {
    setEventTypeFilter(value === '__all__' ? '' : value)
    setPage(1)
  }, [])

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 50))

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4" />
            {t('agent.autonomyLogs.title')}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Select value={eventTypeFilter || '__all__'} onValueChange={handleEventTypeChange}>
              <SelectTrigger className="h-8 w-[140px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EVENT_TYPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value || '__all__'} value={opt.value || '__all__'} className="text-xs">
                    {t(opt.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
            {t('agent.autonomyLogs.empty')}
          </div>
        ) : (
          <ScrollArea className="h-[400px]">
            <div className="space-y-1 p-4 pt-0">
              {items.map((item: AutonomyLogItem, index: number) => (
                <LogEntry key={`${item.timestamp}-${index}`} item={item} />
              ))}
            </div>
          </ScrollArea>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
            <span>
              {t('agent.autonomyLogs.total', { count: total })}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                {t('agent.autonomyLogs.prev')}
              </Button>
              <span>{page}/{totalPages}</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                {t('agent.autonomyLogs.next')}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function LogEntry({ item }: { item: AutonomyLogItem }) {
  const Icon = EVENT_TYPE_ICONS[item.event_type] ?? Activity
  const colorClass = EVENT_TYPE_COLORS[item.event_type] ?? 'bg-muted text-muted-foreground border-muted'

  return (
    <div className="flex items-start gap-2.5 rounded-md border border-transparent px-2.5 py-1.5 text-sm transition-colors hover:border-border hover:bg-muted/30">
      <div className="mt-0.5 shrink-0">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="font-medium">{item.agent_id}</span>
          <Badge variant="outline" className={cn('px-1.5 py-0 text-[10px] font-medium', colorClass)}>
            {item.event_type}
          </Badge>
        </div>
        <p className="truncate text-xs text-muted-foreground">{item.detail}</p>
      </div>
      <span className="shrink-0 text-[10px] text-muted-foreground/60">
        {formatTimestamp(item.timestamp)}
      </span>
    </div>
  )
}