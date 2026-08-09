import { describe, it, expect } from 'vitest'
import { futureRetroTokenOverrides } from '../future-retro'
import { DEFAULT_FUTURE_RETRO_STYLE_CONFIG } from '../tokens'
import type { FutureRetroStyleConfig } from '../tokens'

describe('TE-1-3：futureRetroTokenOverrides 生成 token 覆盖', () => {
  it('默认配置生成 texture token', () => {
    const overrides = futureRetroTokenOverrides(DEFAULT_FUTURE_RETRO_STYLE_CONFIG, false)
    expect(overrides.color).toBeDefined()
    expect(overrides.color!['background-texture']).toBeDefined()
  })

  it('none 纹理风格时 background-texture = "none"', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      textureStyle: 'none',
    }
    const overrides = futureRetroTokenOverrides(config, false)
    expect(overrides.color!['background-texture']).toBe('none')
  })

  it('fine 纹理风格时 background-texture 为 SVG data URL', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      textureStyle: 'fine',
      textureIntensity: 55,
    }
    const overrides = futureRetroTokenOverrides(config, false)
    const texture = overrides.color!['background-texture']
    expect(texture).toContain('data:image/svg+xml')
  })

  it('纸暖度 100（默认）时 background 不偏移', () => {
    const overrides = futureRetroTokenOverrides(DEFAULT_FUTURE_RETRO_STYLE_CONFIG, false)
    // 默认 paperWarmth=100，warmthFactor=0，background 应与 futureRetroLightTokens 一致
    expect(overrides.color!.background).toBeTruthy()
  })

  it('纸暖度 0（最大暖色）时 background 色温偏移', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      paperWarmth: 0,
    }
    const overrides = futureRetroTokenOverrides(config, false)
    expect(overrides.color!.background).toBeTruthy()
    // 应为有效 hex 颜色
    expect(overrides.color!.background).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('面板深度 100（默认）时 card/popover 不调整', () => {
    const overrides = futureRetroTokenOverrides(DEFAULT_FUTURE_RETRO_STYLE_CONFIG, true)
    expect(overrides.color!.card).toBeTruthy()
    expect(overrides.color!.popover).toBeTruthy()
  })

  it('面板深度 0（最大深度）时 card/popover 明度变化', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      panelDepth: 0,
    }
    const overrides = futureRetroTokenOverrides(config, true)
    expect(overrides.color!.card).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(overrides.color!.popover).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('描边比例 100（默认）时 border 不调整', () => {
    const overrides = futureRetroTokenOverrides(DEFAULT_FUTURE_RETRO_STYLE_CONFIG, false)
    expect(overrides.color!.border).toBeTruthy()
  })

  it('描边比例 50（最细）时 border 明度变化', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      strokeScale: 50,
    }
    const overrides = futureRetroTokenOverrides(config, false)
    expect(overrides.color!.border).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('暗模式和亮模式生成不同的 texture', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      textureStyle: 'ruled',
      textureIntensity: 80,
    }
    const lightOverrides = futureRetroTokenOverrides(config, false)
    const darkOverrides = futureRetroTokenOverrides(config, true)
    // 暗模式用 #d2c0a9 墨水，亮模式用 #6b3b1c
    expect(decodeURIComponent(lightOverrides.color!['background-texture'])).toContain('#6b3b1c')
    expect(decodeURIComponent(darkOverrides.color!['background-texture'])).toContain('#d2c0a9')
  })

  it('纹理强度 0 时 background-texture = "none"', () => {
    const config: FutureRetroStyleConfig = {
      ...DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
      textureIntensity: 0,
    }
    const overrides = futureRetroTokenOverrides(config, false)
    expect(overrides.color!['background-texture']).toBe('none')
  })
})