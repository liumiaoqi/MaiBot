import { Link } from '@tanstack/react-router'
import { Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { AgentStatsInfo } from '../types'

interface AgentStatusCardProps {
  agentStats: AgentStatsInfo | undefined
}

export function AgentStatusCard({ agentStats }: AgentStatusCardProps) {
  const { t } = useTranslation()

  return (
    <Link to="/agents" className="block h-full">
      <Card className="h-full transition-colors hover:border-primary/30">
        <CardHeader className="pb-3">
          <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
            <Users className="h-4 w-4" />
            {t('home.agentStatus.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">{t('home.agentStatus.activeAgents')}</span>
              <span className="text-2xl font-bold text-primary">
                {agentStats?.active_agents ?? '--'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">{t('home.agentStatus.totalAgents')}</span>
              <span className="text-sm font-medium">
                {agentStats?.total_agents ?? '--'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">{t('home.agentStatus.activeSessions')}</span>
              <span className="text-sm font-medium">
                {agentStats?.total_active_sessions ?? '--'}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}