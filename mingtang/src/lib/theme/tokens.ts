/**
 * Design Token Schema 定义
 * 集中管理所有设计令牌（颜色、排版、间距、阴影、动画等）
 */

// ============================================================================
// Color Tokens 类型定义
// ============================================================================

export type ColorTokens = {
  primary: string
  'primary-foreground': string
  'primary-gradient': string
  secondary: string
  'secondary-foreground': string
  muted: string
  'muted-foreground': string
  accent: string
  'accent-foreground': string
  destructive: string
  'destructive-foreground': string
  background: string
  foreground: string
  card: string
  'card-foreground': string
  popover: string
  'popover-foreground': string
  border: string
  input: string
  ring: string
  'chart-1': string
  'chart-2': string
  'chart-3': string
  'chart-4': string
  'chart-5': string
}

// ============================================================================
// Typography Tokens 类型定义
// ============================================================================

export type TypographyTokens = Record<string, string>
export type VisualTokens = Record<string, string>
export type AnimationTokens = Record<string, string>

export type LayoutTokens = {
  'space-xs': string
  'space-sm': string
  'space-md': string
  'space-lg': string
  'space-xl': string
  'space-2xl': string
  'sidebar-width': string
  'sidebar-logo-height': string
  'sidebar-logo-padding-x': string
  'sidebar-nav-padding': string
  'sidebar-nav-padding-collapsed': string
  'sidebar-section-gap': string
  'sidebar-section-title-height': string
  'sidebar-section-title-margin-bottom': string
  'sidebar-section-title-margin-bottom-collapsed': string
  'sidebar-nav-item-gap': string
  'sidebar-collapsed-width': string
  'sidebar-nav-item-height': string
  'sidebar-nav-item-padding-x': string
  'sidebar-nav-item-collapsed-width': string
  'header-height': string
}


// ============================================================================
// Aggregated Theme Tokens（十一类——全部直通 Tailwind 4 @theme 变量命名）
// 类别名 = CSS 变量前缀（--color-* / --text-* / --radius-* ...）
// ============================================================================

export type ThemeTokens = {
  color: ColorTokens
  font: Record<string, string>
  text: Record<string, string>
  leading: Record<string, string>
  tracking: Record<string, string>
  radius: Record<string, string>
  shadow: Record<string, string>
  blur: Record<string, string>
  opacity: Record<string, string>
  layout: LayoutTokens
  animation: Record<string, string>
}

// ============================================================================
// Theme Preset & Config Types
// ============================================================================

export type ThemePreset = {
  id: string
  name: string
  description: string
  tokens: ThemeTokens
  isDark: boolean
}

export type DashboardStyle = 'modern' | 'future-retro'

export type StyleTokenOverrides = Partial<Record<DashboardStyle, Partial<ThemeTokens>>>
export type StyleCustomCSS = Partial<Record<DashboardStyle, string>>
export type StyleBackgroundConfigMap = Partial<Record<DashboardStyle, BackgroundConfigMap>>

export type FutureRetroTextureStyle = 'fine' | 'coarse' | 'dot-grid' | 'ruled' | 'none'

export type FutureRetroStyleConfig = {
  paperWarmth: number
  textureStyle: FutureRetroTextureStyle
  textureIntensity: number
  panelDepth: number
  strokeScale: number
}

export type DashboardStyleConfig = {
  futureRetro: FutureRetroStyleConfig
}

export const DEFAULT_DASHBOARD_STYLE: DashboardStyle = 'future-retro'

export const DEFAULT_FUTURE_RETRO_STYLE_CONFIG: FutureRetroStyleConfig = {
  paperWarmth: 100,
  textureStyle: 'fine',
  textureIntensity: 55,
  panelDepth: 100,
  strokeScale: 100,
}

export const DEFAULT_DASHBOARD_STYLE_CONFIG: DashboardStyleConfig = {
  futureRetro: DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
}

export type UserThemeConfig = {
  selectedPreset: string
  accentColor: string
  styleTokenOverrides: StyleTokenOverrides
  styleCustomCSS: StyleCustomCSS
  styleBackgroundConfig?: StyleBackgroundConfigMap
  dashboardStyle: DashboardStyle
  styleConfig: DashboardStyleConfig
}

// ============================================================================
// Default Light Tokens (from index.css :root)
// ============================================================================

