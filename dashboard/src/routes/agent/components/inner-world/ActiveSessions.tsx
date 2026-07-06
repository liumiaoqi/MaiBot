import { Crown, Heart, Link2, Unlink, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'

import type { SessionAgentInfo } from '@/lib/agent-api'

interface ActiveSessionsProps {
  sessions: SessionAgentInfo[]
  onUnbind: (sessionId: string) => void
  onUnbindSpecific?: (sessionId: string, agentId: string) => void
  onBindClick: () => void
  isUnbinding: boolean
}

function VitalityBar({ value }: { value: number }) {
  const { t } = useTranslation()
  const clamped = Math.max(0, Math.min(100, value))
  let barColor = 'bg-gray-400'
  if (clamped >= 60) barColor = 'bg-green-500'
  else if (clamped >= 30) barColor = 'bg-yellow-500'

  return (
    <div className="flex items-center gap-1.5 min-w-[60px]">
      <Heart className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="text-[9px] text-muted-foreground tabular-nums">{clamped.toFixed(0)}</span>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()

  if (status === 'active') {
    return (
      <Badge variant="outline" className="bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/25 px-1.5 py-0 text-[10px]">
        {t('agent.vitality.active')}
      </Badge>
    )
  }
  if (status === 'standby') {
    return (
      <Badge variant="outline" className="bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/25 px-1.5 py-0 text-[10px]">
        {t('agent.vitality.standby')}
      </Badge>
    )
  }
  if (status === 'dormant') {
    return (
      <Badge variant="outline" className="bg-gray-500/15 text-gray-500 dark:text-gray-400 border-gray-500/25 px-1.5 py-0 text-[10px]">
        {t('agent.vitality.dormant')}
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="bg-muted text-muted-foreground border-muted px-1.5 py-0 text-[10px]">
      {t('agent.activeSessions.boundInactive')}
    </Badge>
  )
}

export function ActiveSessions({ sessions, onUnbind, onUnbindSpecific, onBindClick, isUnbinding }: ActiveSessionsProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          {t('agent.activeSessions.title')} · {sessions.length}
        </span>
        <Button variant="outline" size="sm" onClick={onBindClick}>
          <Link2 className="h-3.5 w-3.5 mr-1" />
          {t('agent.activeSessions.bindSession')}
        </Button>
      </div>

      {sessions.length > 0 ? (
        <div className="space-y-2">
          {sessions.map((s) => (
            <div
              key={s.session_id}
              className="flex items-center justify-between p-3 rounded-lg border bg-card"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{s.display_name}</span>
                  <StatusBadge status={s.status} />
                  {s.is_primary && (
                    <Badge variant="outline" className="bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/25 px-1.5 py-0 text-[10px]">
                      <Crown className="h-2.5 w-2.5 mr-0.5" />
                      {t('agent.activeSessions.primary')}
                    </Badge>
                  )}
                </div>
                {s.cohabitants.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 flex-wrap">
                      <Users className="h-3 w-3 text-muted-foreground shrink-0" />
                      {s.cohabitants.map((c) => (
                        <div key={c.agent_id} className="inline-flex items-center gap-1">
                          <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                            {c.display_name}
                            {c.is_primary && <Crown className="h-2 w-2 ml-0.5 inline" />}
                          </Badge>
                          {c.status === 'standby' && c.vitality_value != null && (
                            <VitalityBar value={c.vitality_value} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {s.last_spoke_at && s.status === 'active' && (
                  <div className="text-[10px] text-muted-foreground/60">
                    {t('agent.activeSessions.lastSpokeAt')}: {new Date(s.last_spoke_at).toLocaleString()}
                  </div>
                )}
                {s.status === 'standby' && s.vitality_value != null && (
                  <VitalityBar value={s.vitality_value} />
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0 ml-2">
                {s.cohabitants.length > 0 && onUnbindSpecific ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onUnbindSpecific(s.session_id, s.agent_id)}
                    disabled={isUnbinding}
                    className="h-7 px-2 text-xs"
                  >
                    <Unlink className="h-3 w-3 mr-1" />
                    {t('agent.activeSessions.unbindSpecific')}
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onUnbind(s.session_id)}
                  disabled={isUnbinding}
                  className="h-7 px-2 text-xs"
                >
                  <Unlink className="h-3 w-3 mr-1" />
                  {s.cohabitants.length > 0 ? t('agent.activeSessions.unbindAll') : t('agent.activeSessions.unbind')}
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8 text-muted-foreground text-sm">
          {t('agent.activeSessions.noSessions')}
        </div>
      )}
    </div>
  )
}
