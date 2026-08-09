import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { Monitor, ScanLine } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ThemeProviderContext } from '@/lib/theme-context'
import type { DashboardStyle } from '@/lib/theme/tokens'

/** 界面风格选择 hook——从 ThemeProvider Context 读取（TE-1-1 状态提升，调用方无感知） */
export function useDashboardStyle() {
  const { dashboardStyle, setDashboardStyle } = useContext(ThemeProviderContext)
  return { style: dashboardStyle, setStyle: setDashboardStyle }
}

/** 界面风格选择组件——2 张卡片按钮互斥（modern / future-retro） */
export function StyleSelector() {
  const { t } = useTranslation()
  const { style, setStyle } = useDashboardStyle()

  const styles: {
    value: DashboardStyle
    label: string
    description: string
    icon: typeof Monitor
  }[] = [
    {
      value: 'modern',
      label: t('settings.appearance.styleModern'),
      description: t('settings.appearance.styleModernDesc'),
      icon: Monitor,
    },
    {
      value: 'future-retro',
      label: t('settings.appearance.styleFutureRetro'),
      description: t('settings.appearance.styleFutureRetroDesc'),
      icon: ScanLine,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-4" role="tablist" data-testid="style-selector">
      {styles.map(({ value, label, description, icon: Icon }) => (
        <button
          key={value}
          role="tab"
          aria-selected={style === value}
          data-style={value}
          onClick={() => void setStyle(value)}
          className={cn(
            'flex flex-col items-start gap-2 p-4 rounded-lg border-2 transition-colors text-left',
            style === value
              ? 'border-accent-9 bg-accent-surface'
              : 'border-border hover:border-muted-foreground/30'
          )}
        >
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5" />
            <span className="font-semibold text-foreground">{label}</span>
          </div>
          <p className="text-sm text-muted-foreground">{description}</p>
        </button>
      ))}
    </div>
  )
}