export const defaultLightTokens: ThemeTokens = {
  color: {
    primary: '#e06f06',
    'primary-foreground': '#f8fafc',
    'primary-gradient': 'none',
    secondary: '#f1f7f8',
    'secondary-foreground': '#0f172a',
    muted: '#f4f6f6',
    'muted-foreground': '#608990',
    accent: '#55ab49',
    'accent-foreground': '#f8fafc',
    destructive: '#ef4444',
    'destructive-foreground': '#f8fafc',
    background: '#ffffff',
    foreground: '#020817',
    card: '#fbfcfc',
    'card-foreground': '#020817',
    popover: '#fdfdfe',
    'popover-foreground': '#020817',
    border: '#e5eced',
    input: '#e5eced',
    ring: '#e06f06',
    'chart-1': '#e06f06',
    'chart-2': '#2eb88a',
    'chart-3': '#e88c30',
    'chart-4': '#af57db',
    'chart-5': '#e23670',
  },
  font: {
    sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    mono: '"JetBrains Mono", "Monaco", "Courier New", monospace',
    'weight-normal': '400',
    'weight-medium': '500',
    'weight-semibold': '600',
    'weight-bold': '700',
  },
  text: {
    xs: '0.75rem',
    sm: '0.875rem',
    base: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
    '2xl': '1.5rem',
  },
  leading: {
    tight: '1.2',
    normal: '1.5',
    relaxed: '1.75',
  },
  tracking: {
    tight: '-0.02em',
    normal: '0em',
    wide: '0.02em',
  },
  radius: {
    sm: '0.25rem',
    md: '0.375rem',
    lg: '0.5rem',
    xl: '0.75rem',
    full: '9999px',
  },
  shadow: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
  },
  blur: {
    sm: '4px',
    md: '12px',
    lg: '24px',
  },
  opacity: {
    disabled: '0.5',
    hover: '0.8',
    overlay: '0.75',
  },
  layout: {
    'space-xs': '0.5rem',
    'space-sm': '0.75rem',
    'space-md': '1rem',
    'space-lg': '1.5rem',
    'space-xl': '2rem',
    'space-2xl': '3rem',
    'sidebar-width': '13rem',
    'sidebar-logo-height': '5rem',
    'sidebar-logo-padding-x': '1rem',
    'sidebar-nav-padding': '1rem',
    'sidebar-nav-padding-collapsed': '0.5rem',
    'sidebar-section-gap': '0.75rem',
    'sidebar-section-title-height': '1.25rem',
    'sidebar-section-title-margin-bottom': '0.5rem',
    'sidebar-section-title-margin-bottom-collapsed': '0.25rem',
    'sidebar-nav-item-gap': '0.25rem',
    'sidebar-collapsed-width': '4rem',
    'sidebar-nav-item-height': '2.5rem',
    'sidebar-nav-item-padding-x': '0.75rem',
    'sidebar-nav-item-collapsed-width': '3rem',
    'header-height': '3.5rem',
  },
  animation: {
    'duration-fast': '150ms',
    'duration-normal': '300ms',
    'duration-slow': '500ms',
    'easing-default': 'cubic-bezier(0.4, 0, 0.2, 1)',
    'easing-in': 'cubic-bezier(0.4, 0, 1, 1)',
    'easing-out': 'cubic-bezier(0, 0, 0.2, 1)',
    'easing-in-out': 'cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-colors': 'color 300ms cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-transform': 'transform 300ms cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-opacity': 'opacity 300ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
}

// ============================================================================
// Default Dark Tokens (from index.css .dark)
// ============================================================================

