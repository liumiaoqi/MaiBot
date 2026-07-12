import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface TimeRangeOption {
  hours: number
  label: string
}

const TIME_RANGES: TimeRangeOption[] = [
  { hours: 1, label: '1h' },
  { hours: 6, label: '6h' },
  { hours: 24, label: '24h' },
  { hours: 168, label: '7d' },
  { hours: 720, label: '30d' },
]

interface TimeRangeSelectorProps {
  value: number
  onChange: (hours: number) => void
}

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-1">
      {TIME_RANGES.map((option) => (
        <Button
          key={option.hours}
          variant={value === option.hours ? 'default' : 'outline'}
          size="sm"
          className={cn('h-7 px-2.5 text-xs')}
          onClick={() => onChange(option.hours)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  )
}