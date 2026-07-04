import { Link2, Unlink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { SessionAgentInfo } from '@/lib/agent-api'

interface ActiveSessionsProps {
  sessions: SessionAgentInfo[]
  onUnbind: (sessionId: string) => void
  onBindClick: () => void
  isUnbinding: boolean
}

export function ActiveSessions({ sessions, onUnbind, onBindClick, isUnbinding }: ActiveSessionsProps) {
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
              <span className="text-sm font-medium truncate">{s.display_name}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onUnbind(s.session_id)}
                disabled={isUnbinding}
              >
                <Unlink className="h-3.5 w-3.5 mr-1" />
                {t('agent.activeSessions.unbind')}
              </Button>
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