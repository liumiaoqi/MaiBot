import type { ColorTokens } from './tokens'

type HSL = {
  h: number
  s: number
  l: number
}

export const DEFAULT_ACCENT_COLOR_HSL = '112.7 40.2% 47.8%'
export const DEFAULT_ACCENT_COLOR_HEX = '#55AB49'

// TE-3-1：12 层级明度步进表（Radix 模式）
const LIGHTNESS_STEPS_LIGHT = [95, 90, 85, 80, 75, 70, 65, 58, 50, 40, 30, 20]
const LIGHTNESS_STEPS_DARK = [20, 30, 40, 50, 58, 65, 70, 75, 80, 85, 90, 95]
const SATURATION_RATIOS = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0, 1.0, 0.95, 0.9, 0.8]

const clamp = (value: number, min: number, max: number): number => {
  if (value < min) return min
  if (value > max) return max
  return value
}

const roundToTenth = (value: number): number => Math.round(value * 10) / 10

const wrapHue = (value: number): number => ((value % 360) + 360) % 360

export const parseHSL = (hslStr: string): HSL => {
  const cleaned = hslStr
    .trim()
    .replace(/^hsl\(/i, '')
    .replace(/\)$/i, '')
    .replace(/,/g, ' ')
  const parts = cleaned.split(/\s+/).filter(Boolean)
  const rawH = parts[0] ?? '0'
  const rawS = parts[1] ?? '0%'
  const rawL = parts[2] ?? '0%'

  const h = Number.parseFloat(rawH)
  const s = Number.parseFloat(rawS.replace('%', ''))
  const l = Number.parseFloat(rawL.replace('%', ''))

  return {
    h: Number.isNaN(h) ? 0 : h,
    s: Number.isNaN(s) ? 0 : s,
    l: Number.isNaN(l) ? 0 : l,
  }
}

export const formatHSL = (h: number, s: number, l: number): string => {
  const safeH = roundToTenth(wrapHue(h))
  const safeS = roundToTenth(clamp(s, 0, 100))
  const safeL = roundToTenth(clamp(l, 0, 100))
  return `${safeH} ${safeS}% ${safeL}%`
}

export const isValidHSLString = (value: string): boolean => {
  const cleaned = value.trim()
  return /^-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?%\s+-?\d+(?:\.\d+)?%$/i.test(cleaned)
}

export const isDefaultAccentColor = (hsl: string): boolean => {
  const current = parseHSL(hsl)
  const defaults = parseHSL(DEFAULT_ACCENT_COLOR_HSL)
  return (
    Math.abs(current.h - defaults.h) <= 0.5 &&
    Math.abs(current.s - defaults.s) <= 0.5 &&
    Math.abs(current.l - defaults.l) <= 0.5
  )
}

