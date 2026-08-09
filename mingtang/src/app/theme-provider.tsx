import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'

import { ThemeProviderContext, type ThemeProviderState } from '@/lib/theme-context'
import { loadThemeConfig, saveThemeConfig, resetThemeToDefault } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'
import { updateBotConfigSection, getBotConfig } from '@/lib/config-api'
import type { DashboardStyle, UserThemeConfig } from '@/lib/theme/tokens'

type Theme = 'dark' | 'light' | 'system'

const VALID_THEMES: Theme[] = ['dark', 'light', 'system']


function readStoredTheme(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEYS.MODE)
  return VALID_THEMES.includes(stored as Theme) ? (stored as Theme) : 'dark'
}

function resolveTheme(theme: Theme, systemDark: boolean): 'dark' | 'light' {
  if (theme === 'system') return systemDark ? 'dark' : 'light'
  return theme
}

/** ThemeProvider——加载主题配置 + 初始 pipeline 注入 + 提供 repaint 重注入 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
  )
  const [themeConfig, setThemeConfig] = useState<UserThemeConfig>(() => {
    try {
      return loadThemeConfig()
    } catch {
      return {
        selectedPreset: 'light',
        accentColor: '',
        styleTokenOverrides: {},
        styleCustomCSS: {},
        dashboardStyle: 'future-retro',
        styleBackgroundConfig: {},
        styleConfig: { futureRetro: { baseFontSize: 16, paperWarmth: 100, textureStyle: 'fine', textureIntensity: 55, panelDepth: 100, strokeScale: 100 } },
      }
    }
  })

  const resolvedTheme = resolveTheme(theme, systemDark)

  // 初始 pipeline 注入 + dark 类
  const initialized = useRef(false)
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
    applyThemePipeline(themeConfig, resolvedTheme === 'dark')
  }, [resolvedTheme, themeConfig])

  // 系统主题变化监听
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  /** 从权威源实时计算 isDark（localStorage MODE + 系统偏好实时查询）——连点竞态彻底消除 */
  const currentIsDark = useCallback((): boolean => {
    const stored = localStorage.getItem(THEME_STORAGE_KEYS.MODE)
    const theme = VALID_THEMES.includes(stored as Theme) ? (stored as Theme) : 'dark'
    const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    return resolveTheme(theme, sysDark) === 'dark'
  }, [])

  /** 切换主题模式——写 localStorage + dark 类 + 重跑 pipeline */
  const setTheme = useCallback((newTheme: Theme) => {
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, newTheme)
    setThemeState(newTheme)
    const isDark = resolveTheme(newTheme, window.matchMedia('(prefers-color-scheme: dark)').matches) === 'dark'
    document.documentElement.classList.toggle('dark', isDark)
    applyThemePipeline(loadThemeConfig(), isDark)
  }, [])

  /** 更新主题配置——saveThemeConfig + 重跑 pipeline */
  const updateThemeConfig = useCallback((partial: Partial<UserThemeConfig>) => {
    const current = loadThemeConfig()
    const next = { ...current, ...partial }
    saveThemeConfig(next)
    setThemeConfig(next)
    // isDark 实时计算（localStorage 同步写入——点击顺序保证读到最新——无 state/ref 时序）
    applyThemePipeline(next, currentIsDark())
  }, [currentIsDark])

  /** 重置主题——清 8 键 + 重载默认 + 重跑 pipeline */
  const resetTheme = useCallback(() => {
    resetThemeToDefault()
    const config = loadThemeConfig()
    setThemeConfig(config)
    setThemeState('dark')
    document.documentElement.classList.toggle('dark', true)
    applyThemePipeline(config, true)
  }, [])

  /** dashboardStyle——从 themeConfig 派生（单一数据源） */
  const dashboardStyle = themeConfig.dashboardStyle

  /** dataset 副作用——dashboardStyle 变化时更新 dataset */
  useEffect(() => {
    document.documentElement.dataset.dashboardStyle = dashboardStyle
  }, [dashboardStyle])

  /** 后端 → 本地反向同步（focus / visibilitychange） */
  useEffect(() => {
    const syncFromBackend = async () => {
      try {
        const config = await getBotConfig()
        const webui = config.webui as Record<string, unknown> | undefined
        const webuiStyle = webui?.webui_style
        if (webuiStyle === 'modern' || webuiStyle === 'future-retro') {
          const backendStyle = webuiStyle as DashboardStyle
          if (backendStyle !== themeConfig.dashboardStyle) {
            updateThemeConfig({ dashboardStyle: backendStyle })
          }
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
  }, [themeConfig.dashboardStyle, updateThemeConfig])

  /** 跨标签页主题同步（storage 事件——TE-2-3） */
  useEffect(() => {
    const themeKeySet = new Set<string>(Object.values(THEME_STORAGE_KEYS))
    const handleStorageChange = (e: StorageEvent) => {
      if (!e.key || !themeKeySet.has(e.key)) return

      // 重新加载配置
      const newConfig = loadThemeConfig()
      setThemeConfig(newConfig)

      // MODE 键变化时更新 theme 状态 + dark class
      if (e.key === THEME_STORAGE_KEYS.MODE) {
        const stored = localStorage.getItem(THEME_STORAGE_KEYS.MODE)
        const newTheme = VALID_THEMES.includes(stored as Theme) ? (stored as Theme) : 'dark'
        setThemeState(newTheme)
        const isDark = resolveTheme(newTheme, systemDark) === 'dark'
        document.documentElement.classList.toggle('dark', isDark)
      }

      // 重跑 pipeline
      const isDark = document.documentElement.classList.contains('dark')
      applyThemePipeline(newConfig, isDark)
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [systemDark])

  /** 切换界面风格——updateThemeConfig + dataset + 后端同步 */
  const setDashboardStyle = useCallback(async (newStyle: DashboardStyle) => {
    updateThemeConfig({ dashboardStyle: newStyle })
    document.documentElement.dataset.dashboardStyle = newStyle
    try {
      await updateBotConfigSection('webui', { webui_style: newStyle })
    } catch (error) {
      console.error('后端风格同步失败:', error)
    }
  }, [updateThemeConfig])

  const value: ThemeProviderState = {
    theme,
    resolvedTheme,
    setTheme,
    themeConfig,
    updateThemeConfig,
    resetTheme,
    dashboardStyle,
    setDashboardStyle,
  }

  return (
    <ThemeProviderContext value={value}>
      {children}
    </ThemeProviderContext>
  )
}