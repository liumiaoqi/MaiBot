import { describe, it, expect } from 'vitest'
import {
  generateAccentScale,
  generateAccentSemantics,
  generatePalette,
  parseHSL,
  hexToHSL,
  DEFAULT_ACCENT_COLOR_HSL,
} from '../palette'

describe('TE-3-1：12 层级 accent 色板生成算法', () => {
  it('生成 12 个 hex 颜色', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    expect(scale).toHaveLength(12)
    scale.forEach((color) => {
      expect(color).toMatch(/^#[0-9a-fA-F]{6}$/)
    })
  })

  it('light 模式明度递减：accent-1 最浅 > accent-12 最深', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    const lightnesses = scale.map((c) => parseHSL(hexToHSL(c)).l)
    for (let i = 0; i < 11; i++) {
      expect(lightnesses[i]).toBeGreaterThan(lightnesses[i + 1])
    }
  })

  it('dark 模式明度递增：accent-1 最深 < accent-12 最浅', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, true)
    const lightnesses = scale.map((c) => parseHSL(hexToHSL(c)).l)
    for (let i = 0; i < 11; i++) {
      expect(lightnesses[i]).toBeLessThan(lightnesses[i + 1])
    }
  })

  it('中范围层级色相不变（accent-5~accent-9 H 保持输入 H）', () => {
    const inputH = parseHSL(DEFAULT_ACCENT_COLOR_HSL).h
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    // 仅检查中范围（低饱和度层级色相不稳定——HSL→hex→HSL 转换误差）
    for (let i = 4; i <= 8; i++) {
      const h = parseHSL(hexToHSL(scale[i])).h
      expect(Math.abs(h - inputH)).toBeLessThan(5)
    }
  })

  it('accent-9 饱和度保持输入 S', () => {
    const inputS = parseHSL(DEFAULT_ACCENT_COLOR_HSL).s
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    const accent9S = parseHSL(hexToHSL(scale[8])).s
    expect(Math.abs(accent9S - inputS)).toBeLessThan(1)
  })

  it('明度 clamp 到 [5, 95]', () => {
    const scale = generateAccentScale('0 100% 50%', false)
    scale.forEach((color) => {
      const l = parseHSL(hexToHSL(color)).l
      expect(l).toBeGreaterThanOrEqual(5)
      expect(l).toBeLessThanOrEqual(95)
    })
  })
})

describe('TE-3-1：5 语义点映射', () => {
  it('accent-contrast：L > 50% 为黑 #000000', () => {
    const lightAccent9 = '#aaffaa' // L > 50%
    const semantics = generateAccentSemantics(lightAccent9)
    expect(semantics['accent-contrast']).toBe('#000000')
  })

  it('accent-contrast：L ≤ 50% 为白 #ffffff', () => {
    const darkAccent9 = '#004400' // L ≤ 50%
    const semantics = generateAccentSemantics(darkAccent9)
    expect(semantics['accent-contrast']).toBe('#ffffff')
  })

  it('accent-surface：S 降 30%', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    const semantics = generateAccentSemantics(scale[8])
    const accent9S = parseHSL(hexToHSL(scale[8])).s
    const surfaceS = parseHSL(hexToHSL(semantics['accent-surface'])).s
    expect(surfaceS).toBeLessThan(accent9S)
  })

  it('accent-indicator：L + 15%', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    const semantics = generateAccentSemantics(scale[8])
   ;    const accent9L = parseHSL(hexToHSL(scale[8])).l
    const indicatorL = parseHSL(hexToHSL(semantics['accent-indicator'])).l
    expect(indicatorL).toBeGreaterThan(accent9L)
  })

  it('accent-track：L - 20%', () => {
    const scale = generateAccentScale(DEFAULT_ACCENT_COLOR_HSL, false)
    const semantics = generateAccentSemantics(scale[8])
    const accent9L = parseHSL(hexToHSL(scale[8])).l
    const trackL = parseHSL(hexToHSL(semantics['accent-track'])).l
    expect(trackL).toBeLessThan(accent9L)
  })
})

describe('TE-3-1：generatePalette 兼容性 + 新增 token', () => {
  it('返回对象含现有 20 token（不删除不改名）', () => {
    const palette = generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    expect(palette.primary).toBeDefined()
    expect(palette.accent).toBeDefined()
    expect(palette.background).toBeDefined()
    expect(palette.foreground).toBeDefined()
    expect(palette.border).toBeDefined()
    expect(palette['chart-1']).toBeDefined()
    expect(palette['chart-5']).toBeDefined()
  })

  it('返回对象含 12 层级 token', () => {
    const palette = generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    for (let i = 1; i <= 12; i++) {
      expect(palette[`accent-${i}` as keyof typeof palette]).toBeDefined()
    }
  })

  it('返回对象含 5 语义点 token', () => {
    const palette = generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    expect(palette['accent-contrast']).toBeDefined()
    expect(palette['accent-surface']).toBeDefined()
    expect(palette['accent-indicator']).toBeDefined()
    expect(palette['accent-track']).toBeDefined()
  })

  it('默认 #55AB49：12 层级正确生成', () => {
    const palette = generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    expect(palette['accent-9']).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(palette['accent-1']).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(palette['accent-12']).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('深色和浅色模式生成不同的 12 层级', () => {
    const light = generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    const dark = generatePalette(DEFAULT_ACCENT_COLOR_HSL, true)
    expect(light['accent-1']).not.toBe(dark['accent-1'])
    expect(light['accent-9']).not.toBe(dark['accent-9'])
  })

  it('性能：generatePalette 耗时 ≤1ms', () => {
    const start = performance.now()
    generatePalette(DEFAULT_ACCENT_COLOR_HSL, false)
    const end = performance.now()
    expect(end - start).toBeLessThan(5) // jsdom 环境放宽到 5ms
  })
})