/** HSL 字符串（"112.7 40.2% 47.8%"）→ hex。非法输入回退 #000000。 */
export const hslToHex = (hsl: string): string => {
  const cleaned = hsl.trim().replace(/^hsl\(/i, '').replace(/\)$/i, '').replace(/,/g, ' ')
  const parts = cleaned.split(/\s+/).filter(Boolean)
  if (parts.length < 3) {
    return '#000000'
  }
  const h = Number.parseFloat(parts[0] ?? '0')
  const s = Number.parseFloat((parts[1] ?? '0%').replace('%', '')) / 100
  const l = Number.parseFloat((parts[2] ?? '0%').replace('%', '')) / 100
  if (Number.isNaN(h) || Number.isNaN(s) || Number.isNaN(l)) {
    return '#000000'
  }

  const hue = ((h % 360) + 360) % 360
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1))
  const m = l - c / 2
  let rgb: [number, number, number]
  if (hue < 60) rgb = [c, x, 0]
  else if (hue < 120) rgb = [x, c, 0]
  else if (hue < 180) rgb = [0, c, x]
  else if (hue < 240) rgb = [0, x, c]
  else if (hue < 300) rgb = [x, 0, c]
  else rgb = [c, 0, x]

  const toHex = (v: number) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${toHex(rgb[0])}${toHex(rgb[1])}${toHex(rgb[2])}`
}

export const hexToHSL = (hex: string): string => {
  let cleaned = hex.trim().replace('#', '')
  if (cleaned.length === 3) {
    cleaned = cleaned
      .split('')
      .map((char) => `${char}${char}`)
      .join('')
  }

  if (cleaned.length !== 6) {
    return formatHSL(0, 0, 0)
  }

  const r = Number.parseInt(cleaned.slice(0, 2), 16) / 255
  const g = Number.parseInt(cleaned.slice(2, 4), 16) / 255
  const b = Number.parseInt(cleaned.slice(4, 6), 16) / 255

  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const delta = max - min
  const l = (max + min) / 2

  let h = 0
  let s = 0

  if (delta !== 0) {
    s = l > 0.5 ? delta / (2 - max - min) : delta / (max + min)
    switch (max) {
      case r:
        h = (g - b) / delta + (g < b ? 6 : 0)
        break
      case g:
        h = (b - r) / delta + 2
        break
      case b:
        h = (r - g) / delta + 4
        break
      default:
        break
    }
    h *= 60
  }

  return formatHSL(h, s * 100, l * 100)
}

export const normalizeAccentColor = (accentColor?: string | null): string => {
  const trimmed = accentColor?.trim()

  if (!trimmed) {
    return DEFAULT_ACCENT_COLOR_HSL
  }

  if (trimmed.startsWith('#')) {
    const normalized = hexToHSL(trimmed)
    return isDefaultAccentColor(normalized) ? DEFAULT_ACCENT_COLOR_HSL : normalized
  }

  if (isValidHSLString(trimmed)) {
    const { h, s, l } = parseHSL(trimmed)
    const normalized = formatHSL(h, s, l)
    return isDefaultAccentColor(normalized) ? DEFAULT_ACCENT_COLOR_HSL : normalized
  }

  return DEFAULT_ACCENT_COLOR_HSL
}

export const adjustLightness = (hsl: string, amount: number): string => {
  const { h, s, l } = parseHSL(hsl)
  return formatHSL(h, s, l + amount)
}

export const adjustSaturation = (hsl: string, amount: number): string => {
  const { h, s, l } = parseHSL(hsl)
  return formatHSL(h, s + amount, l)
}

export const rotateHue = (hsl: string, degrees: number): string => {
  const { h, s, l } = parseHSL(hsl)
  return formatHSL(h + degrees, s, l)
}

const setLightness = (hsl: string, lightness: number): string => {
  const { h, s } = parseHSL(hsl)
  return formatHSL(h, s, lightness)
}

const setSaturation = (hsl: string, saturation: number): string => {
  const { h, l } = parseHSL(hsl)
  return formatHSL(h, saturation, l)
}

export const getReadableForeground = (hsl: string): string => {
  const { h, s, l } = parseHSL(hsl)
  const neutralSaturation = clamp(s * 0.15, 6, 20)
  return l > 60
    ? formatHSL(h, neutralSaturation, 10)
    : formatHSL(h, neutralSaturation, 96)
}

const deriveSurfaceColor = (
  accent: HSL,
  saturationRatio: number,
  lightness: number,
  minSaturation: number,
  maxSaturation: number,
): string => {
  return formatHSL(
    accent.h,
    clamp(accent.s * saturationRatio, minSaturation, maxSaturation),
    lightness,
  )
}

/** TE-3-1：生成 12 层级 accent 色板（Radix 模式——HSL 调明度） */
export function generateAccentScale(accentHSL: string, isDark: boolean): string[] {
  const { h, s } = parseHSL(accentHSL)
  const steps = isDark ? LIGHTNESS_STEPS_DARK : LIGHTNESS_STEPS_LIGHT

  return steps.map((stepL, i) => {
    const ratio = SATURATION_RATIOS[i]
    const stepS = s * ratio
    const clampedL = clamp(stepL, 5, 95)
    return hslToHex(formatHSL(h, stepS, clampedL))
  })
}

/** TE-3-1：生成 5 语义点 from accent-9 */
export function generateAccentSemantics(accent9Hex: string): {
  'accent-contrast': string
  'accent-surface': string
  'accent-indicator': string
  'accent-track': string
} {
  const { h, s, l } = parseHSL(hexToHSL(accent9Hex))

  return {
    'accent-contrast': l > 50 ? '#000000' : '#ffffff',
    'accent-surface': hslToHex(formatHSL(h, s * 0.7, l)),
    'accent-indicator': hslToHex(formatHSL(h, s, clamp(l + 15, 5, 95))),
    'accent-track': hslToHex(formatHSL(h, s, clamp(l - 20, 5, 95))),
  }
}

export const generatePalette = (accentHSL: string, isDark: boolean): ColorTokens => {
  const accent = parseHSL(accentHSL)
  const primary = formatHSL(accent.h, accent.s, accent.l)

  const background = isDark
    ? deriveSurfaceColor(accent, 0.2, 5.2, 8, 22)
    : deriveSurfaceColor(accent, 0.12, 98.2, 4, 14)
  const foreground = isDark
    ? deriveSurfaceColor(accent, 0.14, 97.2, 5, 18)
    : deriveSurfaceColor(accent, 0.28, 9.5, 8, 28)

  const secondary = formatHSL(
    accent.h,
    clamp(accent.s * 0.35, 8, 40),
    isDark ? 17.5 : 96,
  )

  const muted = formatHSL(
    accent.h,
    clamp(accent.s * 0.12, 2, 18),
    isDark ? 17.5 : 96,
  )

  const accentVariant = formatHSL(
    accent.h + 35,
    clamp(accent.s * 0.6, 20, 85),
    isDark ? clamp(accent.l * 0.6 + 8, 25, 60) : clamp(accent.l * 0.8 + 14, 40, 75),
  )

  const destructive = formatHSL(
    0,
    clamp(accent.s, 60, 90),
    isDark ? 30.6 : 60.2,
  )

  const border = formatHSL(
    accent.h,
    clamp(accent.s * 0.2, 5, 25),
    isDark ? 17.5 : 91.4,
  )

  const mutedForeground = setSaturation(
    setLightness(muted, isDark ? 65.1 : 46.9),
    clamp(accent.s * 0.2, 10, 30),
  )

  const chartBase = formatHSL(accent.h, accent.s, accent.l)
  const chartSteps = [0, 72, 144, 216, 288]
  const charts = chartSteps.map((step) => rotateHue(chartBase, step))

  const card = isDark
    ? deriveSurfaceColor(accent, 0.18, 8.8, 10, 24)
    : deriveSurfaceColor(accent, 0.14, 98.6, 6, 16)
  const popover = isDark
    ? deriveSurfaceColor(accent, 0.21, 10.5, 12, 28)
    : deriveSurfaceColor(accent, 0.16, 99.3, 7, 18)

  // B 方案：数据层全 hex（Tailwind 4 消费 hex）——内部 HSL 计算保留，输出统一转 hex
  const hex = (hsl: string) => hslToHex(hsl)

  // TE-3-1：12 层级 + 5 语义点
  const accentScale = generateAccentScale(accentHSL, isDark)
  const accentSemantics = generateAccentSemantics(accentScale[8])

  return {
    primary: hex(primary),
    'primary-foreground': hex(getReadableForeground(primary)),
    'primary-gradient': 'none',
    secondary: hex(secondary),
    'secondary-foreground': hex(getReadableForeground(secondary)),
    muted: hex(muted),
    'muted-foreground': hex(mutedForeground),
    accent: hex(accentVariant),
    'accent-foreground': hex(getReadableForeground(accentVariant)),
    destructive: hex(destructive),
    'destructive-foreground': hex(getReadableForeground(destructive)),
    background: hex(background),
    foreground: hex(foreground),
    card: hex(card),
    'card-foreground': hex(foreground),
    popover: hex(popover),
    'popover-foreground': hex(foreground),
    border: hex(border),
    input: hex(border),
    ring: hex(primary),
    'chart-1': hex(charts[0]),
    'chart-2': hex(charts[1]),
    'chart-3': hex(charts[2]),
    'chart-4': hex(charts[3]),
    'chart-5': hex(charts[4]),
    'background-texture': 'none',
    // TE-3-1：12 层级 + 5 语义点
    'accent-1': accentScale[0],
    'accent-2': accentScale[1],
    'accent-3': accentScale[2],
    'accent-4': accentScale[3],
    'accent-5': accentScale[4],
    'accent-6': accentScale[5],
    'accent-7': accentScale[6],
    'accent-8': accentScale[7],
    'accent-9': accentScale[8],
    'accent-10': accentScale[9],
    'accent-11': accentScale[10],
    'accent-12': accentScale[11],
    'accent-contrast': accentSemantics['accent-contrast'],
    'accent-surface': accentSemantics['accent-surface'],
    'accent-indicator': accentSemantics['accent-indicator'],
    'accent-track': accentSemantics['accent-track'],
  }
}
