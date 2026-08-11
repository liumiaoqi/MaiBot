import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'

import { getAgentMonologues, type InnerMonologueEventResponse } from '@/lib/agent-api'

export function MonologuePanel({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: monologues = [], isLoading } = useQuery({
    queryKey: ['agent', 'monologue', agentId],
    queryFn: () => getAgentMonologues(agentId, 10),
    enabled: !!agentId,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        {t('common.loading', '加载中...')}
      </div>
    )
  }

  if (monologues.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        {t('agent.monologue.panel.empty')}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground/80 px-1">
        {t('agent.monologue.panel.title')}
      </h3>
      <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
        {monologues.map((m) => (
          <MonologueCard
            key={m.monologue_id}
            monologue={m}
            expanded={expandedId === m.monologue_id}
            onToggle={() =>
              setExpandedId(expandedId === m.monologue_id ? null : m.monologue_id)
            }
          />
        ))}
      </div>
    </div>
  )
}

function MonologueCard({
  monologue,
  expanded,
  onToggle,
}: {
  monologue: InnerMonologueEventResponse
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()

  const timeStr = monologue.created_at
    ? new Date(monologue.created_at).toLocaleTimeString()
    : ''

  let dominantEmotion = 'calm'
  let dominantIntensity = 0
  try {
    const snapshot = JSON.parse(monologue.emotion_snapshot)
    const entries = Object.entries(snapshot) as [string, number][]
    const top = entries.reduce(
      (a, b) => (b[1] > a[1] ? b : a),
      ['calm', 0] as [string, number]
    )
    dominantEmotion = top[0]
    dominantIntensity = Math.round(top[1])
  } catch {
    // ignore
  }

  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full text-left rounded-lg bg-muted/20 hover:bg-muted/30 border border-border/60 px-3 py-2 transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground/70">{dominantEmotion}</span>
        <span className="text-xs text-muted-foreground">{dominantIntensity}/100</span>
        <span className="ml-auto text-[10px] text-muted-foreground/60">{timeStr}</span>
      </div>
      <p className={`mt-1 text-xs text-muted-foreground/80 ${expanded ? '' : 'line-clamp-2'}`}>
        {monologue.content}
      </p>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-border/60 space-y-1.5 text-xs text-muted-foreground/80">
          <div>
            <span className="text-muted-foreground/70">{t('agent.monologue.emotionSnapshot.label')}：</span>
            {monologue.emotion_snapshot.slice(0, 100)}
          </div>
          <div>
            <span className="text-muted-foreground/70">{t('agent.monologue.selfEffect.label')}：</span>
            {monologue.self_emotion_effect}
          </div>
        </div>
      )}
    </button>
  )
}