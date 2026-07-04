import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

import type { TopView } from '../hooks/useViewSwitch'

interface ViewSwitcherProps {
  currentView: TopView
  onSwitch: (view: TopView) => void
}

const VIEW_ICONS: Record<TopView, string> = {
  dashboard: '📊',
  constellation: '🌌',
  global: '🌍',
}

export function ViewSwitcher({ currentView, onSwitch }: ViewSwitcherProps) {
  const { t } = useTranslation()

  const views: TopView[] = ['dashboard', 'constellation', 'global']

  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
      {views.map((view) => (
        <button
          key={view}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors',
            currentView === view
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          )}
          onClick={() => onSwitch(view)}
        >
          <span>{VIEW_ICONS[view]}</span>
          <span>{t(`agent.commandCenter.${view}`)}</span>
        </button>
      ))}
    </div>
  )
}