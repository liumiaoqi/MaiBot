import { Settings2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

interface CollapsedParametersProps {
  talkValueModifier: number
  idleBackoffModifier: number
  relationshipGrowthRate: number
  emotionDecayRate: number
}

export function CollapsedParameters({
  talkValueModifier,
  idleBackoffModifier,
  relationshipGrowthRate,
  emotionDecayRate,
}: CollapsedParametersProps) {
  const { t } = useTranslation()

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex items-center gap-2 w-full text-sm text-muted-foreground hover:text-foreground py-2">
        <Settings2 className="h-4 w-4" />
        <span className="font-medium">{t('agent.collapsedParameters.title')}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-1.5 pl-6">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">{t('agent.collapsedParameters.talkValueModifier')}</span>
            <span>×{talkValueModifier.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">{t('agent.collapsedParameters.idleBackoffModifier')}</span>
            <span>×{idleBackoffModifier.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">{t('agent.collapsedParameters.relationshipGrowthRate')}</span>
            <span>×{relationshipGrowthRate.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">{t('agent.collapsedParameters.emotionDecayRate')}</span>
            <span>{emotionDecayRate}/h</span>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}