export const defaultDarkTokens: ThemeTokens = {
  color: {
    primary: '#e06f06',
    'primary-foreground': '#f8fafc',
    'primary-gradient': 'none',
    secondary: '#1d383c',
    'secondary-foreground': '#f8fafc',
    muted: '#273032',
    'muted-foreground': '#94b3b8',
    accent: '#3c7a34',
    'accent-foreground': '#f8fafc',
    destructive: '#7f1d1d',
    'destructive-foreground': '#f8fafc',
    background: '#020817',
    foreground: '#f8fafc',
    card: '#12191a',
    'card-foreground': '#f8fafc',
    popover: '#151f20',
    'popover-foreground': '#f8fafc',
    border: '#243336',
    input: '#243336',
    ring: '#e06f06',
    'chart-1': '#e06f06',
    'chart-2': '#33cc99',
    'chart-3': '#eb9947',
    'chart-4': '#b96ce0',
    'chart-5': '#e64c7f',
  },
  font: {
    sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    mono: '"JetBrains Mono", "Monaco", "Courier New", monospace',
    'weight-normal': '400',
    'weight-medium': '500',
    'weight-semibold': '600',
    'weight-bold': '700',
  },
  text: {
    xs: '0.75rem',
    sm: '0.875rem',
    base: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
    '2xl': '1.5rem',
  },
  leading: {
    tight: '1.2',
    normal: '1.5',
    relaxed: '1.75',
  },
  tracking: {
    tight: '-0.02em',
    normal: '0em',
    wide: '0.02em',
  },
  radius: {
    sm: '0.25rem',
    md: '0.375rem',
    lg: '0.5rem',
    xl: '0.75rem',
    full: '9999px',
  },
  shadow: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.25)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.4)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
  },
  blur: {
    sm: '4px',
    md: '12px',
    lg: '24px',
  },
  opacity: {
    disabled: '0.5',
    hover: '0.8',
    overlay: '0.75',
  },
  layout: {
    'space-xs': '0.5rem',
    'space-sm': '0.75rem',
    'space-md': '1rem',
    'space-lg': '1.5rem',
    'space-xl': '2rem',
    'space-2xl': '3rem',
    'sidebar-width': '13rem',
    'sidebar-logo-height': '5rem',
    'sidebar-logo-padding-x': '1rem',
    'sidebar-nav-padding': '1rem',
    'sidebar-nav-padding-collapsed': '0.5rem',
    'sidebar-section-gap': '0.75rem',
    'sidebar-section-title-height': '1.25rem',
    'sidebar-section-title-margin-bottom': '0.5rem',
    'sidebar-section-title-margin-bottom-collapsed': '0.25rem',
    'sidebar-nav-item-gap': '0.25rem',
    'sidebar-collapsed-width': '4rem',
    'sidebar-nav-item-height': '2.5rem',
    'sidebar-nav-item-padding-x': '0.75rem',
    'sidebar-nav-item-collapsed-width': '3rem',
    'header-height': '3.5rem',
  },
  animation: {
    'duration-fast': '150ms',
    'duration-normal': '300ms',
    'duration-slow': '500ms',
    'easing-default': 'cubic-bezier(0.4, 0, 0.2, 1)',
    'easing-in': 'cubic-bezier(0.4, 0, 1, 1)',
    'easing-out': 'cubic-bezier(0, 0, 0.2, 1)',
    'easing-in-out': 'cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-colors': 'color 300ms cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-transform': 'transform 300ms cubic-bezier(0.4, 0, 0.2, 1)',
    'transition-opacity': 'opacity 300ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
}

// ============================================================================
// Future Retro Tokens (MaiBotOneKey shell inspired)
// ============================================================================

const futureRetroBaseFont = {
  sans: '"MaiRetroText", "Microsoft YaHei UI", system-ui, sans-serif',
  mono: '"Agency FB", "Cascadia Mono", "JetBrains Mono", Consolas, monospace',
  'weight-normal': '700',
  'weight-medium': '700',
  'weight-semibold': '800',
  'weight-bold': '800',
} satisfies Partial<Record<string, string>>

const futureRetroBaseTracking = {
  tight: '0em',
  normal: '0em',
  wide: '0em',
} satisfies Partial<Record<string, string>>

const futureRetroBaseRadius = {
  sm: '2px',
  md: '3px',
  lg: '4px',
  xl: '4px',
} satisfies Partial<Record<string, string>>

const futureRetroBaseShadow = {
  sm: 'none',
  md: 'none',
  lg: 'none',
  xl: 'none',
} satisfies Partial<Record<string, string>>

const futureRetroBaseLayout = {
  'sidebar-width': '11rem',
  'sidebar-logo-height': '5rem',
  'sidebar-logo-padding-x': '0.75rem',
  'sidebar-nav-padding': '1rem',
  'sidebar-nav-padding-collapsed': '0.5rem',
  'sidebar-section-gap': '0.75rem',
  'sidebar-section-title-height': '1.25rem',
  'sidebar-section-title-margin-bottom': '0.5rem',
  'sidebar-section-title-margin-bottom-collapsed': '0.25rem',
  'sidebar-nav-item-gap': '0.25rem',
  'sidebar-collapsed-width': '4rem',
  'sidebar-nav-item-height': '2.4rem',
  'sidebar-nav-item-padding-x': '0.75rem',
  'sidebar-nav-item-collapsed-width': '3rem',
} satisfies Partial<LayoutTokens>

