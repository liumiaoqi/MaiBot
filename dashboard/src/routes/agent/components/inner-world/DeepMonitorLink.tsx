import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

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
  const url = `${route}?agent=${encodeURIComponent(agentId)}`

  return (
    <a
      href={url}
      className="flex items-center gap-1.5 text-sm text-primary hover:underline mt-2"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {t('agent.emotionLandscape.deepMonitor')}
    </a>
  )
}