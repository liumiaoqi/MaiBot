import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'

import { ThemeProviderContext, type ThemeProviderState } from '@/lib/theme-context'
import { loadThemeConfig, saveThemeConfig, resetThemeToDefault } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'
import type { UserThemeConfig } from '@/lib/theme/tokens'

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
        styleConfig: { futureRetro: { paperWarmth: 100, textureStyle: 'fine', textureIntensity: 55, panelDepth: 100, strokeScale: 100 } },
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

  /** 切换主题模式——写 localStorage + dark 类 + 重跑 pipeline */
  const setTheme = useCallback((newTheme: Theme) => {
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, newTheme)
    setThemeState(newTheme)
    const isDark = resolveTheme(newTheme, systemDark) === 'dark'
    document.documentElement.classList.toggle('dark', isDark)
    applyThemePipeline(loadThemeConfig(), isDark)
  }, [systemDark])

  /** 更新主题配置——saveThemeConfig + 重跑 pipeline */
  const updateThemeConfig = useCallback((partial: Partial<UserThemeConfig>) => {
    const current = loadThemeConfig()
    const next = { ...current, ...partial }
    saveThemeConfig(next)
    setThemeConfig(next)
    applyThemePipeline(next, resolvedTheme === 'dark')
  }, [resolvedTheme])

  /** 重置主题——清 8 键 + 重载默认 + 重跑 pipeline */
  const resetTheme = useCallback(() => {
    resetThemeToDefault()
    const config = loadThemeConfig()
    setThemeConfig(config)
    setThemeState('dark')
    document.documentElement.classList.toggle('dark', true)
    applyThemePipeline(config, true)
  }, [])

  const value: ThemeProviderState = {
    theme,
    resolvedTheme,
    setTheme,
    themeConfig,
    updateThemeConfig,
    resetTheme,
  }

  return (
    <ThemeProviderContext value={value}>
      {children}
    </ThemeProviderContext>
  )
}