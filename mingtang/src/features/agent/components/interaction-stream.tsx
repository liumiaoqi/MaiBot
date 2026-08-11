import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useState, useMemo } from 'react'
import { Flame } from 'lucide-react'

import { getRecentInteractions, getInteractionHotspots, type InteractionEventResponse } from '@/lib/agent-api'

const TYPE_COLORS: Record<string, string> = {
  emotion_driven: 'bg-rose-500/15 text-rose-700 dark:text-rose-400',
  time_awareness: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  mention_propagation: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  event_ripple: 'bg-purple-500/15 text-purple-700 dark:text-purple-400',
  inner_need: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  memory_driven: 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-400',
  inner_monologue: 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
}

export function InteractionStream() {
  const { t } = useTranslation()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['agent', 'interactions', 'recent'],
    queryFn: () => getRecentInteractions(20),
    refetchInterval: 30_000,
  })

  const { data: hotspots = [] } = useQuery({
    queryKey: ['agent', 'interactions', 'hotspots'],
    queryFn: getInteractionHotspots,
    refetchInterval: 60_000,
  })

  const hotspotPairs = useMemo(() => {
    const set = new Set<string>()
    for (const h of hotspots) {
      set.add(h.pair)
      const [a, b] = h.pair.split(':')
      if (a && b) set.add(`${b}:${a}`)
    }
    return set
  }, [hotspots])

  const hotspotCountMap = useMemo(() => {
    const map = new Map<string, number>()
    for (const h of hotspots) {
      map.set(h.pair, h.count)
      const [a, b] = h.pair.split(':')
      if (a && b) map.set(`${b}:${a}`, h.count)
    }
    return map
  }, [hotspots])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        {t('common.loading', '加载中...')}
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        {t('agent.interaction.stream.empty')}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-medium text-foreground/80">
          {t('agent.interaction.stream.title')}
        </h3>
        <span className="text-xs text-muted-foreground/70">
          {t('agent.interaction.stream.refreshInterval')}
        </span>
      </div>
      {hotspots.length > 0 && (
        <div className="flex items-center gap-1.5 px-1">
          <Flame className="h-3 w-3 text-orange-500" />
          <span className="text-xs text-orange-500/80">
            {t('agent.interaction.hotspot.label')}：{hotspots.length}
          </span>
        </div>
      )}
      <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
        {events.map((event) => {
          const pairKey = `${event.initiator_agent_id}:${event.target_agent_id}`
          const isHotspot = hotspotPairs.has(pairKey)
          const hotspotCount = hotspotCountMap.get(pairKey)
          return (
            <InteractionEventCard
              key={event.event_id}
              event={event}
              expanded={expandedId === event.event_id}
              isHotspot={isHotspot}
              hotspotCount={hotspotCount}
              onToggle={() =>
                setExpandedId(expandedId === event.event_id ? null : event.event_id)
              }
            />
          )
        })}
      </div>
    </div>
  )
}

function InteractionEventCard({
  event,
  expanded,
  isHotspot,
  hotspotCount,
  onToggle,
}: {
  event: InteractionEventResponse
  expanded: boolean
  isHotspot?: boolean
  hotspotCount?: number
  onToggle: () => void
}) {
  const { t } = useTranslation()

  const typeColor = TYPE_COLORS[event.interaction_type] ?? 'bg-muted text-muted-foreground'
  const typeLabel = t(`agent.interaction.typeLabels.${event.interaction_type}`, event.interaction_type)
  const timeStr = event.created_at
    ? new Date(event.created_at).toLocaleTimeString()
    : ''

  const borderClass = isHotspot
    ? 'border-orange-500/30 bg-orange-500/10'
    : 'border-border/60 bg-muted/20'

  return (
    <button
      type="button"
      onClick={onToggle}
      className={`w-full text-left rounded-lg hover:bg-muted/30 border px-3 py-2 transition-colors ${borderClass}`}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground/70">
          {event.initiator_agent_id}
        </span>
        <span className="text-muted-foreground/70">→</span>
        <span className="text-xs font-medium text-foreground/70">
          {event.target_agent_id}
        </span>
        {isHotspot && (
          <span className="flex items-center gap-0.5 text-[10px] text-orange-500">
            <Flame className="h-2.5 w-2.5" />
            {hotspotCount}
          </span>
        )}
        <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded-full font-medium ${typeColor}`}>
          {typeLabel}
        </span>
        <span className="text-[10px] text-muted-foreground/60">{timeStr}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground truncate">
        {event.trigger_reason}
      </p>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-border/60 space-y-1.5 text-xs text-muted-foreground/80">
          <div>
            <span className="text-muted-foreground/70">{t('agent.interaction.detail.triggerReason')}：</span>
            {event.trigger_reason}
          </div>
          <div>
            <span className="text-muted-foreground/70">{t('agent.interaction.detail.emotionEffect')}：</span>
            {event.emotion_effects}
          </div>
          <div>
            <span className="text-muted-foreground/70">{t('agent.interaction.detail.relationshipEffect')}：</span>
            {event.relationship_effect > 0 ? '+' : ''}{event.relationship_effect.toFixed(1)}
          </div>
          <div>
            <span className="text-muted-foreground/70">{t('agent.interaction.detail.memoryStatus')}：</span>
            {t(`agent.interaction.memoryStatus.${event.memory_write_status}`, event.memory_write_status)}
          </div>
          {event.echo_depth > 0 && (
            <div>
              <span className="text-muted-foreground/70">{t('agent.interaction.detail.echoDepth')}：</span>
              {event.echo_depth}
            </div>
          )}
        </div>
      )}
    </button>
  )
}