import type { ThemeTokenOverride, ThemeTokens, UserThemeConfig } from './tokens'

import { generatePalette, getReadableForeground, isDefaultAccentColor } from './palette'
import { getPresetById } from './presets'
import { sanitizeCSS } from './sanitizer'
import { futureRetroTokenOverrides } from './future-retro'
import {
  DEFAULT_DASHBOARD_STYLE,
  DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
  defaultDarkTokens,
  defaultLightTokens,
  futureRetroDarkTokens,
  futureRetroLightTokens,
  tokenToCSSVarName,
} from './tokens'

const CUSTOM_CSS_ID = 'maibot-custom-css'
const COMPONENT_CSS_ID_PREFIX = 'maibot-bg-css-'
const COMPONENT_IDS = ['page', 'sidebar', 'header', 'card', 'dialog'] as const
// generatePalette 输入需要 HSL 字符串（tokens 现为 hex）——独立保留默认主色 HSL
// 默认强调色 = accent 默认（绿 112.7 40.2% 47.8%——#55AB49）——primary 与 accent 同源
const DEFAULT_PRIMARY_COLOR_HSL = '112.7 40.2% 47.8%'

const TOKEN_CATEGORIES = ['color', 'font', 'text', 'leading', 'tracking', 'radius', 'shadow', 'blur', 'opacity', 'layout', 'animation'] as const

const mergeTokens = (base: ThemeTokens, overrides: ThemeTokenOverride): ThemeTokens => {
  const merged = {} as ThemeTokens
  TOKEN_CATEGORIES.forEach((category) => {
    ;(merged as Record<string, unknown>)[category] = {
      ...(base[category] as Record<string, unknown>),
      ...((overrides[category] as Record<string, unknown> | undefined) ?? {}),
    }
  })
  return merged
}

const buildTokens = (config: UserThemeConfig, isDark: boolean): ThemeTokens => {
  const baseTokens = isDark ? defaultDarkTokens : defaultLightTokens
  let mergedTokens = mergeTokens(baseTokens, {
    color: generatePalette(DEFAULT_PRIMARY_COLOR_HSL, isDark),
  })

  if (config.accentColor) {
    if (isDefaultAccentColor(config.accentColor)) {
      mergedTokens = mergeTokens(mergedTokens, {
        color: {
          ...mergedTokens.color,
          accent: config.accentColor,
          'accent-foreground': getReadableForeground(config.accentColor),
        },
      })
    } else {
      mergedTokens = mergeTokens(mergedTokens, {
        color: generatePalette(config.accentColor, isDark),
      })
    }
  }

  if (
    config.selectedPreset &&
    config.selectedPreset !== 'light' &&
    config.selectedPreset !== 'dark'
  ) {
    const preset = getPresetById(config.selectedPreset)
    if (preset?.tokens) {
      mergedTokens = mergeTokens(mergedTokens, preset.tokens)
    }
  }

  if ((config.dashboardStyle ?? DEFAULT_DASHBOARD_STYLE) === 'future-retro') {
    mergedTokens = mergeTokens(
      mergedTokens,
      isDark ? futureRetroDarkTokens : futureRetroLightTokens
    )
    // TE-1-3: 纹理参数注入 pipeline——消费 styleConfig.futureRetro 五维参数
    const frOverrides = futureRetroTokenOverrides(
      config.styleConfig?.futureRetro ?? DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      isDark,
    )
    mergedTokens = mergeTokens(mergedTokens, frOverrides)
  }

  const dashboardStyle = config.dashboardStyle ?? DEFAULT_DASHBOARD_STYLE
  const styleTokenOverrides = config.styleTokenOverrides?.[dashboardStyle]

  if (styleTokenOverrides) {
    mergedTokens = mergeTokens(mergedTokens, styleTokenOverrides)
  }

  return mergedTokens
}

export function getComputedTokens(config: UserThemeConfig, isDark: boolean): ThemeTokens {
  return buildTokens(config, isDark)
}

