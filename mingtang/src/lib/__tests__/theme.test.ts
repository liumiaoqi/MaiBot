import { describe, it, expect, beforeEach } from 'vitest'
import {
  parseHSL,
  formatHSL,
  hexToHSL,
  isValidHSLString,
  isDefaultAccentColor,
  DEFAULT_ACCENT_COLOR_HSL,
  DEFAULT_ACCENT_COLOR_HEX,
} from '../theme/palette'
import { defaultLightPreset, defaultDarkPreset, getPresetById, builtInPresets } from '../theme/presets'
import {
  defaultLightTokens,
  defaultDarkTokens,
  tokenToCSSVarName,
  DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
} from '../theme/tokens'
import { sanitizeCSS } from '../theme/sanitizer'
import { loadThemeConfig, THEME_STORAGE_KEYS } from '../theme/storage'
import { buildFutureRetroTexture } from '../theme/future-retro'

describe('R1-2-4：主题搬移行为等价', () => {
  describe('palette', () => {
    it('parseHSL 解析 HSL 字符串', () => {
      const result = parseHSL('120 50% 50%')
      expect(result.h).toBe(120)
      expect(result.s).toBe(50)
      expect(result.l).toBe(50)
    })

    it('formatHSL 格式化并钳制范围', () => {
      expect(formatHSL(120, 50, 50)).toBe('120 50% 50%')
      expect(formatHSL(480, 150, -10)).toBe('120 100% 0%')
    })

    it('hexToHSL 转换十六进制颜色', () => {
      const result = hexToHSL('#ff0000')
      expect(result).toContain('0%')
      expect(result).toContain('100%')
    })

    it('isValidHSLString 校验 HSL 格式', () => {
      expect(isValidHSLString('120 50% 50%')).toBe(true)
      expect(isValidHSLString('invalid')).toBe(false)
    })

    it('isDefaultAccentColor 判断默认强调色', () => {
      expect(isDefaultAccentColor(DEFAULT_ACCENT_COLOR_HSL)).toBe(true)
      expect(isDefaultAccentColor('0 0% 0%')).toBe(false)
    })

    it('DEFAULT_ACCENT_COLOR 常量一致', () => {
      expect(DEFAULT_ACCENT_COLOR_HSL).toBe('112.7 40.2% 47.8%')
      expect(DEFAULT_ACCENT_COLOR_HEX).toBe('#55AB49')
    })
  })

  describe('presets', () => {
    it('内置预设含亮色和暗色', () => {
      expect(builtInPresets).toHaveLength(2)
      expect(builtInPresets[0].id).toBe('light')
      expect(builtInPresets[1].id).toBe('dark')
    })

    it('getPresetById 查找预设', () => {
      expect(getPresetById('light')).toBe(defaultLightPreset)
      expect(getPresetById('dark')).toBe(defaultDarkPreset)
      expect(getPresetById('nonexistent')).toBeUndefined()
    })

    it('亮色预设 isDark=false，暗色预设 isDark=true', () => {
      expect(defaultLightPreset.isDark).toBe(false)
      expect(defaultDarkPreset.isDark).toBe(true)
    })
  })

  describe('tokens', () => {
    it('defaultLightTokens 和 defaultDarkTokens 结构一致', () => {
      const lightKeys = Object.keys(defaultLightTokens.color).sort()
      const darkKeys = Object.keys(defaultDarkTokens.color).sort()
      expect(lightKeys).toEqual(darkKeys)
    })

    it('tokenToCSSVarName 生成 CSS 变量名', () => {
      const result = tokenToCSSVarName('color', 'primary')
      expect(result).toContain('--')
      expect(result).toContain('primary')
    })
  })

  describe('sanitizer', () => {
    it('sanitizeCSS 移除危险内容', () => {
      const dangerous = '@import url("https://evil.com/style.css");'
      const result = sanitizeCSS(dangerous)
      expect(result.css).not.toContain('@import')
      expect(result.css).not.toContain('evil.com')
      expect(result.warnings.length).toBeGreaterThan(0)
    })

    it('sanitizeCSS 保留安全内容', () => {
      const safe = '.test { color: red; }'
      const result = sanitizeCSS(safe)
      expect(result.css).toContain('color')
      expect(result.css).toContain('red')
      expect(result.warnings).toHaveLength(0)
    })
  })

  describe('storage（future-retro 五维配置——原版对齐）', () => {
    beforeEach(() => {
      localStorage.clear()
    })

    it('存储为空时返回五维默认配置', () => {
      const config = loadThemeConfig()
      expect(config.styleConfig.futureRetro).toEqual(DEFAULT_FUTURE_RETRO_STYLE_CONFIG)
      expect(config.styleConfig.futureRetro.textureStyle).toBe('fine')
    })

    it('旧版 paperTexture 布尔迁移：false → none', () => {
      localStorage.setItem(
        THEME_STORAGE_KEYS.STYLE_CONFIG,
        JSON.stringify({
          futureRetro: { paperTexture: false },
        })
      )
      const config = loadThemeConfig()
      expect(config.styleConfig.futureRetro.textureStyle).toBe('none')
    })

    it('非法值回退与范围钳制', () => {
      localStorage.setItem(
        THEME_STORAGE_KEYS.STYLE_CONFIG,
        JSON.stringify({
          futureRetro: {
            paperTexture: true,
            paperWarmth: 180,
            textureStyle: 'bogus',
            textureIntensity: -20,
            panelDepth: 'deep',
          },
        })
      )
      const config = loadThemeConfig()
      expect(config.styleConfig.futureRetro).toEqual({
        paperWarmth: 100,
        textureStyle: 'fine',
        textureIntensity: 0,
        panelDepth: 100,
        strokeScale: 100,
      })
    })
  })

  describe('future-retro 纹理生成器（原版对齐）', () => {
    it('none 风格返回 none', () => {
      expect(buildFutureRetroTexture('none', 55, true)).toBe('none')
    })

    it('强度为 0 或负值返回 none', () => {
      expect(buildFutureRetroTexture('dot-grid', 0, true)).toBe('none')
      expect(buildFutureRetroTexture('ruled', -10, false)).toBe('none')
    })

    it('dot-grid 生成 SVG data URL', () => {
      const result = buildFutureRetroTexture('dot-grid', 55, false)
      expect(result).toContain('data:image/svg+xml')
      expect(result).toContain('svg')
    })

    it('ruled 暗色使用深色墨水', () => {
      const result = buildFutureRetroTexture('ruled', 100, true)
      expect(decodeURIComponent(result)).toContain('#d2c0a9')
    })

    it('强度钳制在 0-100（130 → 满强度）', () => {
      const result = buildFutureRetroTexture('fine', 130, false)
      expect(decodeURIComponent(result)).toContain('opacity="0.3')
    })
  })
})