import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Moon, Monitor } from 'lucide-react'
import { cn } from '@/lib/utils'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'

/** 主题模式：浅色 / 深色 / 跟随系统 */
export type ThemeMode = 'light' | 'dark' | 'system'

const VALID_MODES: ThemeMode[] = ['light', 'dark', 'system']

/** 从 localStorage 读取主题模式，无存储或非法值时默认深色（R2 深色默认） */
function readStoredMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEYS.MODE)
  return VALID_MODES.includes(stored as ThemeMode) ? (stored as ThemeMode) : 'dark'
}

/** 主题模式切换 hook——管理 localStorage 持久化 + document.dark 类 + 系统偏好监听 */
export function useThemeMode() {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode)
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches
  )

  // 监听系统主题变化
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  const resolvedTheme: 'light' | 'dark' = mode === 'system'
    ? (systemDark ? 'dark' : 'light')
    : mode

  // 应用 dark 类到 document
  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  const setMode = useCallback((newMode: ThemeMode) => {
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, newMode)
    setModeState(newMode)
  }, [])

  return { mode, resolvedTheme, setMode }
}

/** 主题模式切换组件——3 tab 按钮组（浅色 / 深色 / 跟随系统） */
export function ThemeModeSwitch() {
  const { t } = useTranslation()
  const { mode, setMode } = useThemeMode()

  const modes: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: t('settings.appearance.light'), icon: Sun },
    { value: 'dark', label: t('settings.appearance.dark'), icon: Moon },
    { value: 'system', label: t('settings.appearance.system'), icon: Monitor },
  ]

  return (
    <div className="flex gap-2" role="tablist" data-testid="theme-mode-switch">
      {modes.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          role="tab"
          aria-selected={mode === value}
          data-mode={value}
          onClick={() => setMode(value)}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-md border transition-colors',
            mode === value
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border hover:bg-muted'
          )}
        >
          <Icon className="h-4 w-4" />
          {label}
        </button>
      ))}
    </div>
  )
}