/**
 * 数据层已 Tailwind 4 化（十一类 = @theme 变量前缀，值为最终格式 hex/rem/ms）——
 * 注入直通：--${category}-${key} = 原值，无映射无转换。
 */
export function injectTokensAsCSS(tokens: ThemeTokens, target: HTMLElement): void {
  const categories = ['color', 'font', 'text', 'leading', 'tracking', 'radius', 'shadow', 'blur', 'opacity', 'layout', 'animation'] as const
  categories.forEach((category) => {
    const entries = tokens[category] as Record<string, string> | undefined
    if (!entries) {
      return
    }
    Object.entries(entries).forEach(([key, value]) => {
      target.style.setProperty(tokenToCSSVarName(category, key), String(value))
    })
  })
}

export function injectCustomCSS(css: string): void {
  if (css.trim().length === 0) {
    removeCustomCSS()
    return
  }

  const existing = document.getElementById(CUSTOM_CSS_ID)
  if (existing) {
    existing.textContent = css
    return
  }

  const style = document.createElement('style')
  style.id = CUSTOM_CSS_ID
  style.textContent = css
  document.head.appendChild(style)
}

export function removeCustomCSS(): void {
  const existing = document.getElementById(CUSTOM_CSS_ID)
  if (existing) {
    existing.remove()
  }
}

/**
 * 为指定组件注入自定义 CSS
 * 使用独立的 style 标签,CSS 经过 sanitize 处理
 * @param css - 要注入的 CSS 字符串
 * @param componentId - 组件标识符 (page/sidebar/header/card/dialog)
 */
export function injectComponentCSS(css: string, componentId: string): void {
  const styleId = `${COMPONENT_CSS_ID_PREFIX}${componentId}`

  if (css.trim().length === 0) {
    removeComponentCSS(componentId)
    return
  }

  const sanitized = sanitizeCSS(css)
  const sanitizedCss = sanitized.css

  if (sanitizedCss.trim().length === 0) {
    removeComponentCSS(componentId)
    return
  }

  const existing = document.getElementById(styleId)
  if (existing) {
    existing.textContent = sanitizedCss
    return
  }

  const style = document.createElement('style')
  style.id = styleId
  style.textContent = sanitizedCss
  document.head.appendChild(style)
}

/**
 * 移除指定组件的自定义 CSS
 */
export function removeComponentCSS(componentId: string): void {
  const styleId = `${COMPONENT_CSS_ID_PREFIX}${componentId}`
  document.getElementById(styleId)?.remove()
}

/**
 * 移除所有组件的自定义 CSS
 */
export function removeAllComponentCSS(): void {
  COMPONENT_IDS.forEach(removeComponentCSS)
}

export function applyThemePipeline(config: UserThemeConfig, isDark: boolean): void {
  const root = document.documentElement
  const tokens = buildTokens(config, isDark)
  const dashboardStyle = config.dashboardStyle ?? DEFAULT_DASHBOARD_STYLE
  const customCSS = dashboardStyle === 'future-retro' ? undefined : config.styleCustomCSS?.[dashboardStyle]
  const backgroundConfig = config.styleBackgroundConfig?.[dashboardStyle]

  injectTokensAsCSS(tokens, root)
  if (customCSS) {
    const sanitized = sanitizeCSS(customCSS)
    if (sanitized.css.trim().length > 0) {
      injectCustomCSS(sanitized.css)
    } else {
      removeCustomCSS()
    }
  } else {
    removeCustomCSS()
  }

  // 应用组件级 CSS(注入顺序在全局 CSS 之后)
  if (backgroundConfig) {
    const { page, sidebar, header, card, dialog } = backgroundConfig
    ;[
      ['page', page],
      ['sidebar', sidebar],
      ['header', header],
      ['card', card],
      ['dialog', dialog],
    ].forEach(([id, cfg]) => {
      if (cfg && typeof cfg === 'object' && 'customCSS' in cfg && cfg.customCSS) {
        injectComponentCSS(cfg.customCSS, id as string)
      } else {
        removeComponentCSS(id as string)
      }
    })
  } else {
    removeAllComponentCSS()
  }
}
