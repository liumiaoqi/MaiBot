import { Crown, Link2, Unlink, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { SessionAgentInfo } from '@/lib/agent-api'

interface ActiveSessionsProps {
  sessions: SessionAgentInfo[]
  onUnbind: (sessionId: string) => void
  onUnbindSpecific?: (sessionId: string, agentId: string) => void
  onBindClick: () => void
  isUnbinding: boolean
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
                  <Badge
                    variant="outline"
                    className={
                      s.status === 'active'
                        ? 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/25 px-1.5 py-0 text-[10px]'
                        : 'bg-muted text-muted-foreground border-muted px-1.5 py-0 text-[10px]'
                    }
                  >
                    {s.status === 'active' ? t('agent.activeSessions.active') : t('agent.activeSessions.boundInactive')}
                  </Badge>
                  {s.is_primary && (
                    <Badge variant="outline" className="bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/25 px-1.5 py-0 text-[10px]">
                      <Crown className="h-2.5 w-2.5 mr-0.5" />
                      {t('agent.activeSessions.primary')}
                    </Badge>
                  )}
                </div>
                {s.cohabitants.length > 0 && (
                  <div className="flex items-center gap-1 flex-wrap">
                    <Users className="h-3 w-3 text-muted-foreground shrink-0" />
                    {s.cohabitants.map((c) => (
                      <Badge key={c.agent_id} variant="outline" className="px-1.5 py-0 text-[10px]">
                        {c.display_name}
                        {c.is_primary && <Crown className="h-2 w-2 ml-0.5 inline" />}
                      </Badge>
                    ))}
                  </div>
                )}
                {s.last_spoke_at && s.status === 'active' && (
                  <div className="text-[10px] text-muted-foreground/60">
                    {t('agent.activeSessions.lastSpokeAt')}: {new Date(s.last_spoke_at).toLocaleString()}
                  </div>
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
