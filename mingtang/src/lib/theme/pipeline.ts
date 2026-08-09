import type { ThemeTokens, UserThemeConfig } from './tokens'

import { generatePalette, getReadableForeground, isDefaultAccentColor, hslToHex } from './palette'
import { getPresetById } from './presets'
import { sanitizeCSS } from './sanitizer'
import {
  DEFAULT_DASHBOARD_STYLE,
  defaultDarkTokens,
  defaultLightTokens,
  futureRetroDarkTokens,
  futureRetroLightTokens,
  tokenToCSSVarName,
} from './tokens'

const CUSTOM_CSS_ID = 'maibot-custom-css'
const COMPONENT_CSS_ID_PREFIX = 'maibot-bg-css-'
const COMPONENT_IDS = ['page', 'sidebar', 'header', 'card', 'dialog'] as const
const DEFAULT_PRIMARY_COLOR_HSL = defaultLightTokens.color.primary

const mergeTokens = (base: ThemeTokens, overrides: Partial<ThemeTokens>): ThemeTokens => {
  return {
    color: {
      ...base.color,
      ...(overrides.color ?? {}),
    },
    typography: {
      ...base.typography,
      ...(overrides.typography ?? {}),
    },
    visual: {
      ...base.visual,
      ...(overrides.visual ?? {}),
    },
    layout: {
      ...base.layout,
      ...(overrides.layout ?? {}),
    },
    animation: {
      ...base.animation,
      ...(overrides.animation ?? {}),
    },
  }
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
 * 原版五类 token → Tailwind 4 @theme 变量名映射。
 * 关键：mingtang 的样式消费是 Tailwind 4（@theme 变量 + utility 类），
 * 注入的变量名必须与 @theme/类一致才能生效——color.* 直通（--color-*），
 * 其余类别映射到 Tailwind 命名空间（--text-* / --radius-* / --shadow-* / --blur-*）。
 */
const TAILWIND_VAR_OVERRIDES: Record<string, string> = {
  'typography.font-size-xs': '--text-xs',
  'typography.font-size-sm': '--text-sm',
  'typography.font-size-base': '--text-base',
  'typography.font-size-lg': '--text-lg',
  'typography.font-size-xl': '--text-xl',
  'typography.font-size-2xl': '--text-2xl',
  'typography.font-family-base': '--font-sans',
  'typography.font-family-code': '--font-mono',
  'typography.line-height-normal': '--leading-normal',
  'visual.radius-sm': '--radius-sm',
  'visual.radius-md': '--radius-md',
  'visual.radius-lg': '--radius-lg',
  'visual.radius-xl': '--radius-xl',
  'visual.radius-full': '--radius-full',
  'visual.shadow-sm': '--shadow-sm',
  'visual.shadow-md': '--shadow-md',
  'visual.shadow-lg': '--shadow-lg',
  'visual.shadow-xl': '--shadow-xl',
  'visual.blur-md': '--blur-md',
  'layout.sidebar-width': '--layout-sidebar-width',
  'animation.anim-duration-fast': '--anim-duration-fast',
  'animation.anim-duration-normal': '--anim-duration-normal',
}

export function injectTokensAsCSS(tokens: ThemeTokens, target: HTMLElement): void {
  // color 类：HSL → hex（Tailwind 4 消费 hex——裸 HSL 字符串是非法颜色值）
  Object.entries(tokens.color).forEach(([key, value]) => {
    target.style.setProperty(tokenToCSSVarName('color', key), hslToHex(value))
  })

  const injectMapped = (
    category: 'typography' | 'visual' | 'layout' | 'animation',
    entries: Array<[string, string | number]>
  ) => {
    entries.forEach(([key, value]) => {
      const varName = TAILWIND_VAR_OVERRIDES[`${category}.${key}`]
      if (varName) {
        target.style.setProperty(varName, String(value))
      }
    })
  }

  injectMapped('typography', Object.entries(tokens.typography))
  injectMapped('visual', Object.entries(tokens.visual))
  injectMapped('layout', Object.entries(tokens.layout))
  injectMapped('animation', Object.entries(tokens.animation))
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
