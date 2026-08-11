import { useTranslation } from 'react-i18next'

import type { InnerActivityData } from '../utils/vital-signs'

interface InnerActivityIndicatorProps {
  data: InnerActivityData
}

export function InnerActivityIndicator({ data }: InnerActivityIndicatorProps) {
  const { t } = useTranslation()

  const isIntrospecting = data.status === 'introspecting'

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className="w-2.5 h-2.5 rounded-full bg-violet-400"
        style={
          isIntrospecting
            ? { animation: 'agent-breathe 2000ms ease-in-out infinite alternate' }
            : { opacity: 0.3 }
        }
      />
      <span className="text-muted-foreground">
        {t(`agent.vitalSigns.innerActivity.${data.status}`)}
      </span>
    </div>
  )
}