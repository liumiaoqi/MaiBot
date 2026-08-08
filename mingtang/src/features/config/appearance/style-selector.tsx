import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Monitor, ScanLine } from 'lucide-react'
import { cn } from '@/lib/utils'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'
import { DEFAULT_DASHBOARD_STYLE, type DashboardStyle } from '@/lib/theme/tokens'
import { updateBotConfigSection, getBotConfig } from '@/lib/config-api'

const VALID_STYLES: DashboardStyle[] = ['modern', 'future-retro']

/** 从 localStorage 读取界面风格，无存储或非法值时默认 future-retro（7 坑 #7） */
function readStoredStyle(): DashboardStyle {
  const stored = localStorage.getItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE)
  return VALID_STYLES.includes(stored as DashboardStyle)
    ? (stored as DashboardStyle)
    : DEFAULT_DASHBOARD_STYLE
}

/** 界面风格选择 hook——管理 localStorage + 后端双通道同步 + dataset 副作用 */
export function useDashboardStyle() {
  const [style, setStyleState] = useState<DashboardStyle>(readStoredStyle)

  // dataset 副作用（挂载 + 变化时）
  useEffect(() => {
    document.documentElement.dataset.dashboardStyle = style
  }, [style])

  // focus/visibilitychange 反向同步（后端 → 本地）
  useEffect(() => {
    const syncFromBackend = async () => {
      try {
        const config = await getBotConfig()
        const webui = config.webui as Record<string, unknown> | undefined
        const webuiStyle = webui?.webui_style
        if (webuiStyle === 'modern' || webuiStyle === 'future-retro') {
          const backendStyle = webuiStyle as DashboardStyle
          setStyleState((current) => {
            if (backendStyle !== current) {
              localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, backendStyle)
              return backendStyle
            }
            return current
          })
        }
      } catch {
        // 后端不可用时不报错
      }
    }

    const handler = () => void syncFromBackend()
    window.addEventListener('focus', handler)
    document.addEventListener('visibilitychange', handler)
    return () => {
      window.removeEventListener('focus', handler)
      document.removeEventListener('visibilitychange', handler)
    }
  }, [])

  const setStyle = useCallback(async (newStyle: DashboardStyle) => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, newStyle)
    setStyleState(newStyle)
    try {
      await updateBotConfigSection('webui', { webui_style: newStyle })
    } catch (error) {
      console.error('后端风格同步失败:', error)
    }
  }, [])

  return { style, setStyle }
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
              ? 'border-primary bg-primary/5'
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