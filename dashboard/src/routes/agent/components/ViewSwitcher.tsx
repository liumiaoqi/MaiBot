import { LayoutDashboard, Sparkles, Globe } from 'lucide-react'
import type { ComponentType } from 'react'

import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

import type { TopView } from '../hooks/useViewSwitch'

interface ViewSwitcherProps {
  currentView: TopView
  onSwitch: (view: TopView) => void
}

const VIEW_ICONS: Record<TopView, ComponentType<{ className?: string }>> = {
  dashboard: LayoutDashboard,
  constellation: Sparkles,
  global: Globe,
}

export function ViewSwitcher({ currentView, onSwitch }: ViewSwitcherProps) {
  const { t } = useTranslation()

  const views: TopView[] = ['dashboard', 'constellation', 'global']

  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
      {views.map((view) => {
        const Icon = VIEW_ICONS[view]
        return (
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
            <Icon className="h-4 w-4" />
            <span>{t(`agent.commandCenter.${view}`)}</span>
          </button>
        )
      })}
    </div>
  )
}
