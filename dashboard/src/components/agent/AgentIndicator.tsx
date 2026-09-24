import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

export interface AgentIndicatorProps {
  agent_id: string
  display_name: string
  color: string
  size?: 'sm' | 'md' | 'lg'
  showName?: boolean
  className?: string
}

const sizeMap = {
  sm: { avatar: 'w-5 h-5 text-[10px]', gap: 'gap-1', name: 'text-xs' },
  md: { avatar: 'w-7 h-7 text-xs', gap: 'gap-1.5', name: 'text-sm' },
  lg: { avatar: 'w-9 h-9 text-sm', gap: 'gap-2', name: 'text-base' },
} as const

export function AgentIndicator({
  agent_id,
  display_name,
  color,
  size = 'md',
  showName = true,
  className,
}: AgentIndicatorProps) {
  const { t } = useTranslation()
  const s = sizeMap[size]
  const isDefault = !agent_id || agent_id === 'silver_wolf'
  const initial = display_name.charAt(0)

  return (
    <span className={cn('inline-flex items-center', s.gap, className)}>
      <span
        className={cn(
          'inline-flex items-center justify-center rounded-full font-medium text-white shrink-0',
          s.avatar,
        )}
        style={{ backgroundColor: color }}
      >
        {initial}
      </span>
      {showName && (
        <span className={cn('font-medium leading-none', s.name)}>
          {display_name}
          {isDefault && (
            <span className="ml-1 text-[10px] text-muted-foreground font-normal">{t('agent.indicator.default')}</span>
          )}
        </span>
      )}
    </span>
  )
}