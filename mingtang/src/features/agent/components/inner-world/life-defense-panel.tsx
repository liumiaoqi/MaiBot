import { Shield } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

interface LifeDefensePanelProps {
  rules: string[]
}

export function LifeDefensePanel({ rules }: LifeDefensePanelProps) {
  const { t } = useTranslation()

  if (rules.length === 0) return null

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex items-center gap-2 w-full text-sm text-muted-foreground hover:text-foreground py-2">
        <Shield className="h-4 w-4" />
        <span className="font-medium">{t('agent.lifeDefense.title')}</span>
        <span className="text-xs">({rules.length})</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className="text-xs text-muted-foreground mb-2">{t('agent.lifeDefense.description')}</p>
        <div className="space-y-1.5">
          {rules.map((rule, i) => (
            <div key={i} className="text-sm text-muted-foreground pl-6">
              {rule}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}