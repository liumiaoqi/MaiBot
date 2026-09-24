import { Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import { fetchStateAwareness } from '@/lib/agent-api'

interface StateAwarenessPanelProps {
  sessionId: string | null
}

export function StateAwarenessPanel({ sessionId }: StateAwarenessPanelProps) {
  const { t } = useTranslation()

  const { data, isLoading } = useQuery({
    queryKey: ['agents', 'state-awareness', sessionId],
    queryFn: () => fetchStateAwareness(sessionId!),
    enabled: !!sessionId,
    refetchInterval: 30_000,
  })

  if (!sessionId) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Eye className="h-3.5 w-3.5" />
            {t('agent.stateAwareness.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">{t('agent.stateAwareness.noData')}</p>
        </CardContent>
      </Card>
    )
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Eye className="h-3.5 w-3.5" />
            {t('agent.stateAwareness.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">...</p>
        </CardContent>
      </Card>
    )
  }

  const entries = data?.cohabitant_entries ?? []
  const summaryPreview = data?.summary_preview ?? ''
  const activeRules = data?.active_rules ?? []

  if (entries.length === 0 && activeRules.length === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Eye className="h-3.5 w-3.5" />
          {t('agent.stateAwareness.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length > 0 && (
          <div className="space-y-1.5">
            {entries.map((e) => (
              <div key={e.agent_id} className="flex items-center gap-2 text-xs">
                <span className="font-medium">{e.display_name}</span>
                <Badge
                  variant="outline"
                  className={
                    e.state === 'active'
                      ? 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/25 px-1 py-0 text-[9px]'
                      : 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/25 px-1 py-0 text-[9px]'
                  }
                >
                  {e.state === 'active' ? t('agent.vitality.active') : t('agent.vitality.standby')}
                </Badge>
                <Badge variant="outline" className="px-1 py-0 text-[9px]">
                  {t(`agent.stateAwareness.vitalityLevel.${e.vitality_level}`)}
                </Badge>
                {e.emotion_tendency && (
                  <span className="text-muted-foreground">{e.emotion_tendency}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {summaryPreview && (
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {t('agent.stateAwareness.summaryPreview')}
            </span>
            <p className="text-xs text-muted-foreground/80 leading-relaxed">
              {summaryPreview}
            </p>
          </div>
        )}

        {activeRules.length > 0 && (
          <div className="space-y-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {t('agent.stateAwareness.activeRules')}
            </span>
            <div className="flex flex-wrap gap-1">
              {activeRules.map((r, i) => (
                <Badge key={i} variant="outline" className="px-1.5 py-0 text-[9px]">
                  {r.rule_name}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}