import { ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { EmotionPulse } from '../EmotionPulse'
import type { VitalSignsData } from '../../utils/vital-signs'

interface IdentityHeaderProps {
  vitalSigns: VitalSignsData
  personality: string
  onBack: () => void
}

export function IdentityHeader({ vitalSigns, personality, onBack }: IdentityHeaderProps) {

  return (
    <div className="flex items-start gap-4 p-4 border-b">
      <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0">
        <ArrowLeft className="h-4 w-4" />
      </Button>
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-xl shrink-0"
        style={{ backgroundColor: vitalSigns.color }}
      >
        {vitalSigns.displayName.charAt(0)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-lg font-bold">{vitalSigns.displayName}</h2>
          <EmotionPulse data={vitalSigns.emotionPulse} />
        </div>
        {personality && (
          <p className="text-sm text-muted-foreground line-clamp-2">
            {personality.length > 50 ? personality.slice(0, 50) + '…' : personality}
          </p>
        )}
      </div>
    </div>
  )
}