export const futureRetroLightTokens: Partial<ThemeTokens> = {
  color: {
    ...defaultLightTokens.color,
    primary: '#c24d24',
    'primary-foreground': '#fff1d6',
    'primary-gradient': 'none',
    secondary: '#ead4b7',
    'secondary-foreground': '#123f47',
    muted: '#e8d6bd',
    'muted-foreground': '#6f6758',
    accent: '#ddc5a4',
    'accent-foreground': '#0d4650',
    background: '#f3e3cc',
    foreground: '#0d4650',
    card: '#f3e3cc',
    'card-foreground': '#0d4650',
    popover: '#f6e8d3',
    'popover-foreground': '#0d4650',
    border: '#0d4d57',
    input: '#7c7362',
    ring: '#c24d24',
    'chart-1': '#c24d24',
    'chart-2': '#0d4650',
    'chart-3': '#c99a3e',
    'chart-4': '#6f6758',
    'chart-5': '#ead4b7',
  },
  font: {
    ...defaultLightTokens.font,
    ...futureRetroBaseFont,
  },
  text: {
    ...defaultLightTokens.text,
  },
  leading: {
    ...defaultLightTokens.leading,
  },
  tracking: {
    ...defaultLightTokens.tracking,
    ...futureRetroBaseTracking,
  },
  radius: {
    ...defaultLightTokens.radius,
    ...futureRetroBaseRadius,
  },
  shadow: {
    ...defaultLightTokens.shadow,
    ...futureRetroBaseShadow,
  },
  blur: {
    ...defaultLightTokens.blur,
  },
  opacity: {
    ...defaultLightTokens.opacity,
  },
  layout: {
    ...defaultLightTokens.layout,
    ...futureRetroBaseLayout,
  },
  animation: {
    ...defaultLightTokens.animation,
  },
}

export const futureRetroDarkTokens: Partial<ThemeTokens> = {
  color: {
    ...defaultDarkTokens.color,
    primary: '#9d5b3c',
    'primary-foreground': '#eaddcd',
    'primary-gradient': 'none',
    secondary: '#352c27',
    'secondary-foreground': '#d3c4b1',
    muted: '#312a25',
    'muted-foreground': '#a89780',
    accent: '#594d36',
    'accent-foreground': '#d8c9b6',
    background: '#221814',
    foreground: '#d2c0a9',
    card: '#2b211c',
    'card-foreground': '#d2c0a9',
    popover: '#2e251f',
    'popover-foreground': '#d2c0a9',
    border: '#54483b',
    input: '#594d40',
    ring: '#a46241',
    'chart-1': '#9d5b3c',
    'chart-2': '#9f8550',
    'chart-3': '#6b7a5c',
    'chart-4': '#885a53',
    'chart-5': '#d2c0a9',
  },
  font: {
    ...defaultDarkTokens.font,
  },
  text: {
    ...defaultDarkTokens.text,
  },
  leading: {
    ...defaultDarkTokens.leading,
  },
  tracking: {
    ...defaultDarkTokens.tracking,
  },
  radius: {
    ...defaultDarkTokens.radius,
  },
  shadow: {
    ...defaultDarkTokens.shadow,
  },
  blur: {
    ...defaultDarkTokens.blur,
  },
  opacity: {
    ...defaultDarkTokens.opacity,
  },
  layout: {
    ...defaultDarkTokens.layout,
    ...futureRetroBaseLayout,
  },
  animation: {
    ...defaultDarkTokens.animation,
  },
}

// ============================================================================
// Token Utility Functions
// ============================================================================

/**
 * 将 Token 类别和 key 转换为 CSS 变量名
 * @example tokenToCSSVarName('color', 'primary') => '--color-primary'
 */
export function tokenToCSSVarName(
  category: keyof ThemeTokens | 'color' | 'typography' | 'visual' | 'layout' | 'animation',
  key: string
): string {
  return `--${category}-${key}`
}

// ============================================================================
// Background Config Types
// ============================================================================

export type BackgroundEffects = {
  blur: number // px, 0-50
  overlayColor: string // HSL string，如 '0 0% 0%'
  overlayOpacity: number // 0-1
  position: 'cover' | 'contain' | 'center' | 'stretch'
  brightness: number // 0-200, default 100
  contrast: number // 0-200, default 100
  saturate: number // 0-200, default 100
  gradientOverlay?: string // CSS gradient string（可选）
}

export type BackgroundConfig = {
  type: 'none' | 'image' | 'video'
  assetId?: string // IndexedDB asset ID
  inherit?: boolean // true = 继承页面背景
  effects: BackgroundEffects
  customCSS: string // 组件级自定义 CSS
}

export type BackgroundConfigMap = {
  page?: BackgroundConfig
  sidebar?: BackgroundConfig
  header?: BackgroundConfig
  card?: BackgroundConfig
  dialog?: BackgroundConfig
}

export const defaultBackgroundEffects: BackgroundEffects = {
  blur: 0,
  overlayColor: '0 0% 0%',
  overlayOpacity: 0,
  position: 'cover',
  brightness: 100,
  contrast: 100,
  saturate: 100,
}

export const defaultBackgroundConfig: BackgroundConfig = {
  type: 'none',
  effects: defaultBackgroundEffects,
  customCSS: '',
}
