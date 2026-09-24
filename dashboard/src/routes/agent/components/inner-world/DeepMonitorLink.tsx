import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

interface DeepMonitorLinkProps {
  agentId: string
  target: 'emotion' | 'relationship' | 'subagent'
}

const TARGET_ROUTES: Record<string, string> = {
  emotion: '/emotion-monitor',
  relationship: '/relationship-monitor',
  subagent: '/subagent-monitor',
}

export function DeepMonitorLink({ agentId, target }: DeepMonitorLinkProps) {
  const { t } = useTranslation()

  const route = TARGET_ROUTES[target]

  return (
    <Link
      to={route}
      search={{ agent: agentId }}
      className="flex items-center gap-1.5 text-sm text-primary hover:underline mt-2"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {t('agent.emotionLandscape.deepMonitor')}
    </Link>
  )
}
