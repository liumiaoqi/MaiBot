import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import {
  DEFAULT_ACCENT_COLOR_HEX,
  hexToHSL,
  parseHSL,
  adjustLightness,
  rotateHue,
  isDefaultAccentColor,
} from '@/lib/theme/palette'
import { THEME_STORAGE_KEYS, loadThemeConfig, saveThemePartial } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'

/** HSL 字符串转 hex（用于显示） */
function hslToHex(hsl: string): string {
  const { h, s, l } = parseHSL(hsl)
  const sNorm = s / 100
  const lNorm = l / 100
  const c = (1 - Math.abs(2 * lNorm - 1)) * sNorm
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = lNorm - c / 2
  let r = 0, g = 0, b = 0
  if (h < 60) { r = c; g = x; b = 0 }
  else if (h < 120) { r = x; g = c; b = 0 }
  else if (h < 180) { r = 0; g = c; b = x }
  else if (h < 240) { r = 0; g = x; b = c }
  else if (h < 300) { r = x; g = 0; b = c }
  else { r = c; g = 0; b = x }
  const toHex = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase()
}

/** 从 localStorage 读取 accent hex，无存储时默认 #55AB49 */
function readStoredAccentHex(): string {
  const stored = localStorage.getItem(THEME_STORAGE_KEYS.ACCENT)
  if (!stored) return DEFAULT_ACCENT_COLOR_HEX
  try {
    return hslToHex(stored)
  } catch {
    return DEFAULT_ACCENT_COLOR_HEX
  }
}

/** 生成 8 格色板预览（派生展示不可点选） */
function generateSwatches(accentHsl: string): string[] {
  return [
    accentHsl,
    adjustLightness(accentHsl, 10),
    adjustLightness(accentHsl, 20),
    adjustLightness(accentHsl, -10),
    adjustLightness(accentHsl, -20),
    rotateHue(accentHsl, 30),
    rotateHue(accentHsl, 60),
    rotateHue(accentHsl, -30),
  ]
}

/** 强调色选择组件——原生 color input + hex 文本输入 + 8 格色板预览 + 160ms debounce */
export function AccentPicker() {
  const { t } = useTranslation()
  const [hex, setHex] = useState(readStoredAccentHex)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const applyAccent = useCallback((hexValue: string) => {
    const hsl = hexToHSL(hexValue)
    saveThemePartial({ accentColor: hsl })
    const config = loadThemeConfig()
    const isDark = document.documentElement.classList.contains('dark')
    applyThemePipeline(config, isDark)
  }, [])

  // 160ms debounce
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      applyAccent(hex)
    }, 160)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [hex, applyAccent])

  const handleHexChange = (value: string) => {
    const upper = value.toUpperCase().slice(0, 7)
    setHex(upper)
  }

  const handleColorChange = (value: string) => {
    setHex(value.toUpperCase())
  }

  const handleReset = () => {
    setHex(DEFAULT_ACCENT_COLOR_HEX)
  }

  const accentHsl = hexToHSL(hex)
  const swatches = generateSwatches(accentHsl)
  const isDefault = isDefaultAccentColor(accentHsl)

  return (
    <div className="space-y-3" data-testid="accent-picker">
      <div className="flex items-center gap-3">
        {/* 原生 color input */}
        <input
          type="color"
          value={hex}
          onChange={(e) => handleColorChange(e.target.value)}
          className="h-10 w-10 rounded-md border border-border cursor-pointer"
          data-testid="accent-color-input"
          aria-label={t('settings.appearance.accentColor')}
        />
        {/* hex 文本输入 */}
        <input
          type="text"
          value={hex}
          maxLength={7}
          onChange={(e) => handleHexChange(e.target.value)}
          className="w-24 px-3 py-2 rounded-md border border-border font-mono text-sm text-foreground placeholder:text-muted-foreground"
          data-testid="accent-hex-input"
          aria-label={t('settings.appearance.accentHint')}
        />
        {/* 恢复默认按钮 */}
        <button
          onClick={handleReset}
          disabled={isDefault}
          className={cn(
            'px-3 py-2 rounded-md border text-sm transition-colors',
            isDefault
              ? 'border-border text-muted-foreground cursor-not-allowed opacity-50'
              : 'border-border hover:bg-muted'
          )}
        >
          {t('settings.appearance.resetDefault')}
        </button>
      </div>
      {/* 8 格色板预览 */}
      <div className="flex gap-2">
        {swatches.map((swatchHsl, i) => (
          <button
            key={i}
            type="button"
            data-testid={`accent-swatch-${i}`}
            className="h-8 w-8 rounded-md border border-border transition-transform hover:scale-110"
            style={{ backgroundColor: `hsl(${swatchHsl})` }}
            onClick={() => applyAccent(hslToHex(swatchHsl))}
            aria-label={`选择强调色 ${i + 1}`}
          />
        ))}
      </div>
    </div>
  )
}