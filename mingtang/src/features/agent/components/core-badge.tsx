import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'

export function CoreBadge() {
  const { t } = useTranslation()

  return (
    <Badge variant="default" className="shrink-0 text-[10px] px-1.5 py-0">
      {t('agent.vitalSigns.coreBadge')}
    </Badge>
  )
}